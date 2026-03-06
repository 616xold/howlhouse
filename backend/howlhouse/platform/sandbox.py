from __future__ import annotations

import json
import os
import re
import select
import subprocess
import sys
import threading
from contextlib import suppress
from functools import lru_cache
from pathlib import Path
from typing import Any

from howlhouse.core.config import Settings
from howlhouse.engine.domain.models import GameConfig, NightAction, PublicMessage, Vote
from howlhouse.engine.runtime.agents.base import AgentAction
from howlhouse.engine.runtime.observation import Observation

PLAYER_ID_PATTERN = re.compile(r"^p\d+$")
HARNESS_PATH = Path(__file__).with_name("sandbox_harness.py")


@lru_cache(maxsize=1)
def _harness_source() -> str:
    return HARNESS_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def docker_available() -> bool:
    try:
        completed = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return completed.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _json_size_bytes(value: Any) -> int:
    return len(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def _truncate_strings(value: Any, max_len: int) -> Any:
    if isinstance(value, str):
        return value[:max_len]
    if isinstance(value, list):
        return [_truncate_strings(item, max_len) for item in value]
    if isinstance(value, dict):
        return {str(key): _truncate_strings(item, max_len) for key, item in value.items()}
    return value


def _observation_to_payload(obs: Observation) -> dict[str, Any]:
    return {
        "match_id": obs.match_id,
        "phase": obs.phase.value,
        "player_id": obs.player_id,
        "public_state": obs.public_state,
        "private_state": obs.private_state,
        "recent_events": obs.recent_events,
    }


def _fit_observation_budget(payload: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    normalized = json.loads(json.dumps(payload, sort_keys=True, ensure_ascii=False))

    recent_events = normalized.get("recent_events")
    if not isinstance(recent_events, list):
        recent_events = []
        normalized["recent_events"] = recent_events

    while _json_size_bytes(normalized) > max_bytes and recent_events:
        recent_events.pop(0)

    if _json_size_bytes(normalized) > max_bytes:
        normalized = _truncate_strings(normalized, max_len=256)

    if _json_size_bytes(normalized) > max_bytes:
        public_state = normalized.get("public_state", {})
        if not isinstance(public_state, dict):
            public_state = {}
        normalized["recent_events"] = []
        normalized["public_state"] = {
            "day": public_state.get("day"),
            "alive_players": public_state.get("alive_players", []),
            "dead_players": public_state.get("dead_players", []),
            "last_night_death": public_state.get("last_night_death"),
        }

    if _json_size_bytes(normalized) > max_bytes:
        private_state = normalized.get("private_state", {})
        role = "villager"
        if isinstance(private_state, dict):
            role = str(private_state.get("role", "villager"))
        normalized["private_state"] = {"role": role}

    return normalized


def _is_valid_player_id(value: str) -> bool:
    return bool(PLAYER_ID_PATTERN.match(value))


def _coerce_action(raw_action: dict[str, Any], obs: Observation, cfg: GameConfig) -> AgentAction:
    alive_players = {
        str(player_id)
        for player_id in obs.public_state.get("alive_players", [])
        if isinstance(player_id, str)
    }

    confessional_raw = raw_action.get("confessional")
    confessional = str(confessional_raw)[:1_000] if isinstance(confessional_raw, str) else None

    public_message: PublicMessage | None = None
    raw_public_message = raw_action.get("public_message")
    public_text = ""
    if isinstance(raw_public_message, str):
        public_text = raw_public_message
    elif isinstance(raw_public_message, dict):
        text_value = raw_public_message.get("text")
        if isinstance(text_value, str):
            public_text = text_value
    public_text = public_text[: cfg.public_message_char_limit]
    if public_text.strip():
        public_message = PublicMessage(player_id=obs.player_id, text=public_text)

    vote: Vote | None = None
    raw_vote = raw_action.get("vote")
    vote_target = ""
    if isinstance(raw_vote, str):
        vote_target = raw_vote.strip()
    elif isinstance(raw_vote, dict):
        target_value = raw_vote.get("target_id")
        if isinstance(target_value, str):
            vote_target = target_value.strip()
    if (
        vote_target
        and _is_valid_player_id(vote_target)
        and vote_target in alive_players
        and (vote_target != obs.player_id or len(alive_players) == 1)
    ):
        vote = Vote(voter_id=obs.player_id, target_id=vote_target)

    night_action: NightAction | None = None
    raw_night = raw_action.get("night_action")
    if isinstance(raw_night, dict):
        action_name = str(raw_night.get("action", "")).strip()
        target_id = str(raw_night.get("target_id", "")).strip()
        if (
            action_name in {"kill", "inspect", "protect"}
            and _is_valid_player_id(target_id)
            and target_id in alive_players
            and (action_name == "protect" or target_id != obs.player_id)
        ):
            night_action = NightAction(
                actor_id=obs.player_id,
                action=action_name,
                target_id=target_id,
            )

    return AgentAction(
        public_message=public_message,
        vote=vote,
        night_action=night_action,
        confessional=confessional,
    )


class SandboxAgentProxy:
    def __init__(
        self,
        *,
        settings: Settings,
        runtime_mode: str,
        package_path: str,
        entrypoint: str,
        match_id: str,
        player_id: str,
        seed: int,
        config: GameConfig,
    ):
        self._settings = settings
        self._runtime_mode = runtime_mode
        self._package_path = Path(package_path).resolve()
        self._entrypoint = entrypoint
        self._match_id = match_id
        self._player_id = player_id
        self._seed = seed
        self._config = config

        self._process: subprocess.Popen[str] | None = None
        self._turn = 0
        self._act_calls = 0
        self._start_failed = False
        self._closed = False
        self._lock = threading.Lock()

    def act(self, obs: Observation) -> AgentAction:
        with self._lock:
            if self._closed:
                return AgentAction()
            if self._act_calls >= self._settings.sandbox_max_calls_per_match:
                return AgentAction()
            self._act_calls += 1

            if not self._ensure_started():
                return AgentAction()

            observation_payload = _observation_to_payload(obs)
            observation_payload = _fit_observation_budget(
                observation_payload,
                max_bytes=self._settings.sandbox_max_observation_bytes,
            )

            self._turn += 1
            request = {
                "type": "act",
                "turn": self._turn,
                "observation": observation_payload,
            }
            if not self._send_json(request):
                self._terminate_process()
                return AgentAction()

            response = self._read_json(timeout_seconds=self._settings.sandbox_act_timeout_ms / 1000)
            if not isinstance(response, dict):
                self._terminate_process()
                return AgentAction()

            response_type = str(response.get("type", ""))
            if response_type != "act_result":
                return AgentAction()

            action = response.get("action")
            if not isinstance(action, dict):
                return AgentAction()
            return _coerce_action(action, obs, self._config)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._terminate_process()

    def _ensure_started(self) -> bool:
        if self._start_failed:
            return False
        if self._process is not None and self._process.poll() is None:
            return True

        command = self._build_command()
        env = os.environ.copy()

        if self._runtime_mode == "local_py_v1":
            env["HOWLHOUSE_AGENT_PATH"] = str((self._package_path / self._entrypoint).resolve())
        else:
            env["HOWLHOUSE_AGENT_PATH"] = f"/agent/{self._entrypoint}"

        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                cwd=str(self._package_path) if self._runtime_mode == "local_py_v1" else None,
                env=env,
            )
        except OSError:
            self._start_failed = True
            return False

        init_message = {
            "type": "init",
            "player_id": self._player_id,
            "seed": self._seed,
            "match_id": self._match_id,
            "config": {
                "public_message_char_limit": self._config.public_message_char_limit,
                "player_count": self._config.player_count,
                "werewolves": self._config.werewolves,
                "seers": self._config.seers,
                "doctors": self._config.doctors,
                "villagers": self._config.villagers,
            },
        }
        if not self._send_json(init_message):
            self._start_failed = True
            self._terminate_process()
            return False

        response = self._read_json(timeout_seconds=self._settings.sandbox_act_timeout_ms / 1000)
        if not isinstance(response, dict) or str(response.get("type", "")) != "init_ok":
            self._start_failed = True
            self._terminate_process()
            return False

        return True

    def _build_command(self) -> list[str]:
        if self._runtime_mode == "local_py_v1":
            return [sys.executable, "-I", "-u", str(HARNESS_PATH)]

        mount = f"{self._package_path}:/agent:ro"
        return [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network=none",
            "--cpus",
            self._settings.sandbox_cpu_limit,
            "--memory",
            self._settings.sandbox_memory_limit,
            "--pids-limit",
            str(self._settings.sandbox_pids_limit),
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "-v",
            mount,
            "--workdir",
            "/agent",
            "-e",
            f"HOWLHOUSE_AGENT_PATH=/agent/{self._entrypoint}",
            self._settings.sandbox_docker_image,
            "python",
            "-u",
            "-c",
            _harness_source(),
        ]

    def _send_json(self, value: dict[str, Any]) -> bool:
        if self._process is None or self._process.stdin is None:
            return False
        serialized = json.dumps(value, sort_keys=True, ensure_ascii=False)
        try:
            self._process.stdin.write(serialized + "\n")
            self._process.stdin.flush()
        except OSError:
            return False
        return True

    def _read_json(self, *, timeout_seconds: float) -> dict[str, Any] | None:
        if self._process is None or self._process.stdout is None:
            return None
        stdout = self._process.stdout

        try:
            ready, _, _ = select.select([stdout], [], [], timeout_seconds)
        except (ValueError, OSError):
            return None
        if not ready:
            return None

        line = stdout.readline()
        if not line:
            return None
        if len(line.encode("utf-8")) > self._settings.sandbox_max_action_bytes:
            return None

        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _terminate_process(self) -> None:
        process = self._process
        if process is None:
            return
        self._process = None

        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                process.kill()
                with suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=0.2)

        if process.stdin is not None:
            with suppress(OSError):
                process.stdin.close()
        if process.stdout is not None:
            with suppress(OSError):
                process.stdout.close()


def create_registered_agent_proxy(
    *,
    settings: Settings,
    runtime_type: str,
    package_path: str,
    entrypoint: str,
    match_id: str,
    player_id: str,
    seed: int,
    config: GameConfig,
) -> SandboxAgentProxy:
    allow_local_fallback = settings.sandbox_allow_local_fallback
    if settings.env.strip().lower() == "production":
        allow_local_fallback = False

    normalized_runtime = runtime_type
    if runtime_type == "docker_py_v1" and not docker_available():
        if allow_local_fallback:
            normalized_runtime = "local_py_v1"
        else:
            raise RuntimeError(
                "Docker runtime requested but docker is unavailable; "
                "local fallback is disabled in production"
            )

    if normalized_runtime not in {"docker_py_v1", "local_py_v1"}:
        raise ValueError(f"Unsupported runtime_type: {runtime_type}")

    return SandboxAgentProxy(
        settings=settings,
        runtime_mode=normalized_runtime,
        package_path=package_path,
        entrypoint=entrypoint,
        match_id=match_id,
        player_id=player_id,
        seed=seed,
        config=config,
    )
