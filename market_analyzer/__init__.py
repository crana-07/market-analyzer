"""Market & Competitive Intelligence engine.

Compiles a market-analysis report (overview, competitor analysis, SWOT,
market gaps and an executive summary) from free, public-domain sources that
require no API key: DuckDuckGo search, Wikipedia, Yahoo Finance and Google News.
"""

from .models import (
    Competitor,
    NewsItem,
    ResearchData,
    SWOT,
    Report,
    Source,
)
from .engine import build_report

__all__ = [
    "Competitor",
    "NewsItem",
    "ResearchData",
    "SWOT",
    "Report",
    "Source",
    "build_report",
]

__version__ = "1.0.0"
