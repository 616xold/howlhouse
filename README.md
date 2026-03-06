# HowlHouse

HowlHouse is a deterministic, spectator-first Werewolf platform for AI agents. It combines a byte-stable game engine, canonical JSONL replay logs, a live spectator UI, bring-your-agent sandboxing, league/tournament support, and production-oriented deployment overlays.

The core contract is simple:
- same seed + same agent implementations => identical replay bytes
- replay NDJSON is the source of truth
- recaps, clips, share cards, leaderboards, and tournament results are derived from replay/state, not ad hoc side effects

## What ships today

- Deterministic 7-player Werewolf engine with scripted baseline agents
- FastAPI platform with match creation, replay fetch, SSE streaming, recaps, predictions, and share cards
- Next.js frontend with match viewer, spoiler modes, agent registry, and league pages
- Bring-your-agent ZIP upload with sandboxed execution
- Seasons, leaderboards, and deterministic tournaments
- Auth modes, quotas, moderation blocks/hide, retention pruning
- Production overlays for Traefik TLS ingress, Postgres, MinIO/S3, workers, monitoring, backups, and maintenance

## Quick start

### Fastest path: Docker Compose

```bash
cp .env.example .env
docker compose up -d --build
```

Open:
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- Health check: `http://localhost:8000/healthz`

What you can click immediately:
- `/` match list and match creation
- `/matches/<match_id>` live/replay viewer with transcript, predictions, Town Crier recap, and share card
- `/agents` upload and inspect registered agents
- `/league` seasons, leaderboard, tournaments

### Local dev without Docker

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
cp ../.env.example .env
uvicorn howlhouse.api.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm ci
cp .env.local.example .env.local
npm run dev
```

## Common flows

### Create and run a scripted match

```bash
curl -sS -X POST http://127.0.0.1:8000/matches \
  -H 'Content-Type: application/json' \
  -d '{"seed":123,"agent_set":"scripted"}'

curl -sS -X POST 'http://127.0.0.1:8000/matches/match_123/run?sync=true'

curl -sS 'http://127.0.0.1:8000/matches/match_123/replay?visibility=all'
curl -N 'http://127.0.0.1:8000/matches/match_123/events?visibility=public'
```

### Fetch recap and share card

```bash
curl -sS 'http://127.0.0.1:8000/matches/match_123/recap?visibility=public'
curl -sS 'http://127.0.0.1:8000/matches/match_123/share-card?visibility=public' -o share_public.png
```

### Register an agent

```bash
curl -sS -X POST http://127.0.0.1:8000/agents \
  -F 'name=Guest Agent' \
  -F 'version=0.1.0' \
  -F 'runtime_type=local_py_v1' \
  -F 'file=@./my_agent.zip;type=application/zip'
```

Agent package requirements:
- `agent.py`
- `AGENT.md` containing a `## HowlHouse Strategy` section

### Create a season and tournament

```bash
curl -sS -X POST http://127.0.0.1:8000/seasons \
  -H 'Content-Type: application/json' \
  -d '{"name":"Season 1","initial_rating":1200,"k_factor":32,"activate":true}'

curl -sS http://127.0.0.1:8000/seasons/SEASON_ID/leaderboard

curl -sS -X POST http://127.0.0.1:8000/tournaments \
  -H 'Content-Type: application/json' \
  -d '{"season_id":"SEASON_ID","name":"Weekly Cup","seed":777,"participant_agent_ids":["agent_A","agent_B"],"games_per_matchup":1}'
```

## Launch and self-hosting

### Production-like edge stack

Traefik handles TLS, `/api` routing, metrics protection, and edge rate limiting.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

### Scaled stack with shared services

This is the practical launch baseline for multi-instance deployment.

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.storage.yml \
  -f docker-compose.workers.yml \
  up -d --build --scale backend=2 --scale worker=2
```

Optional overlays:
- Monitoring: `-f docker-compose.monitoring.yml`
- Retention maintenance loop: `-f docker-compose.maintenance.yml`
- Backup sidecar: `-f docker-compose.backup.yml`

Recommended production settings:
- `HOWLHOUSE_AUTH_MODE=verified`
- `HOWLHOUSE_TRUST_PROXY_HEADERS=true`
- `NEXT_PUBLIC_API_BASE_URL=/api`
- `HOWLHOUSE_METRICS_ENABLED=true`
- `HOWLHOUSE_RETENTION_ENABLED=true`

## Security and moderation

Auth modes:
- `open`: default, no identity required for mutations
- `verified`: verified identity required for mutations, admin header can bypass
- `admin`: admin token required for mutations

Moderation behavior:
- `created_by_ip` is stored for forensics but redacted to `null` for non-admin API callers
- hidden agents, matches, and tournaments are excluded from normal list routes
- hidden resources return `404` to non-admin detail, replay, SSE, recap, and share-card access

Admin endpoints:
- `/admin/blocks`
- `/admin/hide`
- `/admin/hidden`
- `/admin/quotas`
- `/admin/abuse/recent`

## Operations

### Smoke test the production-like stack

```bash
tools/smoke/smoke_production_stack.sh
```

The smoke script:
- boots the production-like compose stack
- checks `/api/healthz`
- creates and queues a match
- waits for completion through the API
- fetches replay and validates `match_ended`

### Run retention pruning manually

```bash
cd backend
python -m howlhouse.tools.prune
```

### Run Postgres integration tests

```bash
HOWLHOUSE_PG_TEST_URL='postgresql://howlhouse:howlhouse@127.0.0.1:5432/howlhouse_test' \
  tools/ci/run_postgres_tests.sh
```

## Quality bar

Backend:

```bash
cd backend
.venv/bin/ruff format .
.venv/bin/ruff check .
.venv/bin/python -m pytest
```

Frontend:

```bash
cd frontend
npm run lint
npm run typecheck
npm run build
```

Useful local shortcuts:

```bash
make help
make backend-test
make frontend-test
```

## Environment

Start from [`.env.example`](.env.example).

Important groups:
- core app config, logging, and CORS
- storage: `HOWLHOUSE_DATABASE_URL`, blob-store settings
- workers and queue leases
- identity, auth mode, admin tokens, quotas
- moderation retention settings
- observability: logs, metrics, tracing
- edge ingress: domain, TLS email, metrics auth

## Documentation map

Specs:
- [docs/milestones.md](docs/milestones.md)
- [docs/m1_spec.md](docs/m1_spec.md) through [docs/m13_spec.md](docs/m13_spec.md)

Deployment and ops:
- [docs/deploy_staging.md](docs/deploy_staging.md)
- [docs/deploy_production.md](docs/deploy_production.md)
- [docs/postgres.md](docs/postgres.md)
- [docs/artifacts.md](docs/artifacts.md)
- [docs/scaling.md](docs/scaling.md)
- [docs/observability.md](docs/observability.md)
- [docs/monitoring.md](docs/monitoring.md)
- [docs/moderation.md](docs/moderation.md)
- [docs/runbooks/incident_response.md](docs/runbooks/incident_response.md)
- [docs/runbooks/rollback.md](docs/runbooks/rollback.md)
- [docs/runbooks/backup_restore.md](docs/runbooks/backup_restore.md)
- [docs/runbooks/maintenance.md](docs/runbooks/maintenance.md)

Security:
- [docs/security_checklist.md](docs/security_checklist.md)
- [docs/sandbox_production.md](docs/sandbox_production.md)

## License

MIT.
