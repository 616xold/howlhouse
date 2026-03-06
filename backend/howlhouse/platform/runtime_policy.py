from __future__ import annotations

from howlhouse.core.config import Settings

DEV_LIKE_ENVS = {"dev", "local", "test"}
PRODUCTION_LIKE_ENVS = {"prod", "production", "staging"}


def normalized_env_name(env: str) -> str:
    return str(env or "").strip().lower()


def is_dev_like_env(env: str) -> bool:
    return normalized_env_name(env) in DEV_LIKE_ENVS


def is_production_like_env(env: str) -> bool:
    return normalized_env_name(env) in PRODUCTION_LIKE_ENVS


def unsafe_local_agent_runtime_allowed(settings: Settings) -> bool:
    env = normalized_env_name(settings.env)
    if env == "production":
        return False
    if env in DEV_LIKE_ENVS:
        return True
    return bool(settings.enable_unsafe_local_agent_runtime)


def ensure_agent_runtime_allowed(settings: Settings, runtime_type: str) -> None:
    normalized_runtime = str(runtime_type).strip()
    if normalized_runtime not in {"docker_py_v1", "local_py_v1"}:
        raise ValueError(f"Unsupported runtime_type: {runtime_type}")
    if normalized_runtime != "local_py_v1":
        return
    if unsafe_local_agent_runtime_allowed(settings):
        return
    env = normalized_env_name(settings.env)
    if env == "production":
        raise ValueError("local_py_v1 is not allowed when HOWLHOUSE_ENV=production")
    raise ValueError(
        "local_py_v1 is disabled outside dev/test unless "
        "HOWLHOUSE_ENABLE_UNSAFE_LOCAL_AGENT_RUNTIME=true"
    )
