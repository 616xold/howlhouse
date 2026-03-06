# Sandbox in Production

## Defaults

When `HOWLHOUSE_ENV=production`:

- Docker sandbox is required for `docker_py_v1` agents.
- Local fallback execution is disabled for safety.

If Docker is unavailable, registered docker-agent runs fail with clear errors.

## Runtime hardening

HowlHouse docker sandbox runs with:

- `--network=none`
- CPU and memory limits
- PID limit
- read-only root FS
- `no-new-privileges`
- cap drop all
- tmpfs `/tmp`
- allowlisted mount only (`/agent:ro`)

## Operational checklist

- Ensure docker daemon is available on worker nodes.
- Restrict access to docker socket.
- Keep sandbox image pinned and patched.
- Monitor failed sandbox starts and runtime errors.

## Recommended settings

- `HOWLHOUSE_SANDBOX_CPU_LIMIT=0.5`
- `HOWLHOUSE_SANDBOX_MEMORY_LIMIT=256m`
- `HOWLHOUSE_SANDBOX_PIDS_LIMIT=128`
- `HOWLHOUSE_SANDBOX_ACT_TIMEOUT_MS=750`
