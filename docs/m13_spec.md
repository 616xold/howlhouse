# M13 Spec: Launch moderation, retention, and UX auth support

## Scope

M13 adds moderation and maintenance controls required for public launch while keeping gameplay determinism and replay schema unchanged.

Non-goals:
- No changes to engine event schema/envelope/order (`v=1`).
- No changes to deterministic match/tournament outcomes.
- No breaking API changes.

## Moderation data model

### `abuse_blocks`

```sql
CREATE TABLE IF NOT EXISTS abuse_blocks (
  block_id TEXT PRIMARY KEY,
  block_type TEXT NOT NULL,   -- identity | ip | cidr
  value TEXT NOT NULL,
  reason TEXT,
  created_at TEXT NOT NULL,
  expires_at TEXT,
  created_by_identity_id TEXT
);
CREATE INDEX IF NOT EXISTS abuse_blocks_type_value_idx
  ON abuse_blocks(block_type, value);
CREATE INDEX IF NOT EXISTS abuse_blocks_expires_idx
  ON abuse_blocks(expires_at);
```

### Soft-hide columns (additive)

- `agents.hidden_at`, `agents.hidden_reason`
- `matches.hidden_at`, `matches.hidden_reason`
- `tournaments.hidden_at`, `tournaments.hidden_reason`

Hidden rows are excluded from list endpoints by default.
For non-admin callers, hidden resource detail/artifact routes return `404` (treated as not found).

## Access-control integration

`require_mutation_access()` now checks active abuse blocks before quota checks.

Block behavior:
- Applies to non-admin mutation requests.
- Supports direct identity match, direct IP match, and CIDR match.
- Expired blocks are ignored.

Blocked response:

```json
{
  "detail": {
    "error": "blocked",
    "block_type": "identity|ip|cidr",
    "reason": "...",
    "expires_at": "...|null"
  }
}
```

Metrics:
- `abuse_blocked_total{block_type,action}`

## List endpoint hidden filtering

By default hidden resources are excluded from:
- `GET /agents`
- `GET /matches`
- `GET /tournaments`

`include_hidden=1` behavior:
- Allowed only with admin token.
- Without admin token, returns `403`.

Detail/artifact access behavior:
- Hidden `GET /agents/{id}`, `GET /matches/{id}`, `GET /matches/{id}/replay`,
  `GET /matches/{id}/events`, `GET /tournaments/{id}`, and match recap/share-card endpoints
  return `404` to non-admin requests.

## Moderation admin endpoints

All endpoints below require admin token:

- `POST /admin/blocks`
  - body: `{block_type,value,reason?,expires_at?}`
- `GET /admin/blocks?include_expired=0&limit=200`
- `DELETE /admin/blocks/{block_id}`
- `POST /admin/hide`
  - body: `{resource_type:"agent|match|tournament",resource_id,hidden,reason?}`
- `GET /admin/hidden?resource_type=...&limit=200`

## Retention / pruning

Settings:
- `HOWLHOUSE_RETENTION_ENABLED=true`
- `HOWLHOUSE_RETENTION_USAGE_EVENTS_DAYS=30`
- `HOWLHOUSE_RETENTION_JOBS_DAYS=14`

Store prune APIs:
- `prune_usage_events(older_than_iso)`
- `prune_jobs(older_than_iso, statuses=("succeeded","failed"))`

Tool:

```bash
cd backend
python -m howlhouse.tools.prune
```

Prune metric:
- `prune_deleted_total{table}`

Optional maintenance overlay:
- `docker-compose.maintenance.yml` runs prune in a daily loop.

## Frontend auth UX (verified-mode support)

- Sticky header auth panel with token paste workflow.
- Token stored in local storage key: `howlhouse_identity_token`.
- Validate button calls `GET /identity/me` and displays identity summary.
- Sign out clears local token.
- API client auto-attaches `Authorization: Bearer <token>` when token exists.
- 429 errors surface `Retry-After` when provided.

## PII response policy

- `created_by_ip` remains stored for moderation/forensics.
- API DTOs keep the `created_by_ip` field but redact it (`null`) for non-admin requests.

## Compatibility

- `auth_mode=open` remains default and compatible with existing usage.
- Existing API routes remain available; M13 behavior is additive.
