# Production deploy (M9): Traefik edge ingress + TLS

This guide runs HowlHouse behind Traefik with HTTPS, `/api` routing, protected metrics, and edge rate limiting.

## Prerequisites

- Docker + Docker Compose v2
- DNS A/AAAA record for `HOWLHOUSE_DOMAIN` pointing to this host
- Ports `80` and `443` open to the internet

## Required env vars

Set in `.env` (starting from `.env.example`):

- `HOWLHOUSE_DOMAIN` (public hostname)
- `TRAEFIK_ACME_EMAIL` (Let's Encrypt contact)
- `TRAEFIK_METRICS_BASIC_AUTH` (htpasswd string, e.g. `metrics:$2y$...`)
- `HOWLHOUSE_TRUST_PROXY_HEADERS=true`
- `HOWLHOUSE_TRUSTED_PROXY_HOPS=1`
- `HOWLHOUSE_TRUSTED_PROXY_CIDRS=<proxy subnet list>`
- `HOWLHOUSE_ALLOWED_HOSTS=<comma-separated public hostnames>`
- `NEXT_PUBLIC_API_BASE_URL=/api`
- `NEXT_PUBLIC_ENABLE_UNSAFE_LOCAL_AGENT_RUNTIME=false`
- `HOWLHOUSE_SANDBOX_ALLOW_LOCAL_FALLBACK=false`
- `HOWLHOUSE_AUTH_MODE=verified` (or `admin`)
- `HOWLHOUSE_ADMIN_TOKENS=<comma-separated-secret-tokens>`
- `HOWLHOUSE_RETENTION_ENABLED=true`
- `HOWLHOUSE_RETENTION_USAGE_EVENTS_DAYS=30`
- `HOWLHOUSE_RETENTION_JOBS_DAYS=14`

Optional but recommended:

- `HOWLHOUSE_LOG_JSON=true`
- `HOWLHOUSE_METRICS_ENABLED=true`
- `HOWLHOUSE_ENABLE_UNSAFE_LOCAL_AGENT_RUNTIME=false`
- `HOWLHOUSE_ALLOW_DEGRADED_START_WITHOUT_DOCKER=false`
- If identity verification is enabled:
  - `HOWLHOUSE_IDENTITY_VERIFY_URL=https://...`
  - `HOWLHOUSE_IDENTITY_VERIFY_HOST_ALLOWLIST=verifier.example.com`
- If recap distribution is enabled:
  - `HOWLHOUSE_DISTRIBUTION_POST_URL=https://...`
  - `HOWLHOUSE_DISTRIBUTION_POST_HOST_ALLOWLIST=publisher.example.com`
- Quota tuning:
  - `HOWLHOUSE_QUOTA_AGENT_UPLOAD_MAX=10`
  - `HOWLHOUSE_QUOTA_MATCH_CREATE_MAX=30`
  - `HOWLHOUSE_QUOTA_MATCH_RUN_MAX=60`
  - `HOWLHOUSE_QUOTA_TOURNAMENT_RUN_MAX=10`

## Start production stack

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

With dedicated workers + storage (recommended for real traffic):

```bash
docker compose \\
  -f docker-compose.yml \\
  -f docker-compose.prod.yml \\
  -f docker-compose.storage.yml \\
  -f docker-compose.workers.yml \\
  up -d --build --scale backend=2 --scale worker=2
```

With automated retention pruning:

```bash
docker compose \\
  -f docker-compose.yml \\
  -f docker-compose.prod.yml \\
  -f docker-compose.storage.yml \\
  -f docker-compose.workers.yml \\
  -f docker-compose.maintenance.yml \\
  up -d --build
```

What this does:

- Host exposes only Traefik (`80`, `443`)
- Frontend is served at `https://<HOWLHOUSE_DOMAIN>/`
- Backend API is served at `https://<HOWLHOUSE_DOMAIN>/api/*`
- `/api` prefix is stripped at the proxy before forwarding to backend
- Metrics are exposed at `https://<HOWLHOUSE_DOMAIN>/metrics` with basic auth
- Frontend should use `NEXT_PUBLIC_API_BASE_URL=/api` in this mode
- Traefik attaches production security headers on frontend, API, and metrics responses

## Verify TLS and redirects

```bash
curl -I http://<HOWLHOUSE_DOMAIN>/
curl -I https://<HOWLHOUSE_DOMAIN>/
```

Expected:

- HTTP request redirects to HTTPS
- HTTPS responds successfully with valid certificate after ACME issuance

## Verify API and metrics

```bash
curl -sS https://<HOWLHOUSE_DOMAIN>/api/healthz
curl -u metrics:YOUR_PASSWORD -sS https://<HOWLHOUSE_DOMAIN>/metrics | head
curl -sS https://<HOWLHOUSE_DOMAIN>/api/admin/quotas \\
  -H "X-HowlHouse-Admin: YOUR_ADMIN_TOKEN"
```

Moderation checks:

```bash
# create an identity block
curl -sS -X POST https://<HOWLHOUSE_DOMAIN>/api/admin/blocks \\
  -H "X-HowlHouse-Admin: YOUR_ADMIN_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"block_type":"identity","value":"viewer_123","reason":"abuse"}'

# list hidden matches
curl -sS "https://<HOWLHOUSE_DOMAIN>/api/admin/hidden?resource_type=match&limit=50" \\
  -H "X-HowlHouse-Admin: YOUR_ADMIN_TOKEN"
```

For local monitoring stack:

```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

## Edge protections enabled

- API rate limit: average `20 req/s`, burst `40`
- Identity API (`/api/identity/*`) stricter limit: average `5 req/s`, burst `10`
- Metrics route protected by basic auth
- Security headers:
  - `Strict-Transport-Security`
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: same-origin`
  - `Permissions-Policy`
- `X-Forwarded-For` is only trusted when the direct peer is within `HOWLHOUSE_TRUSTED_PROXY_CIDRS`
- Server-side mutation controls support `open`, `verified`, and `admin` auth modes
- Retention pruning should stay enabled in production to cap growth of `jobs`/`usage_events`

## Release checklist

- set `HOWLHOUSE_AUTH_MODE=verified` or `admin`
- set `HOWLHOUSE_ALLOWED_HOSTS` to the exact public hostnames
- set `HOWLHOUSE_TRUSTED_PROXY_CIDRS` to your actual proxy ranges
- confirm admin tokens are present and stored outside shell history
- verify HTTPS redirect, HSTS, and the other security headers with `curl -I`

## ACME certificate storage and rotation

Traefik ACME storage path:

- Host: `./data/traefik/acme.json`
- Container: `/letsencrypt/acme.json`

Operational notes:

- Keep `acme.json` backed up.
- Restrict file permissions on host (`chmod 600`).
- For migration/rotation, stop stack, back up `acme.json`, then restore on new host before starting Traefik.
- Store admin tokens in a secret manager (not plain-text in shell history) and rotate periodically.
