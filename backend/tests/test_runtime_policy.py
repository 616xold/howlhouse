from __future__ import annotations

from pathlib import Path

import pytest

import howlhouse.api.app as app_module
from howlhouse.api.app import create_app
from howlhouse.core.config import Settings
from howlhouse.engine.domain.models import GameConfig
from howlhouse.platform.runtime_policy import (
    ensure_agent_runtime_allowed,
    unsafe_local_agent_runtime_allowed,
)
from howlhouse.platform.sandbox import SandboxAgentProxy


@pytest.mark.parametrize("env_name", ["prod", "production", "staging"])
@pytest.mark.parametrize("unsafe_flag", [False, True])
def test_production_like_envs_never_allow_unsafe_local_runtime(env_name: str, unsafe_flag: bool):
    settings = Settings(env=env_name, enable_unsafe_local_agent_runtime=unsafe_flag)

    assert unsafe_local_agent_runtime_allowed(settings) is False
    with pytest.raises(ValueError, match="local_py_v1 is not allowed in production-like"):
        ensure_agent_runtime_allowed(settings, "local_py_v1")


@pytest.mark.parametrize("env_name", ["dev", "local", "test"])
def test_dev_like_envs_keep_local_runtime_enabled(env_name: str):
    settings = Settings(env=env_name, enable_unsafe_local_agent_runtime=False)

    assert unsafe_local_agent_runtime_allowed(settings) is True
    ensure_agent_runtime_allowed(settings, "local_py_v1")


@pytest.mark.parametrize("env_name", ["prod", "production", "staging"])
def test_production_like_startup_requires_docker_unless_explicitly_degraded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env_name: str
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app_module, "docker_available", lambda: False)

    with pytest.raises(RuntimeError, match="Docker is required when HOWLHOUSE_ENV is prod"):
        create_app(
            Settings(
                env=env_name,
                database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
                data_dir=str(tmp_path / "data"),
            )
        )


def test_production_like_startup_can_degrade_only_when_explicitly_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app_module, "docker_available", lambda: False)

    app = create_app(
        Settings(
            env="staging",
            database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
            data_dir=str(tmp_path / "data"),
            allow_degraded_start_without_docker=True,
        )
    )

    assert app is not None


def test_docker_sandbox_command_runs_as_non_root_and_keeps_isolation_flags(tmp_path: Path):
    package_dir = tmp_path / "agent_pkg"
    package_dir.mkdir()
    (package_dir / "agent.py").write_text(
        "def act(observation):\n    return {}\n", encoding="utf-8"
    )

    proxy = SandboxAgentProxy(
        settings=Settings(env="test"),
        runtime_mode="docker_py_v1",
        package_path=str(package_dir),
        entrypoint="agent.py",
        match_id="match_123",
        player_id="p0",
        seed=123,
        config=GameConfig(rng_seed=123),
    )

    command = proxy._build_command()

    assert "--user" in command
    assert command[command.index("--user") + 1] == "65534:65534"
    assert "--network=none" in command
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges" in command
    assert "--tmpfs" in command


def test_docker_sandbox_stages_readable_mount_copy_under_tmpdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    package_dir = tmp_path / "agent_pkg"
    package_dir.mkdir()
    nested_dir = package_dir / "pkg"
    nested_dir.mkdir()
    entrypoint = package_dir / "agent.py"
    helper = nested_dir / "helper.py"
    entrypoint.write_text(
        "from pkg.helper import MESSAGE\n\ndef act(observation):\n    return {'confessional': MESSAGE}\n",
        encoding="utf-8",
    )
    helper.write_text("MESSAGE = 'sandbox staging ok'\n", encoding="utf-8")

    docker_tmp = tmp_path / "docker_tmp"
    docker_tmp.mkdir()
    monkeypatch.setenv("TMPDIR", str(docker_tmp))

    proxy = SandboxAgentProxy(
        settings=Settings(env="test"),
        runtime_mode="docker_py_v1",
        package_path=str(package_dir),
        entrypoint="agent.py",
        match_id="match_123",
        player_id="p0",
        seed=123,
        config=GameConfig(rng_seed=123),
    )

    proxy._prepare_docker_mount_path()

    staged_path = proxy._docker_mount_path
    assert staged_path is not None
    assert staged_path.parent.parent == docker_tmp
    assert staged_path != package_dir
    assert (staged_path / "agent.py").read_text(encoding="utf-8") == entrypoint.read_text(
        encoding="utf-8"
    )
    assert (staged_path / "pkg" / "helper.py").read_text(encoding="utf-8") == helper.read_text(
        encoding="utf-8"
    )
    assert oct(staged_path.stat().st_mode & 0o777) == "0o755"
    assert oct((staged_path / "agent.py").stat().st_mode & 0o777) == "0o644"

    proxy._terminate_process()

    assert not staged_path.parent.exists()
