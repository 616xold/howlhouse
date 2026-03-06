# Postgres mode

## Connection string

Use:

```bash
HOWLHOUSE_DATABASE_URL=postgresql://user:pass@host:5432/dbname
```

## Local compose with storage overlay

```bash
docker compose -f docker-compose.yml -f docker-compose.storage.yml up -d --build
```

Recommended backend env with the overlay:

```bash
HOWLHOUSE_DATABASE_URL=postgresql://howlhouse:howlhouse@postgres:5432/howlhouse
```

## Startup migration behavior

On app startup, `MatchStore.init_schema()` runs idempotent table creation and additive column checks.
No destructive migration operations are performed.

## CI integration

A dedicated GitHub Actions job starts `postgres:16` and runs the Postgres integration test.
