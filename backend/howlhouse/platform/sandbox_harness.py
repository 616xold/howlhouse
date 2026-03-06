from __future__ import annotations

import importlib.util
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _emit(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, sort_keys=True, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _load_agent_callable(agent_path: Path) -> Callable[[dict[str, Any]], dict[str, Any]]:
    if not agent_path.is_file():
        raise RuntimeError(f"agent file not found: {agent_path}")
    agent_dir = str(agent_path.parent.resolve())
    if not sys.path or sys.path[0] != agent_dir:
        sys.path.insert(0, agent_dir)

    spec = importlib.util.spec_from_file_location("howlhouse_user_agent", agent_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load agent module")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if hasattr(module, "Agent"):
        candidate = module.Agent()
        act_fn = getattr(candidate, "act", None)
        if callable(act_fn):
            return act_fn

    module_level_act = getattr(module, "act", None)
    if callable(module_level_act):
        return module_level_act

    raise RuntimeError("agent.py must define Agent.act(observation) or act(observation)")


def main() -> int:
    agent_path = Path(os.environ.get("HOWLHOUSE_AGENT_PATH", "/agent/agent.py"))

    try:
        act_fn = _load_agent_callable(agent_path)
    except Exception as exc:
        _emit({"type": "error", "message": f"init_error: {exc}"})
        return 1

    while True:
        raw = sys.stdin.readline()
        if not raw:
            break

        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            _emit({"type": "error", "message": "invalid_json"})
            continue

        message_type = str(message.get("type", ""))

        if message_type == "init":
            _emit({"type": "init_ok"})
            continue

        if message_type != "act":
            _emit({"type": "error", "message": "unknown_message_type"})
            continue

        observation = message.get("observation")
        if not isinstance(observation, dict):
            _emit({"type": "error", "message": "invalid_observation"})
            continue

        try:
            action = act_fn(observation)
        except Exception as exc:  # pragma: no cover - executed in child process
            _emit({"type": "error", "message": f"act_error: {exc}"})
            continue

        if action is None:
            action = {}
        if not isinstance(action, dict):
            _emit({"type": "error", "message": "action_must_be_object"})
            continue

        _emit({"type": "act_result", "action": action})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
