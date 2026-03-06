#!/usr/bin/env bash
set -euo pipefail

FILE="${1:-}"
if [[ -z "$FILE" ]]; then
  echo "Usage: $0 <backup-file>" >&2
  exit 1
fi

if [[ ! -f "$FILE" ]]; then
  echo "File not found: $FILE" >&2
  exit 1
fi

case "$FILE" in
  *.sql.gz)
    gzip -t "$FILE"
    echo "OK: gzip SQL backup integrity passed"
    ;;
  *.tar.gz)
    tar -tzf "$FILE" >/dev/null
    echo "OK: tar artifact backup integrity passed"
    ;;
  *)
    echo "Unsupported backup type: $FILE" >&2
    exit 1
    ;;
esac
