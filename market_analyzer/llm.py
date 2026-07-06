"""AI research engine — multi-provider (Anthropic / Google Gemini / Groq).

The active provider is auto-selected from whichever API key is present
(override with MARKET_ANALYZER_PROVIDER). All three produce the same two
passes:

  1. a streamed, per-section market analysis grounded in live public data
     - Anthropic: built-in web_search tool
     - Gemini:    built-in Google Search grounding
     - Groq:      grounded on results from the app's own public-source
                  gatherers (DuckDuckGo / Wikipedia / Google News), since
                  Groq models cannot browse on their own.
  2. a structured JSON extraction that drives the charts, tables and PDF.

No key present anywhere -> the app falls back to the keyless engine.py.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Callable, Optional, List, Dict, Any, Tuple

from .models import Report, Competitor, SWOT, Source
from . import analysis as A

# Default model per provider; override any of them with MARKET_ANALYZER_MODEL.
_MODELS = {
    "anthropic": "claude-opus-4-8",
    "gemini": "gemini-2.0-flash",
    "groq": "llama-3.3-70b-versatile",
}
_KEY_ENV = {
    "anthropic": ["ANTHROPIC_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "groq": ["GROQ_API_KEY"],
}


# --- key / provider detection ------------------------------------------------

def _secret(name: str) -> Optional[str]:
    v = os.environ.get(name)
    if v:
        return v
    try:
        import streamlit as st
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return None


def _key_for(provider: str) -> Optional[str]:
    for name in _KEY_ENV.get(provider, []):
        v = _secret(name)
        if v:
            return v
    return None


def provider() -> Optional[str]:
    """Return the active provider name, or None if no key is configured."""
    override = (os.environ.get("MARKET_ANALYZER_PROVIDER") or _secret("MARKET_ANALYZER_PROVIDER") or "").lower()
    if override in _MODELS and _key_for(override):
        return override
    for p in ("anthropic", "gemini", "groq"):
        if _key_for(p):
            return p
    return None


def available() -> bool:
    return provider() is not None


def model_for(p: str) -> str:
    return os.environ.get("MARKET_ANALYZER_MODEL") or _secret("MARKET_ANALYZER_MODEL") or _MODELS[p]


def active_label() -> str:
    p = provider()
    return f"{p} · {model_for(p)}" if p else "keyless"


# --- shared prompts ----------------------------------------------------------

_SECTIONS = """Write the report in clean markdown with EXACTLY these sections and headings:

## Executive Summary
Three short, distinct paragraphs, each labelled in bold:
**For a CEO entering the space:** ... **For a CEO operating in the space:** ...
**For an aspiring founder:** ... Each must give concrete, decision-useful advice.

## Market Overview
3–5 substantive paragraphs: what the market is, its size (a $ figure and year if
available), growth rate, key dynamics/trends, and structure.

## Competitor Analysis
A markdown table of the key players: Company | Public/Private | Revenue or Funding |
Valuation/Mkt Cap | Est. Share. Then a short Strengths / Weaknesses list per major player.

## SWOT Analysis
Strengths, Weaknesses, Opportunities, Threats — specific to the subject, as bullets.

## Market Gaps & Opportunities
4–6 concrete, evidence-based whitespace opportunities or unmet needs.

Be specific: name real competitors, give real numbers with units, attribute figures.
Handle private startups too (press-reported funding/valuation, marked as estimates).
If a figure is unknown, say so — never invent it. Start directly with the
"## Executive Summary" heading. No preamble."""

SYSTEM_SEARCH = ("You are a senior market & competitive intelligence analyst. Research the "
                 "subject using live web search across credible public sources (company sites, "
                 "news, filings, funding coverage, Wikipedia). Always search several angles "
                 "(the subject, its competitors, market size, funding, recent news) before "
                 "writing. Do not rely on memory for facts, numbers, or company lists.\n\n" + _SECTIONS)

SYSTEM_GROUNDED = ("You are a senior market & competitive intelligence analyst. Base every fact, "
                   "number and company name STRICTLY on the SEARCH RESULTS provided in the user "
                   "message. Do not use outside memory for specific figures; if the results don't "
                   "cover something, say it is unknown.\n\n" + _SECTIONS)

USER_SEARCH = ("Research and analyse: **{query}**\n\nIf this is a company, centre the analysis on "
               "it and its real competitors; if an industry/category, analyse the market and its "
               "leading players. Search the public web thoroughly first.")

USER_GROUNDED = ("Research and analyse: **{query}**\n\nUse ONLY these public search results as "
                 "your evidence:\n\n===== SEARCH RESULTS =====\n{context}\n===== END RESULTS =====")

EXTRACT_SYSTEM = ("You convert a market-analysis report into a single structured JSON object. "
                  "Extract only what the report supports. Use 0 for unknown numbers and \"\" for "
                  "unknown strings. Monetary values in absolute USD (e.g. 1500000000 for $1.5B). "
                  "market_share_pct is 0–100. Do not invent data. Output ONLY the JSON object.")

_JSON_KEYS = """Return a JSON object with exactly these keys:
{
 "is_company": bool,
 "market_overview": string,
 "market_size_usd": number,
 "market_size_text": string,
 "market_size_basis": "revenue"|"valuation"|"funding"|"estimate"|"unknown",
 "market_size_note": string,
 "competitors": [ {"name":string,"type":"Public"|"Private"|"Unknown","ticker":string,
   "market_cap_usd":number,"revenue_usd":number,"funding_usd":number,"valuation_usd":number,
   "market_share_pct":number,"description":string,"strengths":[string],"weaknesses":[string]} ],
 "swot": {"strengths":[string],"weaknesses":[string],"opportunities":[string],"threats":[string]},
 "gaps": [string],
 "executive_summary": {"headline":string,"entrant":string,"operator":string,"founder":string},
 "sources": [ {"title":string,"url":string} ]
}"""

# NOTE: never use str.format() on these — _JSON_KEYS and web snippets contain
# literal { } braces that .format() would misread as fields. Build by concatenation.

def _search_user(query: str) -> str:
    return USER_SEARCH.replace("{query}", query)


def _grounded_user(query: str, context: str) -> str:
    return USER_GROUNDED.replace("{query}", query).replace("{context}", context)


def _extract_user(query: str, analysis: str) -> str:
    return f"Subject: {query}\n\nAnalyst report:\n---\n{analysis}\n---\n\n" + _JSON_KEYS


# --- Anthropic strict JSON schema (used only for the Anthropic path) ---------

_COMP_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["name", "type", "ticker", "market_cap_usd", "revenue_usd", "funding_usd",
                 "valuation_usd", "market_share_pct", "description", "strengths", "weaknesses"],
    "properties": {
        "name": {"type": "string"}, "type": {"type": "string", "enum": ["Public", "Private", "Unknown"]},
        "ticker": {"type": "string"}, "market_cap_usd": {"type": "number"},
        "revenue_usd": {"type": "number"}, "funding_usd": {"type": "number"},
        "valuation_usd": {"type": "number"}, "market_share_pct": {"type": "number"},
        "description": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "weaknesses": {"type": "array", "items": {"type": "string"}},
    },
}
_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["is_company", "market_overview", "market_size_usd", "market_size_text",
                 "market_size_basis", "market_size_note", "competitors", "swot", "gaps",
                 "executive_summary", "sources"],
    "properties": {
        "is_company": {"type": "boolean"}, "market_overview": {"type": "string"},
        "market_size_usd": {"type": "number"}, "market_size_text": {"type": "string"},
        "market_size_basis": {"type": "string", "enum": ["revenue", "valuation", "funding", "estimate", "unknown"]},
        "market_size_note": {"type": "string"},
        "competitors": {"type": "array", "items": _COMP_SCHEMA},
        "swot": {"type": "object", "additionalProperties": False,
                 "required": ["strengths", "weaknesses", "opportunities", "threats"],
                 "properties": {k: {"type": "array", "items": {"type": "string"}}
                                for k in ("strengths", "weaknesses", "opportunities", "threats")}},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "executive_summary": {"type": "object", "additionalProperties": False,
                              "required": ["headline", "entrant", "operator", "founder"],
                              "properties": {k: {"type": "string"} for k in ("headline", "entrant", "operator", "founder")}},
        "sources": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                    "required": ["title", "url"], "properties": {"title": {"type": "string"}, "url": {"type": "string"}}}},
    },
}


# --- provider: Anthropic -----------------------------------------------------

def _anthropic(query, on_text, on_status, model) -> Tuple[str, Dict[str, Any]]:
    import anthropic
    client = anthropic.Anthropic(api_key=_key_for("anthropic"))
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}]
    messages = [{"role": "user", "content": _search_user(query)}]
    parts: List[str] = []
    for _ in range(4):
        if on_status:
            on_status("Searching public sources…")
        with client.messages.stream(model=model, max_tokens=8000, system=SYSTEM_SEARCH,
                                    tools=tools, messages=messages) as stream:
            for ev in stream:
                if ev.type == "content_block_start":
                    bt = getattr(ev.content_block, "type", "")
                    if bt == "server_tool_use" and on_status:
                        on_status("🔎 Searching the web…")
                    elif bt == "text" and on_status:
                        on_status("✍️ Writing the analysis…")
                elif ev.type == "content_block_delta" and getattr(ev.delta, "type", "") == "text_delta":
                    parts.append(ev.delta.text)
                    if on_text:
                        on_text(ev.delta.text)
            final = stream.get_final_message()
        if final.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": final.content})
            continue
        break
    md = "".join(parts)
    try:
        resp = client.messages.create(
            model=model, max_tokens=6000, system=EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": _extract_user(query, md)}],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}})
        text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "{}")
        return md, _loads(text)
    except Exception:
        return md, {}


# --- provider: Google Gemini -------------------------------------------------

def _gemini(query, on_text, on_status, model) -> Tuple[str, Dict[str, Any]]:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=_key_for("gemini"))
    if on_status:
        on_status("🔎 Searching the web (Google)…")
    search_cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM_SEARCH,
        tools=[types.Tool(google_search=types.GoogleSearch())])
    parts: List[str] = []
    started = False
    for chunk in client.models.generate_content_stream(
            model=model, contents=_search_user(query), config=search_cfg):
        if not started and on_status:
            on_status("✍️ Writing the analysis…")
            started = True
        t = getattr(chunk, "text", None)
        if t:
            parts.append(t)
            if on_text:
                on_text(t)
    md = "".join(parts)
    try:
        json_cfg = types.GenerateContentConfig(
            system_instruction=EXTRACT_SYSTEM, response_mime_type="application/json")
        resp = client.models.generate_content(
            model=model, contents=_extract_user(query, md), config=json_cfg)
        return md, _loads(resp.text)
    except Exception:
        return md, {}


# --- provider: Groq (grounded on the app's public-source gatherers) ----------

def _gather_context(query: str, on_status=None, char_limit: int = 5000) -> str:
    """Compact public-source context for grounding (kept small for free-tier TPM)."""
    from .sources import websearch, wikipedia, news
    if on_status:
        on_status("🔎 Gathering public sources…")
    chunks: List[str] = []
    w = wikipedia.best_summary(query)
    if w and w.get("extract"):
        chunks.append("WIKIPEDIA: " + w["extract"][:800])
    for r in websearch.text_search(f"{query} competitors market size funding", 8):
        chunks.append(f"- {r.get('title','')}: {(r.get('body','') or '')[:220]}")
    for n in news.headlines(query, 6):
        chunks.append(f"- NEWS: {n.get('title','')}")
    return "\n".join(c for c in chunks if c.strip())[:char_limit]


def _groq(query, on_text, on_status, model) -> Tuple[str, Dict[str, Any]]:
    from groq import Groq
    client = Groq(api_key=_key_for("groq"))
    context = _gather_context(query, on_status) or "(no results found)"
    if on_status:
        on_status("✍️ Writing the analysis…")
    parts: List[str] = []
    stream = client.chat.completions.create(
        model=model, max_tokens=3000, temperature=0.4, stream=True,
        messages=[{"role": "system", "content": SYSTEM_GROUNDED},
                  {"role": "user", "content": _grounded_user(query, context)}])
    for chunk in stream:
        d = chunk.choices[0].delta.content
        if d:
            parts.append(d)
            if on_text:
                on_text(d)
    md = "".join(parts)
    try:
        resp = client.chat.completions.create(
            model=model, max_tokens=2500, temperature=0, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": EXTRACT_SYSTEM},
                      {"role": "user", "content": _extract_user(query, md[:6000])}])
        return md, _loads(resp.choices[0].message.content)
    except Exception:
        return md, {}


# --- JSON -> Report mapping ---------------------------------------------------

def _loads(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text or "", re.DOTALL)
        return json.loads(m.group(0)) if m else {}


def _pos(v) -> Optional[float]:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _to_report(query: str, data: Dict[str, Any]) -> Report:
    comps: List[Competitor] = []
    for c in data.get("competitors", []) or []:
        pct = c.get("market_share_pct") or 0
        comps.append(Competitor(
            name=c.get("name", "?"), ticker=(c.get("ticker") or None),
            description=c.get("description", ""), is_public=(c.get("type") == "Public"),
            market_cap=_pos(c.get("market_cap_usd")), revenue=_pos(c.get("revenue_usd")),
            funding_total=_pos(c.get("funding_usd")), valuation=_pos(c.get("valuation_usd")),
            market_share=(pct / 100.0) if pct and pct > 0 else None,
            strengths=[s for s in (c.get("strengths") or []) if s],
            weaknesses=[w for w in (c.get("weaknesses") or []) if w]))

    size = _pos(data.get("market_size_usd"))
    basis = data.get("market_size_basis") or "estimate"
    note = data.get("market_size_note") or ""
    if data.get("market_size_text"):
        note = (note + "  " + data["market_size_text"]).strip()
    if not any(c.market_share for c in comps):
        s2, n2, b2 = A.compute_market_share(comps)
        if size is None:
            size, basis = s2, b2
        if not note:
            note = n2

    sw = data.get("swot", {}) or {}
    swot = SWOT(strengths=[x for x in sw.get("strengths", []) if x],
                weaknesses=[x for x in sw.get("weaknesses", []) if x],
                opportunities=[x for x in sw.get("opportunities", []) if x],
                threats=[x for x in sw.get("threats", []) if x])

    es = data.get("executive_summary", {}) or {}
    exec_summary = [s for s in [
        es.get("headline", ""),
        ("For a CEO entering the space: " + es["entrant"]) if es.get("entrant") else "",
        ("For a CEO operating in the space: " + es["operator"]) if es.get("operator") else "",
        ("For an aspiring founder: " + es["founder"]) if es.get("founder") else "",
    ] if s]

    sources = [Source(s.get("title", "") or s.get("url", ""), s.get("url", ""), "Web search")
               for s in (data.get("sources", []) or []) if s.get("url")]

    return Report(query=query, is_company=bool(data.get("is_company")),
                  generated_at=datetime.now(), overview=data.get("market_overview", ""),
                  market_size_usd=size, market_size_note=note, market_size_basis=basis,
                  competitors=comps, swot=swot, gaps=[g for g in data.get("gaps", []) if g],
                  executive_summary=exec_summary, news=[], sources=sources, warnings=[])


# --- top-level ---------------------------------------------------------------

_DISPATCH = {"anthropic": _anthropic, "gemini": _gemini, "groq": _groq}


def build_llm_report(query: str, on_text: Optional[Callable[[str], None]] = None,
                     on_status: Optional[Callable[[str], None]] = None):
    """Return (analysis_markdown, Report). Raises on hard API failure."""
    p = provider()
    if p is None:
        raise RuntimeError("No AI provider key configured.")
    md, data = _DISPATCH[p](query, on_text, on_status, model_for(p))
    if on_status:
        on_status("Structuring results & building charts…")
    try:
        report = _to_report(query, data or {})
        if not data:
            report.warnings.append(
                "The written analysis is ready, but structured charts/tables couldn't be "
                "extracted this run (model returned no valid JSON). Try regenerating.")
    except Exception:
        report = Report(query=query, is_company=False, generated_at=datetime.now(),
                        overview="", market_size_usd=None,
                        market_size_note="Structured extraction unavailable — see the written analysis.",
                        market_size_basis="unknown", competitors=[], swot=SWOT(), gaps=[],
                        executive_summary=[], news=[], sources=[],
                        warnings=["Charts unavailable: could not structure the AI analysis this run."])
    return md, report
