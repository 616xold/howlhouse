# M11 Spec: Operational Launch Readiness

## Scope

M11 hardens operations for multi-instance production without changing game logic:

- DB-backed async jobs for matches/tournaments
- Dedicated worker process/service
- Compose overlays for workers, backups, and monitoring
- Backup/restore tooling + runbooks
- Production sandbox posture defaults

Non-goals:

- Any change to engine event schema (`v=1`), event order, or deterministic outcomes
- Breaking existing API contracts

## Determinism and replay invariants

- Engine replay generation remains canonical and unchanged.
- Async orchestration (queue/worker/metrics/logging) must not affect game outcomes.
- Replays remain NDJSON source of truth.

## Jobs data model

Table: `jobs`

- `job_id TEXT PRIMARY KEY`
- `job_type TEXT` (`match_run` | `tournament_run`)
- `resource_id TEXT` (`match_id` / `tournament_id`)
- `status TEXT` (`queued` | `running` | `succeeded` | `failed`)
- `priority INTEGER`
- `created_at TEXT`
- `updated_at TEXT`
- `locked_by TEXT NULL`
- `locked_at TEXT NULL`
- `attempts INTEGER`
- `error TEXT NULL`

Store APIs:

- `enqueue_job(job_type, resource_id, priority=0)`
- `claim_next_job(worker_id, lease_seconds)`
- `heartbeat_job(job_id, worker_id)`
- `complete_job(job_id, status, error=None)`
- `requeue_stale_jobs(now_iso, stale_after_seconds)`
- `get_active_job(job_type, resource_id)`

Postgres claim is atomic (`FOR UPDATE SKIP LOCKED`); sqlite fallback is serialized with store lock.

## Worker behavior

Worker entrypoint: `python -m howlhouse.worker.main`

Loop behavior:

1. Requeue stale running jobs.
2. Claim next queued job.
3. Heartbeat lease while executing.
4. Execute sync runner:
   - `match_run` -> `MatchRunner.run(..., sync=True, allow_running=True)`
   - `tournament_run` -> `run_tournament_sync(...)`
5. Mark `succeeded`/`failed`.

Settings:

- `HOWLHOUSE_WORKER_ID`
- `HOWLHOUSE_WORKER_CONCURRENCY`
- `HOWLHOUSE_WORKER_POLL_INTERVAL_MS`
- `HOWLHOUSE_WORKER_LEASE_SECONDS`
- `HOWLHOUSE_WORKER_STALE_AFTER_SECONDS`
- `HOWLHOUSE_EMBEDDED_WORKER_ENABLED` (dev/local only)
- `HOWLHOUSE_WORKER_METRICS_ENABLED`
- `HOWLHOUSE_WORKER_METRICS_PORT`

## API async behavior

Existing endpoints remain; `sync=true` stays inline.

- `POST /matches/{match_id}/run?sync=false`
  - Enqueues `match_run` job.
  - Returns match DTO plus additive `job` object.

- `POST /tournaments/{tournament_id}/run?sync=false`
  - Enqueues `tournament_run` job.
  - Returns tournament DTO plus additive `job` object.

Idempotency:

- If resource already terminal, returns existing terminal resource state.
- If a queued/running job already exists for that resource, returns `409`.

## Compose overlays

- `docker-compose.workers.yml`: dedicated worker service.
- `docker-compose.monitoring.yml`: Prometheus + Grafana.
- `docker-compose.backup.yml`: periodic backup container (optional).

## Backup strategy

Scripts under `tools/backup/`:

- `backup_postgres.sh`
- `restore_postgres.sh`
- `backup_artifacts.sh`
- `verify_backup.sh`

Runbook: `docs/runbooks/backup_restore.md`.

## Monitoring

Prometheus scrapes backend `/metrics`.
Worker processes can expose their own Prometheus endpoint (default port `9100`),
scraped by the monitoring overlay.
Grafana dashboard includes:

- HTTP throughput + p95 latency
- match/tournament run counters
- identity verification counters
- recap publish counters
- job run counters

Doc: `docs/monitoring.md`.

## Sandbox production posture

When `HOWLHOUSE_ENV=production`:

- Local fallback sandbox is disabled for docker runtime agents.
- If docker is unavailable, agent match attempts fail clearly.
- App emits startup warning when docker is unavailable in production mode.

Doc: `docs/sandbox_production.md`.
