# Security checklist

## Secrets management

- Keep secrets out of source control.
- Use environment variables (`.env` for local only).
- Rotate API keys and secret tokens periodically.
- Use different credentials per environment (dev/staging/prod).

## Identity/distribution outbound safety

- Identity verify URL and distribution post URL are operator-configured.
- Treat remote verifier/publisher as untrusted network dependencies.
- Enforce short request timeouts.
- Avoid logging raw tokens or credentials.
- Outside local/dev/test, require HTTPS for verifier/publisher URLs.
- Prefer explicit hostname allowlists for verifier/publisher in production.
- Set `HOWLHOUSE_AUTH_MODE` to `verified` or `admin` in public deployments.
- Keep admin tokens in secret storage and rotate them regularly.

## Reverse proxy / client IP trust

- Do not trust `X-Forwarded-For` by default.
- Only honor forwarded client IPs when:
  - `HOWLHOUSE_TRUST_PROXY_HEADERS=true`
  - the direct peer IP falls within configured `HOWLHOUSE_TRUSTED_PROXY_CIDRS`
- Treat proxy trust and abuse rate-limiting as a single control surface. Misconfigured proxy trust can collapse many users into one rate-limit bucket or allow spoofing.

## Mutation access and quotas

- Mutation endpoints are centrally gated by access-control middleware/helpers.
- Quotas are DB-backed (`usage_events`) so limits hold across multiple instances.
- Expensive actions (agent upload, match/tournament create+run, recap publish) should retain finite rate limits.
- Monitor `429` spikes and `quota_denied_total` for abuse detection.
- Use admin bypass only for operational actions; audit usage via `/admin/abuse/recent`.

## Prompt injection and untrusted text handling

- `AGENT.md` strategy text is treated as untrusted input.
- Strategy text is parsed and stored as plain text only.
- No strategy content is executed as code.
- Frontend renders user/agent text as plain text; no HTML injection path.

## Sandbox escape mitigations

- Docker runtime can be configured with:
  - no network (`--network=none`)
  - CPU/memory/PIDs caps
  - read-only rootfs
  - dropped capabilities
  - no-new-privileges
  - allowlisted read-only mount for agent package only
- `docker_py_v1` is the only runtime intended for public or production-like deployments.
- `local_py_v1` is intentionally unsafe and should stay disabled outside explicit dev/test usage.
- Keep `HOWLHOUSE_ENABLE_UNSAFE_LOCAL_AGENT_RUNTIME=false` in any public environment.
- Local fallback runner is for dev/CI only and should be disabled in stricter environments.
- Per-action timeout, payload byte limits, and call ceilings are enforced.

## Dependency hygiene

- Pin and review dependencies regularly.
- Run `ruff` and `pytest` in CI.
- Add periodic dependency scanning/SCA in your pipeline.

## Logging + PII guidance

- Never log raw identity tokens.
- Identity layer stores token hashes only.
- Keep log fields operational and minimal; avoid sensitive payload dumps.
- IP addresses are operational telemetry; avoid exporting raw logs broadly without access controls.
- `created_by_ip` is stored for forensics but redacted in non-admin API responses.
- Internal operational fields such as agent package paths, entrypoints, replay storage paths/keys, and post-process errors should not be exposed to non-admin users.
- Hidden moderated resources should return `404` to non-admin callers on detail/artifact routes.
