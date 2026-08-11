import json
import os
import re
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
        user_id = user["userId"]
        watchlist = _get_watchlist(user_id)
        watchlist_data = _fetch_watchlist_data(watchlist, stock_fetcher, fetch_date)

        try:
            _generate_for_user(user, watchlist_data, radio_date, market_data, all_news, jst_now)
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
    """米国市場概況データを取得 (fetch_date = 前日の市場終値日)"""
    market = {}
    try:
        # Alpha Vantage はインデックス非対応のため ETF で代用
        # DIA=ダウ, QQQ=NASDAQ100, SPY=S&P500
        market["dow"] = stock_fetcher.get_us_stock("DIA", fetch_date)
        market["nasdaq"] = stock_fetcher.get_us_stock("QQQ", fetch_date)
        market["sp500"] = stock_fetcher.get_us_stock("SPY", fetch_date)
    except Exception as e:
        logger.warning(f"市場概況データ取得エラー: {e}")
    return market


def _generate_for_user(user: dict, watchlist_data: list, radio_date: str, market_data: dict,
                        all_news: list, jst_now: datetime):
    user_id = user["userId"]
    plan = user.get("plan", "free")
    language = user.get("language", "ja")
    if language not in ("ja", "en"):
        language = "ja"

    # ウォッチリスト銘柄ごとの関連ニュース・決算情報、および日米それぞれの市場ニュースに分類
    news_bundle = _organize_news(all_news, watchlist_data)

    # 台本生成
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        radio_date=radio_date,
        market_data=market_data,
        watchlist_data=watchlist_data,
        news_bundle=news_bundle,
        language=language,
    )

    # 音声生成(free=standard、standard/pro=neuralを自動選択)
    tts_gen = TTSGenerator(language=language, plan=plan)
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
        "durationSec": _estimate_duration_sec(script, language),
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
    """米国株限定。日本株は前バージョンの登録が残っていてもここで自然に除外される"""
    result = []
    for item in watchlist:
        code = item["stockCode"]
        if item.get("market", "US") != "US":
            continue
        try:
            data = stock_fetcher.get_us_stock(code, date)
            if data:
                result.append({
                    "name": item.get("stockName", code),
                    "code": code,
                    "market": "US",
                    **data,
                })
        except Exception as e:
            logger.warning(f"銘柄データ取得スキップ: code={code}, error={e}")
    return result


EARNINGS_KEYWORDS = (
    "決算", "純利益", "営業利益", "最終利益", "最終赤字", "最高益",
    "上方修正", "下方修正", "四半期", "通期見通し",
    "earnings", "quarterly results", "revenue", "profit", "guidance", "EPS",
)

MAX_NEWS_PER_STOCK = 5
MAX_GENERAL_NEWS = 4


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


def _organize_news(all_news: list, watchlist_data: list) -> dict:
    """
    ウォッチリスト銘柄ごとの関連ニュース(決算関連は別途フラグ)と、
    そこに含まれなかった米国市場の全般ニュースに分類する。
    銘柄名・コードはタイトルと概要の両方から検索し、一致した記事は
    どちらか一方のバケットにのみ入れて重複を避ける。
    """
    stock_news: dict = {}
    earnings_news: dict = {}
    used_links: set = set()

    for stock in watchlist_data:
        code = stock.get("code", "")
        keywords = [kw for kw in (_search_name(stock.get("name", "")), code) if kw]
        matched = []
        for item in all_news:
            link = item.get("link", "")
            if link in used_links:
                continue
            text = item.get("title", "") + item.get("summary", "")
            if any(kw in text for kw in keywords):
                matched.append(item)
                if len(matched) >= MAX_NEWS_PER_STOCK:
                    break

        if not matched:
            continue

        for item in matched:
            used_links.add(item.get("link", ""))
        stock_news[code] = matched

        earnings = [
            item for item in matched
            if any(kw in (item.get("title", "") + item.get("summary", "")) for kw in EARNINGS_KEYWORDS)
        ]
        if earnings:
            earnings_news[code] = earnings

    us_general = []
    for item in all_news:
        if item.get("link", "") in used_links:
            continue
        if item.get("category", "") in ("us_market", "global"):
            us_general.append(item)

    return {
        "stock_news": stock_news,
        "earnings_news": earnings_news,
        "us_general": us_general[:MAX_GENERAL_NEWS],
    }


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


def _estimate_duration_sec(script: str, language: str = "ja") -> int:
    # 日本語は約5文字/秒、英語は約14文字/秒(スペース込み)で読まれる
    chars_per_sec = 14 if language == "en" else 5
    return len(script) // chars_per_sec
