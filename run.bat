@echo off
REM Local launcher (Windows). Creates a venv, installs deps, starts the web UI.
cd /d "%~dp0"

if not exist ".venv" (
  echo Creating virtual environment...
  python -m venv .venv
)
call .venv\Scripts\activate.bat

echo Installing dependencies (first run only)...
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt

echo Launching Market Analyzer at http://localhost:8501 ...
streamlit run app.py
