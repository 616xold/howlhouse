# Rollback runbook

## When to rollback

- Sustained elevated error rate after deployment
- Data corruption risk detected
- Security issue requiring immediate revert

## Application rollback (compose)

1. Checkout previous known-good git SHA/tag.
2. Rebuild and restart services:

```bash
docker compose up -d --build
```

3. Verify with smoke checks (`/healthz`, frontend page load, match create/run).

## Data rollback (SQLite)

- Database file is typically under mounted data directory.
- Before risky deploys, snapshot the DB file.

Backup example:

```bash
cp data/howlhouse.db data/backups/howlhouse-$(date +%Y%m%d%H%M%S).db
```

Restore example (service downtime required):

```bash
cp data/backups/howlhouse-<timestamp>.db data/howlhouse.db
```

## Post-rollback

- Confirm service stability.
- Capture root-cause notes and create follow-up fix task.
