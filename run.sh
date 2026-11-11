#!/usr/bin/env bash
# Arranca MIYJO en http://localhost:8000  (modo demostración activo por defecto)
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
