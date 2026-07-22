import json
import os
import logging
from datetime import datetime, timezone, timedelta

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

JST = timezone(timedelta(hours=9))
dynamodb = boto3.resource("dynamodb")
ssm = boto3.client("ssm")

_firebase_app = None


def _init_firebase():
    global _firebase_app
    if _firebase_app:
        return

    import firebase_admin
    from firebase_admin import credentials

    if firebase_admin._apps:
        _firebase_app = firebase_admin.get_app()
        return

    param_name = os.environ.get(
        "FIREBASE_CREDENTIALS_PARAM", "/stock-radio/dev/firebase-credentials"
    )
    try:
        resp = ssm.get_parameter(Name=param_name, WithDecryption=True)
        cred_dict = json.loads(resp["Parameter"]["Value"])
        cred = credentials.Certificate(cred_dict)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase 初期化完了")
    except Exception as e:
        logger.error(f"Firebase 初期化失敗: {e}")
        raise


def lambda_handler(event, context):
    """7:00 AM JST に全ユーザーへプッシュ通知を送信"""
    _init_firebase()

    from firebase_admin import messaging

    today = datetime.now(JST).strftime("%Y-%m-%d")

    users = _scan_all_users()
    sent, skipped, failed = 0, 0, 0

    for user in users:
        user_id = user.get("userId")
        fcm_token = user.get("fcmToken", "")

        if not fcm_token:
            skipped += 1
            continue

        # 今日のラジオが存在するか確認
        radio = dynamodb.Table(os.environ["RADIOS_TABLE"]).get_item(
            Key={"userId": user_id, "radioDate": today}
        )
        if "Item" not in radio:
            skipped += 1
            continue

        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title="今日の株価ラジオが届きました",
                    body=f"{today} の市場情報をお届けします。今すぐ聴く →",
                ),
                data={
                    "radioDate": today,
                    "type": "radio_ready",
                },
                token=fcm_token,
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            badge=1,
                            sound="default",
                            content_available=True,
                        )
                    )
                ),
            )
            messaging.send(message)
            sent += 1
        except Exception as e:
            logger.warning(f"通知送信失敗: userId={user_id}, {e}")
            failed += 1

    logger.info(f"通知完了: sent={sent}, skipped={skipped}, failed={failed}")
    return {"statusCode": 200, "sent": sent, "skipped": skipped, "failed": failed}


def _scan_all_users() -> list:
    table = dynamodb.Table(os.environ["USERS_TABLE"])
    items = []
    resp = table.scan()
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    return items
