# Artifact storage

HowlHouse stores canonical match artifacts:

- replay JSONL
- recap JSON
- share card PNGs

## Blob store modes

### Local

```bash
HOWLHOUSE_BLOB_STORE=local
HOWLHOUSE_BLOB_BASE_DIR=./blob
```

### S3 / MinIO

```bash
HOWLHOUSE_BLOB_STORE=s3
HOWLHOUSE_S3_ENDPOINT=http://minio:9000   # optional for AWS, required for MinIO
HOWLHOUSE_S3_REGION=us-east-1
HOWLHOUSE_S3_BUCKET=howlhouse-artifacts
HOWLHOUSE_S3_ACCESS_KEY=minioadmin
HOWLHOUSE_S3_SECRET_KEY=minioadmin
HOWLHOUSE_S3_PREFIX=prod
```

## Key layout

Artifacts use deterministic keys:

- `matches/<match_id>/replay.jsonl`
- `matches/<match_id>/recap.json`
- `matches/<match_id>/share_card_public.png`
- `matches/<match_id>/share_card_spoilers.png`

## Read fallback behavior

API endpoints first attempt local file reads for speed; if local file is missing and blob keys exist,
responses are served from blob storage.

This supports container restarts and multi-instance deployments with shared artifact backing.
