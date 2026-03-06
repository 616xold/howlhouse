from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from howlhouse.engine.domain.models import NightAction, PublicMessage, Vote
from howlhouse.engine.runtime.observation import Observation


@dataclass(frozen=True)
class AgentAction:
    public_message: PublicMessage | None = None
    vote: Vote | None = None
    night_action: NightAction | None = None
    confessional: str | None = None
    debug: dict[str, Any] | None = None


class Agent(Protocol):
    """An agent is a pure function of an observation -> action.

    Agents MUST:
    - respect quotas (the engine enforces; but agent should not spam)
    - return quickly (timeouts enforced by runner in later milestones)
    """

    def act(self, obs: Observation) -> AgentAction: ...
