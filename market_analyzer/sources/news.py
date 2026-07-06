"""Google News RSS access (no key required)."""

from __future__ import annotations

from typing import List, Dict
from urllib.parse import quote_plus

import feedparser

_RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def headlines(query: str, limit: int = 12) -> List[Dict]:
    """Return recent news {title, url, source, published} for a query."""
    url = _RSS.format(q=quote_plus(query))
    try:
        feed = feedparser.parse(url)
    except Exception:
        return []
    items = []
    for entry in feed.entries[:limit]:
        items.append(
            {
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "source": entry.get("source", {}).get("title", "")
                if isinstance(entry.get("source"), dict)
                else getattr(entry.get("source", None), "title", ""),
                "published": entry.get("published", ""),
            }
        )
    return items
