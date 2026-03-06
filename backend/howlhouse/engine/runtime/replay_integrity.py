from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from howlhouse.engine.domain.enums import Role


@dataclass(frozen=True)
class ReplayOutcome:
    match_id: str
    winning_team: str
    alive_players: list[str]
    wolves_alive: int
    town_alive: int


def derive_replay_outcome(events: Iterable[dict[str, Any]]) -> ReplayOutcome:
    event_list = list(events)
    if not event_list:
        raise ValueError("Cannot derive replay outcome from an empty event stream")

    match_id = event_list[0]["match_id"]
    alive_players: set[str] = set()
    role_map: dict[str, str] = {}
    winner_from_match_end: str | None = None

    for event in event_list:
        event_type = event["type"]
        payload = event.get("payload", {})

        if event_type == "match_created":
            roster = payload.get("roster", [])
            alive_players = {
                item["player_id"]
                for item in roster
                if isinstance(item, dict) and isinstance(item.get("player_id"), str)
            }
            continue

        if event_type == "roles_assigned":
            roles = payload.get("roles", {})
            role_map = {
                str(player_id): str(role)
                for player_id, role in roles.items()
                if isinstance(player_id, str)
            }
            if not alive_players:
                alive_players = set(role_map.keys())
            continue

        if event_type in {"player_killed", "player_eliminated"}:
            player_id = payload.get("player_id")
            if isinstance(player_id, str):
                alive_players.discard(player_id)
            continue

        if event_type == "match_ended":
            winner_value = payload.get("winning_team")
            if isinstance(winner_value, str):
                winner_from_match_end = winner_value

    wolves_alive = sum(
        1 for player_id in alive_players if role_map.get(player_id) == Role.WEREWOLF.value
    )
    town_alive = sum(
        1 for player_id in alive_players if role_map.get(player_id) != Role.WEREWOLF.value
    )

    winner_recomputed: str | None = None
    if role_map:
        if wolves_alive == 0:
            winner_recomputed = "town"
        elif wolves_alive >= town_alive:
            winner_recomputed = "werewolves"

    if winner_from_match_end and winner_recomputed and winner_from_match_end != winner_recomputed:
        msg = (
            "Replay winner mismatch between match_ended and recomputed state: "
            f"{winner_from_match_end!r} != {winner_recomputed!r}"
        )
        raise ValueError(msg)

    winning_team = winner_from_match_end or winner_recomputed
    if winning_team is None:
        raise ValueError("Replay did not contain enough information to derive a winner")

    return ReplayOutcome(
        match_id=match_id,
        winning_team=winning_team,
        alive_players=sorted(alive_players),
        wolves_alive=wolves_alive,
        town_alive=town_alive,
    )


def derive_winner_from_events(events: Iterable[dict[str, Any]]) -> str:
    return derive_replay_outcome(events).winning_team
