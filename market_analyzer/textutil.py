"""Lightweight, dependency-free NLP helpers.

No LLM / API key is required. Sentiment and SWOT bucketing use small
hand-built lexicons of cue words. This is intentionally transparent and
fast; it is a heuristic, not a language model, and the report labels it
as auto-compiled from public sources.
"""

from __future__ import annotations

import re
from html import unescape
from typing import List

# --- cue-word lexicons -------------------------------------------------------

POSITIVE = {
    "strong", "growth", "growing", "leader", "leading", "profitable", "profit",
    "record", "surge", "surged", "expand", "expanding", "expansion", "innovative",
    "innovation", "popular", "dominant", "dominance", "success", "successful",
    "rising", "boost", "boosted", "gain", "gains", "win", "wins", "award",
    "efficient", "advantage", "robust", "resilient", "demand", "premium",
    "loyal", "trusted", "breakthrough", "upgrade", "outperform", "beat", "beats",
}

NEGATIVE = {
    "weak", "decline", "declining", "loss", "losses", "lawsuit", "fine", "fined",
    "recall", "layoff", "layoffs", "cut", "cuts", "drop", "dropped", "fall",
    "falling", "slump", "risk", "risks", "concern", "concerns", "debt",
    "struggle", "struggling", "miss", "missed", "scandal", "breach", "outage",
    "delay", "delayed", "shortage", "complaint", "complaints", "fraud",
    "investigation", "downturn", "underperform", "warning", "bankruptcy",
    "controversy", "criticism", "criticized", "shrink", "shrinking", "stalled",
}

# Words that hint each SWOT bucket (beyond raw sentiment).
OPPORTUNITY_CUES = {
    "emerging", "untapped", "potential", "expand", "new market", "partnership",
    "acquisition", "trend", "adoption", "demand", "underserved", "shift",
    "regulation", "subsidy", "incentive", "ai", "digital", "online", "global",
}
THREAT_CUES = {
    "competition", "competitor", "regulation", "regulatory", "tariff", "ban",
    "substitute", "saturation", "saturated", "recession", "inflation", "supply",
    "disruption", "entrant", "price war", "commoditization", "churn",
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]+")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    """Strip HTML tags / entities and collapse whitespace."""
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = unescape(text)
    return _WS_RE.sub(" ", text).strip()


def split_sentences(text: str) -> List[str]:
    text = clean_text(text)
    if not text:
        return []
    parts = _SENT_SPLIT.split(text)
    return [p.strip() for p in parts if len(p.strip()) > 15]


def tokens(text: str) -> List[str]:
    return [w.lower() for w in _WORD_RE.findall(text or "")]


def sentiment(text: str) -> float:
    """Return a normalized sentiment score in [-1, 1] using cue words."""
    toks = tokens(text)
    if not toks:
        return 0.0
    pos = sum(1 for t in toks if t in POSITIVE)
    neg = sum(1 for t in toks if t in NEGATIVE)
    total = pos + neg
    if total == 0:
        return 0.0
    return (pos - neg) / total


def contains_any(text: str, cues) -> bool:
    low = (text or "").lower()
    return any(cue in low for cue in cues)


def truncate(text: str, limit: int = 240) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


# --- money / funding extraction (for private companies) ----------------------

INR_TO_USD = 0.012  # approx; Indian coverage uses crore/lakh & ₹

_UNIT_MULT = {
    "trillion": 1e12, "billion": 1e9, "million": 1e6, "thousand": 1e3,
    "bn": 1e9, "mn": 1e6, "k": 1e3, "b": 1e9, "m": 1e6,
    "crore": 1e7, "cr": 1e7, "lakh": 1e5, "lakhs": 1e5,
}

_MONEY_RE = re.compile(
    r"(?P<cur>US\$|\$|₹|Rs\.?|INR)?\s?"
    r"(?P<num>\d+(?:\.\d+)?)\s?"
    r"(?P<unit>trillion|billion|million|thousand|crore|lakhs?|bn|mn|cr|[kbm])\b",
    re.IGNORECASE,
)

FUNDING_CUES = ("raised", "funding", "series", "seed", "round", "investment",
                "invested", "backed", "capital", "fundraise", "financing")
VALUATION_CUES = ("valued at", "valuation", "worth", "unicorn", "post-money", "pre-money")


def _amount_to_usd(num: float, unit: str, cur: str) -> float:
    val = num * _UNIT_MULT.get(unit.lower(), 1.0)
    cur = (cur or "").lower().strip(".")
    is_inr = cur in ("₹", "rs", "inr") or unit.lower() in ("crore", "cr", "lakh", "lakhs")
    if is_inr:
        val *= INR_TO_USD
    return val


def _extract_near(text: str, cues) -> "float | None":
    """Largest monetary amount that appears near any cue word."""
    text = clean_text(text)
    low = text.lower()
    best = None
    for m in _MONEY_RE.finditer(text):
        window = low[max(0, m.start() - 60): m.end() + 25]
        if any(cue in window for cue in cues):
            val = _amount_to_usd(float(m.group("num")), m.group("unit"), m.group("cur"))
            best = val if best is None else max(best, val)
    return best


def extract_funding(text: str) -> "float | None":
    return _extract_near(text, FUNDING_CUES)


def extract_valuation(text: str) -> "float | None":
    val = _extract_near(text, VALUATION_CUES)
    if val is None and "unicorn" in (text or "").lower():
        return 1e9  # "unicorn" implies a $1B+ valuation
    return val


# --- company detection & formatting ------------------------------------------

COMPANY_CUES = (
    "company", "startup", "start-up", "founded", "co-founded", "headquarter",
    "based in", "is an american", "is an indian", "is a technology", "platform",
    "firm", "provider", "corporation", " inc", " ltd", " llc", "maker of",
    "developer of", "operates", "offers", "app ", "saas", "e-commerce",
    "marketplace", "fintech", "brand",
)


def looks_like_company(text: str) -> bool:
    low = (text or "").lower()
    return any(cue in low for cue in COMPANY_CUES)


def fmt_usd(value) -> str:
    if not value:
        return "n/a"
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(value) >= div:
            return f"${value/div:.1f}{unit}"
    return f"${value:.0f}"
