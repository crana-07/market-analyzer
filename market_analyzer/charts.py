"""Plotly chart builders + PNG export helper for the PDF report."""

from __future__ import annotations

from typing import List, Optional

import plotly.graph_objects as go

from .models import Competitor, NewsItem, Report

# Brand-ish palette.
_PALETTE = ["#2563eb", "#16a34a", "#f59e0b", "#dc2626", "#7c3aed",
            "#0891b2", "#db2777", "#65a30d", "#ea580c", "#475569"]


def _empty(msg: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, x=0.5, y=0.5, xref="paper", yref="paper",
                       showarrow=False, font=dict(size=14, color="#64748b"))
    fig.update_layout(xaxis_visible=False, yaxis_visible=False,
                      margin=dict(l=20, r=20, t=40, b=20))
    return fig


_BASIS_TITLE = {
    "revenue": "Estimated Market Share (revenue proxy)",
    "valuation": "Estimated Share (by disclosed valuation)",
    "funding": "Estimated Share (by disclosed funding)",
    "estimate": "Estimated Market Share",
    "unknown": "Estimated Market Share",
    "none": "Estimated Market Share",
}


def market_share_donut(competitors: List[Competitor], basis: str = "revenue") -> go.Figure:
    rows = [(c.name, c.market_share) for c in competitors if c.market_share]
    if not rows:
        return _empty("Market-share data unavailable")
    labels = [r[0] for r in rows]
    values = [r[1] * 100 for r in rows]
    other = 100 - sum(values)
    if other > 0.5:
        labels.append("Others / long tail")
        values.append(other)
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.5,
                           marker=dict(colors=_PALETTE),
                           textinfo="label+percent", sort=True))
    fig.update_layout(title=_BASIS_TITLE.get(basis, _BASIS_TITLE["none"]),
                      margin=dict(l=20, r=20, t=50, b=20), showlegend=False)
    return fig


def funding_bar(competitors: List[Competitor]) -> go.Figure:
    """Funding / valuation chart for private-company (startup) markets."""
    fund = [(c.name, c.funding_total) for c in competitors if c.funding_total]
    val = [(c.name, c.valuation) for c in competitors if c.valuation]
    if not fund and not val:
        return _empty("No funding/valuation data found")
    fig = go.Figure()
    if fund:
        fund.sort(key=lambda r: r[1], reverse=True)
        fig.add_bar(name="Funding raised", x=[r[0] for r in fund],
                    y=[r[1] / 1e6 for r in fund], marker_color=_PALETTE[1])
    if val:
        val.sort(key=lambda r: r[1], reverse=True)
        fig.add_bar(name="Valuation", x=[r[0] for r in val],
                    y=[r[1] / 1e6 for r in val], marker_color=_PALETTE[4])
    fig.update_layout(title="Funding & Valuation by Player (press-reported, USD)",
                      yaxis_title="$ millions", barmode="group",
                      margin=dict(l=20, r=20, t=50, b=80))
    fig.update_xaxes(tickangle=-30)
    return fig


def revenue_bar(competitors: List[Competitor]) -> go.Figure:
    rows = [(c.name, c.revenue) for c in competitors if c.revenue]
    if not rows:
        return _empty("Revenue data unavailable")
    rows.sort(key=lambda r: r[1], reverse=True)
    fig = go.Figure(go.Bar(
        x=[r[1] / 1e9 for r in rows], y=[r[0] for r in rows],
        orientation="h", marker_color=_PALETTE[0],
        text=[f"${r[1]/1e9:.1f}B" for r in rows], textposition="auto"))
    fig.update_layout(title="Annual Revenue by Player (USD, TTM)",
                      xaxis_title="Revenue ($B)", yaxis=dict(autorange="reversed"),
                      margin=dict(l=20, r=20, t=50, b=40))
    return fig


def market_cap_bar(competitors: List[Competitor]) -> go.Figure:
    rows = [(c.name, c.market_cap) for c in competitors if c.market_cap]
    if not rows:
        return _empty("Market-cap data unavailable")
    rows.sort(key=lambda r: r[1], reverse=True)
    fig = go.Figure(go.Bar(
        x=[r[0] for r in rows], y=[r[1] / 1e9 for r in rows],
        marker_color=_PALETTE[4],
        text=[f"${r[1]/1e9:.0f}B" for r in rows], textposition="auto"))
    fig.update_layout(title="Market Capitalisation by Player (USD)",
                      yaxis_title="Market cap ($B)",
                      margin=dict(l=20, r=20, t=50, b=80))
    fig.update_xaxes(tickangle=-30)
    return fig


def sentiment_bar(news: List[NewsItem]) -> go.Figure:
    if not news:
        return _empty("No recent news found")
    pos = sum(1 for n in news if n.sentiment > 0.2)
    neg = sum(1 for n in news if n.sentiment < -0.2)
    neu = len(news) - pos - neg
    fig = go.Figure(go.Bar(
        x=["Positive", "Neutral", "Negative"], y=[pos, neu, neg],
        marker_color=["#16a34a", "#94a3b8", "#dc2626"],
        text=[pos, neu, neg], textposition="auto"))
    fig.update_layout(title="Recent News Sentiment (headline tone)",
                      yaxis_title="# headlines",
                      margin=dict(l=20, r=20, t=50, b=40))
    return fig


def all_figures(report: Report) -> dict:
    """Return a name->figure map of the charts relevant to this report."""
    figs = {}
    if any(c.market_share for c in report.competitors):
        figs["market_share"] = market_share_donut(report.competitors, report.market_size_basis)
    if any(c.revenue for c in report.competitors):
        figs["revenue"] = revenue_bar(report.competitors)
    if any(c.market_cap for c in report.competitors):
        figs["market_cap"] = market_cap_bar(report.competitors)
    if any(c.funding_total or c.valuation for c in report.competitors):
        figs["funding"] = funding_bar(report.competitors)
    if report.news:
        figs["sentiment"] = sentiment_bar(report.news)
    return figs


def fig_to_png(fig: go.Figure, width: int = 760, height: int = 420) -> Optional[bytes]:
    """Render a Plotly figure to PNG bytes via kaleido. None if unavailable."""
    try:
        return fig.to_image(format="png", width=width, height=height, scale=2)
    except Exception:
        return None
