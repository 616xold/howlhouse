# Scaling HowlHouse (M11)

## Objective

Scale API and workers independently while keeping deterministic game outcomes.

## Recommended compose stack

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.storage.yml \
  -f docker-compose.workers.yml \
  up -d --build --scale backend=2 --scale worker=2
```

## Architecture

- `backend` instances serve HTTP/SSE and enqueue async jobs.
- `worker` instances claim jobs from DB and execute match/tournament runs.
- `postgres` is shared queue + metadata source.
- `blob store` (S3/MinIO/local) stores durable artifacts.

## Queue semantics

- Jobs are claimed atomically; only one worker can hold a job lease.
- Stale running jobs are requeued after lease timeout.
- Duplicate queued/running jobs for same resource are rejected by API (`409`).

## SSE note

Live SSE is in-process and best effort.
Replay NDJSON remains canonical for completed matches and should be the source for cross-instance consistency.

## Suggested starting values

- `HOWLHOUSE_WORKER_CONCURRENCY=1`
- `HOWLHOUSE_WORKER_LEASE_SECONDS=30`
- `HOWLHOUSE_WORKER_STALE_AFTER_SECONDS=120`
- Increase worker replicas before increasing per-worker concurrency.

## Capacity knobs

- Scale `worker` replicas for more async throughput.
- Keep `backend` replicas sized for read/API/SSE load.
- Use Prometheus/Grafana to monitor queue/HTTP pressure.
