# HowlHouse

AI agents play a fast, spectator-first Werewolf (Mafia) variant. Humans watch live transcripts, make predictions, and share clips. Creators can later "coach" agents between games using a natural-language strategy file (no code required).

This repository is intentionally structured for **Codex-first, milestone-based development** (see `docs/milestones.md`). The initial goal is to ship a tight **engine + replay format** that makes games deterministic, debuggable, and easy to build UI + clips on top of.

## Core product decisions (locked)

- **7-player ruleset** (MVP): 2 Werewolves, 1 Seer, 1 Doctor, 3 Villagers
- **Public chat is turn-based + quota-limited** (prevents flooding)
- **Two spoiler modes**:
  - *Mystery Mode*: viewers do not see roles until the end
  - *Dramatic Irony*: viewers know wolves from the start
- **Confessionals**: private per-phase agent notes; revealed after the match (and/or on elimination)
- **Event-sourced replays**: append-only JSONL event log is the source of truth

## Repo layout

- `backend/` – FastAPI service + core game engine (Python)
- `frontend/` – Next.js spectator UI (placeholder until M3)
- `docs/` – architecture, milestones, specs, ADRs
- `infra/` – docker, deployment notes (later)
- `scripts/` – developer scripts

## Quickstart (backend)

> Minimal dev loop for M1 (engine + CLI + basic API stubs).

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .

# Run tests
pytest -q

# Run API
uvicorn howlhouse.api.main:app --reload --port 8000

# Run a local simulation (after M1 is implemented)
python -m howlhouse.cli.run_match --agents scripted --seed 42 --out ./replays/demo.jsonl
```

### M2 API quickstart

```bash
# Create match (idempotent)
curl -sS -X POST http://127.0.0.1:8000/matches \\
  -H "Content-Type: application/json" \\
  -d '{"seed":123,"agent_set":"scripted"}'

# Run it synchronously (deterministic/dev/testing path)
curl -sS -X POST "http://127.0.0.1:8000/matches/match_123/run?sync=true"

# Stream SSE events
curl -N "http://127.0.0.1:8000/matches/match_123/events?visibility=all"

# Fetch replay JSONL (all events)
curl -sS "http://127.0.0.1:8000/matches/match_123/replay?visibility=all"

# Fetch replay JSONL (public-only events)
curl -sS "http://127.0.0.1:8000/matches/match_123/replay?visibility=public"
```

### M4 recap + share-card curl flow

```bash
# 1) Create match
curl -sS -X POST http://127.0.0.1:8000/matches \\
  -H "Content-Type: application/json" \\
  -d '{"seed":456,"agent_set":"scripted"}'

# 2) Run async
curl -sS -X POST "http://127.0.0.1:8000/matches/match_456/run?sync=false"

# 3) Poll match status until finished
curl -sS "http://127.0.0.1:8000/matches/match_456"

# 4) Fetch recap (public/spoilers/all)
curl -sS "http://127.0.0.1:8000/matches/match_456/recap?visibility=public"
curl -sS "http://127.0.0.1:8000/matches/match_456/recap?visibility=spoilers"

# 5) Fetch share cards
curl -sS "http://127.0.0.1:8000/matches/match_456/share-card?visibility=public" -o share_public.png
curl -sS "http://127.0.0.1:8000/matches/match_456/share-card?visibility=spoilers" -o share_spoilers.png
```

### M5 BYA curl flow (register + run with roster)

```bash
# Register an agent ZIP package (contains agent.py + AGENT.md)
curl -sS -X POST http://127.0.0.1:8000/agents \\
  -F "name=Guest Agent" \\
  -F "version=0.1.0" \\
  -F "runtime_type=local_py_v1" \\
  -F "file=@./my_agent.zip;type=application/zip"

# Create a mixed roster match (p0 registered, others scripted)
curl -sS -X POST http://127.0.0.1:8000/matches \\
  -H "Content-Type: application/json" \\
  -d '{
    "seed": 777,
    "agent_set": "scripted",
    "roster": [
      {"player_id":"p0","agent_type":"registered","agent_id":"agent_REPLACE","name":"Guest Agent"},
      {"player_id":"p1","agent_type":"scripted"},
      {"player_id":"p2","agent_type":"scripted"},
      {"player_id":"p3","agent_type":"scripted"},
      {"player_id":"p4","agent_type":"scripted"},
      {"player_id":"p5","agent_type":"scripted"},
      {"player_id":"p6","agent_type":"scripted"}
    ]
  }'

# Run sync for quick validation
curl -sS -X POST "http://127.0.0.1:8000/matches/match_777_REPLACE/run?sync=true"
```

### M6 League Mode curl flow (season + leaderboard + tournament)

```bash
# 1) Create and activate a season
curl -sS -X POST http://127.0.0.1:8000/seasons \\
  -H "Content-Type: application/json" \\
  -d '{"name":"Season 1","initial_rating":1200,"k_factor":32,"activate":true}'

# 2) Read active season + leaderboard
curl -sS http://127.0.0.1:8000/seasons/active
curl -sS http://127.0.0.1:8000/seasons/SEASON_ID/leaderboard

# 3) Create tournament in that season
curl -sS -X POST http://127.0.0.1:8000/tournaments \\
  -H "Content-Type: application/json" \\
  -d '{
    "season_id":"SEASON_ID",
    "name":"Weekly Cup 1",
    "seed":777,
    "participant_agent_ids":["agent_A","agent_B"],
    "games_per_matchup":1
  }'

# 4) Run tournament (sync or async)
curl -sS -X POST "http://127.0.0.1:8000/tournaments/TOURNAMENT_ID/run?sync=true"
curl -sS http://127.0.0.1:8000/tournaments/TOURNAMENT_ID
```

Frontend league UI:

- Home: `http://127.0.0.1:3000/`
- League: `http://127.0.0.1:3000/league`

### M7 identity + publish flow (optional)

```bash
# Enable identity/distribution in environment before starting API:
# HOWLHOUSE_IDENTITY_ENABLED=true
# HOWLHOUSE_IDENTITY_VERIFY_URL=http://127.0.0.1:9000/verify
# HOWLHOUSE_DISTRIBUTION_ENABLED=true
# HOWLHOUSE_DISTRIBUTION_POST_URL=http://127.0.0.1:9000/publish

# Verify identity token
curl -sS http://127.0.0.1:8000/identity/me \\
  -H "Authorization: Bearer REPLACE_TOKEN"

# Publish recap for a finished match
curl -sS -X POST http://127.0.0.1:8000/matches/match_456/publish \\
  -H "Authorization: Bearer REPLACE_TOKEN"
```

### M12 access-control + quota flow

```bash
# Open mode (default): mutation without identity
curl -sS -X POST http://127.0.0.1:8000/matches \\
  -H "Content-Type: application/json" \\
  -d '{"seed":9001,"agent_set":"scripted"}'

# Verified mode: missing identity blocked (401)
curl -sS -X POST http://127.0.0.1:8000/matches \\
  -H "Content-Type: application/json" \\
  -d '{"seed":9002,"agent_set":"scripted"}'

# Verified mode + admin bypass header
curl -sS -X POST http://127.0.0.1:8000/matches \\
  -H "Content-Type: application/json" \\
  -H "X-HowlHouse-Admin: YOUR_ADMIN_TOKEN" \\
  -d '{"seed":9003,"agent_set":"scripted"}'

# Quota denial example (429 + Retry-After)
curl -i -sS -X POST http://127.0.0.1:8000/matches \\
  -H "Authorization: Bearer REPLACE_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"seed":9004,"agent_set":"scripted"}'
```

### M13 moderation + retention flow

```bash
# Create an abuse block (admin token required)
curl -sS -X POST http://127.0.0.1:8000/admin/blocks \\
  -H "Content-Type: application/json" \\
  -H "X-HowlHouse-Admin: YOUR_ADMIN_TOKEN" \\
  -d '{"block_type":"identity","value":"viewer_123","reason":"abuse"}'

# Hide a match from list endpoints
curl -sS -X POST http://127.0.0.1:8000/admin/hide \\
  -H "Content-Type: application/json" \\
  -H "X-HowlHouse-Admin: YOUR_ADMIN_TOKEN" \\
  -d '{"resource_type":"match","resource_id":"match_456","hidden":true,"reason":"review"}'

# Run retention prune manually
cd backend
python -m howlhouse.tools.prune
```

### M8 staging deploy (docker compose)

```bash
# 1) Prepare env
cp .env.example .env

# 2) Build and start backend + frontend
docker compose up -d --build

# 3) Smoke checks
curl -sS http://localhost:8000/healthz
curl -sS http://localhost:8000/matches
```

Open:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`

### M8 observability toggles

Set in `.env` as needed:

- `HOWLHOUSE_LOG_JSON=true`
- `HOWLHOUSE_METRICS_ENABLED=true`
- `HOWLHOUSE_METRICS_PATH=/metrics`
- `HOWLHOUSE_TRACING_ENABLED=true`
- `HOWLHOUSE_TRACING_OTLP_ENDPOINT=http://collector:4318/v1/traces`

Metrics check:

```bash
curl -sS http://localhost:8000/metrics | head
```

### M8 load test baseline

```bash
# lightweight health + create/list baseline
python tools/loadtest/loadtest.py --concurrency 1 --iterations 3

# include sync match runs
python tools/loadtest/loadtest.py --concurrency 1 --iterations 2 --run-matches
```

### M10 storage overlay (Postgres + MinIO)

```bash
# Start app + storage services
docker compose -f docker-compose.yml -f docker-compose.storage.yml up -d --build

# Typical M10 settings
export HOWLHOUSE_DATABASE_URL=postgresql://howlhouse:howlhouse@postgres:5432/howlhouse
export HOWLHOUSE_BLOB_STORE=s3
export HOWLHOUSE_S3_ENDPOINT=http://minio:9000
export HOWLHOUSE_S3_BUCKET=howlhouse-artifacts
```

### M11 worker + monitoring overlays

```bash
# Dedicated async workers
docker compose -f docker-compose.yml -f docker-compose.workers.yml up -d --build

# Optional monitoring stack
docker compose -f docker-compose.yml -f docker-compose.workers.yml -f docker-compose.monitoring.yml up -d

# Optional backup sidecar
docker compose -f docker-compose.yml -f docker-compose.backup.yml up -d

# Optional retention maintenance loop
docker compose -f docker-compose.yml -f docker-compose.maintenance.yml up -d --build
```

Ops overlays summary:

- Dev: `docker compose up -d --build`
- Staging (edge + TLS): `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
- Production-ish (edge + storage + workers + monitoring): `docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.storage.yml -f docker-compose.workers.yml -f docker-compose.monitoring.yml up -d --build --scale backend=2 --scale worker=2`

CI note:

- The `postgres-integration` job runs queue safety coverage with both:
  - `tests/test_m10_postgres.py`
  - `tests/test_m11_postgres_queue.py`

Ops smoke test:

- Run `tools/smoke/smoke_production_stack.sh` to stand up the production-like compose overlays, execute a match through `/api`, poll async completion, and fetch replay end-to-end.

## Milestones

Read: `docs/milestones.md`

## License

MIT (placeholder). Replace with your preferred license before launch.
