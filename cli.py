"""Command-line entry point — generate a PDF report without the UI.

Usage:
    python cli.py "Tesla"
    python cli.py "electric vehicles" --out ev_report.pdf --max 8 \
        --competitors "BYD,Rivian,Lucid Motors"
"""

from __future__ import annotations

import argparse
import sys

from market_analyzer import build_report
from market_analyzer.report import generate_pdf


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Generate a market-analysis PDF from public sources.")
    p.add_argument("query", help="Company name or market category")
    p.add_argument("--out", "-o", default=None, help="Output PDF path")
    p.add_argument("--max", "-m", type=int, default=6, help="Max competitors to validate")
    p.add_argument("--competitors", "-c", default="", help="Comma-separated known competitors")
    args = p.parse_args(argv)

    manual = [c.strip() for c in args.competitors.split(",") if c.strip()]
    out = args.out or f"market_analysis_{args.query.replace(' ', '_')}.pdf"

    def progress(msg, frac):
        sys.stderr.write(f"\r[{int(frac*100):3d}%] {msg:<50}")
        sys.stderr.flush()

    print(f"Researching “{args.query}” …", file=sys.stderr)
    report = build_report(args.query, manual_competitors=manual,
                          max_competitors=args.max, progress=progress)
    sys.stderr.write("\n")

    with open(out, "wb") as f:
        f.write(generate_pdf(report))

    print(f"✓ Report written to {out}")
    print(f"  Players: {len(report.competitors)} · "
          f"Market size: {report.market_size_usd or 'n/a'} · "
          f"News: {len(report.news)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
