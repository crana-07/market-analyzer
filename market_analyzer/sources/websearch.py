"""DuckDuckGo web & news search via the keyless `ddgs` package."""

from __future__ import annotations

from typing import List, Dict

try:
    from ddgs import DDGS
except Exception:  # pragma: no cover - older package name fallback
    try:
        from duckduckgo_search import DDGS  # type: ignore
    except Exception:
        DDGS = None  # type: ignore


def available() -> bool:
    return DDGS is not None


def text_search(query: str, max_results: int = 12) -> List[Dict]:
    """Return a list of {title, href, body} web results. Empty on failure."""
    if DDGS is None:
        return []
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results)) or []
    except Exception:
        return []


def news_search(query: str, max_results: int = 12) -> List[Dict]:
    """Return a list of {title, url, body, date, source} news results."""
    if DDGS is None:
        return []
    try:
        with DDGS() as ddgs:
            return list(ddgs.news(query, max_results=max_results)) or []
    except Exception:
        return []
