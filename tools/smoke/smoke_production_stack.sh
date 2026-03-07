#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROJECT="${SMOKE_COMPOSE_PROJECT:-howlhouse_smoke_$(date +%s)_$$}"
KEEP_UP="${SMOKE_KEEP_UP:-0}"
TIMEOUT_S="${SMOKE_TIMEOUT_S:-300}"
POLL_INTERVAL_S="${SMOKE_POLL_INTERVAL_S:-2}"
SEED="${SMOKE_MATCH_SEED:-987654}"
DOMAIN="${HOWLHOUSE_DOMAIN:-localhost}"
PROXY_BASE="${SMOKE_PROXY_BASE:-https://127.0.0.1}"

export HOWLHOUSE_DOMAIN="${DOMAIN}"
export TRAEFIK_ACME_EMAIL="${TRAEFIK_ACME_EMAIL:-smoke@example.com}"
export TRAEFIK_METRICS_BASIC_AUTH="${TRAEFIK_METRICS_BASIC_AUTH:-metrics:\$\$apr1\$\$H6uskkkW\$\$IgXLP6ewTrSuBkTrqE8wj/}"
export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-/api}"
export HOWLHOUSE_AUTH_MODE="${HOWLHOUSE_AUTH_MODE:-open}"
export HOWLHOUSE_IDENTITY_ENABLED="${HOWLHOUSE_IDENTITY_ENABLED:-false}"
export HOWLHOUSE_DISTRIBUTION_ENABLED="${HOWLHOUSE_DISTRIBUTION_ENABLED:-false}"
export HOWLHOUSE_TRUST_PROXY_HEADERS="${HOWLHOUSE_TRUST_PROXY_HEADERS:-true}"
export HOWLHOUSE_TRUSTED_PROXY_HOPS="${HOWLHOUSE_TRUSTED_PROXY_HOPS:-1}"

COMPOSE=(
  docker compose
  -p "${PROJECT}"
  -f "${ROOT_DIR}/docker-compose.yml"
  -f "${ROOT_DIR}/docker-compose.prod.yml"
  -f "${ROOT_DIR}/docker-compose.storage.yml"
  -f "${ROOT_DIR}/docker-compose.workers.yml"
)

CURL_COMMON=(-k -sS -H "Host: ${DOMAIN}" --connect-timeout 5 --max-time 20)

cleanup() {
  local rc=$?
  set +e
  if [[ $rc -ne 0 ]]; then
    echo "[smoke] failed with code ${rc}; dumping compose status" >&2
    "${COMPOSE[@]}" ps >&2 || true
    "${COMPOSE[@]}" logs --tail 120 >&2 || true
  fi

  if [[ "${KEEP_UP}" == "1" ]]; then
    echo "[smoke] SMOKE_KEEP_UP=1; leaving stack running (project=${PROJECT})"
  else
    echo "[smoke] tearing down stack (project=${PROJECT})"
    "${COMPOSE[@]}" down --remove-orphans >/dev/null 2>&1 || true
  fi
  exit $rc
}
trap cleanup EXIT INT TERM

wait_for_200() {
  local url="$1"
  local label="$2"
  local deadline=$((SECONDS + TIMEOUT_S))
  while (( SECONDS < deadline )); do
    local code
    code=$(curl "${CURL_COMMON[@]}" -o /dev/null -w "%{http_code}" "${url}" || true)
    if [[ "${code}" == "200" ]]; then
      echo "[smoke] ${label} healthy (${url})"
      return 0
    fi
    sleep "${POLL_INTERVAL_S}"
  done
  echo "[smoke] timeout waiting for ${label} at ${url}" >&2
  return 1
}

api_url="${PROXY_BASE}/api"
frontend_url="${PROXY_BASE}/"

echo "[smoke] starting stack (project=${PROJECT})"
"${COMPOSE[@]}" up -d --build

wait_for_200 "${api_url}/healthz" "backend"
wait_for_200 "${frontend_url}" "frontend"

echo "[smoke] creating scripted match"
create_response=$(curl "${CURL_COMMON[@]}" -H "Content-Type: application/json" -X POST "${api_url}/matches" -d "{\"seed\":${SEED},\"agent_set\":\"scripted\"}")
match_id=$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["match_id"])' <<<"${create_response}")
echo "[smoke] created match_id=${match_id}"

echo "[smoke] queueing async run"
curl "${CURL_COMMON[@]}" -o /dev/null -w "" -H "Content-Type: application/json" -X POST "${api_url}/matches/${match_id}/run?sync=false"

echo "[smoke] polling for completion"
status=""
deadline=$((SECONDS + TIMEOUT_S))
while (( SECONDS < deadline )); do
  match_json=$(curl "${CURL_COMMON[@]}" "${api_url}/matches/${match_id}")
  status=$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read()).get("status",""))' <<<"${match_json}")
  if [[ "${status}" == "finished" ]]; then
    break
  fi
  if [[ "${status}" == "failed" ]]; then
    echo "[smoke] match failed: ${match_json}" >&2
    exit 1
  fi
  sleep "${POLL_INTERVAL_S}"
done

if [[ "${status}" != "finished" ]]; then
  echo "[smoke] match did not finish in ${TIMEOUT_S}s" >&2
  exit 1
fi

echo "[smoke] checking frontend viewer"
wait_for_200 "${frontend_url}matches/${match_id}" "match viewer"

echo "[smoke] fetching public event stream"
events_file="$(mktemp)"
curl "${CURL_COMMON[@]}" "${api_url}/matches/${match_id}/events?visibility=public" >"${events_file}"
python3 - <<'PY' "${events_file}"
import json
import sys

path = sys.argv[1]
events = []
with open(path, "r", encoding="utf-8") as fh:
    for raw_line in fh:
        line = raw_line.strip()
        if not line.startswith("data: "):
            continue
        events.append(json.loads(line[6:]))
if not events:
    raise SystemExit("empty event stream")
if not any(evt.get("type") == "match_ended" for evt in events):
    raise SystemExit("event stream missing match_ended")
print(f"[smoke] public event stream events={len(events)}")
PY
rm -f "${events_file}"

echo "[smoke] fetching replay"
replay_file="$(mktemp)"
curl "${CURL_COMMON[@]}" "${api_url}/matches/${match_id}/replay?visibility=all" >"${replay_file}"
python3 - <<'PY' "${replay_file}"
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as fh:
    events = [json.loads(line) for line in fh if line.strip()]
if not events:
    raise SystemExit("empty replay")
if not any(evt.get("type") == "match_ended" for evt in events):
    raise SystemExit("replay missing match_ended")
print(f"[smoke] replay events={len(events)}")
PY
rm -f "${replay_file}"

echo "[smoke] success: match_id=${match_id} status=${status}"
