"""Render a Report to a polished, multi-section PDF (returns bytes)."""

from __future__ import annotations

import io
from typing import List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    PageBreak, HRFlowable,
)

from .models import Report, Competitor
from . import charts as C
from .analysis import _fmt_usd

PRIMARY = colors.HexColor("#1e3a8a")
ACCENT = colors.HexColor("#2563eb")
LIGHT = colors.HexColor("#eff6ff")
GREY = colors.HexColor("#475569")


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("H1b", parent=ss["Heading1"], textColor=PRIMARY, spaceAfter=10))
    ss.add(ParagraphStyle("H2b", parent=ss["Heading2"], textColor=ACCENT, spaceBefore=12, spaceAfter=6))
    ss.add(ParagraphStyle("Body2", parent=ss["BodyText"], fontSize=9.5, leading=14))
    ss.add(ParagraphStyle("Small", parent=ss["BodyText"], fontSize=8, textColor=GREY, leading=11))
    ss.add(ParagraphStyle("TitleBig", parent=ss["Title"], fontSize=26, textColor=PRIMARY, leading=30))
    ss.add(ParagraphStyle("Cell", parent=ss["BodyText"], fontSize=8.5, leading=11))
    ss.add(ParagraphStyle("CellH", parent=ss["BodyText"], fontSize=9, leading=11,
                          textColor=colors.white, fontName="Helvetica-Bold"))
    return ss


def _chart_image(fig, width_cm=16.5, height_cm=9.0) -> Optional[Image]:
    png = C.fig_to_png(fig)
    if not png:
        return None
    return Image(io.BytesIO(png), width=width_cm * cm, height=height_cm * cm)


def _hr():
    return HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#cbd5e1"),
                      spaceBefore=6, spaceAfter=8)


def generate_pdf(report: Report) -> bytes:
    ss = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                            leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                            title=f"Market Analysis — {report.query}")
    figs = C.all_figures(report)
    story: List = []

    # --- Cover -------------------------------------------------------------
    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph("Market &amp; Competitive Analysis", ss["TitleBig"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(report.query.title(), ParagraphStyle(
        "Sub", parent=ss["Title"], fontSize=16, textColor=GREY)))
    story.append(Spacer(1, 0.4 * cm))
    kind = "Company analysis" if report.is_company else "Category / market analysis"
    story.append(Paragraph(
        f"{kind} &nbsp;•&nbsp; Generated {report.generated_at:%d %b %Y, %H:%M} &nbsp;•&nbsp; "
        f"Compiled from public-domain sources", ss["Small"]))
    story.append(_hr())
    story.append(Paragraph(
        "Auto-compiled from public sources (Wikipedia, Yahoo Finance, web &amp; news search) "
        "using rule-based synthesis. Figures are best-effort estimates for orientation, not "
        "investment advice.", ss["Small"]))
    story.append(Spacer(1, 0.5 * cm))

    # --- Executive summary -------------------------------------------------
    story.append(Paragraph("Executive Summary", ss["H1b"]))
    for para in report.executive_summary:
        story.append(Paragraph(para, ss["Body2"]))
        story.append(Spacer(1, 0.15 * cm))

    # --- Market overview ---------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("1. Market Overview", ss["H1b"]))
    if report.overview:
        story.append(Paragraph(report.overview, ss["Body2"]))
    size = _fmt_usd(report.market_size_usd) if report.market_size_usd else "Not estimable"
    story.append(Spacer(1, 0.2 * cm))
    story.append(_kv_table([
        ("Estimated tracked market size", size),
        ("Players identified", str(len(report.competitors))),
        ("Recent news items analysed", str(len(report.news))),
    ], ss))
    story.append(Paragraph(report.market_size_note, ss["Small"]))
    if "market_share" in figs:
        img = _chart_image(figs["market_share"])
        if img:
            story.append(Spacer(1, 0.3 * cm))
            story.append(img)

    # --- Competitor analysis ----------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("2. Competitor Analysis", ss["H1b"]))
    if any(not c.is_public for c in report.competitors):
        story.append(Spacer(1, 0.1 * cm))
        story.append(Paragraph(
            "Note: Private companies have no audited market cap/revenue; their funding &amp; "
            "valuation are press-reported estimates.", ss["Small"]))
    story.append(_competitor_table(report.competitors, ss))
    for key in ("revenue", "market_cap", "funding"):
        if key in figs:
            img = _chart_image(figs[key])
            if img:
                story.append(Spacer(1, 0.3 * cm))
                story.append(img)

    story.append(Paragraph("Strengths &amp; Weaknesses by Player", ss["H2b"]))
    for c in report.competitors:
        story.append(Paragraph(f"<b>{c.name}</b>"
                               + (f" ({c.ticker})" if c.ticker else ""), ss["Body2"]))
        sw = [
            [Paragraph("<b>Strengths</b>", ss["Cell"]), Paragraph("<b>Weaknesses</b>", ss["Cell"])],
            [Paragraph("<br/>".join("• " + s for s in c.strengths) or "—", ss["Cell"]),
             Paragraph("<br/>".join("• " + w for w in c.weaknesses) or "—", ss["Cell"])],
        ]
        t = Table(sw, colWidths=[8.3 * cm, 8.3 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#dcfce7")),
            ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#fee2e2")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.25 * cm))

    # --- SWOT --------------------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("3. SWOT Analysis", ss["H1b"]))
    story.append(_swot_grid(report, ss))

    # --- Market gaps -------------------------------------------------------
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("4. Identified Market Gaps &amp; Opportunities", ss["H1b"]))
    for g in report.gaps:
        story.append(Paragraph("• " + g, ss["Body2"]))
        story.append(Spacer(1, 0.08 * cm))

    # --- News --------------------------------------------------------------
    if report.news:
        story.append(PageBreak())
        story.append(Paragraph("5. Recent Signals (News)", ss["H1b"]))
        if "sentiment" in figs:
            img = _chart_image(figs["sentiment"], height_cm=7.5)
            if img:
                story.append(img)
                story.append(Spacer(1, 0.2 * cm))
        for n in report.news[:12]:
            tag = "▲" if n.sentiment > 0.2 else "▼" if n.sentiment < -0.2 else "•"
            story.append(Paragraph(f"{tag} {n.title} <font color='#64748b'>"
                                   f"({n.source or 'news'})</font>", ss["Small"]))

    # --- Sources -----------------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("Sources Consulted", ss["H1b"]))
    story.append(Paragraph("Compiled from the public domain. Verify figures against primary "
                           "filings before relying on them.", ss["Small"]))
    story.append(Spacer(1, 0.2 * cm))
    for s in report.sources[:25]:
        link = f'<a href="{s.url}" color="#2563eb">{s.title or s.url}</a>'
        story.append(Paragraph(f"• {link} <font color='#94a3b8'>[{s.provider}]</font>", ss["Small"]))
    if report.warnings:
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph("Notes &amp; limitations", ss["H2b"]))
        for w in report.warnings:
            story.append(Paragraph("• " + w, ss["Small"]))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    buf.seek(0)
    return buf.read()


# --- table builders ----------------------------------------------------------

def _kv_table(rows, ss):
    data = [[Paragraph(f"<b>{k}</b>", ss["Cell"]), Paragraph(str(v), ss["Cell"])] for k, v in rows]
    t = Table(data, colWidths=[7 * cm, 9.6 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _fmt(v, money=False):
    if v is None:
        return "—"
    if money:
        return _fmt_usd(v)
    if isinstance(v, float):
        return f"{v*100:.1f}%"
    return f"{v:,}"


def _competitor_table(competitors: List[Competitor], ss):
    header = ["Company", "Type", "Mkt Cap", "Revenue", "Funding", "Valuation", "Share"]
    data = [[Paragraph(h, ss["CellH"]) for h in header]]
    for c in competitors:
        data.append([
            Paragraph(c.name, ss["Cell"]),
            Paragraph(c.kind, ss["Cell"]),
            Paragraph(_fmt(c.market_cap, money=True), ss["Cell"]),
            Paragraph(_fmt(c.revenue, money=True), ss["Cell"]),
            Paragraph(_fmt(c.funding_total, money=True), ss["Cell"]),
            Paragraph(_fmt(c.valuation, money=True), ss["Cell"]),
            Paragraph(_fmt(c.market_share), ss["Cell"]),
        ])
    t = Table(data, colWidths=[4.0 * cm, 1.6 * cm, 2.3 * cm, 2.3 * cm, 2.3 * cm, 2.3 * cm, 1.8 * cm],
              repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _swot_grid(report: Report, ss):
    s = report.swot

    def cell(title, items, bg):
        body = "<br/>".join("• " + i for i in items) or "—"
        return [Paragraph(f"<b>{title}</b>", ss["Cell"]), Paragraph(body, ss["Cell"])]

    data = [
        [Paragraph("<b>STRENGTHS</b>", ss["Cell"]), Paragraph("<b>WEAKNESSES</b>", ss["Cell"])],
        [Paragraph("<br/>".join("• " + i for i in s.strengths) or "—", ss["Cell"]),
         Paragraph("<br/>".join("• " + i for i in s.weaknesses) or "—", ss["Cell"])],
        [Paragraph("<b>OPPORTUNITIES</b>", ss["Cell"]), Paragraph("<b>THREATS</b>", ss["Cell"])],
        [Paragraph("<br/>".join("• " + i for i in s.opportunities) or "—", ss["Cell"]),
         Paragraph("<br/>".join("• " + i for i in s.threats) or "—", ss["Cell"])],
    ]
    t = Table(data, colWidths=[8.3 * cm, 8.3 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#bbf7d0")),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#fecaca")),
        ("BACKGROUND", (0, 2), (0, 2), colors.HexColor("#bfdbfe")),
        ("BACKGROUND", (1, 2), (1, 2), colors.HexColor("#fed7aa")),
        ("BACKGROUND", (0, 1), (0, 1), colors.HexColor("#f0fdf4")),
        ("BACKGROUND", (1, 1), (1, 1), colors.HexColor("#fef2f2")),
        ("BACKGROUND", (0, 3), (0, 3), colors.HexColor("#eff6ff")),
        ("BACKGROUND", (1, 3), (1, 3), colors.HexColor("#fff7ed")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(1.8 * cm, 1.0 * cm,
                      "Market Analyzer — auto-compiled from public-domain sources. Not investment advice.")
    canvas.drawRightString(A4[0] - 1.8 * cm, 1.0 * cm, f"Page {doc.page}")
    canvas.restoreState()
