import json
import os
import re
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from news_fetcher import NewsFetcher
from apple_auth import verify_apple_identity_token, AppleTokenError

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

    # POST /auth/apple
    if segments == ["auth", "apple"] and method == "POST":
        return _sign_in_with_apple(body)

    # GET /stocks/search?q=xxx&market=JP|US
    if segments == ["stocks", "search"] and method == "GET":
        return _search_stocks(query_params.get("q", ""), query_params.get("market", ""))

    if len(segments) == 4 and segments[0] == "stocks" and method == "GET":
        market, code, action = segments[1], segments[2], segments[3]
        if action == "news":
            return _get_stock_news(market, code, query_params.get("name", ""))

    if len(segments) >= 2 and segments[0] == "users":
        user_id = segments[1]

        # GET /users/{userId}
        if len(segments) == 2 and method == "GET":
            return _get_user(user_id)

        # PUT /users/{userId}/subscription
        if len(segments) == 3 and segments[2] == "subscription" and method == "PUT":
            return _update_subscription(user_id, body)

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

APPLE_BUNDLE_ID = os.environ.get("APPLE_BUNDLE_ID", "com.stockradio.app")


def _sign_in_with_apple(body: dict):
    identity_token = body.get("identityToken")
    if not identity_token:
        return _res(400, {"error": "identityToken is required"})

    try:
        claims = verify_apple_identity_token(identity_token, APPLE_BUNDLE_ID)
    except AppleTokenError as e:
        logger.warning(f"Apple identityToken検証失敗: {e}")
        return _res(401, {"error": "invalid_token", "message": str(e)})

    user_id = claims["sub"]
    table = dynamodb.Table(os.environ["USERS_TABLE"])
    result = table.get_item(Key={"userId": user_id})

    if "Item" in result:
        # 既存ユーザー: そのままログイン
        item = result["Item"]
        item.pop("fcmToken", None)
        return _res(200, item)

    # 新規ユーザー: emailはAppleから初回サインイン時のみ渡される
    language = body.get("language", "ja")
    if language not in ("ja", "en"):
        language = "ja"
    now = datetime.now(JST).isoformat()
    item = {
        "userId": user_id,
        "email": body.get("email") or claims.get("email", ""),
        "plan": "free",
        "language": language,
        # languageChangedAt はここでは設定しない。登録時刻を起点にすると
        # 有料プランへ切り替えた直後のユーザーが最初の変更すらできなく
        # なるため、_update_language が実際に変更された時点で初めて記録する。
        "createdAt": now,
        "updatedAt": now,
    }
    table.put_item(Item=item)
    return _res(201, item)


def _get_user(user_id: str):
    result = dynamodb.Table(os.environ["USERS_TABLE"]).get_item(Key={"userId": user_id})
    if "Item" not in result:
        return _res(404, {"error": "user not found"})
    item = result["Item"]
    item.pop("fcmToken", None)  # デバイストークンは返さない
    return _res(200, item)


# StoreKit の productId -> プランの対応表
PRODUCT_PLAN_MAP = {
    "com.stockradio.app.standard.monthly": "standard",
    "com.stockradio.app.pro.monthly": "pro",
}


def _update_subscription(user_id: str, body: dict):
    """
    StoreKit 2 が端末上で署名検証済みのtransaction情報をアプリから受け取り、
    プランに反映する。productIdが無い場合は有効なサブスクリプションが
    存在しない(期限切れ・解約)とみなしfreeへ降格する。
    サーバー側での独立したApple App Store Server API検証は今回のスコープ外
    (将来 App Store Server Notifications V2 で強化する余地あり)。
    """
    product_id = body.get("productId")
    if product_id:
        plan = PRODUCT_PLAN_MAP.get(product_id)
        if not plan:
            return _res(400, {"error": f"unknown productId: {product_id}"})
    else:
        plan = "free"

    dynamodb.Table(os.environ["USERS_TABLE"]).update_item(
        Key={"userId": user_id},
        UpdateExpression=(
            "SET #plan = :plan, subscriptionProductId = :pid, "
            "originalTransactionId = :tid, subscriptionExpiresAt = :exp, updatedAt = :now"
        ),
        ExpressionAttributeNames={"#plan": "plan"},
        ExpressionAttributeValues={
            ":plan": plan,
            ":pid": product_id or "",
            ":tid": body.get("transactionId", ""),
            ":exp": body.get("expiresAt", ""),
            ":now": datetime.now(JST).isoformat(),
        },
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
    bucket = os.environ["AUDIO_BUCKET"]
    s3_key = item["s3Key"]
    try:
        item["audioUrl"] = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": s3_key},
            ExpiresIn=AUDIO_URL_EXPIRE_SEC,
        )
        # Pro ユーザーにはダウンロード URL を追加（iOS 側でオフライン保存に使用）
        user_result = dynamodb.Table(os.environ["USERS_TABLE"]).get_item(Key={"userId": user_id})
        if user_result.get("Item", {}).get("plan") == "pro":
            item["downloadUrl"] = s3.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": bucket,
                    "Key": s3_key,
                    "ResponseContentDisposition": f'attachment; filename="radio-{radio_date}.mp3"',
                },
                ExpiresIn=AUDIO_URL_EXPIRE_SEC,
            )
    except Exception as e:
        logger.error(f"presigned URL 生成失敗: {e}")

    return _res(200, item)


# ── ウォッチリスト ────────────────────────────────────────────────────

WATCHLIST_LIMITS = {"free": 3, "standard": 10, "pro": None}  # pro = 無制限


def _get_watchlist(user_id: str):
    result = dynamodb.Table(os.environ["WATCHLISTS_TABLE"]).query(
        KeyConditionExpression=Key("userId").eq(user_id)
    )
    return _res(200, {"watchlist": result.get("Items", [])})


def _add_watchlist(user_id: str, body: dict):
    code = body.get("stockCode", "").upper().strip()
    if not code:
        return _res(400, {"error": "stockCode is required"})

    user_result = dynamodb.Table(os.environ["USERS_TABLE"]).get_item(Key={"userId": user_id})
    if "Item" not in user_result:
        return _res(404, {"error": "user not found"})
    plan = user_result["Item"].get("plan", "free")

    watchlist_table = dynamodb.Table(os.environ["WATCHLISTS_TABLE"])
    existing_items = watchlist_table.query(KeyConditionExpression=Key("userId").eq(user_id)).get("Items", [])
    already_added = any(i["stockCode"] == code for i in existing_items)

    limit = WATCHLIST_LIMITS.get(plan, 3)
    if not already_added and limit is not None and len(existing_items) >= limit:
        return _res(403, {
            "error": "watchlist_limit_reached",
            "message": f"お気に入り銘柄は{limit}件までです。プランをアップグレードすると増やせます。",
        })

    item = {
        "userId": user_id,
        "stockCode": code,
        "stockName": body.get("stockName", code),
        "market": body.get("market", "US"),
        "addedAt": datetime.now(JST).isoformat(),
    }
    watchlist_table.put_item(Item=item)
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

    return _res(200, {"results": _search_us_tickers(query)[:MAX_SEARCH_RESULTS], "query": query})


def _search_us_tickers(query: str) -> list:
    q = query.lower()
    matched = [
        t for t in _US_TICKERS
        if q in t["code"].lower() or q in t["name"].lower()
    ]
    return [{"market": "US", "code": t["code"], "name": t["name"]} for t in matched[:MAX_SEARCH_RESULTS]]


# ── ニュース ─────────────────────────────────────────────────────────

_COMPANY_SUFFIXES = (
    ", Inc.", " Inc.", " Incorporated", " Corporation", " Corp.", " Co.",
    " Ltd.", " plc", " N.V.", " S.A.", " LLC",
)


def _search_name(name: str) -> str:
    """
    ニュース本文とのマッチング用に、正式社名から法人格サフィックスや
    "(Class A)"のような括弧書きを取り除いた簡易名を返す(表示用の
    正式名称はそのまま別途保持する)。ニュース記事は通常「Apple Inc.」
    ではなく「Apple」としか書かないため、正式名称そのままだと
    ほとんど一致しなくなってしまう。
    """
    cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", name)
    changed = True
    while changed:
        changed = False
        for suffix in _COMPANY_SUFFIXES:
            if cleaned.endswith(suffix):
                cleaned = cleaned[: -len(suffix)].rstrip(",").strip()
                changed = True
    cleaned = cleaned.rstrip(" &,").strip()
    return cleaned or name


def _get_stock_news(market: str, code: str, name: str):
    """
    銘柄名/コード/業種セクターでニュースをライブ取得しフィルタ(RSSはレート制限なし)。
    銘柄名・コードだけだとヒットするニュースが少なく市場の動向が掴みにくいため、
    業種の関連ニュースも合わせて拾う。タイトルと概要の両方を検索対象にする。
    """
    all_news = NewsFetcher().get_all_news()
    keywords = {kw for kw in (code, _search_name(name)) if kw}

    sector = _get_sector(market, code)
    if sector:
        keywords.add(sector)

    matched = [
        n for n in all_news
        if any(kw in (n.get("title", "") + n.get("summary", "")) for kw in keywords)
    ]
    return _res(200, {"market": market, "code": code, "sector": sector, "news": matched[:20]})


def _get_sector(market: str, code: str) -> str:
    """銘柄の業種を取得(S&P500静的リストのGICSセクター)"""
    item = next((t for t in _US_TICKERS if t.get("code") == code), None)
    return item.get("sector", "") if item else ""


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
