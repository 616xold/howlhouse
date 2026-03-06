from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class Event:
    v: int
    id: str
    t: int  # synthetic deterministic tick
    ts: str  # ISO UTC timestamp
    match_id: str
    type: str
    visibility: str
    payload: dict[str, Any]


# Suggested event type strings (M1)
EventType = Literal[
    "match_created",
    "roles_assigned",
    "phase_started",
    "public_message",
    "vote_cast",
    "vote_result",
    "night_action",
    "player_killed",
    "player_eliminated",
    "confessional",
    "match_ended",
]
