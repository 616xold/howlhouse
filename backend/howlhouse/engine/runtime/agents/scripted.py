from __future__ import annotations

import random
from dataclasses import dataclass, field

from howlhouse.engine.domain.enums import Phase, Role
from howlhouse.engine.domain.models import NightAction, PublicMessage, Vote
from howlhouse.engine.runtime.agents.base import AgentAction
from howlhouse.engine.runtime.observation import Observation


@dataclass
class RandomScriptedAgent:
    """Deterministic role-aware scripted baseline for M1 tests."""

    rng: random.Random
    last_accusation: str | None = field(default=None, init=False)

    def act(self, obs: Observation) -> AgentAction:
        alive = obs.public_state.get("alive_players", [])
        role = self._read_role(obs)
        confessional = f"{role.value} considering {obs.phase.value}"

        if obs.phase in (Phase.DAY_ROUND_A, Phase.DAY_ROUND_B):
            target = self._pick_day_accusation(obs=obs, role=role, alive=alive)
            text = f"I suspect {target}." if target else "I am still deciding."
            if target is not None:
                self.last_accusation = target
            msg = PublicMessage(player_id=obs.player_id, text=text)
            return AgentAction(public_message=msg, confessional=confessional)

        if obs.phase == Phase.DAY_VOTE:
            target = self._pick_vote_target(obs=obs, role=role, alive=alive)
            if target is None:
                return AgentAction(confessional=confessional)
            return AgentAction(
                vote=Vote(voter_id=obs.player_id, target_id=target), confessional=confessional
            )

        if obs.phase == Phase.NIGHT:
            if role == Role.WEREWOLF:
                target = self._pick_werewolf_kill_target(obs=obs, alive=alive)
                if target is None:
                    return AgentAction(confessional=confessional)
                return AgentAction(
                    night_action=NightAction(
                        actor_id=obs.player_id, action="kill", target_id=target
                    ),
                    confessional=confessional,
                )
            if role == Role.SEER:
                target = self._pick_seer_target(obs=obs, alive=alive)
                if target is None:
                    return AgentAction(confessional=confessional)
                return AgentAction(
                    night_action=NightAction(
                        actor_id=obs.player_id, action="inspect", target_id=target
                    ),
                    confessional=confessional,
                )
            if role == Role.DOCTOR:
                target = self._pick_doctor_target(obs=obs, alive=alive)
                if target is None:
                    return AgentAction(confessional=confessional)
                return AgentAction(
                    night_action=NightAction(
                        actor_id=obs.player_id, action="protect", target_id=target
                    ),
                    confessional=confessional,
                )

        return AgentAction(confessional=confessional)

    def _read_role(self, obs: Observation) -> Role:
        raw_role = obs.private_state.get("role", Role.VILLAGER.value)
        if isinstance(raw_role, Role):
            return raw_role
        try:
            return Role(str(raw_role))
        except ValueError:
            return Role.VILLAGER

    def _pick_werewolf_kill_target(self, obs: Observation, alive: list[str]) -> str | None:
        wolf_ids = set(obs.private_state.get("wolf_ids", []))
        non_wolf_targets = [
            player_id
            for player_id in alive
            if player_id != obs.player_id and player_id not in wolf_ids
        ]
        if non_wolf_targets:
            return self.rng.choice(non_wolf_targets)
        fallback = [player_id for player_id in alive if player_id != obs.player_id]
        if not fallback:
            return None
        return self.rng.choice(fallback)

    def _pick_seer_target(self, obs: Observation, alive: list[str]) -> str | None:
        known = obs.private_state.get("seer_knowledge", {})
        unseen = [
            player_id
            for player_id in alive
            if player_id != obs.player_id and player_id not in known
        ]
        if unseen:
            return self.rng.choice(unseen)
        fallback = [player_id for player_id in alive if player_id != obs.player_id]
        if not fallback:
            return None
        return self.rng.choice(fallback)

    def _pick_doctor_target(self, obs: Observation, alive: list[str]) -> str | None:
        day = int(obs.public_state.get("day", 1))
        if day <= 2 and obs.player_id in alive:
            return obs.player_id

        last_night_death = obs.public_state.get("last_night_death")
        if isinstance(last_night_death, str) and last_night_death in alive:
            return last_night_death

        if not alive:
            return None
        return self.rng.choice(alive)

    def _pick_day_accusation(self, obs: Observation, role: Role, alive: list[str]) -> str | None:
        candidates = [player_id for player_id in alive if player_id != obs.player_id]
        if role == Role.WEREWOLF:
            wolf_ids = set(obs.private_state.get("wolf_ids", []))
            non_wolf_candidates = [
                player_id for player_id in candidates if player_id not in wolf_ids
            ]
            if non_wolf_candidates:
                candidates = non_wolf_candidates
        if not candidates:
            return None
        return self.rng.choice(candidates)

    def _pick_vote_target(self, obs: Observation, role: Role, alive: list[str]) -> str | None:
        if self.last_accusation in alive and self.last_accusation != obs.player_id:
            return self.last_accusation

        candidates = [player_id for player_id in alive if player_id != obs.player_id]
        if role == Role.WEREWOLF:
            wolf_ids = set(obs.private_state.get("wolf_ids", []))
            non_wolf_candidates = [
                player_id for player_id in candidates if player_id not in wolf_ids
            ]
            if non_wolf_candidates:
                candidates = non_wolf_candidates
        if not candidates:
            return None
        return self.rng.choice(candidates)
