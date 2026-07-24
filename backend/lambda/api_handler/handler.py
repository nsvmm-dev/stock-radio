import json
import os
import logging
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from news_fetcher import NewsFetcher

logger = logging.getLogger()
logger.setLevel(logging.INFO)

JST = timezone(timedelta(hours=9))
dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

AUDIO_URL_EXPIRE_SEC = 3600  # presigned URL有効期限: 1時間


def lambda_handler(event, context):
    method = event.get("httpMethod", "GET")
    path = event.get("path", "/")
    query_params = event.get("queryStringParameters") or {}
    body = _parse_body(event)

    logger.info(f"{method} {path}")

    try:
        return _route(method, path, query_params, body)
    except Exception as e:
        logger.error(f"未処理エラー: {e}", exc_info=True)
        return _res(500, {"error": "internal server error"})


def _route(method, path, query_params, body):
    # OPTIONS (CORS プリフライト)
    if method == "OPTIONS":
        return _res(200, {})

    # API Gateway が /{proxy+} の単一ルートのため、pathParameters に
    # userId 等は入らない（"proxy" キーのみ）。path を自前で分解する。
    segments = [s for s in path.split("/") if s]

    # POST /users
    if segments == ["users"] and method == "POST":
        return _create_user(body)

    # GET /stocks/search?q=xxx
    if segments == ["stocks", "search"] and method == "GET":
        return _search_stocks(query_params.get("q", ""))

    # GET /stocks/hot
    if segments == ["stocks", "hot"] and method == "GET":
        return _get_hot_stocks()

    if len(segments) == 4 and segments[0] == "stocks" and method == "GET":
        market, code, action = segments[1], segments[2], segments[3]
        if action == "quote":
            return _get_stock_quote(market, code)
        if action == "news":
            return _get_stock_news(market, code, query_params.get("name", ""))

    if len(segments) >= 2 and segments[0] == "users":
        user_id = segments[1]

        # GET /users/{userId}
        if len(segments) == 2 and method == "GET":
            return _get_user(user_id)

        # PUT /users/{userId}/plan
        if len(segments) == 3 and segments[2] == "plan" and method == "PUT":
            return _update_plan(user_id, body)

        # PUT /users/{userId}/fcm-token
        if len(segments) == 3 and segments[2] == "fcm-token" and method == "PUT":
            return _update_fcm_token(user_id, body)

        # GET /users/{userId}/radios
        if len(segments) == 3 and segments[2] == "radios" and method == "GET":
            return _list_radios(user_id)

        # GET /users/{userId}/radios/{date}
        if len(segments) == 4 and segments[2] == "radios" and method == "GET":
            return _get_radio(user_id, segments[3])

        # GET/POST /users/{userId}/watchlist
        if len(segments) == 3 and segments[2] == "watchlist":
            if method == "GET":
                return _get_watchlist(user_id)
            if method == "POST":
                return _add_watchlist(user_id, body)

        # DELETE /users/{userId}/watchlist/{stockCode}
        if len(segments) == 4 and segments[2] == "watchlist" and method == "DELETE":
            return _remove_watchlist(user_id, segments[3])

    return _res(404, {"error": "not found"})


# ── ユーザー ─────────────────────────────────────────────────────────

def _create_user(body: dict):
    table = dynamodb.Table(os.environ["USERS_TABLE"])
    user_id = str(uuid.uuid4())
    now = datetime.now(JST).isoformat()

    table.put_item(Item={
        "userId": user_id,
        "email": body.get("email", ""),
        "plan": "free",
        "fcmToken": body.get("fcmToken", ""),
        "createdAt": now,
        "updatedAt": now,
    })
    return _res(201, {"userId": user_id, "plan": "free"})


def _get_user(user_id: str):
    result = dynamodb.Table(os.environ["USERS_TABLE"]).get_item(Key={"userId": user_id})
    if "Item" not in result:
        return _res(404, {"error": "user not found"})
    item = result["Item"]
    item.pop("fcmToken", None)  # デバイストークンは返さない
    return _res(200, item)


def _update_plan(user_id: str, body: dict):
    plan = body.get("plan")
    if plan not in ("free", "standard", "pro"):
        return _res(400, {"error": "plan must be free / standard / pro"})

    dynamodb.Table(os.environ["USERS_TABLE"]).update_item(
        Key={"userId": user_id},
        UpdateExpression="SET #plan = :plan, updatedAt = :now",
        ExpressionAttributeNames={"#plan": "plan"},
        ExpressionAttributeValues={":plan": plan, ":now": datetime.now(JST).isoformat()},
    )
    return _res(200, {"plan": plan})


def _update_fcm_token(user_id: str, body: dict):
    token = body.get("fcmToken", "")
    dynamodb.Table(os.environ["USERS_TABLE"]).update_item(
        Key={"userId": user_id},
        UpdateExpression="SET fcmToken = :t, updatedAt = :now",
        ExpressionAttributeValues={":t": token, ":now": datetime.now(JST).isoformat()},
    )
    return _res(200, {"message": "updated"})


# ── ラジオ ───────────────────────────────────────────────────────────

def _list_radios(user_id: str):
    result = dynamodb.Table(os.environ["RADIOS_TABLE"]).query(
        KeyConditionExpression=Key("userId").eq(user_id),
        ScanIndexForward=False,
        Limit=30,
    )
    return _res(200, {"radios": result.get("Items", [])})


def _get_radio(user_id: str, radio_date: str):
    result = dynamodb.Table(os.environ["RADIOS_TABLE"]).get_item(
        Key={"userId": user_id, "radioDate": radio_date}
    )
    if "Item" not in result:
        return _res(404, {"error": "radio not found"})

    item = result["Item"]
    # S3 presigned URL を発行（直接ダウンロードではなくURL返却）
    try:
        item["audioUrl"] = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": os.environ["AUDIO_BUCKET"], "Key": item["s3Key"]},
            ExpiresIn=AUDIO_URL_EXPIRE_SEC,
        )
    except Exception as e:
        logger.error(f"presigned URL 生成失敗: {e}")

    return _res(200, item)


# ── ウォッチリスト ────────────────────────────────────────────────────

def _get_watchlist(user_id: str):
    result = dynamodb.Table(os.environ["WATCHLISTS_TABLE"]).query(
        KeyConditionExpression=Key("userId").eq(user_id)
    )
    return _res(200, {"watchlist": result.get("Items", [])})


def _add_watchlist(user_id: str, body: dict):
    code = body.get("stockCode", "").upper().strip()
    if not code:
        return _res(400, {"error": "stockCode is required"})

    item = {
        "userId": user_id,
        "stockCode": code,
        "stockName": body.get("stockName", code),
        "market": body.get("market", "JP"),
        "addedAt": datetime.now(JST).isoformat(),
    }
    dynamodb.Table(os.environ["WATCHLISTS_TABLE"]).put_item(Item=item)
    return _res(201, item)


def _remove_watchlist(user_id: str, stock_code: str):
    dynamodb.Table(os.environ["WATCHLISTS_TABLE"]).delete_item(
        Key={"userId": user_id, "stockCode": stock_code}
    )
    return _res(200, {"message": "removed"})


# ── 株式検索 ─────────────────────────────────────────────────────────

def _search_stocks(query: str):
    # TODO: J-Quants の銘柄マスタを使った検索を実装
    # 現時点はスタブ実装
    return _res(200, {"results": [], "query": query})


# ── 株価・注目銘柄・ニュース ───────────────────────────────────────────

def _get_hot_stocks():
    """当日の注目銘柄(米国値上がり/値下がり/出来高上位、日本の人気銘柄)"""
    result = dynamodb.Table(os.environ["HOT_STOCKS_TABLE"]).scan()
    by_category = {item["category"]: item.get("items", []) for item in result.get("Items", [])}

    return _res(200, {
        "usGainers": by_category.get("us_gainers", []),
        "usLosers": by_category.get("us_losers", []),
        "usMostActive": by_category.get("us_most_active", []),
        "jpPopular": by_category.get("jp_popular", []),
    })


def _get_stock_quote(market: str, code: str):
    """日次バッチでキャッシュされた株価・チャート履歴を取得"""
    market_code = f"{market.upper()}#{code.upper()}"
    result = dynamodb.Table(os.environ["STOCK_PRICES_TABLE"]).get_item(
        Key={"marketCode": market_code}
    )
    if "Item" not in result:
        return _res(404, {"error": "quote not found"})

    item = result["Item"]
    item["history"] = item.get("history", [])[-30:]  # 直近30件にトリム
    return _res(200, item)


def _get_stock_news(market: str, code: str, name: str):
    """銘柄名/コードでニュースをライブ取得しフィルタ(RSSはレート制限なし)"""
    all_news = NewsFetcher().get_all_news()
    keywords = {kw for kw in (code, name) if kw}

    matched = [n for n in all_news if any(kw in n.get("title", "") for kw in keywords)]
    return _res(200, {"market": market, "code": code, "news": matched[:20]})


# ── ヘルパー ─────────────────────────────────────────────────────────

def _parse_body(event: dict) -> dict:
    raw = event.get("body", "")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _json_default(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    return str(obj)


def _res(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        },
        "body": json.dumps(body, ensure_ascii=False, default=_json_default),
    }
