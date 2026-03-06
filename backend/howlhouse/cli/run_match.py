from __future__ import annotations

import argparse
import random
from pathlib import Path

from howlhouse.engine.domain.models import GameConfig
from howlhouse.engine.runtime.agents.scripted import RandomScriptedAgent
from howlhouse.engine.runtime.game_engine import GameEngine
from howlhouse.engine.runtime.io.replay import write_jsonl
from howlhouse.engine.runtime.replay_integrity import derive_replay_outcome


def _derive_agent_seed(base_seed: int, player_index: int) -> int:
    return ((base_seed + 1) * 10007 + player_index * 97) & 0xFFFFFFFF


def build_scripted_agents(
    cfg: GameConfig, player_ids: list[str] | None = None
) -> dict[str, RandomScriptedAgent]:
    agents: dict[str, RandomScriptedAgent] = {}
    selected_ids = player_ids or [f"p{i}" for i in range(cfg.player_count)]
    for player_id in selected_ids:
        if not player_id.startswith("p"):
            raise ValueError(f"Invalid player_id for scripted agent: {player_id}")
        index = int(player_id[1:])
        seed = _derive_agent_seed(cfg.rng_seed, index)
        agents[player_id] = RandomScriptedAgent(rng=random.Random(seed))
    return agents


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default=None)
    parser.add_argument("--agents", type=str, default="scripted", choices=["scripted"])
    args = parser.parse_args()

    cfg = GameConfig(rng_seed=args.seed)
    engine = GameEngine(cfg)

    if args.agents == "scripted":
        agents = build_scripted_agents(cfg)
    else:
        raise ValueError("Unsupported agent set")

    result = engine.run_match(agents=agents)
    out_path = Path(args.out) if args.out else Path("./replays") / f"{result.match_id}.jsonl"
    write_jsonl(out_path, result.events)

    replay_outcome = derive_replay_outcome(result.events)
    print(f"Wrote replay: {out_path} (match_id={result.match_id})")
    print(
        "Winner: "
        f"{result.winning_team} | Events: {len(result.events)} | "
        f"Alive at end: {','.join(replay_outcome.alive_players) or 'none'}"
    )


if __name__ == "__main__":
    main()
