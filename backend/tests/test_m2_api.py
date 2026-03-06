import json

import pytest
from fastapi.testclient import TestClient

from howlhouse.api.app import create_app
from howlhouse.core.config import Settings
from howlhouse.engine.domain.models import GameConfig
from howlhouse.engine.runtime.agents.base import AgentAction
from howlhouse.engine.runtime.game_engine import GameEngine
from howlhouse.engine.runtime.observation import Observation
from howlhouse.engine.runtime.replay_integrity import derive_replay_outcome


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    settings = Settings(env="test", database_url=f"sqlite:///{db_path}")
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _create_match(client: TestClient, seed: int = 123) -> dict:
    response = client.post("/matches", json={"seed": seed, "agent_set": "scripted"})
    assert response.status_code == 200
    return response.json()


def _run_match_sync(client: TestClient, match_id: str) -> dict:
    response = client.post(f"/matches/{match_id}/run?sync=true")
    assert response.status_code == 200
    return response.json()


def _read_replay_events(client: TestClient, match_id: str, visibility: str = "all") -> list[dict]:
    response = client.get(f"/matches/{match_id}/replay?visibility={visibility}")
    assert response.status_code == 200
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_create_match_idempotent(client: TestClient):
    created_a = _create_match(client, seed=555)
    created_b = _create_match(client, seed=555)

    assert created_a["match_id"] == created_b["match_id"] == "match_555"
    assert {
        "recap",
        "share_card_public",
        "share_card_spoilers",
    }.issubset(set(created_a["links"].keys()))

    listed = client.get("/matches")
    assert listed.status_code == 200
    records = listed.json()
    assert len(records) == 1


def test_run_sync_writes_replay_and_updates_status(client: TestClient):
    created = _create_match(client, seed=123)
    match_id = created["match_id"]

    run_result = _run_match_sync(client, match_id)
    assert run_result["status"] == "finished"
    assert run_result["winner"] in {"town", "werewolves"}

    fetched = client.get(f"/matches/{match_id}")
    assert fetched.status_code == 200
    fetched_record = fetched.json()
    assert fetched_record["status"] == "finished"
    assert fetched_record["winner"] == run_result["winner"]

    events = _read_replay_events(client, match_id)
    assert any(event["type"] == "match_ended" for event in events)

    replay_outcome = derive_replay_outcome(events)
    assert replay_outcome.winning_team == fetched_record["winner"]


def test_sse_events_match_replay_all_visibility(client: TestClient):
    created = _create_match(client, seed=321)
    match_id = created["match_id"]
    _run_match_sync(client, match_id)

    replay_response = client.get(f"/matches/{match_id}/replay?visibility=all")
    assert replay_response.status_code == 200
    replay_lines = [line for line in replay_response.text.splitlines() if line.strip()]

    with client.stream("GET", f"/matches/{match_id}/events?visibility=all") as response:
        assert response.status_code == 200
        assert response.headers.get("cache-control") == "no-cache"
        assert response.headers.get("x-accel-buffering") == "no"
        sse_lines = []
        for raw in response.iter_lines():
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if line.startswith("data: "):
                sse_lines.append(line[6:])
    assert sse_lines == replay_lines


class MutatingObservationAgent:
    def act(self, obs: Observation) -> AgentAction:
        if obs.recent_events:
            obs.recent_events[0]["payload"]["config"]["rng_seed"] = 999
        return AgentAction()


class RaisingAgent:
    def act(self, obs: Observation) -> AgentAction:
        raise RuntimeError(f"boom at {obs.phase}")


def test_agent_cannot_mutate_event_log_via_observation():
    cfg = GameConfig(rng_seed=777)
    engine = GameEngine(cfg)
    agents = {f"p{i}": MutatingObservationAgent() for i in range(cfg.player_count)}

    result = engine.run_match(agents=agents)
    match_created = next(event for event in result.events if event["type"] == "match_created")
    assert match_created["payload"]["config"]["rng_seed"] == 777


def test_engine_survives_agent_exception():
    cfg = GameConfig(rng_seed=888)
    engine = GameEngine(cfg)
    agents = {f"p{i}": RaisingAgent() for i in range(cfg.player_count)}

    result = engine.run_match(agents=agents)
    assert any(event["type"] == "match_ended" for event in result.events)
