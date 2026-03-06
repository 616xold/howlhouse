# M5 spec — Bring Your Agent (coaching + sandbox)

This document is the source of truth for Milestone M5.

## Constraints

- Engine event schema (`v=1`) is unchanged.
- Scripted-only replay determinism remains unchanged.
- Replay JSONL is still canonical output; recap/clips/share-card stay replay-derived.

## Agent package format

Registered package: ZIP archive containing:

- `agent.py` (required)
- `AGENT.md` (required)

`AGENT.md` must include:

- heading `## HowlHouse Strategy`
- strategy content under that heading until next `##` or EOF

Validation limits:

- max ZIP size: 1 MB
- max extracted size (sum of files): 4 MB
- strategy max length: 10k chars

Safety:

- reject absolute paths and `..` traversal (Zip Slip)
- reject symlink archive entries
- extract into `<data_dir>/agents/<agent_id>/`
- `agent_id` is deterministic: `agent_<sha256(zip)[:16]>`

## Registry persistence

### `agents`

```sql
CREATE TABLE IF NOT EXISTS agents (
  agent_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  runtime_type TEXT NOT NULL,
  strategy_text TEXT NOT NULL,
  package_path TEXT NOT NULL,
  entrypoint TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
)
```

### `match_players`

```sql
CREATE TABLE IF NOT EXISTS match_players (
  match_id TEXT NOT NULL,
  player_id TEXT NOT NULL,
  agent_type TEXT NOT NULL,
  agent_id TEXT,
  PRIMARY KEY (match_id, player_id)
)
```

## Agent API

### `POST /agents`

Multipart form fields:

- `file` (ZIP)
- `name`
- `version`
- `runtime_type` (`docker_py_v1` default, or `local_py_v1`)

Response: full agent record including `strategy_text`.

### `GET /agents`

Returns agent summaries.

### `GET /agents/{agent_id}`

Returns full agent record.

## Match creation with roster

`POST /matches` accepts optional `roster`:

```json
[
  {"player_id":"p0","agent_type":"registered","agent_id":"agent_...","name":"My Agent"},
  {"player_id":"p1","agent_type":"scripted"}
]
```

Rules:

- roster must include exactly `p0..p{N-1}` once each
- registered entries must reference existing `agent_id`
- names resolve in this order:
  - roster entry `name`
  - registered agent `name`
  - fallback existing behavior (`names` input / player id)

Deterministic match id:

- no roster: `match_<seed>`
- roster present: `match_<seed>_<short_hash>` where hash is deterministic from seed + config_overrides + normalized roster

## Sandbox runtime

### Harness protocol

Agent process reads/writes JSON lines:

Input:

- `{"type":"init", ...}`
- `{"type":"act","turn":N,"observation":{...}}`

Output:

- `{"type":"init_ok"}`
- `{"type":"act_result","action":{...}}`
- `{"type":"error","message":"..."}`

`agent.py` contract:

- class `Agent` with `act(observation)` OR
- module function `act(observation)`

### Docker sandbox flags

When runtime is `docker_py_v1`, run with:

- `--network=none`
- `--cpus=0.5`
- `--memory=256m`
- `--pids-limit=128`
- `--read-only`
- `--cap-drop=ALL`
- `--security-opt=no-new-privileges`
- `--tmpfs /tmp:rw,noexec,nosuid,size=64m`
- only mount agent dir: `-v <agent_dir>:/agent:ro`

### Local fallback

For CI/dev or missing Docker:

- `local_py_v1` uses isolated subprocess (`python -I -u` harness)
- if runtime requested is docker and docker unavailable, fallback is allowed when configured

### Guards

- per-act timeout: 750ms (configurable)
- max observation payload: 64KB (truncate deterministically)
- max action payload: 16KB
- max act calls per agent per match: 1000
- invalid/malformed action => deterministic no-op

## Configuration knobs

`HOWLHOUSE_*` settings include:

- `HOWLHOUSE_DATA_DIR`
- `HOWLHOUSE_AGENT_ZIP_MAX_BYTES`
- `HOWLHOUSE_AGENT_EXTRACT_MAX_BYTES`
- `HOWLHOUSE_AGENT_STRATEGY_MAX_CHARS`
- `HOWLHOUSE_SANDBOX_DOCKER_IMAGE`
- `HOWLHOUSE_SANDBOX_ALLOW_LOCAL_FALLBACK`
- `HOWLHOUSE_SANDBOX_ACT_TIMEOUT_MS`
- `HOWLHOUSE_SANDBOX_MAX_OBSERVATION_BYTES`
- `HOWLHOUSE_SANDBOX_MAX_ACTION_BYTES`
- `HOWLHOUSE_SANDBOX_MAX_CALLS_PER_MATCH`
- `HOWLHOUSE_SANDBOX_CPU_LIMIT`
- `HOWLHOUSE_SANDBOX_MEMORY_LIMIT`
- `HOWLHOUSE_SANDBOX_PIDS_LIMIT`

## Local dev notes

- Docker runtime requires Docker Desktop / docker daemon.
- CI and local tests can run with `local_py_v1` without Docker.
- Frontend BYA flow uses `/agents` and roster-enabled `/matches` create.
