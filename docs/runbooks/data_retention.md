# Data retention runbook

## Stored data

- SQLite database (`matches`, `agents`, `seasons`, `tournaments`, recaps, identity events)
- Replay NDJSON files (`replays/*.jsonl`)
- Share cards (`replays/share_cards/*.png`)

## Recommended policy (starter)

- Keep replay files and DB for at least 30 days in staging.
- Keep production backups for 90+ days based on compliance needs.
- Prune stale artifacts older than policy thresholds.

## Backup

- Daily DB file backup.
- Periodic backup of `replays/` and `replays/share_cards/`.

## Restore checklist

1. Stop writers (API service).
2. Restore DB and replay directories from same snapshot window.
3. Start service.
4. Validate sample matches, recaps, and share cards.
