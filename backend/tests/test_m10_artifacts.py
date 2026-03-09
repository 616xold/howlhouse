from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from howlhouse.api.app import create_app
from howlhouse.cli.regenerate_share_cards import main as regenerate_share_cards_main
from howlhouse.core.config import Settings

ADMIN_HEADERS = {"X-HowlHouse-Admin": "ops-secret"}


def test_replay_and_share_card_fallback_to_blob_store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{db_path}",
        blob_store="local",
        blob_base_dir=str(tmp_path / "blob"),
        admin_tokens="ops-secret",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        created = client.post("/matches", json={"seed": 2101, "agent_set": "scripted"})
        assert created.status_code == 200, created.text
        match_id = created.json()["match_id"]

        ran = client.post(f"/matches/{match_id}/run?sync=true", headers=ADMIN_HEADERS)
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

        replay = client.get(f"/matches/{match_id}/replay?visibility=all", headers=ADMIN_HEADERS)
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


def test_share_card_regeneration_cli_backfills_persisted_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    blob_dir = tmp_path / "blob"
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{db_path}",
        blob_store="local",
        blob_base_dir=str(blob_dir),
        admin_tokens="ops-secret",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        created = client.post("/matches", json={"seed": 2102, "agent_set": "scripted"})
        assert created.status_code == 200, created.text
        match_id = created.json()["match_id"]

        ran = client.post(f"/matches/{match_id}/run?sync=true", headers=ADMIN_HEADERS)
        assert ran.status_code == 200, ran.text
        assert ran.json()["status"] == "finished"

        recap_record = app.state.store.get_recap(match_id)
        assert recap_record is not None

        public_path = Path(recap_record.share_card_public_path)
        spoilers_path = Path(recap_record.share_card_spoilers_path)
        assert recap_record.share_card_public_key is not None
        assert recap_record.share_card_spoilers_key is not None
        public_blob_path = blob_dir / recap_record.share_card_public_key
        spoilers_blob_path = blob_dir / recap_record.share_card_spoilers_key

        original_public = public_path.read_bytes()
        original_spoilers = spoilers_path.read_bytes()

        public_path.write_bytes(b"stale-public")
        spoilers_path.write_bytes(b"stale-spoilers")
        public_blob_path.write_bytes(b"stale-public-blob")
        spoilers_blob_path.write_bytes(b"stale-spoilers-blob")

    monkeypatch.setenv("HOWLHOUSE_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HOWLHOUSE_BLOB_STORE", "local")
    monkeypatch.setenv("HOWLHOUSE_BLOB_BASE_DIR", str(blob_dir))
    monkeypatch.setattr(
        "sys.argv",
        ["regenerate_share_cards", "--match-id", match_id],
    )

    regenerate_share_cards_main()

    assert public_path.read_bytes() == original_public
    assert spoilers_path.read_bytes() == original_spoilers
    assert public_blob_path.read_bytes() == original_public
    assert spoilers_blob_path.read_bytes() == original_spoilers
