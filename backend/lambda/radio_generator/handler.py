import json
import os
import re
import logging
from datetime import datetime, timezone, timedelta

import boto3
from boto3.dynamodb.conditions import Key, Attr

from stock_fetcher import StockFetcher
from news_fetcher import NewsFetcher

logger = logging.getLogger()
logger.setLevel(logging.INFO)

JST = timezone(timedelta(hours=9))
dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
sqs = boto3.client("sqs")

# 米国株: S&P500構成銘柄の静的リスト(セクター判定・競合企業ニュース補完に使用)
with open(os.path.join(os.path.dirname(__file__), "us_tickers.json"), encoding="utf-8") as f:
    _US_TICKERS = json.load(f)

_SECTOR_BY_CODE = {t["code"]: t.get("sector", "") for t in _US_TICKERS if t.get("code")}
_TICKERS_BY_SECTOR: dict = {}
for _t in _US_TICKERS:
    if _t.get("sector") and _t.get("code"):
        _TICKERS_BY_SECTOR.setdefault(_t["sector"], []).append(_t)


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

    # 全ユーザーのウォッチリストを先に取得してユニーク銘柄を収集
    all_watchlists = {user["userId"]: _get_watchlist(user["userId"]) for user in users}
    unique_symbols = {
        item["stockCode"]
        for wl in all_watchlists.values()
        for item in wl
        if item.get("market", "US") == "US"
    }

    # Finnhub: 銘柄単位でニュース取得（全ユーザー共有・重複APIコールなし）
    finnhub_from = (jst_now - timedelta(days=3)).strftime("%Y-%m-%d")
    finnhub_to = jst_now.strftime("%Y-%m-%d")
    finnhub_news = news_fetcher.get_stocks_news(unique_symbols, finnhub_from, finnhub_to)

    # 共有コンテキスト(market_data + all_news)をS3に一時保存
    # → SQSメッセージに全ユーザー分埋め込む256KB制限を回避
    audio_bucket = os.environ["AUDIO_BUCKET"]
    context_s3_key = f"shared/{radio_date}/context.json"
    s3.put_object(
        Bucket=audio_bucket,
        Key=context_s3_key,
        Body=json.dumps({"market_data": market_data, "all_news": all_news}, default=str).encode("utf-8"),
        ContentType="application/json",
    )
    logger.info(f"共有コンテキスト保存: {context_s3_key}")

    queue_url = os.environ["WORKER_QUEUE_URL"]
    sent = 0

    for user in users:
        user_id = user["userId"]
        watchlist = all_watchlists[user_id]
        watchlist_data = _fetch_watchlist_data(watchlist, stock_fetcher, fetch_date)

        # このユーザーの銘柄だけに絞り込んだFinnhubニュースを送信
        user_symbols = {item["stockCode"] for item in watchlist if item.get("market", "US") == "US"}
        user_finnhub = {k: v for k, v in finnhub_news.items() if k in user_symbols}

        message_body = json.dumps({
            "user": user,
            "watchlist_data": watchlist_data,
            "radio_date": radio_date,
            "context_s3_key": context_s3_key,
            "finnhub_news": user_finnhub,
            "jst_now": jst_now.isoformat(),
        }, default=str)

        sqs.send_message(QueueUrl=queue_url, MessageBody=message_body)
        sent += 1
        logger.info(f"SQSキュー送信: userId={user_id}")

    logger.info(f"SQS送信完了: {sent}件")

    return {
        "statusCode": 200,
        "body": json.dumps({"queued": sent, "date": radio_date}),
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
                    "sector": _SECTOR_BY_CODE.get(code, ""),
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


RELATED_NEWS_MIN_DIRECT = 2  # 直接ニュースがこの件数未満の銘柄は業界動向で補完する
RELATED_NEWS_MAX = 2  # 業界動向として補完する最大件数


def _related_keywords(sector: str, exclude_code: str) -> list:
    """
    同一セクター内の他銘柄の簡易社名を、競合企業ニュース検索用のキーワードとして返す。
    件数を絞るとアルファベット順で先頭寄りの企業しか拾えなくなる
    (Dell/Ciscoのような有名企業が漏れる)ため、セクター内全社を対象にする。
    ニュース記事数(最大80件程度)との突き合わせなので計算コストは小さい。
    """
    peers = _TICKERS_BY_SECTOR.get(sector, [])
    return [
        _search_name(p["name"]) for p in peers
        if p.get("code") != exclude_code and p.get("name")
    ]


def _organize_news(all_news: list, watchlist_data: list, finnhub_news: dict = None) -> dict:
    """
    ウォッチリスト銘柄ごとの関連ニュース(決算関連は別途フラグ)と、
    そこに含まれなかった米国市場の全般ニュースに分類する。
    Finnhub ニュースが取得できた銘柄はそれを優先使用し、
    取得できなかった銘柄は RSS からキーワードマッチングで補完する。
    直接ニュースが少ないマイナー銘柄には、同じセクターの競合企業の
    ニュースを「業界動向」として別バケットで補完する。
    """
    _finnhub = finnhub_news or {}
    stock_news: dict = {}
    earnings_news: dict = {}
    related_news: dict = {}
    used_links: set = set()

    for stock in watchlist_data:
        code = stock.get("code", "")
        sector = stock.get("sector", "")

        if code in _finnhub and _finnhub[code]:
            # Finnhub ニュースを優先使用（銘柄特化・精度が高い）
            matched = _finnhub[code]
            for item in matched:
                used_links.add(item.get("link", ""))
        else:
            # RSS からキーワードマッチング（フォールバック）
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
            if matched:
                for item in matched:
                    used_links.add(item.get("link", ""))

        if matched:
            stock_news[code] = matched
            earnings = [
                item for item in matched
                if any(kw in (item.get("title", "") + item.get("summary", "")) for kw in EARNINGS_KEYWORDS)
            ]
            if earnings:
                earnings_news[code] = earnings

        if sector and len(matched) < RELATED_NEWS_MIN_DIRECT:
            matched_links = {item.get("link", "") for item in matched}
            peer_keywords = _related_keywords(sector, code)
            related = []
            for item in all_news:
                link = item.get("link", "")
                if link in used_links or link in matched_links:
                    continue
                text = item.get("title", "") + item.get("summary", "")
                if any(kw in text for kw in peer_keywords):
                    related.append(item)
                    if len(related) >= RELATED_NEWS_MAX:
                        break
            if related:
                related_news[code] = related

    us_general = []
    for item in all_news:
        if item.get("link", "") in used_links:
            continue
        if item.get("category", "") in ("us_market", "global"):
            us_general.append(item)

    return {
        "stock_news": stock_news,
        "earnings_news": earnings_news,
        "related_news": related_news,
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
