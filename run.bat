@echo off
cd /d %~dp0
if not exist .venv python -m venv .venv
call .venv\Scripts\activate
pip install -q -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
