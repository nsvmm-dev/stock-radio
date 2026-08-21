import os
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import requests

logger = logging.getLogger()

ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"

ALPHA_VANTAGE_INTERVAL_SEC = 13


class StockFetcher:
    def __init__(self):
        self._alpha_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
        self._alpha_last_call: float = 0.0
        self._us_cache: dict = {}

    # ── Alpha Vantage (米国株) ───────────────────────────────────────

    def get_us_stock(self, symbol: str, date: str) -> Optional[dict]:
        """米国株の日足データを取得 (Alpha Vantage)"""
        if not self._alpha_key:
            return None

        if symbol not in self._us_cache:
            # レート制限等で失敗した結果も{}としてキャッシュする。
            # そうしないと、同じ銘柄を複数ユーザーが持っている場合に
            # 失敗するたびリトライしてクォータをさらに浪費してしまう。
            self._us_cache[symbol] = self._fetch_alpha_vantage(symbol) or {}
        data = self._us_cache[symbol]

        if not data:
            return None

        # 指定日または直近の営業日を探す
        for i in range(5):
            check_date = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=i)).strftime("%Y-%m-%d")
            if check_date in data:
                daily = data[check_date]
                close = float(daily["4. close"])
                open_ = float(daily["1. open"])
                change = close - open_
                change_pct = (change / open_ * 100) if open_ else 0
                return {
                    "close": round(close, 2),
                    "high": round(float(daily["2. high"]), 2),
                    "low": round(float(daily["3. low"]), 2),
                    "volume": int(daily["5. volume"]),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                }

        return None

    def _fetch_alpha_vantage(self, symbol: str) -> Optional[dict]:
        """Alpha Vantage API を呼び出す (レート制限付き)"""
        # 5req/分 = 12秒間隔
        elapsed = time.time() - self._alpha_last_call
        if elapsed < ALPHA_VANTAGE_INTERVAL_SEC:
            time.sleep(ALPHA_VANTAGE_INTERVAL_SEC - elapsed)
        self._alpha_last_call = time.time()

        try:
            r = requests.get(
                ALPHA_VANTAGE_BASE,
                params={
                    "function": "TIME_SERIES_DAILY",
                    "symbol": symbol,
                    "apikey": self._alpha_key,
                    "outputsize": "compact",
                },
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()

            if "Note" in data:
                logger.warning(f"Alpha Vantage レート制限: {data['Note']}")
                return None
            if "Error Message" in data:
                logger.warning(f"Alpha Vantage エラー: {data['Error Message']}")
                return None

            return data.get("Time Series (Daily)", {})
        except Exception as e:
            logger.error(f"Alpha Vantage 取得エラー: symbol={symbol}, {e}")
            return None
