#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

: "${TMPDIR:=${ROOT_DIR}/.tmp}"
: "${HOWLHOUSE_SANDBOX_DOCKER_IMAGE:=python:3.11.11-slim-bookworm}"
: "${HOWLHOUSE_SANDBOX_CPU_LIMIT:=0.5}"
: "${HOWLHOUSE_SANDBOX_MEMORY_LIMIT:=256m}"
: "${HOWLHOUSE_SANDBOX_PIDS_LIMIT:=128}"

mkdir -p "${TMPDIR}"
AGENT_DIR="$(mktemp -d "${TMPDIR%/}/howlhouse-docker-agent.XXXXXX")"
trap 'rm -rf "${AGENT_DIR}"' EXIT

install -d -m 755 "${AGENT_DIR}"
cat > "${AGENT_DIR}/helper.py" <<'PY'
def build_message() -> str:
    return "docker sandbox import ok"
PY

cat > "${AGENT_DIR}/agent.py" <<'PY'
import helper


def act(observation):
    return {"confessional": helper.build_message()}
PY

chmod 755 "${AGENT_DIR}"
chmod 644 "${AGENT_DIR}/helper.py" "${AGENT_DIR}/agent.py"

echo "Docker version:"
docker version
echo

echo "Docker info:"
docker info
echo

echo "Pulling sandbox image: ${HOWLHOUSE_SANDBOX_DOCKER_IMAGE}"
docker pull "${HOWLHOUSE_SANDBOX_DOCKER_IMAGE}"
echo

echo "Docker images:"
docker images
echo

echo "Running hardened sandbox preflight..."
OUTPUT="$(
  docker run \
    --rm \
    --network=none \
    --user 65534:65534 \
    --cpus "${HOWLHOUSE_SANDBOX_CPU_LIMIT}" \
    --memory "${HOWLHOUSE_SANDBOX_MEMORY_LIMIT}" \
    --pids-limit "${HOWLHOUSE_SANDBOX_PIDS_LIMIT}" \
    --read-only \
    --cap-drop=ALL \
    --security-opt=no-new-privileges \
    --tmpfs /tmp:rw,noexec,nosuid,size=64m \
    -v "${AGENT_DIR}:/agent:ro" \
    --workdir /agent \
    "${HOWLHOUSE_SANDBOX_DOCKER_IMAGE}" \
    python -c "import agent, helper; print(helper.build_message()); print(agent.act({})['confessional'])"
)"

printf '%s\n' "${OUTPUT}"
printf '%s\n' "${OUTPUT}" | grep -q "docker sandbox import ok"

echo
echo "Docker sandbox preflight passed."
