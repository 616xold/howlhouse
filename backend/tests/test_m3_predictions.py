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


def _create_match(client: TestClient, seed: int = 123) -> str:
    response = client.post("/matches", json={"seed": seed, "agent_set": "scripted"})
    assert response.status_code == 200
    return response.json()["match_id"]


def test_predictions_upsert_and_summary(client: TestClient):
    match_id = _create_match(client, seed=123)

    r1 = client.post(
        f"/matches/{match_id}/predictions",
        json={"viewer_id": "viewer-alpha-123", "wolves": ["p4", "p5"]},
    )
    assert r1.status_code == 200
    assert r1.json()["total_predictions"] == 1

    r2 = client.post(
        f"/matches/{match_id}/predictions",
        json={"viewer_id": "viewer-bravo-456", "wolves": ["p4", "p6"]},
    )
    assert r2.status_code == 200
    assert r2.json()["total_predictions"] == 2

    r3 = client.post(
        f"/matches/{match_id}/predictions",
        json={"viewer_id": "viewer-alpha-123", "wolves": ["p1", "p6"]},
    )
    assert r3.status_code == 200
    summary_after_upsert = r3.json()
    assert summary_after_upsert["total_predictions"] == 2

    summary_response = client.get(f"/matches/{match_id}/predictions/summary")
    assert summary_response.status_code == 200
    summary = summary_response.json()

    assert summary["total_predictions"] == 2
    assert summary["by_player"] == {
        "p0": 0,
        "p1": 1,
        "p2": 0,
        "p3": 0,
        "p4": 1,
        "p5": 0,
        "p6": 2,
    }
    assert summary["top_pairs"] == [
        {"pair": ["p1", "p6"], "count": 1},
        {"pair": ["p4", "p6"], "count": 1},
    ]
