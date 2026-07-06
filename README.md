# 📊 Market Analyzer

Type a **company name** *or* a **market category** and get a full market & competitive
analysis report — **market overview & size, competitor analysis (with strengths/weaknesses),
SWOT, market gaps, and an audience-segmented executive summary** — complete with **charts**
and a **one-click PDF export**.

It runs as a **web app** and a **local app** from the *same* codebase (Streamlit), plus a
headless **CLI**. **No API key required** — all intelligence is compiled live from the
public domain.

---

## What it produces

| Section | Contents |
|---|---|
| **Market overview** | Encyclopedic summary + estimated tracked market size, with a market-share donut chart |
| **Competitor analysis** | Validated player table (market cap, revenue, share, employees) + per-player strengths & weaknesses + revenue / market-cap bar charts |
| **SWOT** | Strengths / Weaknesses / Opportunities / Threats, synthesized from financials + news |
| **Market gaps** | Data- and text-driven unmet-need / whitespace opportunities |
| **Executive summary** | Tailored for a CEO **entering** the space, a CEO **operating** in it, and an **aspiring founder** |
| **News & sources** | Recent headlines with sentiment + every public source consulted |
| **PDF export** | Polished multi-page PDF with all tables and charts embedded |

## Data sources (all free, keyless, public-domain)

- **Wikipedia** REST/Action API — overviews & background
- **Yahoo Finance** (`yfinance`) — financials + ticker validation of competitors
- **DuckDuckGo** (`ddgs`) — web & news search for competitor discovery and context
- **Google News RSS** — recent headlines & sentiment signal

> The report is **auto-compiled and rule-based** (no LLM). Figures are best-effort estimates
> for orientation — **not investment advice**. Verify against primary filings before relying on them.

---

## Quick start

### Web app / local app (Streamlit)

macOS / Linux:
```bash
cd market-analyzer
./run.sh
```
Windows:
```bat
cd market-analyzer
run.bat
```
Then open <http://localhost:8501>. (The launcher creates a virtualenv and installs deps on first run.)

Manual setup, if you prefer:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

### CLI (headless PDF)
```bash
python cli.py "Tesla"
python cli.py "electric vehicles" --max 8 --competitors "BYD,Rivian,Lucid Motors" -o ev.pdf
```

### Deploy to the web
Push this folder to GitHub and point **[Streamlit Community Cloud](https://streamlit.io/cloud)**
(or any host that runs `streamlit run app.py`) at `app.py`. No secrets/keys needed.

---

## Usage tips

- **Company query** (e.g. `Tesla`) → analysis is centred on that firm and its rivals.
- **Category query** (e.g. `electric vehicles`, `cloud storage`) → analysis describes the market.
- Auto-discovered competitors are **validated against Yahoo Finance**, so private companies may
  be missed — add them under **Advanced → known competitors** to enrich the report.
- Accuracy depends on what is public; thinly-covered or mostly-private markets yield lighter reports
  (the app flags this with a warning).

## Project layout
```
market-analyzer/
├── app.py                  # Streamlit web/local UI + PDF download
├── cli.py                  # Headless CLI -> PDF
├── requirements.txt
├── run.sh / run.bat        # One-command local launchers
└── market_analyzer/
    ├── engine.py           # query -> Report pipeline
    ├── research.py         # gather & cross-validate public data
    ├── analysis.py         # market share, SWOT, gaps, exec summary
    ├── charts.py           # Plotly charts + PNG export for PDF
    ├── report.py           # ReportLab PDF generation
    ├── textutil.py         # keyless sentiment / NLP helpers
    ├── models.py           # typed data structures
    └── sources/            # wikipedia, finance, websearch, news connectors
```

## Notes & limitations
- Market size is a **serviceable-market proxy** (sum of tracked public-player revenue), not TAM.
- Market share is **revenue-based** among identified listed players; private/long-tail excluded.
- Sentiment is a transparent **lexicon heuristic**, not a language model.
- Live sources may rate-limit or change; the app degrades gracefully and reports what it found.
