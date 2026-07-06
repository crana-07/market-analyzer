"""Typed data structures shared across the research, analysis and report layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any


@dataclass
class Source:
    """A single public-domain reference used to compile the report."""

    title: str
    url: str
    provider: str = ""          # e.g. "Wikipedia", "Yahoo Finance", "DuckDuckGo"
    snippet: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "provider": self.provider,
            "snippet": self.snippet,
        }


@dataclass
class NewsItem:
    title: str
    url: str
    source: str = ""
    published: str = ""
    sentiment: float = 0.0      # -1.0 (negative) .. +1.0 (positive)


@dataclass
class Competitor:
    name: str
    ticker: Optional[str] = None
    description: str = ""
    is_public: bool = False                 # True if listed (has verifiable filings)
    market_cap: Optional[float] = None      # USD
    revenue: Optional[float] = None         # USD, trailing twelve months
    employees: Optional[int] = None
    funding_total: Optional[float] = None   # USD, press-reported cumulative funding
    valuation: Optional[float] = None       # USD, press-reported valuation
    market_share: Optional[float] = None    # 0..1, share on the chosen basis
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    source_url: str = ""

    @property
    def kind(self) -> str:
        return "Public" if self.is_public else "Private"


@dataclass
class SWOT:
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    opportunities: List[str] = field(default_factory=list)
    threats: List[str] = field(default_factory=list)


@dataclass
class ResearchData:
    """Raw, structured material gathered from public sources before synthesis."""

    query: str
    is_company: bool
    overview: str = ""
    competitors: List[Competitor] = field(default_factory=list)
    news: List[NewsItem] = field(default_factory=list)
    sources: List[Source] = field(default_factory=list)
    financials: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    warnings: List[str] = field(default_factory=list)


@dataclass
class Report:
    """The finished, synthesized market-analysis report."""

    query: str
    is_company: bool
    generated_at: datetime
    overview: str
    market_size_usd: Optional[float]
    market_size_note: str
    market_size_basis: str          # "revenue" | "valuation" | "funding" | "none"
    competitors: List[Competitor]
    swot: SWOT
    gaps: List[str]
    executive_summary: List[str]      # audience-segmented paragraphs
    news: List[NewsItem]
    sources: List[Source]
    warnings: List[str] = field(default_factory=list)
