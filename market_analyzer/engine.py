"""Top-level orchestration: query -> Report."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from .models import Report
from . import research as R
from . import analysis as A


def build_report(query: str, manual_competitors: Optional[List[str]] = None,
                 max_competitors: int = 6, progress=None) -> Report:
    """Run the full pipeline and return a finished Report."""
    data = R.gather(query, manual_competitors=manual_competitors,
                    max_competitors=max_competitors, progress=progress)

    total_market, note, basis = A.compute_market_share(data.competitors)
    swot = A.build_swot(data)
    gaps = A.find_gaps(data, swot)
    exec_summary = A.build_executive_summary(data, total_market, swot, gaps, basis)

    # Order competitors by market share (then market cap) for presentation.
    data.competitors.sort(
        key=lambda c: (c.market_share or 0, c.market_cap or 0), reverse=True
    )

    return Report(
        query=data.query,
        is_company=data.is_company,
        generated_at=datetime.now(),
        overview=data.overview,
        market_size_usd=total_market,
        market_size_note=note,
        market_size_basis=basis,
        competitors=data.competitors,
        swot=swot,
        gaps=gaps,
        executive_summary=exec_summary,
        news=data.news,
        sources=data.sources,
        warnings=data.warnings,
    )
