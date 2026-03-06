# ADR 0001: Tech stack

- Backend: Python 3.11+ with FastAPI
- Engine: pure Python, dataclasses, deterministic RNG
- Persistence: SQLite in dev, Postgres in prod (via SQLAlchemy)
- Streaming: SSE (simple) -> websockets later
- Frontend: Next.js (TypeScript)
- Jobs: RQ/Redis or Celery (decide in M2)

Status: Accepted
