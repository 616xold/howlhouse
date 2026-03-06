# Sandbox in Production

## Defaults

When `HOWLHOUSE_ENV=production`:

- Docker sandbox is required for `docker_py_v1` agents.
- `local_py_v1` should be rejected for uploads and execution.
- Local fallback execution is disabled for safety unless an operator explicitly opts into unsafe behavior.

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
- Keep `HOWLHOUSE_ENABLE_UNSAFE_LOCAL_AGENT_RUNTIME=false`.

## Recommended settings

- `HOWLHOUSE_SANDBOX_CPU_LIMIT=0.5`
- `HOWLHOUSE_SANDBOX_MEMORY_LIMIT=256m`
- `HOWLHOUSE_SANDBOX_PIDS_LIMIT=128`
- `HOWLHOUSE_SANDBOX_ACT_TIMEOUT_MS=750`
