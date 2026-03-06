import json

import pytest
from fastapi.testclient import TestClient

from howlhouse.api.app import create_app
from howlhouse.core.config import Settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    settings = Settings(env="test", database_url=f"sqlite:///{db_path}")
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _create_and_run(client: TestClient, seed: int = 123) -> str:
    create_response = client.post("/matches", json={"seed": seed, "agent_set": "scripted"})
    assert create_response.status_code == 200
    match_id = create_response.json()["match_id"]

    run_response = client.post(f"/matches/{match_id}/run?sync=true")
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "finished"
    return match_id


def _sse_data_lines(client: TestClient, url: str) -> list[str]:
    data_lines: list[str] = []
    with client.stream("GET", url) as response:
        assert response.status_code == 200
        for raw_line in response.iter_lines():
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
            if line.startswith("data: "):
                data_lines.append(line[6:])
    return data_lines


def test_replay_spoilers_visibility(client: TestClient):
    match_id = _create_and_run(client, seed=123)

    replay_response = client.get(f"/matches/{match_id}/replay?visibility=spoilers")
    assert replay_response.status_code == 200

    events = [json.loads(line) for line in replay_response.text.splitlines() if line.strip()]
    roles_assigned_events = [event for event in events if event["type"] == "roles_assigned"]
    assert len(roles_assigned_events) == 1

    invalid_private_events = [
        event
        for event in events
        if event["visibility"] != "public" and event["type"] != "roles_assigned"
    ]
    assert not invalid_private_events


def test_sse_spoilers_matches_replay(client: TestClient):
    match_id = _create_and_run(client, seed=456)

    replay_response = client.get(f"/matches/{match_id}/replay?visibility=spoilers")
    assert replay_response.status_code == 200
    replay_lines = [line for line in replay_response.text.splitlines() if line.strip()]

    sse_lines = _sse_data_lines(client, f"/matches/{match_id}/events?visibility=spoilers")
    assert sse_lines == replay_lines
