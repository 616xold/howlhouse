#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"

PG_URL="${HOWLHOUSE_PG_TEST_URL:-}"
if [[ -z "${PG_URL}" ]]; then
  echo "HOWLHOUSE_PG_TEST_URL is required" >&2
  exit 1
fi

echo "[postgres-tests] using HOWLHOUSE_PG_TEST_URL=${PG_URL}"
cd "${BACKEND_DIR}"
pytest -q tests/test_m10_postgres.py tests/test_m11_postgres_queue.py
