#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${1:-./backups/postgres}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUTPUT_DIR"

if [[ -n "${HOWLHOUSE_DATABASE_URL:-}" ]]; then
  DB_URL="$HOWLHOUSE_DATABASE_URL"
elif [[ -n "${DATABASE_URL:-}" ]]; then
  DB_URL="$DATABASE_URL"
else
  echo "Set HOWLHOUSE_DATABASE_URL or DATABASE_URL for pg_dump." >&2
  exit 1
fi

OUT_FILE="$OUTPUT_DIR/howlhouse_${TIMESTAMP}.sql.gz"
pg_dump "$DB_URL" | gzip -c > "$OUT_FILE"
echo "Wrote $OUT_FILE"
