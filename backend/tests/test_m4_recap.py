import json
from copy import deepcopy
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from howlhouse.api.app import create_app
from howlhouse.core.config import Settings
from howlhouse.recap import generate_recap, generate_share_cards
from howlhouse.recap.share_card import CANVAS

ADMIN_HEADERS = {"X-HowlHouse-Admin": "ops-secret"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    settings = Settings(env="test", database_url=f"sqlite:///{db_path}", admin_tokens="ops-secret")
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _create_and_run_sync(client: TestClient, seed: int = 123) -> str:
    create_response = client.post("/matches", json={"seed": seed, "agent_set": "scripted"})
    assert create_response.status_code == 200
    match_id = create_response.json()["match_id"]

    run_response = client.post(f"/matches/{match_id}/run?sync=true")
    assert run_response.status_code == 200
    return match_id


def _read_events(client: TestClient, match_id: str) -> list[dict]:
    replay_response = client.get(
        f"/matches/{match_id}/replay?visibility=all", headers=ADMIN_HEADERS
    )
    assert replay_response.status_code == 200
    return [json.loads(line) for line in replay_response.text.splitlines() if line.strip()]


def _assert_valid_png(payload: bytes) -> None:
    with Image.open(BytesIO(payload)) as image:
        assert image.format == "PNG"
        assert image.size == CANVAS


def test_recap_and_share_card_endpoints(client: TestClient):
    match_id = _create_and_run_sync(client, seed=2024)

    recap_public = client.get(f"/matches/{match_id}/recap?visibility=public")
    assert recap_public.status_code == 200
    public_payload = recap_public.json()
    assert len(public_payload["bullets"]) == 5
    assert bool(public_payload["narration_15s"])
    assert len(public_payload["clips"]) >= 3
    assert "confessional_highlights" not in public_payload

    recap_all = client.get(f"/matches/{match_id}/recap?visibility=all", headers=ADMIN_HEADERS)
    assert recap_all.status_code == 200
    all_payload = recap_all.json()
    assert "confessional_highlights" in all_payload
    assert isinstance(all_payload["confessional_highlights"], list)

    public_card = client.get(f"/matches/{match_id}/share-card?visibility=public")
    assert public_card.status_code == 200
    assert public_card.headers.get("content-type") == "image/png"
    assert len(public_card.content) > 400
    _assert_valid_png(public_card.content)

    spoilers_card = client.get(f"/matches/{match_id}/share-card?visibility=spoilers")
    assert spoilers_card.status_code == 200
    assert spoilers_card.headers.get("content-type") == "image/png"
    assert len(spoilers_card.content) > 400
    _assert_valid_png(spoilers_card.content)
    assert public_card.content != spoilers_card.content


def test_generate_share_cards_fresh_outputs_are_valid_and_spoiler_safe(
    client: TestClient, tmp_path: Path
):
    match_id = _create_and_run_sync(client, seed=2026)
    events = _read_events(client, match_id)
    recap = generate_recap(events)

    public_path, spoilers_path = generate_share_cards(match_id, recap, tmp_path / "cards")
    public_bytes = Path(public_path).read_bytes()
    spoilers_bytes = Path(spoilers_path).read_bytes()

    _assert_valid_png(public_bytes)
    _assert_valid_png(spoilers_bytes)
    assert public_bytes != spoilers_bytes

    role_mutated_recap = deepcopy(recap)
    role_mutated_recap["roles"] = {
        player_id: f"private-role-{index}"
        for index, player_id in enumerate(sorted(role_mutated_recap.get("roles", {}).keys()))
    }
    role_mutated_recap["confessional_highlights"] = [
        {
            "event_id": "evt_private",
            "player_id": "p0",
            "text": "Private-only content should never affect the public card.",
            "phase": "night",
        }
    ]

    public_only_path, _ = generate_share_cards(
        match_id, role_mutated_recap, tmp_path / "cards_role_mutated"
    )
    assert Path(public_only_path).read_bytes() == public_bytes


def test_generate_share_cards_fresh_outputs_are_deterministic(client: TestClient, tmp_path: Path):
    match_id = _create_and_run_sync(client, seed=2025)
    events = _read_events(client, match_id)

    recap_a = generate_recap(events)
    recap_b = generate_recap(events)
    assert recap_a == recap_b

    cards_a = tmp_path / "cards_a"
    cards_b = tmp_path / "cards_b"
    public_a, spoilers_a = generate_share_cards(match_id, recap_a, cards_a)
    public_b, spoilers_b = generate_share_cards(match_id, recap_a, cards_b)

    assert Path(public_a).read_bytes() == Path(public_b).read_bytes()
    assert Path(spoilers_a).read_bytes() == Path(spoilers_b).read_bytes()
