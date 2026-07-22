import json
import os
import logging
import uuid
from datetime import datetime, timezone, timedelta

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

JST = timezone(timedelta(hours=9))
dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

AUDIO_URL_EXPIRE_SEC = 3600  # presigned URL有効期限: 1時間


def lambda_handler(event, context):
    method = event.get("httpMethod", "GET")
    path = event.get("path", "/")
    path_params = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}
    body = _parse_body(event)

    logger.info(f"{method} {path}")

    try:
        return _route(method, path, path_params, query_params, body)
    except Exception as e:
        logger.error(f"未処理エラー: {e}", exc_info=True)
        return _res(500, {"error": "internal server error"})


def _route(method, path, path_params, query_params, body):
    # OPTIONS (CORS プリフライト)
    if method == "OPTIONS":
        return _res(200, {})

    # POST /users
    if path == "/users" and method == "POST":
        return _create_user(body)

    user_id = path_params.get("userId")

    # GET /users/{userId}
    if user_id and path.endswith(f"/users/{user_id}") and method == "GET":
        return _get_user(user_id)

    # PUT /users/{userId}/plan
    if user_id and path.endswith("/plan") and method == "PUT":
        return _update_plan(user_id, body)

    # PUT /users/{userId}/fcm-token
    if user_id and path.endswith("/fcm-token") and method == "PUT":
        return _update_fcm_token(user_id, body)

    # GET /users/{userId}/radios
    if user_id and path.endswith("/radios") and method == "GET":
        return _list_radios(user_id)

    # GET /users/{userId}/radios/{date}
    radio_date = path_params.get("date")
    if user_id and radio_date and method == "GET":
        return _get_radio(user_id, radio_date)

    # GET/POST/DELETE /users/{userId}/watchlist
    if user_id and "/watchlist" in path:
        stock_code = path_params.get("stockCode")
        if method == "GET":
            return _get_watchlist(user_id)
        if method == "POST":
            return _add_watchlist(user_id, body)
        if method == "DELETE" and stock_code:
            return _remove_watchlist(user_id, stock_code)

    # GET /stocks/search?q=xxx
    if path == "/stocks/search" and method == "GET":
        return _search_stocks(query_params.get("q", ""))

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


# ── ヘルパー ─────────────────────────────────────────────────────────

def _parse_body(event: dict) -> dict:
    raw = event.get("body", "")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _res(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        },
        "body": json.dumps(body, ensure_ascii=False, default=str),
    }
