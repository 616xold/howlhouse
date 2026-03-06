# Observability

## Configuration

Set these environment variables:

- `HOWLHOUSE_LOG_LEVEL` (default `INFO`)
- `HOWLHOUSE_LOG_JSON` (default `false`)
- `HOWLHOUSE_METRICS_ENABLED` (default `false`)
- `HOWLHOUSE_METRICS_PATH` (default `/metrics`)
- `HOWLHOUSE_TRACING_ENABLED` (default `false`)
- `HOWLHOUSE_TRACING_SERVICE_NAME` (default `howlhouse`)
- `HOWLHOUSE_TRACING_OTLP_ENDPOINT` (empty by default)
- `HOWLHOUSE_TRACING_SAMPLE_RATE` (default `1.0`)
- `HOWLHOUSE_WORKER_METRICS_ENABLED` (default `false`)
- `HOWLHOUSE_WORKER_METRICS_PORT` (default `9100`)

## Request correlation

- Incoming `X-Request-ID` is accepted and propagated.
- If absent, backend generates a request id.
- Response always includes `X-Request-ID`.
- If `traceparent` is present, trace id is extracted for correlation.
- Observability middleware wraps identity middleware, so early-return responses
  (for example identity rate-limit `429`) still include:
  - `X-Request-ID`
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: same-origin`
  - HTTP request metrics (`http_requests_total`, `http_request_duration_seconds`)

## JSON log example

```json
{
  "ts": "2026-03-03T16:00:00Z",
  "level": "INFO",
  "logger": "howlhouse.api.routers.matches",
  "msg": "match_created",
  "request_id": "req-123",
  "method": "POST",
  "path": "/matches",
  "status_code": 200,
  "duration_ms": 12.4,
  "match_id": "match_123"
}
```

## Metrics

When metrics are enabled, scrape `GET /metrics` (or configured path).

Metrics exported:

- `http_requests_total{method,path,status}`
- `http_request_duration_seconds{method,path}`
- `matches_created_total`
- `matches_run_total{status}`
- `tournaments_run_total{status}`
- `identity_verifications_total{ok,reason}`
- `recap_publishes_total{status}`
- `jobs_run_total{job_type,status}`
- `auth_denied_total{reason,endpoint}`
- `quota_denied_total{action}`
- `admin_bypass_total{endpoint}`
- `abuse_blocked_total{block_type,action}`
- `prune_deleted_total{table}`

Production note:

- Do not expose `/metrics` publicly.
- In M9 production ingress, metrics are routed through Traefik at `/metrics` and protected with basic auth.
- For local dashboarding, use `docker-compose.monitoring.yml` (Prometheus + Grafana).

## Tracing

Enable tracing with:

- `HOWLHOUSE_TRACING_ENABLED=true`

Optional OTLP export:

- set `HOWLHOUSE_TRACING_OTLP_ENDPOINT` to collector endpoint.
- if unset, traces go to console exporter.

Manual spans are emitted around:

- match runner execution
- tournament runner execution
