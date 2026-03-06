# M2 spec — Match API + persistence + streaming

This document is the source of truth for Milestone M2.

## Compatibility constraints

- M1 event schema `v=1` remains unchanged.
- M1 determinism remains unchanged: same seed + config + agents => identical engine JSONL replay bytes.
- No required new engine event type in M2.

## Architecture (M2)

- Replay JSONL is canonical output.
- SQLite stores match metadata/state.
- In-memory EventBus stores per-match JSON history and live subscribers for SSE.
- MatchRunner executes games and writes replay incrementally while publishing identical JSON lines to EventBus.

## SQLite schema

Table: `matches`

```sql
CREATE TABLE matches (
  match_id TEXT PRIMARY KEY,
  seed INTEGER NOT NULL,
  agent_set TEXT NOT NULL,
  config_json TEXT NOT NULL,
  names_json TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  replay_path TEXT,
  winner TEXT,
  error TEXT
)
```

- `status`: `created | running | finished | failed`
- `config_json`: fully resolved `GameConfig` JSON object
- `agent_set`: M2 supports `scripted` only

## API endpoints

### 1) `POST /matches`

Create or return an idempotent match record.

Request body:

```json
{
  "seed": 123,
  "agent_set": "scripted",
  "names": {"p0": "p0"},
  "config_overrides": {"public_message_char_limit": 280}
}
```

Behavior:

- `match_id = "match_<seed>"`
- idempotent by `match_id`
- validates config override keys against `GameConfig`

### 2) `GET /matches`

Return match records, most recent first.

### 3) `GET /matches/{match_id}`

Return a single match record.

### 4) `POST /matches/{match_id}/run?sync={true|false}`

- default `sync=false`: launch background thread
- `sync=true`: run to completion in-process (testing/dev)
- updates status and timing fields

### 5) `GET /matches/{match_id}/replay?visibility={all|public|spoilers}`

- media type: `application/x-ndjson`
- `public` (default): server-side filter to events where `visibility == "public"`
- `spoilers` (M3 extension): `public` events plus `roles_assigned` only
- `all`: exact replay lines, admin-only
- returns `409` if replay is not ready

### 6) `GET /matches/{match_id}/events?visibility={all|public|spoilers}`

SSE stream:

- sends existing history first
- then sends live events
- closes after match completion

SSE message format:

```text
id: evt_000123
data: {"id":"evt_000123",...}

```

Visibility filtering:

- `public`: only events with `visibility == "public"`
- `spoilers`: `public` events plus `roles_assigned` only
- `all`: all history/live JSON lines, admin-only

## EventBus behavior

Per match:

- `history`: list of canonical event JSON strings (one per event, no trailing newline)
- `subscribers`: async queues receiving live events
- `close(match_id)`: marks closed and pushes `None` sentinel to all subscribers

Publishing from runner thread uses `loop.call_soon_threadsafe(...)` to execute EventBus operations on the FastAPI loop thread.

## MatchRunner behavior

- validates match/status before running
- marks `running` with `started_at`
- writes replay file incrementally as events emit
- publishes the exact same JSON strings to EventBus in emit order
- on success marks `finished`, sets `winner`, `finished_at`, `replay_path`
- on failure marks `failed`, sets `error`, closes EventBus

## Hardening requirements carried from M1

- Observation objects passed to agents must not expose mutable references to canonical event objects.
- Agent exceptions must not crash a match; engine falls back to no-op actions.
- Optional `on_event` callback failures must not break engine determinism.
