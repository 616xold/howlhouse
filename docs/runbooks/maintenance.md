# Maintenance runbook (retention pruning)

## What is pruned

When retention is enabled, prune removes old operational rows:
- `usage_events` older than `HOWLHOUSE_RETENTION_USAGE_EVENTS_DAYS`
- `jobs` older than `HOWLHOUSE_RETENTION_JOBS_DAYS` with terminal status (`succeeded`, `failed`)

It does **not** prune canonical replay artifacts.

## Manual prune

```bash
cd backend
python -m howlhouse.tools.prune
```

Example output:

```text
pruned usage_events=42 (cutoff=...), jobs=17 (cutoff=...)
```

## Automated prune (compose)

Use maintenance overlay:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.workers.yml \
  -f docker-compose.maintenance.yml \
  up -d --build
```

The maintenance service runs `python -m howlhouse.tools.prune` in a loop.

Tune interval:
- `HOWLHOUSE_MAINTENANCE_INTERVAL_SECONDS` (default `86400`)

## Verification

1. Check service logs for prune counts.
2. Confirm `/metrics` includes `prune_deleted_total` increments.
3. Confirm active jobs are unaffected (`queued`/`running` are never deleted by prune).
