# M8 spec — Production hardening + launch

This document is the source of truth for Milestone M8.

## Constraints

- Engine replay envelope and event schema remain `v=1` and unchanged.
- Replay determinism remains unchanged for identical seed/config/agents.
- Observability and deployment layers must not alter game outcomes.

## Observability

### Structured logging

Configuration:

- `HOWLHOUSE_LOG_JSON` (`false` default; set `true` in production)
- `HOWLHOUSE_LOG_LEVEL` (`INFO` default)

When JSON logging is enabled, each log line includes:

- `ts` (UTC RFC3339/ISO8601)
- `level`
- `logger`
- `msg`
- `request_id` (when present)
- `trace_id` (when present)
- request completion context when applicable: `method`, `path`, `status_code`, `duration_ms`
- optional domain context where relevant: `match_id`, `tournament_id`, `identity_id`, `seed`, `status`

### Request correlation

HTTP middleware behavior:

- uses incoming `X-Request-ID` if provided, otherwise generates one
- stores `request_id` and optional `trace_id` (`traceparent` header) on request state and contextvars
- adds `X-Request-ID` to every response
- applies security headers to every middleware-returned response (`nosniff`, `DENY`, `same-origin`)
- wraps identity middleware so early identity responses (including rate-limit `429`) are still correlated and metered
- logs request completion/failure with latency

### Metrics

Configuration:

- `HOWLHOUSE_METRICS_ENABLED` (`false` default)
- `HOWLHOUSE_METRICS_PATH` (`/metrics` default)

When enabled, Prometheus metrics endpoint is mounted at `metrics_path`.
When disabled, endpoint is not mounted.

Metrics:

- `http_requests_total{method,path,status}`
- `http_request_duration_seconds{method,path}`
- `matches_created_total`
- `matches_run_total{status}`
- `tournaments_run_total{status}`
- `identity_verifications_total{ok,reason}`
- `recap_publishes_total{status}`

### Tracing

Configuration:

- `HOWLHOUSE_TRACING_ENABLED` (`false` default)
- `HOWLHOUSE_TRACING_SERVICE_NAME` (`howlhouse` default)
- `HOWLHOUSE_TRACING_OTLP_ENDPOINT` (empty default)
- `HOWLHOUSE_TRACING_SAMPLE_RATE` (`1.0` default)

Behavior:

- initializes OpenTelemetry SDK when enabled
- instruments FastAPI server
- exports traces via OTLP when endpoint is configured, otherwise console exporter
- adds manual spans around match runner and tournament runner execution paths

## Security hardening in M8

- Adds response security headers:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: same-origin`
- CORS is configurable via `HOWLHOUSE_CORS_ORIGINS` (comma-separated); disabled when unset.

## Deployment and staging

Artifacts:

- `backend/Dockerfile`
- `frontend/Dockerfile`
- root `docker-compose.yml`

Staging workflow:

1. Copy `.env.example` to `.env` and configure values.
2. Run `docker compose up -d --build`.
3. Verify backend health: `GET /healthz`.
4. Verify metrics if enabled: `GET /metrics`.
5. Open frontend at `http://localhost:3000`.

## Runbooks

Runbooks included in `docs/runbooks/`:

- `incident_response.md`
- `rollback.md`
- `data_retention.md`

## Load testing

Baseline script:

- `tools/loadtest/loadtest.py`

Behavior:

- low-concurrency, safe defaults
- repeatedly checks `/healthz`
- creates scripted matches
- optionally runs matches synchronously
- lists matches

Configuration uses env vars documented in `docs/load_test.md`.
