"""Synthesize a ResearchData object into report sections.

Everything here is rule-based and transparent — no LLM. It turns the
gathered facts (financials, sentiment, competitor set) into a market
overview, market-share estimate, SWOT, market gaps and an
audience-segmented executive summary.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .models import ResearchData, Competitor, SWOT
from . import textutil as T

# Each basis: (name, value-accessor, explanatory note). Listed in preference
# order, used only to break ties — the basis that can rank the MOST players wins,
# so a mostly-private market isn't distorted by one lone public company.
_BASES = [
    ("revenue", lambda c: c.revenue,
     "Estimated as combined trailing-twelve-month revenue of the publicly-listed players "
     "identified here — a serviceable-market proxy, not total addressable market. Private "
     "and long-tail players are excluded."),
    ("valuation", lambda c: c.valuation or c.market_cap,
     "Share is estimated from company valuations — press-reported for private firms and "
     "market capitalisation for listed ones. Valuations are estimates, not audited figures."),
    ("funding", lambda c: c.funding_total,
     "Share is estimated from combined press-reported total funding raised. This reflects "
     "capital deployed, not market size."),
]


def compute_market_share(competitors: List[Competitor]) -> Tuple[Optional[float], str, str]:
    """Assign market share on the basis with the widest player coverage.

    Returns (total, note, basis) where basis is 'revenue', 'valuation',
    'funding' or 'none'. Coverage-first (then preference order) so private /
    startup markets get a fair share breakdown instead of a single public
    player showing 100%.
    """
    best = None  # (coverage, -pref_index, name, accessor, note)
    for i, (name, acc, note) in enumerate(_BASES):
        coverage = sum(1 for c in competitors if acc(c) and acc(c) > 0)
        if coverage == 0:
            continue
        key = (coverage, -i)
        if best is None or key > best[0]:
            best = (key, name, acc, note)

    if best is None:
        for c in competitors:
            c.market_share = None
        return None, ("Market size could not be estimated — no public revenue, valuation or "
                      "funding figures were available for the identified players."), "none"

    _, name, acc, note = best
    total = sum(acc(c) for c in competitors if acc(c) and acc(c) > 0)
    for c in competitors:
        v = acc(c)
        c.market_share = (v / total) if (v and v > 0) else None
    return total, note, name


def concentration(competitors: List[Competitor]) -> Optional[float]:
    """Top-player share (a simple concentration signal)."""
    shares = [c.market_share for c in competitors if c.market_share]
    return max(shares) if shares else None


# --- SWOT --------------------------------------------------------------------

def build_swot(data: ResearchData) -> SWOT:
    swot = SWOT()
    sents = T.split_sentences(data.raw_text) + [n.title for n in data.news]

    subject = next((c for c in data.competitors if c.name.lower() == data.query.lower()), None)

    # Strengths / Weaknesses — prefer subject-specific when the query is a company.
    if subject:
        swot.strengths.extend(subject.strengths[:4])
        swot.weaknesses.extend(subject.weaknesses[:4])
    else:
        # Category view: strengths/weaknesses describe the market structure.
        avg_sent = (sum(n.sentiment for n in data.news) / len(data.news)) if data.news else 0
        if avg_sent > 0.1:
            swot.strengths.append("Generally positive market sentiment in recent coverage")
        elif avg_sent < -0.1:
            swot.weaknesses.append("Generally negative market sentiment in recent coverage")
        if len(data.competitors) >= 4:
            swot.strengths.append("Multiple established, investable players — a validated, liquid market")
        if len(data.competitors) <= 2:
            swot.weaknesses.append("Few publicly-validated players — thin or hard-to-benchmark market")

    # Opportunities — cue-word sentences + structural signals.
    for s in sents:
        if len(swot.opportunities) >= 5:
            break
        if T.contains_any(s, T.OPPORTUNITY_CUES) and T.sentiment(s) >= 0:
            swot.opportunities.append(T.truncate(s, 180))
    conc = concentration(data.competitors)
    if conc and conc > 0.4:
        swot.opportunities.append(
            f"Market is concentrated (top player ≈ {conc*100:.0f}% of tracked revenue) — "
            "room for a focused challenger or niche disruptor")
    elif conc and conc < 0.25:
        swot.opportunities.append(
            "Market is fragmented — opportunity for consolidation or a category-defining brand")

    # Threats — cue-word sentences + structural signals.
    for s in sents:
        if len(swot.threats) >= 5:
            break
        if T.contains_any(s, T.THREAT_CUES) or T.sentiment(s) < -0.2:
            swot.threats.append(T.truncate(s, 180))
    big = [c for c in data.competitors if c.market_cap and c.market_cap > 5e10]
    if big:
        swot.threats.append(
            f"{len(big)} well-capitalised incumbent(s) (>$50B) able to out-spend new entrants")

    # De-duplicate while preserving order, and guarantee non-empty buckets.
    for field in ("strengths", "weaknesses", "opportunities", "threats"):
        setattr(swot, field, _dedupe(getattr(swot, field)))
    if not swot.opportunities:
        swot.opportunities.append("Underserved sub-segments and geographies remain to be mapped (low public signal).")
    if not swot.threats:
        swot.threats.append("Competitive response and macro/regulatory shifts remain the primary risks.")
    if not swot.strengths:
        swot.strengths.append("Recognised, researchable market with identifiable players.")
    if not swot.weaknesses:
        swot.weaknesses.append("Limited public-data depth constrains precise benchmarking.")
    return swot


# --- market gaps -------------------------------------------------------------

GAP_CUES = ("lack of", "lack ", "underserved", "no clear", "gap in", "demand for",
            "unmet", "missing", "few options", "limited options", "frustrat",
            "complaint", "wish there", "hard to find", "too expensive", "lacking")


def find_gaps(data: ResearchData, swot: SWOT) -> List[str]:
    gaps: List[str] = []
    sents = T.split_sentences(data.raw_text) + [n.title for n in data.news]
    for s in sents:
        if len(gaps) >= 5:
            break
        if T.contains_any(s, GAP_CUES):
            gaps.append(T.truncate(s, 200))

    conc = concentration(data.competitors)
    if conc and conc > 0.5:
        gaps.append("Concentration leaves room for a differentiated, lower-cost or premium "
                    "alternative to the dominant incumbent.")
    revs = [c for c in data.competitors if c.revenue]
    if len(revs) >= 3 and conc and conc < 0.3:
        gaps.append("Fragmentation suggests a gap for a trusted, category-defining brand or an "
                    "aggregator/platform play.")

    # Structural gaps that are almost always worth testing.
    if data.news and (sum(n.sentiment for n in data.news) / len(data.news)) < 0:
        gaps.append("Negative sentiment in coverage hints at unmet customer satisfaction — a "
                    "service/experience gap to exploit.")

    gaps = _dedupe(gaps)
    if not gaps:
        gaps.append("No explicit gap surfaced in public text — validate via primary research "
                    "(customer interviews, review-mining) before committing.")
    return gaps[:6]


# --- executive summary (audience-segmented) ----------------------------------

_BASIS_LABEL = {
    "revenue": "in tracked annual revenue",
    "valuation": "in combined disclosed valuation",
    "funding": "in combined disclosed funding raised",
    "none": "(size not estimable from public data)",
}


def build_executive_summary(data: ResearchData, total_market: Optional[float],
                            swot: SWOT, gaps: List[str], basis: str = "revenue") -> List[str]:
    leaders = sorted(
        [c for c in data.competitors if c.market_share],
        key=lambda c: c.market_share or 0, reverse=True,
    )[:3]
    leader_str = ", ".join(f"{c.name} (~{c.market_share*100:.0f}%)" for c in leaders) or \
                 ", ".join(c.name for c in data.competitors[:3]) or "no clearly dominant player"
    basis_label = _BASIS_LABEL.get(basis, "")
    size_str = f"{_fmt_usd(total_market)} {basis_label}" if total_market else \
               "an undetermined (public data limited)"
    conc = concentration(data.competitors)
    structure = ("concentrated" if (conc and conc > 0.4)
                 else "fragmented" if (conc and conc < 0.25) else "moderately competitive")
    top_gap = gaps[0] if gaps else "unmet needs require primary validation"
    top_opp = swot.opportunities[0] if swot.opportunities else "niche differentiation"
    top_threat = swot.threats[0] if swot.threats else "incumbent competitive response"

    headline = (
        f"The {data.query} space is a {structure} market with an estimated "
        f"{size_str}. Leading identified players: {leader_str}."
    )

    ceo_enter = (
        "For a CEO looking to ENTER the space: "
        f"Entry is most attractive through the gap — {T.truncate(top_gap, 140)} "
        f"The clearest opening is: {T.truncate(top_opp, 140)} "
        f"Plan against the dominant risk — {T.truncate(top_threat, 140)} "
        "Differentiate sharply rather than competing head-on with capitalised incumbents."
    )

    ceo_operate = (
        "For a CEO currently OPERATING in the space: "
        "Benchmark your revenue-per-employee and capitalisation against the players in the "
        "competitor table; defend share where you are strong and reallocate toward the "
        f"identified opportunity ({T.truncate(top_opp, 120)}). Monitor the threats list and "
        "the news feed for early signals of competitive or regulatory shifts."
    )

    founder = (
        "For an aspiring FOUNDER exploring the space: "
        f"The market is real and investable ({size_str}), which is validating, "
        "but it is contested by established firms. Win by going narrow first — target the "
        f"specific gap ({T.truncate(top_gap, 120)}) with a focused wedge, prove retention, then "
        "expand. Use the SWOT threats as your pre-mortem checklist before raising capital."
    )

    return [headline, ceo_enter, ceo_operate, founder]


# --- helpers -----------------------------------------------------------------

def _dedupe(items: List[str]) -> List[str]:
    seen, out = set(), []
    for it in items:
        key = it.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(it)
    return out


def _fmt_usd(value: Optional[float]) -> str:
    # Kept for import compatibility; delegates to the shared formatter.
    return T.fmt_usd(value)
