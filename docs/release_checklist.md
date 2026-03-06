# Release checklist

Run this before a public deploy:

- set `HOWLHOUSE_AUTH_MODE=verified` or `admin`
- set `HOWLHOUSE_ALLOWED_HOSTS` to the exact public hostnames
- set `HOWLHOUSE_TRUST_PROXY_HEADERS=true`
- set `HOWLHOUSE_TRUSTED_PROXY_CIDRS` to the real proxy/network CIDRs
- keep `HOWLHOUSE_SANDBOX_ALLOW_LOCAL_FALLBACK=false`
- keep `HOWLHOUSE_ENABLE_UNSAFE_LOCAL_AGENT_RUNTIME=false`
- confirm Docker is available on backend/worker nodes
- set strong `HOWLHOUSE_ADMIN_TOKENS` and store them outside the repo and shell history
- verify outbound identity/distribution URLs use HTTPS and allowlists where applicable
- verify TLS redirect and response headers:
  - `Strict-Transport-Security`
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: same-origin`
  - `Permissions-Policy`
- verify replay, recap, and admin routes with real deployment hostnames
