# Incident response runbook

## Detection signals

- Elevated `5xx` responses in logs/metrics
- High request latency (`http_request_duration_seconds`)
- Match/tournament failures increasing (`matches_run_total{status="failed"}`, `tournaments_run_total{status="failed"}`)
- Identity verification spike / rate-limit events
- Mutation quota denials increasing (`quota_denied_total`)
- Authorization denials increasing (`auth_denied_total`)

## Initial triage

1. Check service health (`/healthz`).
2. Inspect recent backend logs by `request_id`.
3. Check `/metrics` for failing endpoint patterns.
4. Identify blast radius (all users vs one feature).
5. Check `/admin/quotas` and `/admin/abuse/recent` with admin token for abuse patterns.

## Immediate mitigations

1. Disable optional integrations if needed:
   - `HOWLHOUSE_IDENTITY_ENABLED=false`
   - `HOWLHOUSE_DISTRIBUTION_ENABLED=false`
2. Pause tournament/match load generation.
3. Scale down traffic or temporarily block abusive clients.
4. Temporarily raise specific quota windows or limits only if abuse source is understood.
5. If emergency operations are needed, use admin-token bypass and record the request IDs.

## Escalation

- Notify on-call owner.
- Capture timeline with request ids, timestamps, and affected endpoints.
- Open incident ticket with impact summary and current status.

## Recovery validation

- Health endpoint stable
- Error rates back to baseline
- Critical flows: create match, run match, replay fetch, recap fetch
