#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../backend"
python -m venv .venv || true
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
uvicorn howlhouse.api.main:app --reload --port 8000
