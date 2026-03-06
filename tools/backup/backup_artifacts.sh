#!/usr/bin/env bash
set -euo pipefail

REPLAYS_DIR="${1:-./replays}"
OUTPUT_DIR="${2:-./backups/artifacts}"
BLOB_DIR="${3:-./blob}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUTPUT_DIR"

if [[ ! -d "$REPLAYS_DIR" ]]; then
  echo "Replay directory not found: $REPLAYS_DIR" >&2
  exit 1
fi

OUT_FILE="$OUTPUT_DIR/howlhouse_artifacts_${TIMESTAMP}.tar.gz"
TAR_ARGS=(-C "$(dirname "$REPLAYS_DIR")" "$(basename "$REPLAYS_DIR")")
if [[ -d "$BLOB_DIR" ]]; then
  TAR_ARGS+=(-C "$(dirname "$BLOB_DIR")" "$(basename "$BLOB_DIR")")
fi
tar -czf "$OUT_FILE" "${TAR_ARGS[@]}"
echo "Wrote $OUT_FILE"
