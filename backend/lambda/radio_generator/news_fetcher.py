import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import feedparser

logger = logging.getLogger()

# NewsAPI の代わりに RSS を使用: 無料・商用OK・レート制限なし
RSS_FEEDS = [
    # Japan economy news
    {
        "url": "https://www3.nhk.or.jp/rss/news/cat4.xml",
        "lang": "ja",
        "category": "jp_economy",
    },
    {
        "url": "https://news.yahoo.co.jp/rss/topics/business.xml",
        "lang": "ja",
        "category": "jp_market",
    },
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
]

MAX_NEWS_HOURS = 24  # 24時間以内のニュースのみ使用
MAX_PER_FEED = 10
MAX_TOTAL = 40


class NewsFetcher:
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
