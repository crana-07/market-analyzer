#!/usr/bin/env bash
# Local launcher (macOS / Linux). Creates a venv, installs deps, starts the web UI.
set -e
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment…"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "Installing dependencies (first run only)…"
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "Launching Market Analyzer at http://localhost:8501 …"
exec streamlit run app.py
