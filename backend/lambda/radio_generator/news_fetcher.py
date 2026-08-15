import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import feedparser
import requests

logger = logging.getLogger()

FINNHUB_BASE = "https://finnhub.io/api/v1"
MAX_FINNHUB_PER_SYMBOL = 5

# NewsAPI の代わりに RSS を使用: 無料・商用OK・レート制限なし
RSS_FEEDS = [
    # US / global market news
    {
        "url": "https://feeds.bloomberg.com/markets/news.rss",
        "lang": "en",
        "category": "us_market",
    },
    {
        "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "lang": "en",
        "category": "us_market",
    },
    {
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "lang": "en",
        "category": "global",
    },
    {
        "url": "https://www.cnbc.com/id/10000108/device/rss/rss.html",
        "lang": "en",
        "category": "us_market",
    },
    {
        "url": "https://www.cnbc.com/id/15839135/device/rss/rss.html",
        "lang": "en",
        "category": "us_market",
    },
    {
        "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "lang": "en",
        "category": "us_market",
    },
]

MAX_NEWS_HOURS = 36  # 直近36時間以内のニュースを使用(電車通勤等での閲覧を想定し少し広めに)
MAX_PER_FEED = 15
MAX_TOTAL = 80


class NewsFetcher:
    def __init__(self):
        self._finnhub_key = os.environ.get("FINNHUB_API_KEY", "")

    def get_stocks_news(self, symbols: set, from_date: str, to_date: str) -> dict:
        """Finnhub から複数銘柄のニュースを一括取得（銘柄コードをキーとする dict）"""
        if not self._finnhub_key or not symbols:
            return {}
        result = {}
        for i, symbol in enumerate(symbols):
            if i > 0:
                time.sleep(1.0)  # 60 req/min 制限
            news = self._fetch_finnhub_symbol(symbol, from_date, to_date)
            if news:
                result[symbol] = news
        logger.info(f"Finnhub ニュース取得完了: {len(result)}/{len(symbols)} 銘柄")
        return result

    def _fetch_finnhub_symbol(self, symbol: str, from_date: str, to_date: str) -> list:
        try:
            r = requests.get(
                f"{FINNHUB_BASE}/company-news",
                params={"symbol": symbol, "from": from_date, "to": to_date, "token": self._finnhub_key},
                timeout=10,
            )
            r.raise_for_status()
            items = r.json()
            if not isinstance(items, list):
                return []
            result = []
            for item in items[:MAX_FINNHUB_PER_SYMBOL]:
                title = item.get("headline", "")
                if not title:
                    continue
                ts = item.get("datetime", 0)
                pub = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else ""
                result.append({
                    "title": title,
                    "summary": item.get("summary", "")[:300],
                    "link": item.get("url", ""),
                    "published_at": pub,
                    "category": "stock_specific",
                    "source": item.get("source", "Finnhub"),
                })
            return result
        except Exception as e:
            logger.warning(f"Finnhub news fetch error: symbol={symbol}, {e}")
            return []

    def get_all_news(self) -> list:
        """全RSSフィードからニュースを収集"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_NEWS_HOURS)
        all_items = []

        for feed_config in RSS_FEEDS:
            try:
                items = self._parse_feed(feed_config["url"], cutoff, feed_config["category"])
                all_items.extend(items)
            except Exception as e:
                logger.warning(f"フィード取得失敗: {feed_config['url']}, {e}")

        # 最新順にソート
        all_items.sort(key=lambda x: x.get("published_at", ""), reverse=True)
        return all_items[:MAX_TOTAL]

    def _parse_feed(self, url: str, cutoff: datetime, category: str) -> list:
        feed = feedparser.parse(url)

        if feed.bozo and not feed.entries:
            logger.warning(f"RSS パース失敗: {url}")
            return []

        items = []
        for entry in feed.entries[:MAX_PER_FEED]:
            pub_date = self._parse_date(entry)
            if pub_date and pub_date < cutoff:
                continue

            items.append({
                "title": getattr(entry, "title", ""),
                "summary": self._clean_text(getattr(entry, "summary", ""), 300),
                "link": getattr(entry, "link", ""),
                "published_at": pub_date.isoformat() if pub_date else "",
                "category": category,
                "source": getattr(feed.feed, "title", url),
            })

        return items

    @staticmethod
    def _parse_date(entry) -> Optional[datetime]:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                t = entry.published_parsed
                return datetime(t[0], t[1], t[2], t[3], t[4], t[5], tzinfo=timezone.utc)
            except Exception:
                pass
        return None

    @staticmethod
    def _clean_text(text: str, max_len: int) -> str:
        """HTMLタグを除去して最大文字数で切り詰め"""
        import re
        text = re.sub(r"<[^>]+>", "", text)
        return text[:max_len].strip()
