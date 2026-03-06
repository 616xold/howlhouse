import io
import json
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from howlhouse.api.app import create_app
from howlhouse.core.config import Settings
from howlhouse.engine.domain.models import GameConfig
from howlhouse.league.tournament import derive_game_seed, derive_tournament_match_id

ADMIN_HEADERS = {"X-HowlHouse-Admin": "ops-secret"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{db_path}",
        data_dir=str(tmp_path / "data"),
        sandbox_allow_local_fallback=True,
        admin_tokens="ops-secret",
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _build_agent_zip(token: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr(
            "agent.py",
            (f'def act(observation):\n    return {{"confessional": "{token}"}}\n'),
        )
        zip_file.writestr(
            "AGENT.md",
            (f"# Agent\n\n## HowlHouse Strategy\nPlay as {token} with deterministic discipline.\n"),
        )
    return buffer.getvalue()


def _upload_agent(client: TestClient, name: str, token: str) -> dict:
    response = client.post(
        "/agents",
        data={"name": name, "version": "1.0.0", "runtime_type": "local_py_v1"},
        files={"file": (f"{name}.zip", _build_agent_zip(token), "application/zip")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_active_season(client: TestClient, name: str = "League Season") -> dict:
    response = client.post(
        "/seasons",
        json={
            "name": name,
            "initial_rating": 1200,
            "k_factor": 32,
            "activate": True,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_season_leaderboard_updates_after_season_match(client: TestClient):
    agent_a = _upload_agent(client, "Alpha", "alpha")
    agent_b = _upload_agent(client, "Bravo", "bravo")
    season = _create_active_season(client)

    roster = [
        {
            "player_id": "p0",
            "agent_type": "registered",
            "agent_id": agent_a["agent_id"],
            "name": "Alpha Agent",
        },
        {
            "player_id": "p1",
            "agent_type": "registered",
            "agent_id": agent_b["agent_id"],
            "name": "Bravo Agent",
        },
        {"player_id": "p2", "agent_type": "scripted"},
        {"player_id": "p3", "agent_type": "scripted"},
        {"player_id": "p4", "agent_type": "scripted"},
        {"player_id": "p5", "agent_type": "scripted"},
        {"player_id": "p6", "agent_type": "scripted"},
    ]

    create_match_response = client.post(
        "/matches",
        json={
            "seed": 606,
            "agent_set": "scripted",
            "season_id": season["season_id"],
            "roster": roster,
        },
    )
    assert create_match_response.status_code == 200, create_match_response.text
    match = create_match_response.json()
    assert match["season_id"] == season["season_id"]

    run_response = client.post(f"/matches/{match['match_id']}/run?sync=true")
    assert run_response.status_code == 200, run_response.text
    assert run_response.json()["status"] == "finished"

    leaderboard_a = client.get(f"/seasons/{season['season_id']}/leaderboard")
    leaderboard_b = client.get(f"/seasons/{season['season_id']}/leaderboard")
    assert leaderboard_a.status_code == 200
    assert leaderboard_b.status_code == 200
    assert leaderboard_a.json() == leaderboard_b.json()

    entries = leaderboard_a.json()["entries"]
    entries_by_agent = {entry["agent_id"]: entry for entry in entries}
    for agent_id in [agent_a["agent_id"], agent_b["agent_id"]]:
        assert agent_id in entries_by_agent
        entry = entries_by_agent[agent_id]
        assert entry["games"] >= 1
        assert entry["wins"] + entry["losses"] == entry["games"]
        assert isinstance(entry["rating"], float | int)


def test_seasons_list_active_first(client: TestClient):
    active = _create_active_season(client, name="Season Active")
    archived_response = client.post(
        "/seasons",
        json={
            "name": "Season Archived",
            "initial_rating": 1200,
            "k_factor": 32,
            "activate": False,
        },
    )
    assert archived_response.status_code == 200, archived_response.text

    listed = client.get("/seasons")
    assert listed.status_code == 200, listed.text
    payload = listed.json()
    assert payload
    assert payload[0]["season_id"] == active["season_id"]
    assert payload[0]["status"] == "active"


def test_tournament_end_to_end(client: TestClient):
    season = _create_active_season(client, name="Cup Season")
    agent_a = _upload_agent(client, "CupAlpha", "cup_alpha")
    agent_b = _upload_agent(client, "CupBravo", "cup_bravo")

    create_tournament = client.post(
        "/tournaments",
        json={
            "season_id": season["season_id"],
            "name": "Weekly Cup 1",
            "seed": 777,
            "participant_agent_ids": [agent_a["agent_id"], agent_b["agent_id"]],
            "games_per_matchup": 1,
        },
    )
    assert create_tournament.status_code == 200, create_tournament.text
    tournament = create_tournament.json()

    run = client.post(f"/tournaments/{tournament['tournament_id']}/run?sync=true")
    assert run.status_code == 200, run.text
    ran = run.json()
    assert ran["status"] == "completed"
    assert ran["champion_agent_id"] in {agent_a["agent_id"], agent_b["agent_id"]}

    bracket = ran["bracket"]
    game_match_ids: list[str] = []
    for round_payload in bracket["rounds"]:
        for matchup in round_payload["matchups"]:
            for game in matchup["games"]:
                if isinstance(game.get("match_id"), str) and game["match_id"]:
                    game_match_ids.append(game["match_id"])

    assert game_match_ids, "Expected tournament bracket to include underlying match ids"
    match_id = game_match_ids[0]

    match_response = client.get(f"/matches/{match_id}")
    assert match_response.status_code == 200, match_response.text

    replay_response = client.get(
        f"/matches/{match_id}/replay?visibility=all", headers=ADMIN_HEADERS
    )
    assert replay_response.status_code == 200, replay_response.text
    events = [json.loads(line) for line in replay_response.text.splitlines() if line.strip()]
    assert any(event["type"] == "match_ended" for event in events)


def test_tournament_async_run_returns_running(client: TestClient):
    season = _create_active_season(client, name="Async Season")
    agent_a = _upload_agent(client, "AsyncAlpha", "async_alpha")
    agent_b = _upload_agent(client, "AsyncBravo", "async_bravo")

    create_tournament = client.post(
        "/tournaments",
        json={
            "season_id": season["season_id"],
            "name": "Async Cup",
            "seed": 404,
            "participant_agent_ids": [agent_a["agent_id"], agent_b["agent_id"]],
            "games_per_matchup": 1,
        },
    )
    assert create_tournament.status_code == 200, create_tournament.text
    tournament_id = create_tournament.json()["tournament_id"]

    run_response = client.post(f"/tournaments/{tournament_id}/run?sync=false")
    assert run_response.status_code == 200, run_response.text
    assert run_response.json()["status"] == "running"

    job_worker = client.app.state.job_worker
    for _ in range(120):
        job_worker.run_once()
        current = client.get(f"/tournaments/{tournament_id}")
        assert current.status_code == 200, current.text
        if current.json()["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)
    else:
        pytest.fail("tournament did not reach terminal status in time")


def test_tournament_rerun_reuses_existing_finished_game(client: TestClient):
    season = _create_active_season(client, name="Rerun Season")
    agent_a = _upload_agent(client, "ReuseAlpha", "reuse_alpha")
    agent_b = _upload_agent(client, "ReuseBravo", "reuse_bravo")

    create_tournament = client.post(
        "/tournaments",
        json={
            "season_id": season["season_id"],
            "name": "Rerun Cup",
            "seed": 909,
            "participant_agent_ids": [agent_a["agent_id"], agent_b["agent_id"]],
            "games_per_matchup": 1,
        },
    )
    assert create_tournament.status_code == 200, create_tournament.text
    tournament = create_tournament.json()
    tournament_id = tournament["tournament_id"]
    matchup_id = tournament["bracket"]["rounds"][0]["matchups"][0]["matchup_id"]

    seed = derive_game_seed(
        tournament_seed=tournament["seed"],
        tournament_id=tournament_id,
        matchup_id=matchup_id,
        game_index=1,
    )
    match_id = derive_tournament_match_id(
        tournament_id=tournament_id,
        matchup_id=matchup_id,
        game_index=1,
        seed=seed,
    )
    cfg = GameConfig(rng_seed=seed)
    names = {f"p{i}": f"p{i}" for i in range(cfg.player_count)}
    names["p0"] = "ReuseAlpha"
    names["p1"] = "ReuseBravo"

    store = client.app.state.store
    store.create_match_if_missing(
        match_id=match_id,
        seed=seed,
        agent_set="scripted",
        config_json=json.dumps(cfg.__dict__, sort_keys=True, ensure_ascii=False),
        names_json=json.dumps(names, sort_keys=True, ensure_ascii=False),
        replay_path=f"replays/{match_id}.jsonl",
        season_id=season["season_id"],
        tournament_id=tournament_id,
    )
    store.set_match_players(
        match_id,
        [
            {"player_id": "p0", "agent_type": "registered", "agent_id": agent_a["agent_id"]},
            {"player_id": "p1", "agent_type": "registered", "agent_id": agent_b["agent_id"]},
            {"player_id": "p2", "agent_type": "scripted", "agent_id": None},
            {"player_id": "p3", "agent_type": "scripted", "agent_id": None},
            {"player_id": "p4", "agent_type": "scripted", "agent_id": None},
            {"player_id": "p5", "agent_type": "scripted", "agent_id": None},
            {"player_id": "p6", "agent_type": "scripted", "agent_id": None},
        ],
    )
    store.mark_finished(match_id, winner="town", replay_path=f"replays/{match_id}.jsonl")
    store.upsert_agent_match_results(
        [
            {
                "match_id": match_id,
                "season_id": season["season_id"],
                "tournament_id": tournament_id,
                "agent_id": agent_a["agent_id"],
                "player_id": "p0",
                "role": "villager",
                "team": "town",
                "winning_team": "town",
                "won": 1,
                "died": 0,
                "death_t": 1_000_000_000,
                "votes_against": 0,
                "votes_cast": 1,
            },
            {
                "match_id": match_id,
                "season_id": season["season_id"],
                "tournament_id": tournament_id,
                "agent_id": agent_b["agent_id"],
                "player_id": "p1",
                "role": "werewolf",
                "team": "werewolves",
                "winning_team": "town",
                "won": 0,
                "died": 1,
                "death_t": 42,
                "votes_against": 2,
                "votes_cast": 1,
            },
        ]
    )

    failed = store.upsert_tournament(
        tournament_id=tournament_id,
        season_id=season["season_id"],
        name=tournament["name"],
        seed=tournament["seed"],
        status="failed",
        bracket=tournament["bracket"],
        champion_agent_id=None,
        error="simulated_failure",
    )
    assert failed.status == "failed"

    run_response = client.post(f"/tournaments/{tournament_id}/run?sync=true")
    assert run_response.status_code == 200, run_response.text
    completed = run_response.json()
    assert completed["status"] == "completed"
    game = completed["bracket"]["rounds"][0]["matchups"][0]["games"][0]
    assert game["match_id"] == match_id
