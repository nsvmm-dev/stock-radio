import json
import os
import logging
from datetime import datetime, timezone, timedelta

import boto3
from boto3.dynamodb.conditions import Key, Attr

from stock_fetcher import StockFetcher
from news_fetcher import NewsFetcher
from script_generator import ScriptGenerator
from tts_generator import TTSGenerator

logger = logging.getLogger()
logger.setLevel(logging.INFO)

JST = timezone(timedelta(hours=9))
dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")


def lambda_handler(event, context):
    jst_now = datetime.now(JST)
    # radio_date: ラジオのキー(今日の放送日) = 通知Lambdaと一致させる
    # fetch_date: 市場データの取得日(前日の市場終値)
    radio_date = jst_now.strftime("%Y-%m-%d")
    fetch_date = (jst_now - timedelta(days=1)).strftime("%Y-%m-%d")

    logger.info(f"ラジオ生成開始: radio_date={radio_date}, fetch_date={fetch_date}")

    users = _scan_all_users()
    logger.info(f"対象ユーザー数: {len(users)}")

    if not users:
        return {"statusCode": 200, "body": json.dumps({"generated": 0, "message": "no users"})}

    # 市場全体データは全ユーザー共通 → 1回だけ取得してキャッシュ
    stock_fetcher = StockFetcher()
    news_fetcher = NewsFetcher()

    market_data = _fetch_market_overview(stock_fetcher, fetch_date)
    all_news = news_fetcher.get_all_news()

    generated, failed = 0, 0
    for user in users:
        try:
            _generate_for_user(user, radio_date, fetch_date, market_data, all_news, stock_fetcher, jst_now)
            generated += 1
        except Exception as e:
            logger.error(f"ユーザー {user.get('userId')} の生成失敗: {e}", exc_info=True)
            failed += 1

    logger.info(f"生成完了: success={generated}, failed={failed}")
    return {
        "statusCode": 200,
        "body": json.dumps({"generated": generated, "failed": failed, "date": radio_date}),
    }


def _fetch_market_overview(stock_fetcher: StockFetcher, fetch_date: str) -> dict:
    """市場概況データを取得 (fetch_date = 前日の市場終値日)"""
    market = {}
    try:
        market["nikkei"] = stock_fetcher.get_jp_index("N225", fetch_date)
        market["topix"] = stock_fetcher.get_jp_index("TOPX", fetch_date)
        # Alpha Vantage はインデックス非対応のため ETF で代用
        # DIA=ダウ, QQQ=NASDAQ100, SPY=S&P500
        market["dow"] = stock_fetcher.get_us_stock("DIA", fetch_date)
        market["nasdaq"] = stock_fetcher.get_us_stock("QQQ", fetch_date)
        market["sp500"] = stock_fetcher.get_us_stock("SPY", fetch_date)
    except Exception as e:
        logger.warning(f"市場概況データ取得エラー: {e}")
    return market


def _generate_for_user(user: dict, radio_date: str, fetch_date: str, market_data: dict,
                        all_news: list, stock_fetcher: StockFetcher, jst_now: datetime):
    user_id = user["userId"]
    plan = user.get("plan", "free")

    watchlist = _get_watchlist(user_id)
    watchlist_data = _fetch_watchlist_data(watchlist, stock_fetcher, fetch_date)

    # ユーザーウォッチリストに関連するニュースをフィルタ
    relevant_news = _filter_relevant_news(all_news, watchlist_data)

    # 台本生成
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        radio_date=radio_date,
        market_data=market_data,
        watchlist_data=watchlist_data,
        news=relevant_news,
    )

    # 音声生成
    tts_gen = TTSGenerator()
    audio_bytes = tts_gen.synthesize(script)

    # S3 に保存
    audio_bucket = os.environ["AUDIO_BUCKET"]
    s3_key = f"radios/{user_id}/{radio_date}.mp3"

    s3.put_object(
        Bucket=audio_bucket,
        Key=s3_key,
        Body=audio_bytes,
        ContentType="audio/mpeg",
        Tagging=f"plan={plan}",
    )

    # DynamoDB にメタ情報保存
    ttl = _calc_ttl(plan, jst_now)
    item = {
        "userId": user_id,
        "radioDate": radio_date,
        "s3Key": s3_key,
        "durationSec": _estimate_duration_sec(script),
        "scriptLength": len(script),
        "stockCount": len(watchlist_data),
        "createdAt": jst_now.isoformat(),
    }
    if ttl is not None:
        item["ttl"] = ttl

    dynamodb.Table(os.environ["RADIOS_TABLE"]).put_item(Item=item)
    logger.info(f"ラジオ保存: userId={user_id}, date={radio_date}, s3={s3_key}")


def _calc_ttl(plan: str, now: datetime):
    if plan == "free":
        return int((now + timedelta(days=2)).timestamp())
    elif plan == "standard":
        return int((now + timedelta(days=31)).timestamp())
    return None  # pro = 無制限


def _fetch_watchlist_data(watchlist: list, stock_fetcher: StockFetcher, date: str) -> list:
    result = []
    for item in watchlist:
        code = item["stockCode"]
        market = item.get("market", "JP")
        try:
            data = (
                stock_fetcher.get_jp_stock(code, date)
                if market == "JP"
                else stock_fetcher.get_us_stock(code, date)
            )
            if data:
                result.append({
                    "name": item.get("stockName", code),
                    "code": code,
                    "market": market,
                    **data,
                })
        except Exception as e:
            logger.warning(f"銘柄データ取得スキップ: code={code}, error={e}")
    return result


def _filter_relevant_news(all_news: list, watchlist_data: list) -> list:
    names = {s.get("name", "") for s in watchlist_data}
    codes = {s.get("code", "") for s in watchlist_data}
    relevant, general = [], []

    for item in all_news:
        title = item.get("title", "")
        if any(kw in title for kw in names | codes if kw):
            relevant.append(item)
        else:
            general.append(item)

    return relevant[:5] + general[:5]


def _scan_all_users() -> list:
    table = dynamodb.Table(os.environ["USERS_TABLE"])
    items = []
    resp = table.scan()
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    return items


def _get_watchlist(user_id: str) -> list:
    table = dynamodb.Table(os.environ["WATCHLISTS_TABLE"])
    resp = table.query(KeyConditionExpression=Key("userId").eq(user_id))
    return resp.get("Items", [])


def _estimate_duration_sec(script: str) -> int:
    # 日本語は約5文字/秒で読まれる
    return len(script) // 5
