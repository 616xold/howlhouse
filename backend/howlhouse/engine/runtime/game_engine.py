from __future__ import annotations

import copy
import logging
import random
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from howlhouse.engine.domain.enums import Phase, Role
from howlhouse.engine.domain.models import GameConfig, PlayerState, Vote
from howlhouse.engine.runtime.agents.base import Agent, AgentAction
from howlhouse.engine.runtime.observation import Observation

SCHEMA_VERSION = 1
RECENT_PUBLIC_EVENT_LIMIT = 50
SYNTHETIC_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
logger = logging.getLogger(__name__)


@dataclass
class DeterministicEventClock:
    tick: int = 0

    def next(self) -> tuple[int, str, str]:
        self.tick += 1
        ts = (SYNTHETIC_EPOCH + timedelta(seconds=self.tick)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return self.tick, f"evt_{self.tick:06d}", ts


@dataclass
class GameState:
    players: dict[str, PlayerState]
    player_order: list[str]
    day: int = 1
    phase: Phase = Phase.SETUP
    seer_knowledge: dict[str, dict[str, bool]] = field(default_factory=dict)
    last_night_death: str | None = None

    def alive_player_ids(self) -> list[str]:
        return [player_id for player_id in self.player_order if self.players[player_id].alive]

    def dead_player_ids(self) -> list[str]:
        return [player_id for player_id in self.player_order if not self.players[player_id].alive]


@dataclass
class MatchResult:
    match_id: str
    winning_team: str  # "town" | "werewolves"
    events: list[dict]


class GameEngine:
    """Deterministic, spectator-first Werewolf engine for M1."""

    def __init__(self, config: GameConfig):
        self.config = config
        self._on_event: Callable[[dict[str, Any]], None] | None = None

    def run_match(
        self,
        agents: dict[str, Agent],
        names: dict[str, str] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        match_id: str | None = None,
    ) -> MatchResult:
        self._on_event = on_event
        try:
            rng = random.Random(self.config.rng_seed)
            resolved_match_id = (
                match_id if match_id is not None else f"match_{self.config.rng_seed}"
            )
            clock = DeterministicEventClock()
            events: list[dict[str, Any]] = []
            state = self._build_initial_state(rng=rng, names=names or {})

            self._emit(
                events=events,
                clock=clock,
                match_id=resolved_match_id,
                event_type="match_created",
                visibility="public",
                payload={
                    "config": asdict(self.config),
                    "roster": [
                        {"player_id": player_id, "name": state.players[player_id].name}
                        for player_id in state.player_order
                    ],
                },
            )
            self._emit(
                events=events,
                clock=clock,
                match_id=resolved_match_id,
                event_type="roles_assigned",
                visibility="private:all",
                payload={
                    "roles": {
                        player_id: state.players[player_id].role.value
                        for player_id in state.player_order
                    }
                },
            )

            state.phase = Phase.SETUP
            self._emit_phase_started(
                events=events,
                clock=clock,
                match_id=resolved_match_id,
                state=state,
            )

            winning_team: str | None = None
            while winning_team is None:
                state.phase = Phase.NIGHT
                self._emit_phase_started(
                    events=events,
                    clock=clock,
                    match_id=resolved_match_id,
                    state=state,
                )
                self._run_night_phase(
                    state=state,
                    agents=agents,
                    match_id=resolved_match_id,
                    events=events,
                    clock=clock,
                )
                winning_team = self._check_win_and_emit(
                    state=state,
                    events=events,
                    clock=clock,
                    match_id=resolved_match_id,
                )
                if winning_team is not None:
                    break

                state.phase = Phase.DAY_ROUND_A
                self._emit_phase_started(
                    events=events,
                    clock=clock,
                    match_id=resolved_match_id,
                    state=state,
                    round_label="A",
                )
                self._run_day_round_phase(
                    state=state,
                    agents=agents,
                    match_id=resolved_match_id,
                    events=events,
                    clock=clock,
                    round_label="A",
                )

                state.phase = Phase.DAY_ROUND_B
                self._emit_phase_started(
                    events=events,
                    clock=clock,
                    match_id=resolved_match_id,
                    state=state,
                    round_label="B",
                )
                self._run_day_round_phase(
                    state=state,
                    agents=agents,
                    match_id=resolved_match_id,
                    events=events,
                    clock=clock,
                    round_label="B",
                )

                state.phase = Phase.DAY_VOTE
                self._emit_phase_started(
                    events=events,
                    clock=clock,
                    match_id=resolved_match_id,
                    state=state,
                )
                self._run_day_vote_phase(
                    state=state,
                    agents=agents,
                    match_id=resolved_match_id,
                    events=events,
                    clock=clock,
                    rng=rng,
                )
                winning_team = self._check_win_and_emit(
                    state=state,
                    events=events,
                    clock=clock,
                    match_id=resolved_match_id,
                )
                if winning_team is None:
                    state.day += 1

            return MatchResult(
                match_id=resolved_match_id,
                winning_team=winning_team,
                events=events,
            )
        finally:
            self._on_event = None

    def _build_initial_state(self, rng: random.Random, names: dict[str, str]) -> GameState:
        role_pool = (
            [Role.WEREWOLF] * self.config.werewolves
            + [Role.SEER] * self.config.seers
            + [Role.DOCTOR] * self.config.doctors
            + [Role.VILLAGER] * self.config.villagers
        )
        if len(role_pool) != self.config.player_count:
            msg = (
                "Role counts must sum to player_count; got "
                f"{len(role_pool)} roles for player_count={self.config.player_count}"
            )
            raise ValueError(msg)

        player_order = [f"p{i}" for i in range(self.config.player_count)]
        shuffled_players = list(player_order)
        rng.shuffle(shuffled_players)
        role_map = {
            player_id: role for player_id, role in zip(shuffled_players, role_pool, strict=True)
        }

        players = {
            player_id: PlayerState(
                player_id=player_id,
                name=names.get(player_id, player_id),
                role=role_map[player_id],
                alive=True,
            )
            for player_id in player_order
        }
        seer_knowledge = {
            player_id: {} for player_id in player_order if players[player_id].role == Role.SEER
        }
        return GameState(players=players, player_order=player_order, seer_knowledge=seer_knowledge)

    def _emit(
        self,
        *,
        events: list[dict[str, Any]],
        clock: DeterministicEventClock,
        match_id: str,
        event_type: str,
        visibility: str,
        payload: dict[str, Any],
    ) -> None:
        t, event_id, ts = clock.next()
        event = {
            "v": SCHEMA_VERSION,
            "id": event_id,
            "t": t,
            "ts": ts,
            "match_id": match_id,
            "type": event_type,
            "visibility": visibility,
            "payload": payload,
        }
        events.append(event)
        if self._on_event is not None:
            try:
                self._on_event(copy.deepcopy(event))
            except Exception:  # pragma: no cover - callback safety
                logger.exception("on_event callback failed; continuing")

    def _emit_phase_started(
        self,
        *,
        events: list[dict[str, Any]],
        clock: DeterministicEventClock,
        match_id: str,
        state: GameState,
        round_label: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"phase": state.phase.value, "day": state.day}
        if round_label is not None:
            payload["round"] = round_label
        self._emit(
            events=events,
            clock=clock,
            match_id=match_id,
            event_type="phase_started",
            visibility="public",
            payload=payload,
        )

    def _run_night_phase(
        self,
        *,
        state: GameState,
        agents: dict[str, Agent],
        match_id: str,
        events: list[dict[str, Any]],
        clock: DeterministicEventClock,
    ) -> None:
        alive_players = state.alive_player_ids()
        wolf_kill_proposals: list[str] = []
        doctor_protect_proposals: list[str] = []
        seer_inspections: list[tuple[str, str]] = []

        for player_id in alive_players:
            action = self._agent_action(
                state=state,
                agents=agents,
                events=events,
                match_id=match_id,
                player_id=player_id,
            )
            self._emit_confessional_if_present(
                state=state,
                action=action,
                player_id=player_id,
                match_id=match_id,
                events=events,
                clock=clock,
            )
            role = state.players[player_id].role
            if role == Role.WEREWOLF:
                target = self._validated_night_target(
                    proposed=action.night_action,
                    actor_id=player_id,
                    expected_action="kill",
                    allow_self=False,
                    alive_players=alive_players,
                )
                if target is None:
                    target = self._default_wolf_target(state=state, actor_id=player_id)
                wolf_kill_proposals.append(target)
                self._emit(
                    events=events,
                    clock=clock,
                    match_id=match_id,
                    event_type="night_action",
                    visibility="private:role:werewolf",
                    payload={
                        "actor_id": player_id,
                        "action": "kill",
                        "target_id": target,
                        "day": state.day,
                    },
                )
                continue

            if role == Role.SEER:
                target = self._validated_night_target(
                    proposed=action.night_action,
                    actor_id=player_id,
                    expected_action="inspect",
                    allow_self=False,
                    alive_players=alive_players,
                )
                if target is None:
                    target = self._default_seer_target(state=state, seer_id=player_id)
                seer_inspections.append((player_id, target))
                self._emit(
                    events=events,
                    clock=clock,
                    match_id=match_id,
                    event_type="night_action",
                    visibility=f"private:player:{player_id}",
                    payload={
                        "actor_id": player_id,
                        "action": "inspect",
                        "target_id": target,
                        "day": state.day,
                    },
                )
                continue

            if role == Role.DOCTOR:
                target = self._validated_night_target(
                    proposed=action.night_action,
                    actor_id=player_id,
                    expected_action="protect",
                    allow_self=True,
                    alive_players=alive_players,
                )
                if target is None:
                    target = self._default_doctor_target(state=state, doctor_id=player_id)
                doctor_protect_proposals.append(target)
                self._emit(
                    events=events,
                    clock=clock,
                    match_id=match_id,
                    event_type="night_action",
                    visibility=f"private:player:{player_id}",
                    payload={
                        "actor_id": player_id,
                        "action": "protect",
                        "target_id": target,
                        "day": state.day,
                    },
                )

        kill_target = self._majority_target(wolf_kill_proposals)
        protect_target = self._majority_target(doctor_protect_proposals)
        state.last_night_death = None

        for seer_id, target_id in seer_inspections:
            is_wolf = state.players[target_id].role == Role.WEREWOLF
            state.seer_knowledge.setdefault(seer_id, {})[target_id] = is_wolf
            self._emit(
                events=events,
                clock=clock,
                match_id=match_id,
                event_type="night_action",
                visibility=f"private:player:{seer_id}",
                payload={
                    "actor_id": seer_id,
                    "action": "inspect_result",
                    "target_id": target_id,
                    "target_role_is_wolf": is_wolf,
                    "day": state.day,
                },
            )

        if kill_target is not None and kill_target != protect_target:
            state.players[kill_target].alive = False
            state.last_night_death = kill_target
            self._emit(
                events=events,
                clock=clock,
                match_id=match_id,
                event_type="player_killed",
                visibility="public",
                payload={"player_id": kill_target, "day": state.day, "prevented": False},
            )

    def _run_day_round_phase(
        self,
        *,
        state: GameState,
        agents: dict[str, Agent],
        match_id: str,
        events: list[dict[str, Any]],
        clock: DeterministicEventClock,
        round_label: str,
    ) -> None:
        message_count_by_player = Counter()
        for player_id in state.alive_player_ids():
            action = self._agent_action(
                state=state,
                agents=agents,
                events=events,
                match_id=match_id,
                player_id=player_id,
            )
            self._emit_confessional_if_present(
                state=state,
                action=action,
                player_id=player_id,
                match_id=match_id,
                events=events,
                clock=clock,
            )
            message = action.public_message
            if message is None:
                continue
            if (
                message_count_by_player[player_id]
                >= self.config.public_messages_per_player_per_round
            ):
                continue
            text = str(message.text or "")
            if not text:
                continue
            text = text[: self.config.public_message_char_limit]
            self._emit(
                events=events,
                clock=clock,
                match_id=match_id,
                event_type="public_message",
                visibility="public",
                payload={
                    "player_id": player_id,
                    "text": text,
                    "day": state.day,
                    "round": round_label,
                },
            )
            message_count_by_player[player_id] += 1

    def _run_day_vote_phase(
        self,
        *,
        state: GameState,
        agents: dict[str, Agent],
        match_id: str,
        events: list[dict[str, Any]],
        clock: DeterministicEventClock,
        rng: random.Random,
    ) -> None:
        alive_players = state.alive_player_ids()
        votes: dict[str, str] = {}

        for voter_id in alive_players:
            action = self._agent_action(
                state=state,
                agents=agents,
                events=events,
                match_id=match_id,
                player_id=voter_id,
            )
            self._emit_confessional_if_present(
                state=state,
                action=action,
                player_id=voter_id,
                match_id=match_id,
                events=events,
                clock=clock,
            )
            target_id = self._validated_vote_target(
                proposed_vote=action.vote,
                voter_id=voter_id,
                alive_players=alive_players,
            )
            if target_id is None:
                target_id = self._default_vote_target(
                    voter_id=voter_id, alive_players=alive_players
                )
            votes[voter_id] = target_id
            self._emit(
                events=events,
                clock=clock,
                match_id=match_id,
                event_type="vote_cast",
                visibility="public",
                payload={"voter_id": voter_id, "target_id": target_id, "day": state.day},
            )

        tally = {player_id: 0 for player_id in alive_players}
        for target_id in votes.values():
            tally[target_id] += 1

        top_vote_count = max(tally.values())
        tied_targets = [player_id for player_id, count in tally.items() if count == top_vote_count]
        if len(tied_targets) == 1:
            eliminated_id = tied_targets[0]
        else:
            eliminated_id = rng.choice(sorted(tied_targets))

        self._emit(
            events=events,
            clock=clock,
            match_id=match_id,
            event_type="vote_result",
            visibility="public",
            payload={"day": state.day, "tally": tally, "eliminated": eliminated_id},
        )
        self._emit(
            events=events,
            clock=clock,
            match_id=match_id,
            event_type="player_eliminated",
            visibility="public",
            payload={"player_id": eliminated_id, "day": state.day},
        )
        state.players[eliminated_id].alive = False

    def _check_win_and_emit(
        self,
        *,
        state: GameState,
        events: list[dict[str, Any]],
        clock: DeterministicEventClock,
        match_id: str,
    ) -> str | None:
        wolves_alive = [
            player_id
            for player_id in state.alive_player_ids()
            if state.players[player_id].role == Role.WEREWOLF
        ]
        town_alive = [
            player_id
            for player_id in state.alive_player_ids()
            if state.players[player_id].role != Role.WEREWOLF
        ]

        winning_team: str | None = None
        reason: str | None = None
        if not wolves_alive:
            winning_team = "town"
            reason = "all_werewolves_eliminated"
        elif len(wolves_alive) >= len(town_alive):
            winning_team = "werewolves"
            reason = "werewolves_reached_parity"

        if winning_team is None or reason is None:
            return None

        state.phase = Phase.GAME_OVER
        self._emit_phase_started(events=events, clock=clock, match_id=match_id, state=state)
        self._emit(
            events=events,
            clock=clock,
            match_id=match_id,
            event_type="match_ended",
            visibility="public",
            payload={"winning_team": winning_team, "reason": reason, "day": state.day},
        )
        return winning_team

    def _agent_action(
        self,
        *,
        state: GameState,
        agents: dict[str, Agent],
        events: list[dict[str, Any]],
        match_id: str,
        player_id: str,
    ) -> AgentAction:
        obs = self._build_observation(
            state=state,
            match_id=match_id,
            player_id=player_id,
            events=events,
        )
        agent = agents.get(player_id)
        if agent is None:
            return AgentAction()
        try:
            action = agent.act(obs)
        except Exception:  # pragma: no cover - agent safety
            logger.exception("agent.act raised for player_id=%s; falling back to no-op", player_id)
            return AgentAction()
        return action if action is not None else AgentAction()

    def _build_observation(
        self,
        *,
        state: GameState,
        match_id: str,
        player_id: str,
        events: list[dict[str, Any]],
    ) -> Observation:
        player_state = state.players[player_id]
        private_state: dict[str, Any] = {"role": player_state.role.value}

        if player_state.role == Role.SEER:
            known = state.seer_knowledge.get(player_id, {})
            private_state["seer_knowledge"] = {
                target_id: known[target_id] for target_id in sorted(known.keys())
            }
        if player_state.role == Role.WEREWOLF:
            private_state["wolf_ids"] = [
                candidate_id
                for candidate_id in state.player_order
                if state.players[candidate_id].role == Role.WEREWOLF
            ]

        public_state = {
            "day": state.day,
            "alive_players": state.alive_player_ids(),
            "dead_players": state.dead_player_ids(),
            "last_night_death": state.last_night_death,
        }

        recent_public_events = [
            copy.deepcopy(event) for event in events if event["visibility"] == "public"
        ][-RECENT_PUBLIC_EVENT_LIMIT:]

        return Observation(
            match_id=match_id,
            phase=state.phase,
            player_id=player_id,
            public_state=copy.deepcopy(public_state),
            private_state=copy.deepcopy(private_state),
            recent_events=recent_public_events,
        )

    def _emit_confessional_if_present(
        self,
        *,
        state: GameState,
        action: AgentAction,
        player_id: str,
        match_id: str,
        events: list[dict[str, Any]],
        clock: DeterministicEventClock,
    ) -> None:
        if not action.confessional:
            return
        self._emit(
            events=events,
            clock=clock,
            match_id=match_id,
            event_type="confessional",
            visibility=f"private:player:{player_id}",
            payload={
                "player_id": player_id,
                "phase": state.phase.value,
                "day": state.day,
                "text": action.confessional,
            },
        )

    def _validated_night_target(
        self,
        *,
        proposed: Any,
        actor_id: str,
        expected_action: str,
        allow_self: bool,
        alive_players: list[str],
    ) -> str | None:
        if proposed is None:
            return None
        if proposed.actor_id != actor_id:
            return None
        if proposed.action != expected_action:
            return None
        target_id = proposed.target_id
        if target_id not in alive_players:
            return None
        if not allow_self and target_id == actor_id:
            return None
        return target_id

    def _validated_vote_target(
        self,
        *,
        proposed_vote: Vote | None,
        voter_id: str,
        alive_players: list[str],
    ) -> str | None:
        if proposed_vote is None:
            return None
        if proposed_vote.voter_id != voter_id:
            return None
        target_id = proposed_vote.target_id
        if target_id not in alive_players:
            return None
        if target_id == voter_id and len(alive_players) > 1:
            return None
        return target_id

    def _majority_target(self, targets: list[str]) -> str | None:
        if not targets:
            return None
        tally = Counter(targets)
        top_count = max(tally.values())
        tied_targets = [target_id for target_id, count in tally.items() if count == top_count]
        return sorted(tied_targets)[0]

    def _default_wolf_target(self, *, state: GameState, actor_id: str) -> str:
        alive = state.alive_player_ids()
        wolf_ids = [
            player_id for player_id in alive if state.players[player_id].role == Role.WEREWOLF
        ]
        candidates = [player_id for player_id in alive if player_id not in wolf_ids]
        if not candidates:
            candidates = [player_id for player_id in alive if player_id != actor_id]
        if not candidates:
            return actor_id
        return candidates[0]

    def _default_seer_target(self, *, state: GameState, seer_id: str) -> str:
        alive = state.alive_player_ids()
        known = state.seer_knowledge.get(seer_id, {})
        candidates = [
            player_id for player_id in alive if player_id != seer_id and player_id not in known
        ]
        if not candidates:
            candidates = [player_id for player_id in alive if player_id != seer_id]
        if not candidates:
            return seer_id
        return candidates[0]

    def _default_doctor_target(self, *, state: GameState, doctor_id: str) -> str:
        if state.day <= 2 and doctor_id in state.alive_player_ids():
            return doctor_id
        if state.last_night_death and state.players[state.last_night_death].alive:
            return state.last_night_death
        alive = state.alive_player_ids()
        if not alive:
            return doctor_id
        return alive[0]

    def _default_vote_target(self, *, voter_id: str, alive_players: list[str]) -> str:
        candidates = [player_id for player_id in alive_players if player_id != voter_id]
        if not candidates:
            return voter_id
        return candidates[0]
