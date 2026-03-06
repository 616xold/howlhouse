from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from opentelemetry import trace

from howlhouse.engine.domain.models import GameConfig
from howlhouse.platform.observability import increment_tournaments_run
from howlhouse.platform.store import (
    AgentMatchResultRecord,
    MatchStore,
    TournamentRecord,
)

if TYPE_CHECKING:  # pragma: no cover
    from howlhouse.platform.runner import MatchRunner

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def _stable_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def derive_tournament_id(
    *,
    season_id: str,
    name: str,
    seed: int,
    participant_agent_ids: list[str],
    games_per_matchup: int,
) -> str:
    payload = {
        "season_id": season_id,
        "name": name,
        "seed": int(seed),
        "participant_agent_ids": sorted(participant_agent_ids),
        "games_per_matchup": int(games_per_matchup),
    }
    digest = hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()[:10]
    return f"tourn_{digest}"


def derive_game_seed(
    *, tournament_seed: int, tournament_id: str, matchup_id: str, game_index: int
) -> int:
    material = f"{tournament_seed}:{tournament_id}:{matchup_id}:{game_index}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % 2_147_483_647


def derive_tournament_match_id(
    *,
    tournament_id: str,
    matchup_id: str,
    game_index: int,
    seed: int,
) -> str:
    payload = {
        "tournament_id": tournament_id,
        "matchup_id": matchup_id,
        "game_index": game_index,
        "seed": seed,
    }
    digest = hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()[:16]
    return f"match_t_{digest}"


def _seeded_participants(
    *,
    participant_agent_ids: list[str],
    ratings_by_agent: dict[str, float],
) -> list[dict[str, Any]]:
    ordered = sorted(
        participant_agent_ids,
        key=lambda agent_id: (-ratings_by_agent.get(agent_id, 0.0), agent_id),
    )
    return [
        {"agent_id": agent_id, "seed_rank": index}
        for index, agent_id in enumerate(ordered, start=1)
    ]


def _fresh_games(games_per_matchup: int) -> list[dict[str, Any]]:
    return [
        {
            "game_index": game_index,
            "seed": None,
            "match_id": None,
            "winner_agent_id": None,
            "winning_team": None,
        }
        for game_index in range(1, games_per_matchup + 1)
    ]


def _build_round_matchups(
    *,
    slots: list[str | None],
    round_number: int,
    games_per_matchup: int,
) -> tuple[list[dict[str, Any]], list[str | None]]:
    matchups: list[dict[str, Any]] = []
    next_round_slots: list[str | None] = []

    for offset in range(0, len(slots), 2):
        agent_a = slots[offset]
        agent_b = slots[offset + 1] if offset + 1 < len(slots) else None
        matchup_id = f"r{round_number}m{(offset // 2) + 1}"

        if agent_a is None and agent_b is None:
            winner_agent_id = None
            games: list[dict[str, Any]] = []
        elif agent_a is None:
            winner_agent_id = agent_b
            games = []
        elif agent_b is None:
            winner_agent_id = agent_a
            games = []
        else:
            winner_agent_id = None
            games = _fresh_games(games_per_matchup)

        matchups.append(
            {
                "matchup_id": matchup_id,
                "agent_a": agent_a,
                "agent_b": agent_b,
                "games": games,
                "winner_agent_id": winner_agent_id,
            }
        )
        next_round_slots.append(winner_agent_id)

    return matchups, next_round_slots


def generate_bracket(
    *,
    tournament_id: str,
    season_id: str,
    seed: int,
    participant_agent_ids: list[str],
    ratings_by_agent: dict[str, float],
    games_per_matchup: int,
) -> dict[str, Any]:
    participants = _seeded_participants(
        participant_agent_ids=participant_agent_ids,
        ratings_by_agent=ratings_by_agent,
    )
    current_slots: list[str | None] = [entry["agent_id"] for entry in participants]
    rounds: list[dict[str, Any]] = []
    round_number = 1

    while len(current_slots) > 1:
        round_matchups, next_slots = _build_round_matchups(
            slots=current_slots,
            round_number=round_number,
            games_per_matchup=games_per_matchup,
        )
        rounds.append({"round": round_number, "matchups": round_matchups})
        current_slots = next_slots
        round_number += 1

    champion_agent_id = current_slots[0] if len(current_slots) == 1 else None
    return {
        "v": 1,
        "tournament_id": tournament_id,
        "season_id": season_id,
        "seed": int(seed),
        "games_per_matchup": int(games_per_matchup),
        "participants": participants,
        "rounds": rounds,
        "champion_agent_id": champion_agent_id,
    }


def _reset_bracket_for_rerun(bracket: dict[str, Any]) -> dict[str, Any]:
    reset = json.loads(_stable_json(bracket))
    games_per_matchup = int(reset.get("games_per_matchup", 3))

    for round_payload in reset.get("rounds", []):
        matchups = round_payload.get("matchups", [])
        if not isinstance(matchups, list):
            continue
        for matchup in matchups:
            if not isinstance(matchup, dict):
                continue
            agent_a = matchup.get("agent_a")
            agent_b = matchup.get("agent_b")

            if isinstance(agent_a, str) and isinstance(agent_b, str):
                matchup["winner_agent_id"] = None
                matchup["games"] = _fresh_games(games_per_matchup)
            elif isinstance(agent_a, str):
                matchup["winner_agent_id"] = agent_a
                matchup["games"] = []
            elif isinstance(agent_b, str):
                matchup["winner_agent_id"] = agent_b
                matchup["games"] = []
            else:
                matchup["winner_agent_id"] = None
                matchup["games"] = []

    reset["champion_agent_id"] = None
    participants = reset.get("participants", [])
    if (
        isinstance(participants, list)
        and len(participants) == 1
        and isinstance(participants[0], dict)
    ):
        only_agent = participants[0].get("agent_id")
        if isinstance(only_agent, str):
            reset["champion_agent_id"] = only_agent
    return reset


def _pick_game_winner(
    *,
    rows_by_agent: dict[str, AgentMatchResultRecord],
    agent_a: str,
    agent_b: str,
) -> str:
    def _key(agent_id: str) -> tuple[int, int, int, int, str]:
        row = rows_by_agent[agent_id]
        alive = 1 if row.died == 0 else 0
        return (
            int(row.won),
            alive,
            int(row.death_t),
            -int(row.votes_against),
            agent_id,
        )

    return sorted([agent_a, agent_b], key=_key, reverse=True)[0]


def _resolve_matchup_winner(
    *,
    game_wins: dict[str, int],
    metrics: dict[str, dict[str, int]],
    agent_a: str,
    agent_b: str,
) -> str:
    if game_wins[agent_a] > game_wins[agent_b]:
        return agent_a
    if game_wins[agent_b] > game_wins[agent_a]:
        return agent_b

    def _metric_key(agent_id: str) -> tuple[int, int, int, int, str]:
        data = metrics[agent_id]
        return (
            int(data["team_win_count"]),
            int(data["alive_count"]),
            int(data["sum_death_t"]),
            -int(data["sum_votes_against"]),
            agent_id,
        )

    return sorted([agent_a, agent_b], key=_metric_key, reverse=True)[0]


def _run_tournament_game(
    *,
    store: MatchStore,
    match_runner: MatchRunner,
    tournament: TournamentRecord,
    season_id: str,
    matchup_id: str,
    game_index: int,
    agent_a: str,
    agent_b: str,
    agent_name_by_id: dict[str, str],
) -> dict[str, Any]:
    seed = derive_game_seed(
        tournament_seed=tournament.seed,
        tournament_id=tournament.tournament_id,
        matchup_id=matchup_id,
        game_index=game_index,
    )
    match_id = derive_tournament_match_id(
        tournament_id=tournament.tournament_id,
        matchup_id=matchup_id,
        game_index=game_index,
        seed=seed,
    )

    config = GameConfig(rng_seed=seed)
    names = {f"p{i}": f"p{i}" for i in range(config.player_count)}
    names["p0"] = agent_name_by_id[agent_a]
    names["p1"] = agent_name_by_id[agent_b]

    match_record = store.create_match_if_missing(
        match_id=match_id,
        seed=seed,
        agent_set="scripted",
        config_json=json.dumps(asdict(config), sort_keys=True, ensure_ascii=False),
        names_json=json.dumps(names, sort_keys=True, ensure_ascii=False),
        replay_path=f"replays/{match_id}.jsonl",
        season_id=season_id,
        tournament_id=tournament.tournament_id,
    )
    store.set_match_players(
        match_id,
        [
            {"player_id": "p0", "agent_type": "registered", "agent_id": agent_a},
            {"player_id": "p1", "agent_type": "registered", "agent_id": agent_b},
            {"player_id": "p2", "agent_type": "scripted", "agent_id": None},
            {"player_id": "p3", "agent_type": "scripted", "agent_id": None},
            {"player_id": "p4", "agent_type": "scripted", "agent_id": None},
            {"player_id": "p5", "agent_type": "scripted", "agent_id": None},
            {"player_id": "p6", "agent_type": "scripted", "agent_id": None},
        ],
    )

    current_match = store.get_match(match_id)
    if current_match is None:
        raise RuntimeError(f"missing tournament game match record: {match_id}")

    if current_match.status == "finished":
        result_rows = match_runner.ensure_registered_agent_results(match_id)
    else:
        ran_record = match_runner.run(match_record.match_id, sync=True)
        if ran_record.status != "finished":
            raise RuntimeError(f"tournament game did not finish: {match_id} ({ran_record.status})")
        result_rows = match_runner.ensure_registered_agent_results(match_id)
    row_by_agent = {row.agent_id: row for row in result_rows if row.agent_id in {agent_a, agent_b}}
    if agent_a not in row_by_agent or agent_b not in row_by_agent:
        raise RuntimeError(f"missing agent match results for tournament game {match_id}")

    winner_agent_id = _pick_game_winner(
        rows_by_agent=row_by_agent, agent_a=agent_a, agent_b=agent_b
    )
    winning_team = row_by_agent[agent_a].winning_team

    metrics_by_agent = {
        agent_a: {
            "team_win_count": int(row_by_agent[agent_a].won),
            "alive_count": 1 if row_by_agent[agent_a].died == 0 else 0,
            "sum_death_t": int(row_by_agent[agent_a].death_t),
            "sum_votes_against": int(row_by_agent[agent_a].votes_against),
        },
        agent_b: {
            "team_win_count": int(row_by_agent[agent_b].won),
            "alive_count": 1 if row_by_agent[agent_b].died == 0 else 0,
            "sum_death_t": int(row_by_agent[agent_b].death_t),
            "sum_votes_against": int(row_by_agent[agent_b].votes_against),
        },
    }

    return {
        "seed": seed,
        "match_id": match_id,
        "winner_agent_id": winner_agent_id,
        "winning_team": winning_team,
        "metrics_by_agent": metrics_by_agent,
    }


def run_tournament_sync(
    *,
    store: MatchStore,
    match_runner: MatchRunner,
    tournament_id: str,
) -> TournamentRecord:
    with tracer.start_as_current_span("tournament.run_sync") as span:
        span.set_attribute("tournament_id", tournament_id)
        tournament = store.get_tournament(tournament_id)
        if tournament is None:
            raise KeyError(tournament_id)

        bracket = tournament.bracket
        if tournament.status == "failed":
            bracket = _reset_bracket_for_rerun(bracket)

        tournament = store.upsert_tournament(
            tournament_id=tournament.tournament_id,
            season_id=tournament.season_id,
            name=tournament.name,
            seed=tournament.seed,
            status="running",
            bracket=bracket,
            champion_agent_id=None,
            error=None,
        )

        agent_name_by_id = {record.agent_id: record.name for record in store.list_agents()}

        try:
            rounds = bracket.get("rounds", [])
            if not isinstance(rounds, list):
                raise ValueError("tournament bracket rounds must be a list")
            games_per_matchup = int(bracket.get("games_per_matchup", 3))
            if games_per_matchup <= 0:
                raise ValueError("games_per_matchup must be positive")

            if not rounds:
                champion = bracket.get("champion_agent_id")
                if champion is None:
                    participants = bracket.get("participants", [])
                    if isinstance(participants, list) and len(participants) == 1:
                        first = participants[0]
                        if isinstance(first, dict):
                            champion = first.get("agent_id")
                completed = store.upsert_tournament(
                    tournament_id=tournament.tournament_id,
                    season_id=tournament.season_id,
                    name=tournament.name,
                    seed=tournament.seed,
                    status="completed",
                    bracket=bracket,
                    champion_agent_id=str(champion) if champion else None,
                    error=None,
                )
                increment_tournaments_run("completed")
                logger.info(
                    "tournament_run_finished",
                    extra={
                        "tournament_id": tournament_id,
                        "status": "completed",
                    },
                )
                return completed

            for round_index, round_payload in enumerate(rounds):
                matchups = round_payload.get("matchups", [])
                if not isinstance(matchups, list):
                    raise ValueError("tournament round matchups must be a list")

                for matchup in matchups:
                    if not isinstance(matchup, dict):
                        continue
                    agent_a = matchup.get("agent_a")
                    agent_b = matchup.get("agent_b")

                    if not isinstance(agent_a, str) and not isinstance(agent_b, str):
                        matchup["winner_agent_id"] = None
                        matchup["games"] = []
                        continue
                    if isinstance(agent_a, str) and not isinstance(agent_b, str):
                        matchup["winner_agent_id"] = agent_a
                        matchup["games"] = []
                        continue
                    if isinstance(agent_b, str) and not isinstance(agent_a, str):
                        matchup["winner_agent_id"] = agent_b
                        matchup["games"] = []
                        continue

                    assert isinstance(agent_a, str)
                    assert isinstance(agent_b, str)

                    if agent_a not in agent_name_by_id or agent_b not in agent_name_by_id:
                        raise ValueError(
                            f"unknown agent in tournament matchup: {agent_a}, {agent_b}"
                        )

                    matchup["games"] = _fresh_games(games_per_matchup)
                    matchup_id = str(matchup.get("matchup_id", ""))
                    game_wins = {agent_a: 0, agent_b: 0}
                    metrics = {
                        agent_a: {
                            "team_win_count": 0,
                            "alive_count": 0,
                            "sum_death_t": 0,
                            "sum_votes_against": 0,
                        },
                        agent_b: {
                            "team_win_count": 0,
                            "alive_count": 0,
                            "sum_death_t": 0,
                            "sum_votes_against": 0,
                        },
                    }

                    for game_index in range(1, games_per_matchup + 1):
                        game_result = _run_tournament_game(
                            store=store,
                            match_runner=match_runner,
                            tournament=tournament,
                            season_id=tournament.season_id,
                            matchup_id=matchup_id,
                            game_index=game_index,
                            agent_a=agent_a,
                            agent_b=agent_b,
                            agent_name_by_id=agent_name_by_id,
                        )
                        game_winner = str(game_result["winner_agent_id"])
                        game_wins[game_winner] += 1

                        metrics_by_agent = game_result["metrics_by_agent"]
                        for agent_id in [agent_a, agent_b]:
                            metrics[agent_id]["team_win_count"] += int(
                                metrics_by_agent[agent_id]["team_win_count"]
                            )
                            metrics[agent_id]["alive_count"] += int(
                                metrics_by_agent[agent_id]["alive_count"]
                            )
                            metrics[agent_id]["sum_death_t"] += int(
                                metrics_by_agent[agent_id]["sum_death_t"]
                            )
                            metrics[agent_id]["sum_votes_against"] += int(
                                metrics_by_agent[agent_id]["sum_votes_against"]
                            )

                        matchup["games"][game_index - 1] = {
                            "game_index": game_index,
                            "seed": int(game_result["seed"]),
                            "match_id": str(game_result["match_id"]),
                            "winner_agent_id": game_winner,
                            "winning_team": str(game_result["winning_team"]),
                        }

                    matchup["winner_agent_id"] = _resolve_matchup_winner(
                        game_wins=game_wins,
                        metrics=metrics,
                        agent_a=agent_a,
                        agent_b=agent_b,
                    )

                if round_index + 1 < len(rounds):
                    next_round = rounds[round_index + 1]
                    next_matchups = next_round.get("matchups", [])
                    if isinstance(next_matchups, list):
                        winners = [
                            matchup.get("winner_agent_id") if isinstance(matchup, dict) else None
                            for matchup in matchups
                        ]
                        for next_index, next_matchup in enumerate(next_matchups):
                            if not isinstance(next_matchup, dict):
                                continue
                            agent_a = (
                                winners[next_index * 2] if next_index * 2 < len(winners) else None
                            )
                            agent_b = (
                                winners[next_index * 2 + 1]
                                if (next_index * 2 + 1) < len(winners)
                                else None
                            )
                            next_matchup["agent_a"] = agent_a
                            next_matchup["agent_b"] = agent_b
                            if isinstance(agent_a, str) and isinstance(agent_b, str):
                                next_matchup["winner_agent_id"] = None
                                next_matchup["games"] = _fresh_games(games_per_matchup)
                            elif isinstance(agent_a, str):
                                next_matchup["winner_agent_id"] = agent_a
                                next_matchup["games"] = []
                            elif isinstance(agent_b, str):
                                next_matchup["winner_agent_id"] = agent_b
                                next_matchup["games"] = []
                            else:
                                next_matchup["winner_agent_id"] = None
                                next_matchup["games"] = []

                tournament = store.upsert_tournament(
                    tournament_id=tournament.tournament_id,
                    season_id=tournament.season_id,
                    name=tournament.name,
                    seed=tournament.seed,
                    status="running",
                    bracket=bracket,
                    champion_agent_id=None,
                    error=None,
                )

            final_round = rounds[-1] if rounds else {"matchups": []}
            final_matchups = (
                final_round.get("matchups", []) if isinstance(final_round, dict) else []
            )
            champion_agent_id = None
            if isinstance(final_matchups, list) and final_matchups:
                first = final_matchups[0]
                if isinstance(first, dict):
                    winner = first.get("winner_agent_id")
                    if isinstance(winner, str):
                        champion_agent_id = winner

            bracket["champion_agent_id"] = champion_agent_id
            completed = store.upsert_tournament(
                tournament_id=tournament.tournament_id,
                season_id=tournament.season_id,
                name=tournament.name,
                seed=tournament.seed,
                status="completed",
                bracket=bracket,
                champion_agent_id=champion_agent_id,
                error=None,
            )
            increment_tournaments_run("completed")
            logger.info(
                "tournament_run_finished",
                extra={
                    "tournament_id": tournament_id,
                    "status": "completed",
                },
            )
            return completed
        except Exception as exc:  # pragma: no cover - defensive
            increment_tournaments_run("failed")
            logger.exception(
                "tournament_run_failed",
                extra={
                    "tournament_id": tournament_id,
                    "status": "failed",
                },
            )
            failed = store.upsert_tournament(
                tournament_id=tournament.tournament_id,
                season_id=tournament.season_id,
                name=tournament.name,
                seed=tournament.seed,
                status="failed",
                bracket=bracket,
                champion_agent_id=None,
                error=str(exc),
            )
            return failed


class TournamentRunner:
    def __init__(self, *, store: MatchStore, match_runner: MatchRunner):
        self.store = store
        self.match_runner = match_runner
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def run(self, tournament_id: str, *, sync: bool = False) -> TournamentRecord:
        record = self.store.get_tournament(tournament_id)
        if record is None:
            raise KeyError(tournament_id)

        if record.status == "running":
            raise ValueError(f"tournament {tournament_id} is already running")
        if record.status == "completed":
            raise ValueError(f"tournament {tournament_id} already completed")

        if sync:
            increment_tournaments_run("running")
            logger.info(
                "tournament_run_started",
                extra={
                    "tournament_id": tournament_id,
                    "status": "running",
                },
            )
            return run_tournament_sync(
                store=self.store,
                match_runner=self.match_runner,
                tournament_id=tournament_id,
            )

        bracket = (
            _reset_bracket_for_rerun(record.bracket)
            if record.status == "failed"
            else record.bracket
        )
        running_record = self.store.upsert_tournament(
            tournament_id=record.tournament_id,
            season_id=record.season_id,
            name=record.name,
            seed=record.seed,
            status="running",
            bracket=bracket,
            champion_agent_id=None,
            error=None,
        )
        increment_tournaments_run("running")
        logger.info(
            "tournament_run_started",
            extra={
                "tournament_id": tournament_id,
                "status": "running",
            },
        )

        with self._lock:
            active = self._threads.get(tournament_id)
            if active is not None and active.is_alive():
                raise ValueError(f"tournament {tournament_id} is already running")
            thread = threading.Thread(
                target=self._run_job,
                args=(tournament_id,),
                daemon=True,
                name=f"tournament-runner-{tournament_id}",
            )
            self._threads[tournament_id] = thread
            thread.start()

        return running_record

    def _run_job(self, tournament_id: str) -> None:
        run_tournament_sync(
            store=self.store,
            match_runner=self.match_runner,
            tournament_id=tournament_id,
        )
