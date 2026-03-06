# M3 spec — Spectator UI + Spoiler Modes + Predictions

This document is the source of truth for Milestone M3.

## Scope

M3 delivers a working spectator web app and minimal backend extensions for:

- spoiler-mode replay/event filtering
- anonymous prediction persistence + summary
- browser dev ergonomics (CORS)

M1/M2 constraints still apply:

- engine event schema remains `v=1`
- deterministic replay generation remains unchanged
- event log remains canonical output

## Backend

### App lifecycle

- FastAPI startup/shutdown must use lifespan handlers.
- Startup:
  - `store.init_schema()`
  - `runner.set_event_loop(asyncio.get_running_loop())`
- Shutdown:
  - `store.close()`

### CORS (dev)

Allow frontend local origins:

- `http://localhost:3000`
- `http://127.0.0.1:3000`

Settings:

- `allow_methods=["*"]`
- `allow_headers=["*"]`
- `allow_credentials=False`

### Visibility modes for replay + SSE

`visibility` query param accepts:

- `public`: only events where `visibility == "public"`
- `spoilers`: `public` events plus exactly one private exception: `roles_assigned`
- `all`: all events

`spoilers` must not include any other private events.

### Predictions persistence

SQLite table:

```sql
CREATE TABLE IF NOT EXISTS predictions (
  match_id TEXT NOT NULL,
  viewer_id TEXT NOT NULL,
  wolves_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (match_id, viewer_id)
)
```

- `wolves_json` stores stable JSON text.
- upsert key: `(match_id, viewer_id)`

### Predictions API

#### POST `/matches/{match_id}/predictions`

Body:

```json
{
  "viewer_id": "viewer-abc-1234",
  "wolves": ["p4", "p5"]
}
```

Validation:

- match exists
- `viewer_id` length 8..128
- wolves length equals configured `werewolves` count
- wolves are unique
- wolves are valid player IDs for the match roster (`p0..pN-1`)

Behavior:

- upsert prediction for `(match_id, viewer_id)`
- return latest summary object

#### GET `/matches/{match_id}/predictions/summary`

Response:

```json
{
  "match_id": "match_123",
  "total_predictions": 2,
  "by_player": {"p0": 0, "p1": 1, "p2": 0, "p3": 1, "p4": 2, "p5": 0, "p6": 0},
  "top_pairs": [
    {"pair": ["p1", "p4"], "count": 1},
    {"pair": ["p3", "p4"], "count": 1}
  ]
}
```

Computation is done in Python from stored rows (no SQLite JSON1 dependency).

## Frontend

### Stack

- Next.js + TypeScript
- ESLint + type checking
- env: `NEXT_PUBLIC_API_BASE_URL`

### Pages

- `/`: match list + create + run controls
- `/matches/[id]`: match viewer

### Match list (`/`)

- fetch and render `/matches`
- create match (`POST /matches`)
- run match (`POST /matches/{id}/run?sync=false`)
- poll match status until completion

### Match viewer (`/matches/[id]`)

Supports:

- live mode via SSE (`/events`)
- replay mode via NDJSON (`/replay`)
- spoiler toggle:
  - mystery: `visibility=public`
  - dramatic irony: `visibility=spoilers`

Operational note:

- `visibility=all` remains available only for admin/ops use and is not exposed as a normal spectator control in the default frontend.

Transcript rendering requirements:

- phase markers from `phase_started`
- plain-text public messages
- notices for kill/elimination
- vote result tally summary
- winner banner on `match_ended`

Sidebar requirements:

- roster with alive/dead state
- roles shown only when spoiler mode includes `roles_assigned`
- prediction widget

### Prediction widget

- generate/store `viewer_id` with `crypto.randomUUID()` in `localStorage`
- select exactly configured wolf count (MVP=2)
- submit via `POST /matches/{id}/predictions`
- show summary response
- poll summary periodically while page is open

### Event data hook

`useMatchEvents(matchId, visibility, mode)`:

- `mode="live"`: EventSource to `/events`
- `mode="replay"`: fetch `/replay` and parse NDJSON
- append events in order
- basic reconnect on SSE error (1s)
- reconnect stops after `match_ended` is received (no infinite reconnect loop after clean stream end)
- viewer switches to `replay` mode automatically once match status is `finished`

### Safety

- never render agent text as HTML
- do not use `dangerouslySetInnerHTML`
- render text content only
