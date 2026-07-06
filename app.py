"""Market & Competitive Analysis — Streamlit app.

Run locally:   streamlit run app.py
Deploy to web: push to Streamlit Community Cloud / any host (same file).

No API key required. Live research uses free public sources.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from market_analyzer import build_report
from market_analyzer import charts as C
from market_analyzer import llm
from market_analyzer.report import generate_pdf
from market_analyzer.analysis import _fmt_usd

st.set_page_config(page_title="Market Analyzer", page_icon="📊", layout="wide")

AI_ON = llm.available()

# --- Sidebar / input ---------------------------------------------------------
with st.sidebar:
    st.title("📊 Market Analyzer")
    if AI_ON:
        st.caption("Company **or** category → full market report. "
                   "🤖 **AI mode** — Claude researches the live web.")
    else:
        st.caption("Company **or** category → full market report. "
                   "Keyless mode — public sources (set `ANTHROPIC_API_KEY` for AI insights).")
    query = st.text_input("Company name or category",
                          placeholder="e.g. Tesla  •  electric vehicles  •  Sarvam AI")
    with st.expander("Advanced options"):
        max_comp = st.slider("Max competitors (keyless mode)", 3, 10, 6)
        manual = st.text_area("Add known competitors (keyless mode, one per line)",
                              placeholder="Optional — improves accuracy")
    run = st.button("🚀 Generate report", type="primary", use_container_width=True)
    if AI_ON:
        st.caption(f"AI engine: `{llm.active_label()}` + live web grounding.")
    else:
        st.caption("Sources: Wikipedia · Yahoo Finance · DuckDuckGo · Google News")

# --- Session cache -----------------------------------------------------------
if "report" not in st.session_state:
    st.session_state.report = None
if "analysis_md" not in st.session_state:
    st.session_state.analysis_md = None

if run and not query.strip():
    st.sidebar.error("Enter a company or category first.")
elif run and AI_ON:
    # AI path: stream the analyst's write-up live, then structure it for charts.
    st.session_state.analysis_md = None
    status = st.empty()
    live = st.empty()
    _buf = []

    def _on_status(msg):
        status.info(msg)

    def _on_text(chunk):
        _buf.append(chunk)
        live.markdown("".join(_buf) + " ▌")

    try:
        md, rep = llm.build_llm_report(query.strip(), on_text=_on_text, on_status=_on_status)
        st.session_state.report = rep
        st.session_state.analysis_md = md
    except Exception as e:
        st.session_state.report = None
        st.error(f"AI research failed: {e}")
    finally:
        status.empty()
        live.empty()
elif run:
    # Keyless path.
    st.session_state.analysis_md = None
    bar = st.progress(0.0, text="Starting research…")

    def _progress(msg, frac):
        bar.progress(min(max(frac, 0.0), 1.0), text=msg)

    manual_list = [m for m in (manual or "").splitlines() if m.strip()]
    try:
        st.session_state.report = build_report(
            query.strip(), manual_competitors=manual_list,
            max_competitors=max_comp, progress=_progress)
    except Exception as e:
        st.session_state.report = None
        st.error(f"Research failed: {e}")
    finally:
        bar.empty()

report = st.session_state.report

# --- Empty state -------------------------------------------------------------
if report is None:
    st.title("Market & Competitive Intelligence")
    st.markdown(
        "Enter a **company** (e.g. *Tesla*) or a **category** (e.g. *electric vehicles*) "
        "in the sidebar and generate a full report with:"
    )
    c1, c2, c3 = st.columns(3)
    c1.markdown("- 📈 **Market overview** & size\n- 🏢 **Competitor analysis**\n  (strengths/weaknesses)")
    c2.markdown("- 🧭 **SWOT** analysis\n- 🔍 **Market gaps**\n  & opportunities")
    c3.markdown("- 📝 **Executive summary**\n  (entrant · operator · founder)\n- 📄 **PDF export** with charts")
    if AI_ON:
        st.success("🤖 **AI mode is on.** Claude will research the live web (works for startups "
                   "too — try *Sarvam AI*) and stream the analysis here as it writes.")
    else:
        st.info("Keyless mode: data is auto-compiled from the public domain. Set `ANTHROPIC_API_KEY` "
                "for AI-researched insights. Estimates are for orientation, not investment advice.")
    st.stop()

# --- Header + PDF download ---------------------------------------------------
left, right = st.columns([3, 1])
with left:
    kind = "Company" if report.is_company else "Category / Market"
    st.title(f"{report.query.title()}")
    st.caption(f"{kind} analysis · generated {report.generated_at:%d %b %Y %H:%M} · "
               f"{len(report.competitors)} players · {len(report.news)} news items")
with right:
    st.write("")
    try:
        pdf_bytes = generate_pdf(report)
        st.download_button("📄 Export PDF", data=pdf_bytes,
                           file_name=f"market_analysis_{report.query.replace(' ', '_')}.pdf",
                           mime="application/pdf", type="primary", use_container_width=True)
    except Exception as e:
        st.warning(f"PDF export unavailable: {e}")

for w in report.warnings:
    st.warning(w)

figs = C.all_figures(report)

tabs = st.tabs(["📋 Summary", "📈 Market", "🏢 Competitors", "🧭 SWOT",
                "🔍 Gaps", "📰 News", "🔗 Sources"])

# --- Executive summary -------------------------------------------------------
with tabs[0]:
    st.subheader("Executive Summary")
    if st.session_state.analysis_md:
        # AI mode: show the full streamed narrative (all sections, readable).
        st.markdown(st.session_state.analysis_md)
    elif report.executive_summary:
        st.markdown(f"**{report.executive_summary[0]}**")
        for para in report.executive_summary[1:]:
            st.markdown(para)
    _size_label = {
        "revenue": "Tracked market size (revenue)",
        "valuation": "Combined valuation",
        "funding": "Combined funding raised",
        "estimate": "Market size (est.)",
        "unknown": "Market size",
        "none": "Market size",
    }.get(report.market_size_basis, "Market size")
    m1, m2, m3 = st.columns(3)
    m1.metric(_size_label, _fmt_usd(report.market_size_usd) if report.market_size_usd else "n/a")
    m2.metric("Players identified", len(report.competitors))
    leader = next((c for c in report.competitors if c.market_share), None)
    m3.metric("Top player share", f"{leader.market_share*100:.0f}%" if leader and leader.market_share else "n/a")

# --- Market overview ---------------------------------------------------------
with tabs[1]:
    st.subheader("Market Overview")
    if report.overview:
        st.write(report.overview)
    st.caption(report.market_size_note)
    if "market_share" in figs:
        st.plotly_chart(figs["market_share"], use_container_width=True)

# --- Competitors -------------------------------------------------------------
with tabs[2]:
    st.subheader("Competitor Analysis")
    table = [{
        "Company": c.name, "Type": c.kind,
        "Market cap": _fmt_usd(c.market_cap) if c.market_cap else "—",
        "Revenue": _fmt_usd(c.revenue) if c.revenue else "—",
        "Funding": _fmt_usd(c.funding_total) if c.funding_total else "—",
        "Valuation": _fmt_usd(c.valuation) if c.valuation else "—",
        "Share": f"{c.market_share*100:.1f}%" if c.market_share else "—",
    } for c in report.competitors]
    if table:
        st.dataframe(table, use_container_width=True, hide_index=True)
    if any(not c.is_public for c in report.competitors):
        st.caption("Private companies have no audited market cap/revenue; funding & valuation "
                   "are press-reported estimates.")
    cc1, cc2 = st.columns(2)
    if "revenue" in figs:
        cc1.plotly_chart(figs["revenue"], use_container_width=True)
    if "market_cap" in figs:
        cc2.plotly_chart(figs["market_cap"], use_container_width=True)
    if "funding" in figs:
        st.plotly_chart(figs["funding"], use_container_width=True)

    st.markdown("#### Strengths & Weaknesses")
    for c in report.competitors:
        with st.expander(f"**{c.name}**" + (f"  ·  {c.ticker}" if c.ticker else "")):
            if c.description:
                st.caption(c.description)
            a, b = st.columns(2)
            a.markdown("**✅ Strengths**\n\n" + "\n".join(f"- {s}" for s in c.strengths))
            b.markdown("**⚠️ Weaknesses**\n\n" + "\n".join(f"- {w}" for w in c.weaknesses))

# --- SWOT --------------------------------------------------------------------
with tabs[3]:
    st.subheader("SWOT Analysis")
    s = report.swot
    q1, q2 = st.columns(2)
    q1.success("**Strengths**\n\n" + "\n".join(f"- {i}" for i in s.strengths))
    q2.error("**Weaknesses**\n\n" + "\n".join(f"- {i}" for i in s.weaknesses))
    q3, q4 = st.columns(2)
    q3.info("**Opportunities**\n\n" + "\n".join(f"- {i}" for i in s.opportunities))
    q4.warning("**Threats**\n\n" + "\n".join(f"- {i}" for i in s.threats))

# --- Gaps --------------------------------------------------------------------
with tabs[4]:
    st.subheader("Identified Market Gaps & Opportunities")
    for g in report.gaps:
        st.markdown(f"- {g}")

# --- News --------------------------------------------------------------------
with tabs[5]:
    st.subheader("Recent Signals")
    if "sentiment" in figs:
        st.plotly_chart(figs["sentiment"], use_container_width=True)
    for n in report.news:
        tag = "🟢" if n.sentiment > 0.2 else "🔴" if n.sentiment < -0.2 else "⚪"
        title = f"[{n.title}]({n.url})" if n.url else n.title
        st.markdown(f"{tag} {title}  \n<small>{n.source} · {n.published}</small>",
                    unsafe_allow_html=True)

# --- Sources -----------------------------------------------------------------
with tabs[6]:
    st.subheader("Sources Consulted")
    st.caption("Public-domain references. Verify figures against primary filings before relying on them.")
    for src in report.sources:
        st.markdown(f"- [{src.title or src.url}]({src.url}) · _{src.provider}_")
