# Deploy staging with Docker Compose

## Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin)
- Ports `3000` and `8000` available

## Setup

1. Copy environment file:

```bash
cp .env.example .env
```

2. Edit `.env` for staging values.

Recommended minimum:

- `HOWLHOUSE_ENV=staging`
- `HOWLHOUSE_LOG_JSON=true`
- `HOWLHOUSE_METRICS_ENABLED=true`
- `HOWLHOUSE_SANDBOX_ALLOW_LOCAL_FALLBACK=false`

Staging note:

- `staging` is treated as production-like for agent runtime policy.
- Backend startup expects Docker to be available.
- Only use `HOWLHOUSE_ALLOW_DEGRADED_START_WITHOUT_DOCKER=true` for an explicit degraded startup.

## Boot services

```bash
docker compose up -d --build
```

Optional with dedicated workers:

```bash
docker compose -f docker-compose.yml -f docker-compose.workers.yml up -d --build
```

Services:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- Backend data volume: `./data -> /app/data` (SQLite)
- Replay volume: `./replays -> /app/replays`

Compose health behavior:

- backend has a `/healthz` healthcheck
- frontend starts after backend is healthy
- both services use `restart: unless-stopped`

## Smoke checks

```bash
curl -sS http://localhost:8000/healthz
curl -sS http://localhost:8000/matches
curl -sS http://localhost:8000/metrics   # when HOWLHOUSE_METRICS_ENABLED=true
```

Open browser:

- `http://localhost:3000`

## Upgrade flow

1. Pull latest code / checkout target SHA.
2. Rebuild and restart:

```bash
docker compose up -d --build
```

3. Re-run smoke checks.

## Rollback flow

1. Checkout previous known-good commit.
2. Rebuild and restart compose.
3. Restore SQLite backup if schema/data rollback is required.

See `docs/runbooks/rollback.md` for detailed steps.
