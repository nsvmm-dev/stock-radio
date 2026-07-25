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
MAX_SEARCH_RESULTS = 20

# 米国株: S&P500構成銘柄の静的リスト(商用利用の外部API呼び出しを避けるため同梱)
with open(os.path.join(os.path.dirname(__file__), "us_tickers.json"), encoding="utf-8") as f:
    _US_TICKERS = json.load(f)

_jp_stock_master_cache = None  # Lambda実行コンテナ内でのメモリキャッシュ(コールドスタート毎に再取得)


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

    # GET /stocks/search?q=xxx&market=JP|US
    if segments == ["stocks", "search"] and method == "GET":
        return _search_stocks(query_params.get("q", ""), query_params.get("market", ""))

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

        # PUT /users/{userId}/language
        if len(segments) == 3 and segments[2] == "language" and method == "PUT":
            return _update_language(user_id, body)

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
    language = body.get("language", "ja")
    if language not in ("ja", "en"):
        language = "ja"

    table.put_item(Item={
        "userId": user_id,
        "email": body.get("email", ""),
        "plan": "free",
        "fcmToken": body.get("fcmToken", ""),
        "language": language,
        # languageChangedAt はここでは設定しない。登録時刻を起点にすると
        # 有料プランへ切り替えた直後のユーザーが最初の変更すらできなく
        # なるため、_update_language が実際に変更された時点で初めて記録する。
        "createdAt": now,
        "updatedAt": now,
    })
    return _res(201, {"userId": user_id, "plan": "free", "language": language})


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


LANGUAGE_CHANGE_COOLDOWN_DAYS = 30


def _update_language(user_id: str, body: dict):
    language = body.get("language")
    if language not in ("ja", "en"):
        return _res(400, {"error": "language must be ja / en"})

    table = dynamodb.Table(os.environ["USERS_TABLE"])
    result = table.get_item(Key={"userId": user_id})
    if "Item" not in result:
        return _res(404, {"error": "user not found"})
    user = result["Item"]

    if user.get("plan", "free") == "free":
        return _res(403, {"error": "free_plan_locked",
                           "message": "ラジオ言語の変更には有料プランへのアップグレードが必要です"})

    now = datetime.now(JST)
    changed_at_str = user.get("languageChangedAt")
    if changed_at_str:
        changed_at = datetime.fromisoformat(changed_at_str)
        elapsed_days = (now - changed_at).days
        if elapsed_days < LANGUAGE_CHANGE_COOLDOWN_DAYS:
            next_available = changed_at + timedelta(days=LANGUAGE_CHANGE_COOLDOWN_DAYS)
            return _res(403, {
                "error": "cooldown",
                "message": "ラジオ言語は前回の変更から30日間は再変更できません",
                "nextAvailableDate": next_available.strftime("%Y-%m-%d"),
            })

    table.update_item(
        Key={"userId": user_id},
        UpdateExpression="SET #lang = :lang, languageChangedAt = :now, updatedAt = :now",
        ExpressionAttributeNames={"#lang": "language"},
        ExpressionAttributeValues={":lang": language, ":now": now.isoformat()},
    )
    return _res(200, {"language": language})


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

def _search_stocks(query: str, market: str):
    query = query.strip()
    if not query:
        return _res(200, {"results": [], "query": query})

    market = market.upper()
    results = []
    if market in ("", "US"):
        results += _search_us_tickers(query)
    if market in ("", "JP"):
        results += _search_jp_stock_master(query)

    return _res(200, {"results": results[:MAX_SEARCH_RESULTS], "query": query})


def _search_us_tickers(query: str) -> list:
    q = query.lower()
    matched = [
        t for t in _US_TICKERS
        if q in t["code"].lower() or q in t["name"].lower()
    ]
    return [{"market": "US", "code": t["code"], "name": t["name"]} for t in matched[:MAX_SEARCH_RESULTS]]


def _search_jp_stock_master(query: str) -> list:
    master = _load_jp_stock_master()
    q = query.lower()
    matched = [
        t for t in master
        if q in t["code"].lower() or q in t["name"].lower()
    ]
    return [{"market": "JP", "code": t["code"], "name": t["name"]} for t in matched[:MAX_SEARCH_RESULTS]]


def _load_jp_stock_master() -> list:
    global _jp_stock_master_cache
    if _jp_stock_master_cache is not None:
        return _jp_stock_master_cache

    try:
        obj = s3.get_object(Bucket=os.environ["AUDIO_BUCKET"], Key="stock-master/jp.json")
        _jp_stock_master_cache = json.loads(obj["Body"].read())
    except s3.exceptions.NoSuchKey:
        logger.warning("銘柄マスタ未生成(日次バッチ未実行)")
        _jp_stock_master_cache = []
    except Exception as e:
        logger.error(f"銘柄マスタ取得エラー: {e}")
        _jp_stock_master_cache = []

    return _jp_stock_master_cache


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
