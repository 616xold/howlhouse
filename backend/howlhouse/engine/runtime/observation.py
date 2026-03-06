from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from howlhouse.engine.domain.enums import Phase


@dataclass(frozen=True)
class Observation:
    match_id: str
    phase: Phase
    player_id: str
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    # Recent public transcript slice (already filtered to public)
    recent_events: list[dict[str, Any]]
