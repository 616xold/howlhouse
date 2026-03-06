#!/usr/bin/env bash
set -euo pipefail

DUMP_FILE="${1:-}"
if [[ -z "$DUMP_FILE" ]]; then
  echo "Usage: $0 <dump.sql.gz> [database_url]" >&2
  exit 1
fi

if [[ ! -f "$DUMP_FILE" ]]; then
  echo "Dump file not found: $DUMP_FILE" >&2
  exit 1
fi

DB_URL="${2:-${HOWLHOUSE_DATABASE_URL:-${DATABASE_URL:-}}}"
if [[ -z "$DB_URL" ]]; then
  echo "Provide database URL as arg2 or set HOWLHOUSE_DATABASE_URL/DATABASE_URL." >&2
  exit 1
fi

gzip -dc "$DUMP_FILE" | psql "$DB_URL"
echo "Restored $DUMP_FILE"
