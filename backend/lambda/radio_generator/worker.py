import json
import logging
import os
from datetime import datetime, timezone, timedelta

import boto3

from handler import _organize_news, _estimate_duration_sec, _calc_ttl
from script_generator import ScriptGenerator
from tts_generator import TTSGenerator

logger = logging.getLogger()
logger.setLevel(logging.INFO)

JST = timezone(timedelta(hours=9))
dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")


def lambda_handler(event, context):
    for record in event.get("Records", []):
        try:
            message = json.loads(record["body"])
            _process_user(message)
        except Exception as e:
            logger.error(f"Worker処理失敗: {e}", exc_info=True)
            raise  # SQSにリトライさせる


def _process_user(message: dict):
    user = message["user"]
    watchlist_data = message["watchlist_data"]
    radio_date = message["radio_date"]
    market_data = message["market_data"]
    all_news = message["all_news"]
    finnhub_news = message.get("finnhub_news", {})
    jst_now = datetime.fromisoformat(message["jst_now"])

    user_id = user["userId"]
    plan = user.get("plan", "free")
    language = user.get("language", "ja")
    if language not in ("ja", "en"):
        language = "ja"

    news_bundle = _organize_news(all_news, watchlist_data, finnhub_news)

    script_gen = ScriptGenerator(plan=plan)
    script = script_gen.generate(
        radio_date=radio_date,
        market_data=market_data,
        watchlist_data=watchlist_data,
        news_bundle=news_bundle,
        language=language,
    )

    tts_gen = TTSGenerator(language=language, plan=plan)
    audio_bytes = tts_gen.synthesize(script)

    audio_bucket = os.environ["AUDIO_BUCKET"]
    s3_key = f"radios/{user_id}/{radio_date}.mp3"

    s3.put_object(
        Bucket=audio_bucket,
        Key=s3_key,
        Body=audio_bytes,
        ContentType="audio/mpeg",
        Tagging=f"plan={plan}",
    )

    ttl = _calc_ttl(plan, jst_now)
    item = {
        "userId": user_id,
        "radioDate": radio_date,
        "s3Key": s3_key,
        "durationSec": _estimate_duration_sec(script, language),
        "scriptLength": len(script),
        "stockCount": len(watchlist_data),
        "createdAt": jst_now.isoformat(),
    }
    if ttl is not None:
        item["ttl"] = ttl

    dynamodb.Table(os.environ["RADIOS_TABLE"]).put_item(Item=item)
    logger.info(f"ラジオ保存: userId={user_id}, date={radio_date}, s3={s3_key}")
