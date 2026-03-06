# M10 spec — Scalable persistence + shared artifacts

This document is the source of truth for Milestone M10.

## Constraints

- Engine determinism is unchanged.
- Replay event schema stays `v=1`.
- JSONL replay remains canonical output.
- Existing APIs remain stable; only additive fields/behavior are introduced.

## Database support

Supported `HOWLHOUSE_DATABASE_URL` values:

- `sqlite:///...` (default local/dev/tests)
- `postgresql://user:pass@host:5432/db` (production scale path)

Store behavior:

- one `MatchStore` API supports both backends
- startup migration runner remains idempotent (`CREATE TABLE IF NOT EXISTS` + additive `ALTER TABLE`)
- query ordering remains explicit where user-visible ordering exists

### Additive schema fields

`matches`:

- `replay_key` (nullable)
- `replay_uri` (nullable)

`recaps`:

- `recap_key` (nullable)
- `share_card_public_key` (nullable)
- `share_card_spoilers_key` (nullable)

## Blob storage abstraction

`platform/blob_store.py` defines a storage interface:

- `put_bytes(key, data, content_type)`
- `get_bytes(key)`
- `exists(key)`
- `uri_for_key(key)`
- convenience: `put_text`, `get_text`

Implementations:

- `LocalBlobStore` (filesystem-backed)
- `S3BlobStore` (AWS S3 or MinIO-compatible)

## Artifact lifecycle

During match run:

- replay JSONL is still written locally incrementally for live streaming and local inspection

After completion:

- replay JSONL is uploaded to blob store
- recap JSON is uploaded to blob store
- share cards are uploaded to blob store
- DB records canonical artifact keys/URIs

## API read behavior

- replay/share-card endpoints keep existing behavior
- if local artifact file exists, serve local file
- if local file is missing but blob key exists, read from blob store and serve fallback response

## Config

New settings:

- `HOWLHOUSE_BLOB_STORE=local|s3`
- `HOWLHOUSE_BLOB_BASE_DIR`
- `HOWLHOUSE_S3_ENDPOINT`
- `HOWLHOUSE_S3_REGION`
- `HOWLHOUSE_S3_BUCKET`
- `HOWLHOUSE_S3_ACCESS_KEY`
- `HOWLHOUSE_S3_SECRET_KEY`
- `HOWLHOUSE_S3_PREFIX`

## Deployment overlays

- `docker-compose.storage.yml` adds Postgres + MinIO and wires backend env to use them.

## Validation

- SQLite default test suite remains green.
- Postgres mode integration is covered by env-gated test and CI service container.
- Blob store roundtrips (local + s3 mock) and artifact fallback are tested.
