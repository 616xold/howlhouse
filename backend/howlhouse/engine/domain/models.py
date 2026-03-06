from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .enums import Role


@dataclass(frozen=True)
class GameConfig:
    # MVP ruleset: 7 players (2W/1S/1D/3V)
    player_count: int = 7
    werewolves: int = 2
    seers: int = 1
    doctors: int = 1
    villagers: int = 3

    # Spectator-optimized constraints
    public_message_char_limit: int = 360
    public_messages_per_player_per_round: int = 1  # Round A and Round B each
    day_rounds: int = 2  # A + B

    # Determinism
    rng_seed: int = 0


@dataclass
class PlayerState:
    player_id: str
    name: str
    role: Role
    alive: bool = True

    # private knowledge
    known: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PublicMessage:
    player_id: str
    text: str


@dataclass(frozen=True)
class Vote:
    voter_id: str
    target_id: str


@dataclass(frozen=True)
class NightAction:
    actor_id: str
    action: Literal["kill", "inspect", "protect"]
    target_id: str
