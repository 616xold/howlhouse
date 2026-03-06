from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from howlhouse.api.app import create_app
from howlhouse.core.config import Settings


def test_replay_and_share_card_fallback_to_blob_store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{db_path}",
        blob_store="local",
        blob_base_dir=str(tmp_path / "blob"),
    )
    app = create_app(settings)

    with TestClient(app) as client:
        created = client.post("/matches", json={"seed": 2101, "agent_set": "scripted"})
        assert created.status_code == 200, created.text
        match_id = created.json()["match_id"]

        ran = client.post(f"/matches/{match_id}/run?sync=true")
        assert ran.status_code == 200, ran.text
        assert ran.json()["status"] == "finished"

        match_payload = ran.json()
        replay_path = Path(match_payload["replay_path"])
        assert replay_path.exists()

        recap_record = app.state.store.get_recap(match_id)
        assert recap_record is not None

        public_card_path = Path(recap_record.share_card_public_path)
        spoilers_card_path = Path(recap_record.share_card_spoilers_path)
        assert public_card_path.exists()
        assert spoilers_card_path.exists()

        replay_path.unlink()
        public_card_path.unlink()
        spoilers_card_path.unlink()

        replay = client.get(f"/matches/{match_id}/replay?visibility=all")
        assert replay.status_code == 200, replay.text
        events = [json.loads(line) for line in replay.text.splitlines() if line.strip()]
        assert any(event["type"] == "match_ended" for event in events)

        public_card = client.get(f"/matches/{match_id}/share-card?visibility=public")
        assert public_card.status_code == 200, public_card.text
        assert public_card.headers["content-type"].startswith("image/png")
        assert len(public_card.content) > 128

        spoilers_card = client.get(f"/matches/{match_id}/share-card?visibility=spoilers")
        assert spoilers_card.status_code == 200, spoilers_card.text
        assert spoilers_card.headers["content-type"].startswith("image/png")
        assert len(spoilers_card.content) > 128
