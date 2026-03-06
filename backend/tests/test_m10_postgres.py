from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from howlhouse.api.app import create_app
from howlhouse.core.config import Settings

ADMIN_HEADERS = {"X-HowlHouse-Admin": "ops-secret"}


@pytest.mark.skipif(
    not os.getenv("HOWLHOUSE_PG_TEST_URL"),
    reason="HOWLHOUSE_PG_TEST_URL is not set",
)
def test_postgres_mode_create_run_replay(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=os.environ["HOWLHOUSE_PG_TEST_URL"],
        blob_store="local",
        blob_base_dir=str(tmp_path / "blob"),
        admin_tokens="ops-secret",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        created = client.post("/matches", json={"seed": 3001, "agent_set": "scripted"})
        assert created.status_code == 200, created.text
        match_id = created.json()["match_id"]

        ran = client.post(f"/matches/{match_id}/run?sync=true", headers=ADMIN_HEADERS)
        assert ran.status_code == 200, ran.text
        assert ran.json()["status"] == "finished"

        replay = client.get(f"/matches/{match_id}/replay?visibility=all", headers=ADMIN_HEADERS)
        assert replay.status_code == 200, replay.text
        events = [json.loads(line) for line in replay.text.splitlines() if line.strip()]
        assert events
        assert events[-1]["type"] == "match_ended"
