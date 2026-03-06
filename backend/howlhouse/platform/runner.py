from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import Counter
from pathlib import Path
from typing import Any

from opentelemetry import trace

from howlhouse.cli.run_match import build_scripted_agents
from howlhouse.core.config import Settings
from howlhouse.engine.domain.models import GameConfig
from howlhouse.engine.runtime.game_engine import GameEngine
from howlhouse.engine.runtime.replay_integrity import derive_replay_outcome
from howlhouse.platform.blob_store import BlobStore
from howlhouse.platform.event_bus import EventBus
from howlhouse.platform.observability import increment_matches_run
from howlhouse.platform.sandbox import SandboxAgentProxy, create_registered_agent_proxy
from howlhouse.platform.store import (
    AgentMatchResultRecord,
    MatchRecord,
    MatchStore,
    parse_json_lines,
)
from howlhouse.recap import generate_recap, generate_share_cards

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class MatchRunner:
    def __init__(
        self,
        *,
        settings: Settings,
        store: MatchStore,
        blob_store: BlobStore,
        bus: EventBus,
        replay_dir: Path,
    ):
        self.settings = settings
        self.store = store
        self.blob_store = blob_store
        self.bus = bus
        self.replay_dir = replay_dir
        self.replay_dir.mkdir(parents=True, exist_ok=True)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread_id: int | None = None
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._loop_thread_id = threading.get_ident()

    def run(self, match_id: str, *, sync: bool = False, allow_running: bool = False) -> MatchRecord:
        match = self.store.get_match(match_id)
        if match is None:
            raise KeyError(match_id)

        if match.status == "running" and not allow_running:
            return match
        if match.status == "finished":
            return match
        if match.status not in {"created", "failed", "running"}:
            raise ValueError(f"match {match_id} cannot run from status {match.status!r}")

        if match.status != "running":
            self.store.mark_running(match_id)
            increment_matches_run("running")
            logger.info(
                "match_run_started",
                extra={
                    "match_id": match_id,
                    "seed": match.seed,
                    "status": "running",
                },
            )

        if sync:
            self._run_job(match_id)
            updated = self.store.get_match(match_id)
            if updated is None:
                raise KeyError(match_id)
            return updated

        with self._lock:
            existing_thread = self._threads.get(match_id)
            if existing_thread is not None and existing_thread.is_alive():
                updated = self.store.get_match(match_id)
                if updated is None:
                    raise KeyError(match_id)
                return updated

            thread = threading.Thread(
                target=self._run_job,
                args=(match_id,),
                daemon=True,
                name=f"match-runner-{match_id}",
            )
            self._threads[match_id] = thread
            thread.start()

        updated = self.store.get_match(match_id)
        if updated is None:
            raise KeyError(match_id)
        return updated

    def _run_job(self, match_id: str) -> None:
        match = self.store.get_match(match_id)
        if match is None:
            return

        replay_path = self._resolve_replay_path(match.replay_path, match_id)
        replay_path.parent.mkdir(parents=True, exist_ok=True)
        bus_closed = False
        managed_agents: list[SandboxAgentProxy] = []

        with tracer.start_as_current_span("match_runner.run_job") as span:
            span.set_attribute("match_id", match_id)
            span.set_attribute("seed", match.seed)
            try:
                config = GameConfig(**match.config)
                engine = GameEngine(config)
                agents, managed_agents = self._build_agents(match=match, cfg=config)
                names = match.names

                with replay_path.open("w", encoding="utf-8") as replay_file:

                    def on_event(event: dict[str, Any]) -> None:
                        line = json.dumps(event, sort_keys=True, ensure_ascii=False)
                        replay_file.write(line + "\n")
                        replay_file.flush()
                        self._call_bus(self.bus.publish, match_id, line)

                    result = engine.run_match(
                        agents=agents,
                        names=names,
                        on_event=on_event,
                        match_id=match_id,
                    )

                replay_bytes = replay_path.read_bytes()
                replay_key = self._replay_blob_key(match_id)
                self.blob_store.put_bytes(
                    replay_key, replay_bytes, content_type="application/x-ndjson"
                )
                finished_match = self.store.mark_finished(
                    match_id,
                    winner=result.winning_team,
                    replay_path=str(replay_path),
                    replay_key=replay_key,
                    replay_uri=self.blob_store.uri_for_key(replay_key),
                )
                increment_matches_run("finished")
                logger.info(
                    "match_run_finished",
                    extra={
                        "match_id": match_id,
                        "seed": match.seed,
                        "status": "finished",
                    },
                )
                self._call_bus(self.bus.close, match_id)
                bus_closed = True
                postprocess_errors: list[str] = []
                events: list[dict[str, Any]] | None = None
                try:
                    events = parse_json_lines(
                        line
                        for line in replay_bytes.decode("utf-8").splitlines(keepends=False)
                        if line.strip()
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    logger.exception(
                        "match_postprocess_events_parse_failed",
                        extra={"match_id": match_id, "reason": str(exc)},
                    )
                    postprocess_errors.append(f"events_parse: {exc}")

                if events is not None:
                    try:
                        recap = generate_recap(events)
                        share_card_public_path, share_card_spoilers_path = generate_share_cards(
                            match_id=match_id,
                            recap=recap,
                            output_dir=Path.cwd() / "replays" / "share_cards",
                        )
                        recap_key = self._recap_blob_key(match_id)
                        share_card_public_key = self._share_card_blob_key(match_id, "public")
                        share_card_spoilers_key = self._share_card_blob_key(match_id, "spoilers")
                        self.blob_store.put_text(
                            recap_key, json.dumps(recap, sort_keys=True, ensure_ascii=False)
                        )
                        self.blob_store.put_bytes(
                            share_card_public_key,
                            Path(share_card_public_path).read_bytes(),
                            content_type="image/png",
                        )
                        self.blob_store.put_bytes(
                            share_card_spoilers_key,
                            Path(share_card_spoilers_path).read_bytes(),
                            content_type="image/png",
                        )
                        self.store.upsert_recap(
                            match_id=match_id,
                            recap=recap,
                            share_card_public_path=share_card_public_path,
                            share_card_spoilers_path=share_card_spoilers_path,
                            recap_key=recap_key,
                            share_card_public_key=share_card_public_key,
                            share_card_spoilers_key=share_card_spoilers_key,
                        )
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.exception(
                            "match_postprocess_recap_failed",
                            extra={"match_id": match_id, "reason": str(exc)},
                        )
                        postprocess_errors.append(f"recap_artifacts: {exc}")

                    try:
                        self._ingest_registered_agent_results(match=finished_match, events=events)
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.exception(
                            "match_postprocess_agent_results_failed",
                            extra={"match_id": match_id, "reason": str(exc)},
                        )
                        postprocess_errors.append(f"agent_results: {exc}")

                if postprocess_errors:
                    merged_error = " | ".join(postprocess_errors)[:2000]
                    try:
                        self.store.mark_postprocess_error(match_id, error=merged_error)
                    except Exception:  # pragma: no cover - best effort state update
                        logger.exception(
                            "match_postprocess_error_persist_failed",
                            extra={"match_id": match_id},
                        )
            except Exception as exc:  # pragma: no cover - defensive
                increment_matches_run("failed")
                logger.exception(
                    "match_run_failed",
                    extra={
                        "match_id": match_id,
                        "seed": match.seed,
                        "status": "failed",
                    },
                )
                self.store.mark_failed(match_id, error=str(exc), replay_path=str(replay_path))
            finally:
                for agent in managed_agents:
                    try:
                        agent.close()
                    except Exception:  # pragma: no cover - cleanup safety
                        logger.exception("failed to close sandbox agent for %s", match_id)
                if not bus_closed:
                    self._call_bus(self.bus.close, match_id)

    def _build_agents(
        self,
        *,
        match: MatchRecord,
        cfg: GameConfig,
    ) -> tuple[dict[str, Any], list[SandboxAgentProxy]]:
        if match.agent_set != "scripted":
            raise ValueError(f"Unsupported agent_set: {match.agent_set}")

        roster_rows = {row.player_id: row for row in self.store.list_match_players(match.match_id)}
        agents: dict[str, Any] = {}
        managed_agents: list[SandboxAgentProxy] = []
        scripted_player_ids: list[str] = []

        for player_index in range(cfg.player_count):
            player_id = f"p{player_index}"
            roster_row = roster_rows.get(player_id)
            if roster_row is None or roster_row.agent_type == "scripted":
                scripted_player_ids.append(player_id)
                continue

            if roster_row.agent_type != "registered":
                raise ValueError(f"Unsupported agent_type for {player_id}: {roster_row.agent_type}")
            if not roster_row.agent_id:
                raise ValueError(f"registered roster row missing agent_id for {player_id}")

            agent_record = self.store.get_agent(roster_row.agent_id)
            if agent_record is None:
                raise ValueError(f"Unknown agent_id {roster_row.agent_id} for {player_id}")

            proxy = create_registered_agent_proxy(
                settings=self.settings,
                runtime_type=agent_record.runtime_type,
                package_path=agent_record.package_path,
                entrypoint=agent_record.entrypoint,
                match_id=match.match_id,
                player_id=player_id,
                seed=cfg.rng_seed,
                config=cfg,
            )
            agents[player_id] = proxy
            managed_agents.append(proxy)

        agents.update(build_scripted_agents(cfg, scripted_player_ids))
        return agents, managed_agents

    def _resolve_replay_path(self, replay_path: str | None, match_id: str) -> Path:
        path = Path(replay_path) if replay_path else self.replay_dir / f"{match_id}.jsonl"
        if path.is_absolute():
            return path
        return Path.cwd() / path

    @staticmethod
    def _replay_blob_key(match_id: str) -> str:
        return f"matches/{match_id}/replay.jsonl"

    @staticmethod
    def _recap_blob_key(match_id: str) -> str:
        return f"matches/{match_id}/recap.json"

    @staticmethod
    def _share_card_blob_key(match_id: str, visibility: str) -> str:
        return f"matches/{match_id}/share_card_{visibility}.png"

    def ensure_registered_agent_results(self, match_id: str) -> list[AgentMatchResultRecord]:
        match = self.store.get_match(match_id)
        if match is None:
            raise KeyError(match_id)

        roster_rows = [
            row
            for row in self.store.list_match_players(match.match_id)
            if row.agent_type == "registered" and row.agent_id
        ]
        if not roster_rows:
            return []

        existing = self.store.list_agent_match_results_for_match(match_id)
        expected_players = {row.player_id for row in roster_rows}
        if expected_players.issubset({row.player_id for row in existing}):
            return existing

        replay_path = self._resolve_replay_path(match.replay_path, match_id)
        if replay_path.exists():
            replay_lines = replay_path.read_text(encoding="utf-8").splitlines(keepends=False)
        elif match.replay_key and self.blob_store.exists(match.replay_key):
            replay_lines = self.blob_store.get_text(match.replay_key).splitlines(keepends=False)
        else:
            raise RuntimeError(f"replay file missing for match {match_id}: {replay_path}")
        events = parse_json_lines(line for line in replay_lines if line.strip())
        self._ingest_registered_agent_results(match=match, events=events)
        return self.store.list_agent_match_results_for_match(match_id)

    def _call_bus(self, fn, *args) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            fn(*args)
            return

        if threading.get_ident() == self._loop_thread_id:
            fn(*args)
            return

        done = threading.Event()

        def wrapped() -> None:
            try:
                fn(*args)
            finally:
                done.set()

        loop.call_soon_threadsafe(wrapped)
        done.wait(timeout=5)

    def _ingest_registered_agent_results(
        self, *, match: MatchRecord, events: list[dict[str, Any]]
    ) -> None:
        roster_rows = [
            row
            for row in self.store.list_match_players(match.match_id)
            if row.agent_type == "registered" and row.agent_id
        ]
        if not roster_rows:
            return

        roles_by_player: dict[str, str] = {}
        death_t_by_player: dict[str, int] = {}
        votes_cast = Counter()
        votes_against = Counter()
        winning_team = match.winner or self._winning_team_from_events(events)

        for event in events:
            event_type = str(event.get("type", ""))
            payload = event.get("payload", {})
            if not isinstance(payload, dict):
                continue

            if event_type == "roles_assigned":
                raw_roles = payload.get("roles")
                if isinstance(raw_roles, dict):
                    roles_by_player = {
                        str(player_id): str(role)
                        for player_id, role in raw_roles.items()
                        if isinstance(player_id, str)
                    }
                continue

            if event_type in {"player_killed", "player_eliminated"}:
                player_id = payload.get("player_id")
                event_tick = event.get("t")
                if isinstance(player_id, str) and isinstance(event_tick, int):
                    previous = death_t_by_player.get(player_id)
                    if previous is None or event_tick < previous:
                        death_t_by_player[player_id] = event_tick
                continue

            if event_type == "vote_cast":
                voter_id = payload.get("voter_id")
                target_id = payload.get("target_id")
                if isinstance(voter_id, str):
                    votes_cast[voter_id] += 1
                if isinstance(target_id, str):
                    votes_against[target_id] += 1

        result_rows: list[dict[str, Any]] = []
        for roster_row in sorted(roster_rows, key=lambda row: row.player_id):
            player_id = roster_row.player_id
            agent_id = roster_row.agent_id
            if not agent_id:
                continue
            role = roles_by_player.get(player_id, "villager")
            team = "werewolves" if role == "werewolf" else "town"
            won = 1 if team == winning_team else 0
            death_t = death_t_by_player.get(player_id, 1_000_000_000)
            died = 1 if player_id in death_t_by_player else 0
            result_rows.append(
                {
                    "match_id": match.match_id,
                    "season_id": match.season_id,
                    "tournament_id": match.tournament_id,
                    "agent_id": agent_id,
                    "player_id": player_id,
                    "role": role,
                    "team": team,
                    "winning_team": winning_team,
                    "won": won,
                    "died": died,
                    "death_t": death_t,
                    "votes_against": int(votes_against.get(player_id, 0)),
                    "votes_cast": int(votes_cast.get(player_id, 0)),
                }
            )

        self.store.upsert_agent_match_results(result_rows)

    @staticmethod
    def _winning_team_from_events(events: list[dict[str, Any]]) -> str:
        for event in reversed(events):
            if event.get("type") != "match_ended":
                continue
            payload = event.get("payload", {})
            if isinstance(payload, dict):
                value = payload.get("winning_team")
                if isinstance(value, str) and value in {"town", "werewolves"}:
                    return value
        return derive_replay_outcome(events).winning_team
