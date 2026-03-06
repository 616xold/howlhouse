# M7 spec — Optional Identity + Distribution + Anti-Spam

This document is the source of truth for Milestone M7.

## Constraints

- Engine event schema and replay determinism remain unchanged.
- Identity is optional and configurable.
- Core platform usage (matches, replays, league) does not require third-party identity.
- Distribution is optional and configurable.

## Settings

- `HOWLHOUSE_IDENTITY_ENABLED` (`bool`, default `false`)
- `HOWLHOUSE_IDENTITY_VERIFY_URL` (`str | null`)
- `HOWLHOUSE_IDENTITY_TOKEN_HEADER` (`str`, default `authorization`)
- `HOWLHOUSE_IDENTITY_RATE_LIMIT_WINDOW_S` (`int`, default `60`)
- `HOWLHOUSE_IDENTITY_RATE_LIMIT_MAX_FAILURES` (`int`, default `20`)

- `HOWLHOUSE_DISTRIBUTION_ENABLED` (`bool`, default `false`)
- `HOWLHOUSE_DISTRIBUTION_POST_URL` (`str | null`)

If identity/distribution is enabled, corresponding URL must be configured.

## Identity model

`VerifiedIdentity`:

- `identity_id: str`
- `handle: str | None`
- `display_name: str | None`
- `feed_url: str | None`
- `raw: dict[str, Any]`

## Identity adapters

- `NoOpIdentityVerifier`
- `HttpIdentityVerifier`

HTTP verifier contract:

- request: POST JSON `{"token":"..."}`
- response: JSON containing `identity_id` (or `id`/`user_id` fallback)

Failure handling:

- verifier outage maps to service-unavailable state
- invalid token maps to verification-failed state
- middleware never crashes the app

## Anti-spam monitoring

SQLite table:

```sql
CREATE TABLE IF NOT EXISTS identity_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ip TEXT NOT NULL,
  token_hash TEXT NOT NULL,
  ok INTEGER NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL
)
```

Rules:

- token hashes are stored (SHA-256 truncated), not raw tokens
- before verifier call, recent failures for IP are checked
- if failures in window exceed limit, request returns `429`

## Request context

When identity middleware runs:

- disabled identity: `request.state.identity = None`
- enabled identity + no token: `request.state.identity = None`
- enabled identity + valid token: `request.state.identity = VerifiedIdentity`
- enabled identity + invalid/unavailable token: `request.state.identity = None` and error state set

Dependencies:

- `get_optional_identity(request)`
- `require_identity(request)`

## APIs

## `GET /identity/me`

- identity disabled: `404`
- enabled + missing/invalid token: `401`
- enabled + valid token: identity payload

## `POST /matches/{match_id}/publish`

Purpose: optionally post match recap to external distribution endpoint.

Behavior:

- distribution disabled: `409`
- recap missing/not ready: `409`
- if identity enabled: requires verified identity
- if identity disabled: optional identity
- on success:

```json
{
  "match_id": "match_123",
  "published": true,
  "receipt": {...}
}
```

## Distribution adapters

- `NoOpRecapPublisher`
- `HttpRecapPublisher`

HTTP publisher sends JSON payload with:

- `match_id`
- `recap`
- `identity` (id/handle/display_name/feed_url) when available

## Security notes

- identity is never required for base platform usage unless enabled and endpoint explicitly requires it
- tokens are never persisted in plaintext
- identity failures are rate-limited per client IP
- external integrations are optional and replaceable via app state for testing
