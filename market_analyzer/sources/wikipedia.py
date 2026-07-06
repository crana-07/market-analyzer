"""Wikipedia REST + Action API access (no key required)."""

from __future__ import annotations

from typing import List, Dict, Optional

import requests

_HEADERS = {"User-Agent": "MarketAnalyzer/1.0 (public-domain research tool)"}
_REST = "https://en.wikipedia.org/api/rest_v1/page/summary/"
_ACTION = "https://en.wikipedia.org/w/api.php"
_TIMEOUT = 12


def search_titles(query: str, limit: int = 5) -> List[str]:
    """Return Wikipedia article titles matching the query."""
    try:
        r = requests.get(
            _ACTION,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": limit,
                "format": "json",
            },
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        hits = r.json().get("query", {}).get("search", [])
        return [h["title"] for h in hits]
    except Exception:
        return []


def summary(title: str) -> Optional[Dict]:
    """Return {title, extract, url} for a Wikipedia page, or None."""
    try:
        r = requests.get(_REST + requests.utils.quote(title), headers=_HEADERS, timeout=_TIMEOUT)
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("type") == "disambiguation":
            return None
        return {
            "title": data.get("title", title),
            "extract": data.get("extract", ""),
            "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
        }
    except Exception:
        return None


def best_summary(query: str) -> Optional[Dict]:
    """Search then fetch the summary of the top relevant article."""
    for title in search_titles(query, limit=3):
        s = summary(title)
        if s and s.get("extract"):
            return s
    return None
