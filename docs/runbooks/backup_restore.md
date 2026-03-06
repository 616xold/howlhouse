# Runbook: Backup and Restore

## Scope

Covers Postgres metadata and artifact backups for both local and shared blob modes.

Canonical artifact source:

- Replay NDJSON is canonical match truth.
- Recaps/share cards are derived artifacts and should be backed up with replays for fast restore.

## What to back up

- Postgres DB (matches, seasons, jobs, agents, etc.).
- If `HOWLHOUSE_BLOB_STORE=local`:
  - `replays/`
  - `blob/`
- If `HOWLHOUSE_BLOB_STORE=s3`:
  - Postgres DB
  - S3/MinIO bucket contents (prefixes used by HowlHouse)
  - `replays/` if retained for local operational tailing/caching

## Manual backup

```bash
# Postgres SQL dump (gzipped)
./tools/backup/backup_postgres.sh ./backups/postgres

# Local artifacts archive (replays + blob)
./tools/backup/backup_artifacts.sh ./replays ./backups/artifacts ./blob

# Integrity checks
./tools/backup/verify_backup.sh ./backups/postgres/<file>.sql.gz
./tools/backup/verify_backup.sh ./backups/artifacts/<file>.tar.gz
```

## Restore Postgres

```bash
./tools/backup/restore_postgres.sh ./backups/postgres/<file>.sql.gz "$HOWLHOUSE_DATABASE_URL"
```

## Restore artifacts (local blob mode)

```bash
mkdir -p ./replays ./blob
# replace <artifact-file>.tar.gz
tar -xzf ./backups/artifacts/<artifact-file>.tar.gz -C .
```

## Incident recovery checklist

1. Stop API + workers.
2. Restore DB snapshot.
3. Restore artifacts.
4. Start services.
5. Verify:
   - `/healthz`
   - replay fetch for known finished match
   - leaderboard/tournament APIs load

## Optional scheduled backups

Use overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.backup.yml up -d
```

This runs periodic DB + artifact backups to `./backups/`.
