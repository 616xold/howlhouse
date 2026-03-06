# M12 Spec: Launch Security & Abuse Prevention

## Scope

M12 adds additive platform controls for public launch safety without changing engine replay behavior.

Non-goals:
- No replay schema changes (`v=1` remains unchanged).
- No deterministic engine behavior changes.
- No breaking API contract changes.

## Configuration

All fields are under `HOWLHOUSE_` env prefix.

- `HOWLHOUSE_AUTH_MODE`:
  - `open` (default): mutations allowed without identity.
  - `verified`: mutation requires verified identity or admin token.
  - `admin`: mutation requires admin token.
- `HOWLHOUSE_ADMIN_TOKENS`: comma-separated admin tokens.
- `HOWLHOUSE_ADMIN_TOKEN_HEADER`: admin token header name (default `X-HowlHouse-Admin`).

Quota overrides (set `0` to use mode defaults):
- `HOWLHOUSE_QUOTA_AGENT_UPLOAD_MAX`, `HOWLHOUSE_QUOTA_AGENT_UPLOAD_WINDOW_S`
- `HOWLHOUSE_QUOTA_MATCH_CREATE_MAX`, `HOWLHOUSE_QUOTA_MATCH_CREATE_WINDOW_S`
- `HOWLHOUSE_QUOTA_MATCH_RUN_MAX`, `HOWLHOUSE_QUOTA_MATCH_RUN_WINDOW_S`
- `HOWLHOUSE_QUOTA_TOURNAMENT_CREATE_MAX`, `HOWLHOUSE_QUOTA_TOURNAMENT_CREATE_WINDOW_S`
- `HOWLHOUSE_QUOTA_TOURNAMENT_RUN_MAX`, `HOWLHOUSE_QUOTA_TOURNAMENT_RUN_WINDOW_S`
- `HOWLHOUSE_QUOTA_RECAP_PUBLISH_MAX`, `HOWLHOUSE_QUOTA_RECAP_PUBLISH_WINDOW_S`

Default quota behavior:
- `open` mode uses permissive defaults.
- `verified` and `admin` use stricter defaults.
- Admin-token requests bypass quotas.

## Persistence changes

Additive DB fields:
- `agents.created_by_identity_id`, `agents.created_by_ip`
- `matches.created_by_identity_id`, `matches.created_by_ip`
- `tournaments.created_by_identity_id`, `tournaments.created_by_ip`

New table:

```sql
CREATE TABLE IF NOT EXISTS usage_events (
  event_id TEXT PRIMARY KEY,
  identity_id TEXT,
  client_ip TEXT NOT NULL,
  action TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS usage_events_action_created_idx
  ON usage_events(action, created_at);
CREATE INDEX IF NOT EXISTS usage_events_identity_action_created_idx
  ON usage_events(identity_id, action, created_at);
CREATE INDEX IF NOT EXISTS usage_events_ip_action_created_idx
  ON usage_events(client_ip, action, created_at);
```

## Access-control behavior

Mutation endpoints call shared access control before work:
- `POST /agents`
- `POST /matches`
- `POST /matches/{match_id}/run`
- `POST /seasons`
- `POST /seasons/{season_id}/activate`
- `POST /tournaments`
- `POST /tournaments/{tournament_id}/run`
- `POST /matches/{match_id}/predictions`
- `POST /matches/{match_id}/publish`

Expensive-action quota keys:
- `agent_upload`
- `match_create`
- `match_run`
- `tournament_create`
- `tournament_run`
- `recap_publish`

Denial responses:
- Auth denied: `401`/`403` with existing FastAPI `detail` payload.
- Quota denied: `429` with
  - `Retry-After: <seconds>` header
  - body: `{ "detail": { "error": "rate_limited", "action": "...", "retry_after_s": <int> } }`

Moderation visibility:
- Hidden moderated resources are returned as `404` to non-admin callers on detail/artifact routes.

## Ownership DTO fields

Additive fields included in API responses:
- Agent DTO: `created_by_identity_id`, `created_by_ip`
- Match DTO: `created_by_identity_id`, `created_by_ip`
- Tournament DTO: `created_by_identity_id`, `created_by_ip`

PII handling:
- `created_by_ip` is admin-only in responses; non-admin requests receive `created_by_ip: null`.

## Admin endpoints

Admin token protected:
- `GET /admin/quotas`
  - returns auth mode, effective quota config, usage totals for last hour/day.
- `GET /admin/abuse/recent?limit=100`
  - returns recent `usage_events` entries.

## Metrics

Added Prometheus counters:
- `auth_denied_total{reason,endpoint}`
- `quota_denied_total{action}`
- `admin_bypass_total{endpoint}`

## Determinism & replay guarantee

M12 does not modify engine event generation, envelope, ordering, or replay serialization. Replay NDJSON remains canonical.
