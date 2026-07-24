import os
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import requests

logger = logging.getLogger()

# J-Quants V2 API: x-api-key header auth
JQUANTS_BASE = "https://api.jquants.com/v2"
ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"

ALPHA_VANTAGE_INTERVAL_SEC = 13


class StockFetcher:
    def __init__(self):
        self._jquants_api_key = os.environ.get("JQUANTS_API_KEY", "")
        self._alpha_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
        self._alpha_last_call: float = 0.0
        self._us_cache: dict = {}
        self._jp_cache: dict = {}

        if not self._jquants_api_key:
            logger.warning("JQUANTS_API_KEY not set. Skipping JP stock data.")

    def _jquants_headers(self) -> dict:
        return {"x-api-key": self._jquants_api_key}

    # ── J-Quants V2 (日本株) ─────────────────────────────────────────

    def get_jp_stock(self, code: str, date: str) -> Optional[dict]:
        """日本株の日足データを取得 (J-Quants V2)"""
        cache_key = f"{code}_{date}"
        if cache_key in self._jp_cache:
            return self._jp_cache[cache_key]

        if not self._jquants_api_key:
            return None

        clean_code = code.replace(".T", "").zfill(4)
        jquants_date = date.replace("-", "")

        try:
            r = requests.get(
                f"{JQUANTS_BASE}/prices/daily_quotes",
                headers=self._jquants_headers(),
                params={"code": clean_code, "date": jquants_date},
                timeout=10,
            )
            r.raise_for_status()

            quotes = r.json().get("daily_quotes", [])
            if not quotes:
                return None

            q = quotes[0]
            close = float(q.get("Close") or 0)
            prev_close = float(q.get("AdjustmentClose") or q.get("Close") or close)
            change = close - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0

            result = {
                "close": round(close, 1),
                "high": round(float(q.get("High") or 0), 1),
                "low": round(float(q.get("Low") or 0), 1),
                "volume": int(q.get("Volume") or 0),
                "change": round(change, 1),
                "change_pct": round(change_pct, 2),
            }
            self._jp_cache[cache_key] = result
            return result
        except Exception as e:
            logger.error(f"J-Quants stock fetch error: code={code}, {e}")
            return None

    def get_jp_index(self, index_code: str, date: str) -> Optional[dict]:
        """日経平均・TOPIX を取得 (J-Quants V2)"""
        if not self._jquants_api_key:
            return None

        jquants_date = date.replace("-", "")
        try:
            r = requests.get(
                f"{JQUANTS_BASE}/indices",
                headers=self._jquants_headers(),
                params={"code": index_code, "date": jquants_date},
                timeout=10,
            )
            r.raise_for_status()

            indices = r.json().get("indices", [])
            if not indices:
                return None

            idx = indices[0]
            close = float(idx.get("Close") or 0)
            open_ = float(idx.get("Open") or close)
            change = close - open_
            change_pct = (change / open_ * 100) if open_ else 0

            return {
                "close": round(close, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
            }
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 403:
                logger.info(f"J-Quants /v2/indices requires paid plan (code={index_code})")
            else:
                logger.warning(f"J-Quants index fetch error: {index_code}, {e}")
            return None
        except Exception as e:
            logger.warning(f"J-Quants index fetch error: {index_code}, {e}")
            return None

    # ── Alpha Vantage (米国株) ───────────────────────────────────────

    def get_us_stock(self, symbol: str, date: str) -> Optional[dict]:
        """米国株の日足データを取得 (Alpha Vantage)"""
        if not self._alpha_key:
            return None

        if symbol in self._us_cache:
            data = self._us_cache[symbol]
        else:
            data = self._fetch_alpha_vantage(symbol)
            if data:
                self._us_cache[symbol] = data

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

    def get_us_stock_series(self, symbol: str, limit: int = 30) -> Optional[list]:
        """米国株の日足履歴を取得 (Alpha Vantage, 追加APIコールなし)

        get_us_stock() が既に _fetch_alpha_vantage() で ~100日分の
        Time Series (Daily) を _us_cache に保持しているため、それを
        古い→新しい順に並べ替えて直近 limit 件だけ返す。
        """
        if not self._alpha_key:
            return None

        if symbol in self._us_cache:
            data = self._us_cache[symbol]
        else:
            data = self._fetch_alpha_vantage(symbol)
            if data:
                self._us_cache[symbol] = data

        if not data:
            return None

        dates = sorted(data.keys())[-limit:]
        return [
            {"date": d, "close": round(float(data[d]["4. close"]), 2)}
            for d in dates
        ]

    def get_us_top_movers(self) -> Optional[dict]:
        """米国市場の値上がり/値下がり/出来高上位を取得 (Alpha Vantage TOP_GAINERS_LOSERS)

        レスポンス形式(未認証環境のため実データで最終確認できていない前提):
        {"top_gainers": [{"ticker","price","change_amount","change_percentage","volume"}, ...],
         "top_losers": [...], "most_actively_traded": [...]}
        フィールドは他のAlpha Vantageエンドポイント同様、文字列として返る想定。
        """
        if not self._alpha_key:
            return None

        elapsed = time.time() - self._alpha_last_call
        if elapsed < ALPHA_VANTAGE_INTERVAL_SEC:
            time.sleep(ALPHA_VANTAGE_INTERVAL_SEC - elapsed)
        self._alpha_last_call = time.time()

        try:
            r = requests.get(
                ALPHA_VANTAGE_BASE,
                params={"function": "TOP_GAINERS_LOSERS", "apikey": self._alpha_key},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()

            if "Note" in data or "Information" in data:
                logger.warning(f"Alpha Vantage top-movers レート制限/情報: {data}")
                return None

            def _parse(items):
                result = []
                for item in items or []:
                    try:
                        result.append({
                            "code": item.get("ticker", ""),
                            "close": round(float(item.get("price", 0)), 2),
                            "change_pct": round(
                                float(str(item.get("change_percentage", "0")).rstrip("%")), 2
                            ),
                        })
                    except (ValueError, TypeError):
                        continue
                return result

            return {
                "gainers": _parse(data.get("top_gainers"))[:10],
                "losers": _parse(data.get("top_losers"))[:10],
                "most_active": _parse(data.get("most_actively_traded"))[:10],
            }
        except Exception as e:
            logger.error(f"Alpha Vantage top-movers取得エラー: {e}")
            return None

    def get_jp_stock_history(self, code: str, limit: int = 30) -> Optional[list]:
        """日本株の日足履歴を取得 (J-Quants V2)

        code のみを指定し date を省略すると、その銘柄の全履歴が返る
        (J-Quants公式ドキュメント: code/date いずれか一方の指定が必須で、
        code のみの場合は日付を横断した全データが返る)。V2でも同様の
        挙動を想定しているが、実データでの最終確認は未実施。
        """
        cache_key = f"history_{code}"
        if cache_key in self._jp_cache:
            return self._jp_cache[cache_key]

        if not self._jquants_api_key:
            return None

        clean_code = code.replace(".T", "").zfill(4)

        try:
            r = requests.get(
                f"{JQUANTS_BASE}/prices/daily_quotes",
                headers=self._jquants_headers(),
                params={"code": clean_code},
                timeout=15,
            )
            r.raise_for_status()

            quotes = r.json().get("daily_quotes", [])
            if not quotes:
                return None

            quotes.sort(key=lambda q: q.get("Date", ""))
            history = [
                {
                    "date": q["Date"],
                    "close": round(float(q.get("Close") or 0), 1),
                }
                for q in quotes[-limit:]
                if q.get("Date") and q.get("Close")
            ]
            self._jp_cache[cache_key] = history
            return history
        except Exception as e:
            logger.error(f"J-Quants history fetch error: code={code}, {e}")
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
