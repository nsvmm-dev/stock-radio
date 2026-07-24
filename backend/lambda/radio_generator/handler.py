import json
import os
import logging
from collections import Counter
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
    # 米国の値上がり/値下がり上位は全ユーザー共通 → ループ前に1回だけ取得
    # (Alpha Vantage 25req/日の枠を最初に確保しておく)
    top_movers = stock_fetcher.get_us_top_movers()

    generated, failed = 0, 0
    unique_stock_prices: dict = {}  # marketCode -> {code, name, market}
    jp_code_counter: Counter = Counter()  # JP銘柄コード -> ウォッチ登録ユーザー数

    for user in users:
        user_id = user["userId"]
        watchlist = _get_watchlist(user_id)
        watchlist_data = _fetch_watchlist_data(watchlist, stock_fetcher, fetch_date)

        for w in watchlist:
            if w.get("market", "JP") == "JP":
                jp_code_counter[w["stockCode"]] += 1

        for s in watchlist_data:
            market_code = f"{s['market']}#{s['code']}"
            unique_stock_prices.setdefault(market_code, {
                "market": s["market"], "code": s["code"], "name": s["name"],
            })

        try:
            _generate_for_user(user, watchlist_data, radio_date, market_data, all_news, jst_now)
            generated += 1
        except Exception as e:
            logger.error(f"ユーザー {user.get('userId')} の生成失敗: {e}", exc_info=True)
            failed += 1

    logger.info(f"生成完了: success={generated}, failed={failed}")

    try:
        _update_stock_prices_table(stock_fetcher, unique_stock_prices)
        _update_hot_stocks_table(top_movers, jp_code_counter, unique_stock_prices)
    except Exception as e:
        logger.error(f"株価キャッシュ更新失敗: {e}", exc_info=True)

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


def _generate_for_user(user: dict, watchlist_data: list, radio_date: str, market_data: dict,
                        all_news: list, jst_now: datetime):
    user_id = user["userId"]
    plan = user.get("plan", "free")

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


def _update_stock_prices_table(stock_fetcher: StockFetcher, unique_stock_prices: dict):
    """当日ウォッチリストに登場した銘柄ごとに履歴を取得し StockPricesTable を更新"""
    table = dynamodb.Table(os.environ["STOCK_PRICES_TABLE"])
    now = datetime.now(JST).isoformat()

    for market_code, info in unique_stock_prices.items():
        market, code = info["market"], info["code"]
        history = (
            stock_fetcher.get_jp_stock_history(code)
            if market == "JP"
            else stock_fetcher.get_us_stock_series(code)
        )
        if not history:
            continue

        latest = history[-1]
        prev = history[-2] if len(history) >= 2 else None
        change_pct = (
            round((latest["close"] - prev["close"]) / prev["close"] * 100, 2)
            if prev and prev["close"]
            else 0
        )

        # _update_hot_stocks_table (jp_popular) がこの後に参照するため in-place で補完
        info["latestClose"] = latest["close"]
        info["changePct"] = change_pct

        table.put_item(Item={
            "marketCode": market_code,
            "market": market,
            "code": code,
            "name": info["name"],
            "latestClose": latest["close"],
            "changePct": change_pct,
            "history": history,
            "updatedAt": now,
        })

    logger.info(f"StockPricesTable更新: {len(unique_stock_prices)}銘柄")


def _update_hot_stocks_table(top_movers: dict, jp_code_counter: Counter, unique_stock_prices: dict):
    """当日の注目銘柄(米国値上がり/値下がり/出来高、日本の人気銘柄)を HotStocksTable に保存"""
    table = dynamodb.Table(os.environ["HOT_STOCKS_TABLE"])
    now = datetime.now(JST).isoformat()

    if top_movers:
        for category_key, us_key in (
            ("us_gainers", "gainers"), ("us_losers", "losers"), ("us_most_active", "most_active"),
        ):
            items = [
                {"market": "US", "code": m["code"], "name": m["code"], "latestClose": m["close"],
                 "changePct": m["change_pct"]}
                for m in top_movers.get(us_key, [])
            ]
            table.put_item(Item={"category": category_key, "items": items, "updatedAt": now})

    # 日本株の「人気銘柄」= 全ユーザーのウォッチリストでの登場回数が多い順
    jp_popular = []
    for code, _count in jp_code_counter.most_common(10):
        info = unique_stock_prices.get(f"JP#{code}")
        if not info:
            continue  # その日の価格取得に失敗した銘柄は除外
        jp_popular.append({
            "market": "JP", "code": code, "name": info["name"],
            "latestClose": info.get("latestClose"), "changePct": info.get("changePct"),
        })

    table.put_item(Item={"category": "jp_popular", "items": jp_popular, "updatedAt": now})
    logger.info("HotStocksTable更新完了")
