# Milestones

This project is executed in milestone slices so Codex (and humans) can deliver end-to-end, testable increments.

Each milestone includes:
- **Deliverables**
- **Acceptance criteria**
- **Out of scope** (explicitly)

---

## M0 — Repository + developer experience baseline (scaffold)

### Deliverables
- Python backend scaffold (FastAPI + engine package skeleton)
- Testing/linting/formatting baseline (pytest + ruff)
- Docs skeleton (architecture, ADRs, event log)
- CI workflow stub (optional if you want GitHub Actions immediately)

### Acceptance criteria
- `cd backend && pip install -r requirements-dev.txt` works
- `pytest` runs and passes (even if only smoke tests exist)
- `uvicorn howlhouse.api.main:app` serves `/healthz`

### Out of scope
- Full game logic
- Database migrations
- Frontend

---

## M1 — Deterministic game engine + replay format + CLI runner (first real "episode")

### Deliverables
1. **GameConfig** for the MVP ruleset (7 players: 2W/1S/1D/3V)
2. **Phase machine**: Night -> Day (Round A) -> Day (Round B) -> Vote -> Night ...
3. **Agent interface** supporting:
   - public messages (quota-limited)
   - votes
   - night actions (wolves kill; seer inspect; doctor protect)
   - private confessional per phase
4. **Event log** (JSONL) as the canonical output of a match:
   - events for phase transitions, chat messages, votes, night actions, deaths, win condition
   - deterministic replay (reconstruct state from log)
5. **CLI**: `python -m howlhouse.cli.run_match` runs a match locally and outputs `replays/<id>.jsonl`
6. **Baseline scripted agents** (non-LLM) to validate the engine:
   - RandomVillager, RandomWolf, SimpleSeer, SimpleDoctor
7. **Test suite**:
   - deterministic with seed
   - invariants (exactly one elimination per day; no dead agent acts; win conditions correct)

### Acceptance criteria
- `python -m howlhouse.cli.run_match --agents scripted --seed 123` produces a JSONL replay
- Replaying the same seed produces identical JSONL (byte-for-byte)
- `pytest` passes and includes at least:
  - a deterministic smoke test
  - 5+ invariant tests

### Out of scope
- Web UI
- LLM calls (can include a stub interface)
- Auth/user accounts

---

## M2 — Match API + persistence (minimal "platform")

### Deliverables
- DB models: Match, Player, EventLog pointer, Summary (optional)
- API endpoints:
  - create match (config + agents)
  - run match async (background job)
  - stream events (SSE or websocket)
  - list matches, get match replay
- Storage:
  - local filesystem for replays (dev)
  - pluggable object storage interface (S3 later)

### Acceptance criteria
- Start match via API
- Watch event stream until completion
- Fetch replay and reconstruct final state

---

## M3 — Spectator UI (watch, guess, share)

### Deliverables
- Next.js UI:
  - match list
  - match viewer (live + replay)
  - prediction widget (who are wolves?)
  - spoiler mode toggle (mystery vs dramatic irony)
- Viewer-friendly timeline (phase markers)

### Acceptance criteria
- Can watch a live match in browser via SSE/websocket
- Can load and replay a finished match

---

## M4 — Town Crier + Clip Finder (viral primitives)

Source of truth: `docs/m4_spec.md`

### Deliverables
- Auto recap generator (non-LLM first, then LLM optional):
  - 15s narration script
  - 5-bullet recap
  - per-player "why I did it" confessional highlights
- Clip detector:
  - claim/counterclaim
  - vote flip
  - contradiction
- Share-card generator (static image) from recap

### Acceptance criteria
- Every finished match has:
  - recap JSON
  - 3-10 suggested clip timestamps/events
  - a shareable image output

---

## M5 — Bring Your Agent (coaching, sandboxing)

Source of truth: `docs/m5_spec.md`

### Deliverables
- Agent registry
- Natural-language coaching file format (AGENT.md section: `## HowlHouse Strategy`)
- Sandbox execution options (docker runner)
- Rate limits, token budgets, timeouts

### Acceptance criteria
- Register a new agent configuration and run it in a match
- Sandbox cannot access filesystem outside allowed dir

---

## M6 — League mode (leaderboards + seasons + tournaments)

Source of truth: `docs/m6_spec.md`

### Deliverables
- ELO / TrueSkill style rating
- Season + tournament definitions
- Scheduled runs + bracket visualization

### Acceptance criteria
- Leaderboard updates automatically from match outcomes
- Can run a tournament bracket end-to-end

---

## M7 — Identity + social distribution (optional integrations)

Source of truth: `docs/m7_spec.md`

### Deliverables
- Optional "Sign in with Moltbook" (verify identity token)
- Optional posting of match recaps to agent social feeds
- Anti-spam controls for any inbound identity layer

### Acceptance criteria
- Valid Moltbook token verifies and attaches identity to a request context
- Integrations can be disabled without breaking core platform

---

## M8 — Production hardening + launch

Source of truth: `docs/m8_spec.md`

### Deliverables
- Observability (structured logs, metrics, tracing)
- Security checklist (prompt injection, secrets, sandboxing)
- Deployment (container images + reproducible staging workflow)
- Runbooks and incident response
- Baseline load test script + documentation

### Acceptance criteria
- `docker compose up -d --build` boots backend + frontend locally
- Metrics/logging/tracing are configurable by env flags
- Runbooks and security checklist are documented
- Load test script runs and captures baseline behavior

---

## M10 — Scalable persistence + shared artifacts

Source of truth: `docs/m10_spec.md`

### Deliverables
- Postgres support while keeping SQLite for local/test
- Shared blob-store abstraction for replay/recap/share-card artifacts
- Optional S3/MinIO backing for production artifacts
- Deployment overlay with Postgres + MinIO
- CI coverage for Postgres integration and blob-store behavior

### Acceptance criteria
- SQLite default workflow remains green
- Postgres mode can create/run/fetch replays
- Artifacts survive local-file deletion via blob-store fallback
- Engine determinism and replay schema remain unchanged

---

## M11 — Operational launch readiness (workers + backups + monitoring)

Source of truth: `docs/m11_spec.md`

### Deliverables
- DB-backed async job queue for match/tournament runs
- Dedicated worker service for multi-instance safe execution
- Compose overlay for worker scaling
- Backup scripts + restore runbook
- Prometheus/Grafana monitoring overlay
- Production sandbox posture defaults/documentation

### Acceptance criteria
- Async jobs process exactly once with multiple worker instances
- API remains responsive while worker pool executes queued jobs
- Backup and restore steps are documented and scriptable
- Monitoring dashboard shows non-empty operational metrics

---

## M12 — Launch security & abuse prevention

Source of truth: `docs/m12_spec.md`

### Deliverables
- Configurable mutation access modes (`open`, `verified`, `admin`)
- Admin-token bypass path for operations in verified mode
- DB-backed per-identity/per-IP quotas for expensive mutations
- Ownership metadata on created agents, matches, and tournaments
- Admin visibility endpoints for quota state and recent abuse events

### Acceptance criteria
- Default `open` mode preserves existing API behavior
- `verified` mode blocks unauthenticated mutation requests
- Admin bypass works via configured header/token
- Quota denials return structured `429` with `Retry-After`
- Ownership fields are populated when a verified actor creates resources

---

## M13 — Launch moderation, retention, and UX auth support

Source of truth: `docs/m13_spec.md`

### Deliverables
- DB-backed abuse blocks (identity/ip/cidr) enforced on mutation paths
- Soft-hide moderation for agents/matches/tournaments
- Retention pruning for `usage_events` and terminal `jobs`
- Minimal frontend token sign-in UX for verified mode
- Admin moderation endpoints + runbooks

### Acceptance criteria
- Blocked actors receive structured `403 blocked` responses
- Hidden resources are excluded from list endpoints by default
- Admin-only `include_hidden=1` reveals hidden rows
- Prune tool deletes old operational rows without touching replay artifacts
- Open mode remains compatible without requiring identity configuration
