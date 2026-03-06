# Monitoring (Prometheus + Grafana)

## Start monitoring overlay

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.workers.yml \
  -f docker-compose.monitoring.yml \
  up -d
```

Use the workers overlay with monitoring when you want job metrics (`jobs_run_total`) and worker-level metrics from `worker:9100`.

Services:

- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3001`

## Metrics scraped

Prometheus scrapes:

- backend `/metrics` (`backend:8000`)
- worker `/metrics` (`worker:9100`) when worker metrics are enabled (provided by `docker-compose.workers.yml`)

Key metric families:

- `http_requests_total`
- `http_request_duration_seconds`
- `matches_created_total`
- `matches_run_total`
- `tournaments_run_total`
- `identity_verifications_total`
- `recap_publishes_total`
- `jobs_run_total`

## Grafana dashboard

Provisioned dashboard: `HowlHouse Overview`

Panels:

- HTTP req/s
- HTTP p95 latency
- match/tournament run rates by status
- identity verification rate by outcome
- recap publish rate
- job run rate by type/status

## Production note

Use production ingress controls for `/metrics` (basic auth/IP restrictions). See `docs/deploy_production.md`.
