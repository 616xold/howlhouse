from __future__ import annotations

from collections import defaultdict
from typing import Any

from howlhouse.platform.store import AgentMatchResultRecord, MatchStore


def _expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def compute_leaderboard(
    *,
    initial_rating: int,
    k_factor: int,
    rows: list[AgentMatchResultRecord],
) -> list[dict[str, Any]]:
    ratings: dict[str, float] = {}
    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"games": 0, "wins": 0, "losses": 0})

    rows_by_match: dict[str, list[AgentMatchResultRecord]] = defaultdict(list)
    for row in rows:
        rows_by_match[row.match_id].append(row)
        ratings.setdefault(row.agent_id, float(initial_rating))
        stats[row.agent_id]["games"] += 1
        stats[row.agent_id]["wins"] += int(row.won)
        stats[row.agent_id]["losses"] += int(1 - row.won)

    for match_id in sorted(rows_by_match.keys()):
        match_rows = rows_by_match[match_id]
        town_agents = sorted({row.agent_id for row in match_rows if row.team == "town"})
        wolf_agents = sorted({row.agent_id for row in match_rows if row.team == "werewolves"})

        town_rating = (
            sum(ratings[agent_id] for agent_id in town_agents) / len(town_agents)
            if town_agents
            else float(initial_rating)
        )
        wolf_rating = (
            sum(ratings[agent_id] for agent_id in wolf_agents) / len(wolf_agents)
            if wolf_agents
            else float(initial_rating)
        )

        expected_town = _expected_score(town_rating, wolf_rating)
        winning_team = match_rows[0].winning_team
        actual_town = 1.0 if winning_team == "town" else 0.0

        delta_town = float(k_factor) * (actual_town - expected_town)
        delta_wolves = -delta_town

        if town_agents:
            per_agent_delta = delta_town / max(1, len(town_agents))
            for agent_id in town_agents:
                ratings[agent_id] += per_agent_delta

        if wolf_agents:
            per_agent_delta = delta_wolves / max(1, len(wolf_agents))
            for agent_id in wolf_agents:
                ratings[agent_id] += per_agent_delta

    entries = [
        {
            "agent_id": agent_id,
            "rating": ratings.get(agent_id, float(initial_rating)),
            "games": stats[agent_id]["games"],
            "wins": stats[agent_id]["wins"],
            "losses": stats[agent_id]["losses"],
        }
        for agent_id in sorted(ratings.keys())
    ]
    entries.sort(
        key=lambda entry: (-float(entry["rating"]), -int(entry["games"]), str(entry["agent_id"]))
    )
    return entries


def compute_agent_profile(
    *,
    store: MatchStore,
    season_id: str,
    agent_id: str,
    recent_limit: int = 10,
) -> dict[str, Any]:
    season = store.get_season(season_id)
    if season is None:
        raise KeyError(season_id)

    season_rows = store.list_agent_match_results_for_season(season_id)
    leaderboard = compute_leaderboard(
        initial_rating=season.initial_rating,
        k_factor=season.k_factor,
        rows=season_rows,
    )
    entry = next((item for item in leaderboard if item["agent_id"] == agent_id), None)
    if entry is None:
        entry = {
            "agent_id": agent_id,
            "rating": float(season.initial_rating),
            "games": 0,
            "wins": 0,
            "losses": 0,
        }

    recent_rows = store.list_agent_match_results_for_agent(season_id, agent_id, recent_limit)
    recent_matches = [
        {
            "match_id": row.match_id,
            "won": bool(row.won),
            "team": row.team,
            "winning_team": row.winning_team,
            "link": f"/matches/{row.match_id}",
        }
        for row in recent_rows
    ]

    return {
        "season_id": season_id,
        "agent_id": agent_id,
        "rating": round(float(entry["rating"]), 2),
        "games": int(entry["games"]),
        "wins": int(entry["wins"]),
        "losses": int(entry["losses"]),
        "recent_matches": recent_matches,
    }
