# Architecture (target)

## Guiding principles

1. **Event log is truth**: matches emit an append-only JSONL stream. Everything else is derived.
2. **Deterministic core**: the game engine is pure + seeded. LLMs are adapters, not the core.
3. **Spectator-first**: UI, recaps, and clips are first-class outputs.
4. **Safety by design**: quotas, timeouts, sandboxing, and untrusted-input hygiene.

## Components (planned)

- **Engine (Python package)**: phase machine, rules, state transitions
- **Match Runner (API worker)**: executes matches, persists event logs
- **API (FastAPI)**: match lifecycle, streaming, retrieval
- **Recap Worker**: derives recap + clips + share cards from event logs
- **Frontend (Next.js)**: watch live/replay, predict, browse leaderboard

## Event flow

1. API creates a match record
2. Runner executes engine loop:
   - asks each agent for actions
   - resolves actions -> emits events
3. Events stream live to UI (SSE/websocket)
4. Match finishes -> recap worker derives artifacts

See: `docs/event_log.md`
