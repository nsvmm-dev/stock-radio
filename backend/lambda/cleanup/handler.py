import os
import logging
from datetime import datetime, timezone, timedelta

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")


def lambda_handler(event, context):
    """DynamoDB TTL が削除した/するはずのレコードに対応するS3ファイルを削除する。
    DynamoDB TTLはDB削除に最大48時間かかるため、このLambdaでS3側を先行削除。
    """
    now_ts = int(datetime.now(timezone.utc).timestamp())
    radios_table = dynamodb.Table(os.environ["RADIOS_TABLE"])
    audio_bucket = os.environ["AUDIO_BUCKET"]

    deleted_db = 0
    deleted_s3 = 0
    errors = 0

    # ttl が設定されていて、かつ期限切れのレコードを取得
    resp = radios_table.scan(
        FilterExpression=Attr("ttl").exists() & Attr("ttl").lt(now_ts)
    )

    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        resp = radios_table.scan(
            FilterExpression=Attr("ttl").exists() & Attr("ttl").lt(now_ts),
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        items.extend(resp.get("Items", []))

    logger.info(f"期限切れレコード: {len(items)} 件")

    for item in items:
        try:
            s3_key = item.get("s3Key")
            if s3_key:
                s3.delete_object(Bucket=audio_bucket, Key=s3_key)
                deleted_s3 += 1

            radios_table.delete_item(
                Key={"userId": item["userId"], "radioDate": item["radioDate"]}
            )
            deleted_db += 1
        except Exception as e:
            logger.error(f"削除失敗: {item.get('userId')}/{item.get('radioDate')}: {e}")
            errors += 1

    logger.info(f"クリーンアップ完了: s3={deleted_s3}, db={deleted_db}, errors={errors}")
    return {"statusCode": 200, "deleted_s3": deleted_s3, "deleted_db": deleted_db, "errors": errors}
