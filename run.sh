#!/usr/bin/env bash
# One-command local start (macOS / Linux). Requires Python 3.10+.
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
if [ ! -d .venv ]; then
  echo "Creating virtual environment…"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo "Created .env from .env.example. Set LLM_API_KEY (or point LLM_BASE_URL at Ollama) and re-run."
  exit 1
fi

PORT=$(grep -E '^PORT=' .env | cut -d= -f2 | tr -d '"' || true)
PORT=${PORT:-8080}
echo "Enfactum AI Assistant → http://localhost:${PORT}"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
