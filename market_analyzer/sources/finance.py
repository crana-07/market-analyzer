"""Yahoo Finance access via yfinance (no key required).

Used to (a) resolve a company name to a stock ticker, which doubles as a
validity check for auto-discovered competitor names, and (b) pull financial
fundamentals (market cap, revenue, employees, business summary).
"""

from __future__ import annotations

from typing import Optional, Dict, List

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None  # type: ignore


def available() -> bool:
    return yf is not None


def resolve_ticker(name: str) -> Optional[Dict]:
    """Resolve a company name to {symbol, name} using Yahoo search.

    Returns None if no equity match is found. Acts as a real-company filter
    for noisy auto-extracted competitor candidates.
    """
    if yf is None or not name:
        return None
    try:
        res = yf.Search(name, max_results=3)
        quotes = getattr(res, "quotes", None) or []
        for q in quotes:
            if q.get("quoteType") == "EQUITY" and q.get("symbol"):
                return {
                    "symbol": q["symbol"],
                    "name": q.get("shortname") or q.get("longname") or name,
                }
    except Exception:
        return None
    return None


def fundamentals(ticker: str) -> Dict:
    """Return a dict of financial fundamentals for a ticker. Empty on failure."""
    if yf is None or not ticker:
        return {}
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        return {}
    return {
        "name": info.get("shortName") or info.get("longName"),
        "market_cap": info.get("marketCap"),
        "revenue": info.get("totalRevenue"),
        "employees": info.get("fullTimeEmployees"),
        "summary": info.get("longBusinessSummary", ""),
        "industry": info.get("industry", ""),
        "sector": info.get("sector", ""),
        "website": info.get("website", ""),
    }


def enrich(name: str) -> Optional[Dict]:
    """Resolve `name` to a ticker and pull its fundamentals in one call."""
    hit = resolve_ticker(name)
    if not hit:
        return None
    f = fundamentals(hit["symbol"])
    if not f:
        return None
    f["symbol"] = hit["symbol"]
    f["name"] = f.get("name") or hit["name"]
    return f
