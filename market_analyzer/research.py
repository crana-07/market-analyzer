"""Gather raw, structured material from public sources into a ResearchData.

Handles both publicly-listed companies (verified via Yahoo Finance) and
PRIVATE companies / startups (validated via Wikipedia or news presence,
with funding & valuation extracted from press coverage).
"""

from __future__ import annotations

import re
from typing import List, Dict, Set, Optional, Tuple

from .models import ResearchData, Competitor, NewsItem, Source
from .sources import websearch, wikipedia, finance, news
from . import textutil as T

# Sequences of capitalised words = candidate company names.
_PROPER = re.compile(r"\b([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,3})\b")

_STOP = {
    "The", "A", "An", "This", "That", "These", "Those", "Top", "Best", "Leading",
    "Major", "Other", "Its", "Their", "How", "Why", "What", "When", "Where",
    "Who", "Which", "New", "Global", "Market", "Markets", "Industry", "Report",
    "Company", "Companies", "News", "Read", "According", "However", "Meanwhile",
    "Today", "Here", "List", "Compare", "United", "States", "America", "Europe",
    "Asia", "China", "India", "World", "January", "February", "March", "April",
    "May", "June", "July", "August", "September", "October", "November",
    "December", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
    "Saturday", "Sunday", "Series", "Startup", "Startups", "Founder", "CEO",
}


def _extract_candidates(snippets: List[str], exclude: str) -> List[str]:
    counts: Dict[str, int] = {}
    exclude_low = exclude.lower()
    for text in snippets:
        for m in _PROPER.finditer(text or ""):
            phrase = m.group(1).strip(" .,&-")
            if not phrase:
                continue
            first = phrase.split()[0]
            if first in _STOP or len(phrase) < 3 or len(phrase) > 40:
                continue
            if phrase.lower() == exclude_low or exclude_low in phrase.lower():
                continue
            counts[phrase] = counts.get(phrase, 0) + 1
    return [name for name, _ in sorted(counts.items(), key=lambda kv: -kv[1])]


def _news_text(name: str, limit: int = 8) -> Tuple[str, List[Dict]]:
    items = news.headlines(name, limit)
    text = " ".join(T.clean_text(n.get("title", "")) for n in items)
    return text, items


def _validate_candidate(name: str) -> Tuple[str, Optional[Dict]]:
    """Classify a candidate as 'public', 'private' or 'none' with payload.

    - public : resolves to a stock ticker on Yahoo Finance (full financials).
    - private: has a company-like Wikipedia page, OR real news presence.
    - none   : could not be corroborated -> discarded as noise.
    """
    fin = finance.enrich(name)
    if fin:
        return "public", fin

    wiki = wikipedia.best_summary(name)
    if wiki and T.looks_like_company(wiki.get("extract", "")):
        return "private", {
            "name": wiki.get("title") or name,
            "description": wiki.get("extract", ""),
            "url": wiki.get("url", ""),
        }

    # News-corroboration fallback (catches startups without a Wikipedia page).
    text, items = _news_text(name, 6)
    if len(items) >= 3 and (T.looks_like_company(text) or T.extract_funding(text)):
        return "private", {"name": name, "description": "", "url": "", "news_text": text}

    return "none", None


def _classify_subject(query: str) -> Tuple[bool, bool, Optional[Dict], Optional[Dict]]:
    """Return (is_company, is_public, finance_payload, wiki_payload)."""
    fin = finance.enrich(query)
    wiki = wikipedia.best_summary(query)
    if fin:
        return True, True, fin, wiki
    if wiki and T.looks_like_company(wiki.get("extract", "")):
        return True, False, None, wiki
    # Even without a wiki page, a short 1-3 word query with company news is a company.
    if len(query.split()) <= 3:
        text, items = _news_text(query, 6)
        if len(items) >= 3 and T.looks_like_company(text):
            return True, False, None, {"extract": "", "url": "", "news_text": text}
    return False, False, None, wiki


def gather(query: str, manual_competitors: Optional[List[str]] = None,
           max_competitors: int = 6, progress=None) -> ResearchData:
    def step(msg: str, frac: float):
        if progress:
            progress(msg, frac)

    query = query.strip()
    data = ResearchData(query=query, is_company=False)

    # --- 1. Classify subject (public co / private co / category) ------------
    step("Identifying subject…", 0.05)
    is_company, is_public, subject_fin, subject_wiki = _classify_subject(query)
    data.is_company = is_company

    # --- 2. Overview --------------------------------------------------------
    step("Reading Wikipedia & background…", 0.15)
    overview = (subject_wiki or {}).get("extract", "") if subject_wiki else ""
    if not overview and subject_fin and subject_fin.get("summary"):
        overview = subject_fin["summary"]
    data.overview = overview
    if subject_wiki and subject_wiki.get("url"):
        data.sources.append(Source(subject_wiki.get("title", query), subject_wiki["url"],
                                   "Wikipedia", T.truncate(overview)))

    # --- 3. Web search to seed competitor discovery -------------------------
    step("Searching the public web…", 0.30)
    if is_company:
        seeds = (websearch.text_search(f"{query} competitors", 12)
                 + websearch.text_search(f"companies like {query} alternatives rivals", 10))
    else:
        seeds = (websearch.text_search(f"top companies in {query} market", 12)
                 + websearch.text_search(f"leading {query} startups companies", 10))

    snippets = [f"{r.get('title','')} {r.get('body','')}" for r in seeds]
    data.raw_text = " ".join(snippets)
    for r in seeds[:8]:
        if r.get("href"):
            data.sources.append(Source(T.clean_text(r.get("title", "")), r["href"],
                                       "DuckDuckGo", T.truncate(r.get("body", ""))))

    # --- 4. Build & validate the competitor set (public + private) ----------
    step("Identifying & validating competitors…", 0.45)
    candidates: List[str] = []
    if manual_competitors:
        candidates.extend([c.strip() for c in manual_competitors if c.strip()])
    candidates.extend(_extract_candidates(snippets, exclude=query))

    competitors: List[Competitor] = []
    seen_tickers: Set[str] = set()
    seen_names: Set[str] = set()

    # Include the subject itself when it is a company.
    if is_company:
        if subject_fin:
            competitors.append(_competitor_from_public(subject_fin))
            if subject_fin.get("symbol"):
                seen_tickers.add(subject_fin["symbol"].upper())
        else:
            competitors.append(_competitor_from_private(
                {"name": query, "description": overview, "url": (subject_wiki or {}).get("url", "")}))
        seen_names.add(query.lower())

    checked = 0
    cap = max_competitors + (1 if is_company else 0)
    for cand in candidates:
        if len(competitors) >= cap or checked >= 30:
            break
        if cand.lower() in seen_names or (query.lower() in cand.lower()):
            continue
        checked += 1
        step(f"Validating competitors… ({len(competitors)} found)",
             0.45 + 0.30 * min(checked / 30, 1.0))
        kind, payload = _validate_candidate(cand)
        if kind == "none":
            continue
        if kind == "public":
            sym = (payload.get("symbol") or "").upper()
            if sym and sym in seen_tickers:
                continue
            seen_tickers.add(sym)
            seen_names.add((payload.get("name") or cand).lower())
            competitors.append(_competitor_from_public(payload))
        else:
            nm = (payload.get("name") or cand).lower()
            if nm in seen_names:
                continue
            seen_names.add(nm)
            competitors.append(_competitor_from_private(payload))

    data.competitors = competitors

    # --- 5. News & sentiment (subject-level) --------------------------------
    step("Collecting recent news…", 0.80)
    raw_news = news.headlines(query, 12) or websearch.news_search(query, 12)
    for n in raw_news:
        title = T.clean_text(n.get("title", ""))
        if not title:
            continue
        data.news.append(NewsItem(title=title, url=n.get("url", ""),
                                  source=n.get("source", "") or "",
                                  published=n.get("published", "") or n.get("date", ""),
                                  sentiment=T.sentiment(title)))

    # --- 6. Per-competitor signals (financial or funding-based) -------------
    step("Synthesising competitor signals…", 0.90)
    for c in data.competitors:
        _attach_competitor_signals(c)

    data.financials = subject_fin or {}
    if not data.competitors:
        data.warnings.append(
            "No competitors could be corroborated from public data. Add known "
            "competitor names manually (sidebar → Advanced) to enrich the report.")
    private_n = sum(1 for c in data.competitors if not c.is_public)
    if private_n:
        data.warnings.append(
            f"{private_n} of {len(data.competitors)} players are private companies. Their "
            "funding/valuation figures are press-reported estimates, not audited filings.")
    if not data.overview:
        data.warnings.append("No encyclopedic overview was found for this subject.")

    step("Done.", 1.0)
    return data


# --- competitor constructors -------------------------------------------------

def _competitor_from_public(fin: Dict) -> Competitor:
    return Competitor(
        name=fin.get("name") or fin.get("symbol", "Unknown"),
        ticker=fin.get("symbol"),
        description=T.truncate(fin.get("summary", ""), 360),
        is_public=True,
        market_cap=fin.get("market_cap"),
        revenue=fin.get("revenue"),
        employees=fin.get("employees"),
        source_url=fin.get("website", ""),
    )


def _competitor_from_private(payload: Dict) -> Competitor:
    text = (payload.get("description", "") + " " + payload.get("news_text", "")).strip()
    return Competitor(
        name=payload.get("name", "Unknown"),
        ticker=None,
        description=T.truncate(payload.get("description", ""), 360),
        is_public=False,
        funding_total=T.extract_funding(text),
        valuation=T.extract_valuation(text),
        source_url=payload.get("url", ""),
    )


def _attach_competitor_signals(c: Competitor) -> None:
    if c.is_public:
        if c.market_cap and c.market_cap > 1e11:
            c.strengths.append("Very large market cap (>$100B) — strong scale & access to capital")
        elif c.market_cap and c.market_cap > 1e10:
            c.strengths.append("Large market cap (>$10B) — established market position")
        if c.revenue and c.market_cap and c.revenue > 0:
            ratio = c.market_cap / c.revenue
            if ratio > 12:
                c.strengths.append("High market-cap-to-revenue ratio — growth priced in by investors")
            elif ratio < 2:
                c.weaknesses.append("Low market-cap-to-revenue ratio — market cautious on growth/margins")
        if c.employees and c.revenue and c.employees > 0:
            rpe = c.revenue / c.employees
            if rpe > 800_000:
                c.strengths.append("High revenue per employee — operationally efficient")
            elif rpe < 150_000:
                c.weaknesses.append("Low revenue per employee — labour-intensive / lower margin")
    else:
        # Private: enrich funding/valuation from targeted news, derive signals.
        text, items = _news_text(f"{c.name} funding valuation raised", 6)
        if not items:
            text, items = _news_text(c.name, 6)
        c.funding_total = c.funding_total or T.extract_funding(text + " " + c.description)
        c.valuation = c.valuation or T.extract_valuation(text + " " + c.description)
        if c.valuation and c.valuation >= 1e9:
            c.strengths.append(f"Unicorn — ~{T.fmt_usd(c.valuation)} valuation (press-reported)")
        elif c.valuation:
            c.strengths.append(f"Valued ~{T.fmt_usd(c.valuation)} (press-reported)")
        if c.funding_total:
            c.strengths.append(f"Well-funded — ~{T.fmt_usd(c.funding_total)} raised (press-reported)")
        else:
            c.weaknesses.append("No disclosed funding found — capital position unclear from public data")
        c.weaknesses.append("Private — limited audited financials for benchmarking")

    # News sentiment (both types).
    _text, items = _news_text(c.name, 8)
    pos = [T.clean_text(n.get("title", "")) for n in items if T.sentiment(n.get("title", "")) > 0.2]
    neg = [T.clean_text(n.get("title", "")) for n in items if T.sentiment(n.get("title", "")) < -0.2]
    if pos:
        c.strengths.append("Positive recent press: " + T.truncate(pos[0], 120))
    if neg:
        c.weaknesses.append("Negative recent press: " + T.truncate(neg[0], 120))
    if not c.strengths:
        c.strengths.append("Operates as a recognised player in the space")
    if not c.weaknesses:
        c.weaknesses.append("No material public weakness signal detected")
