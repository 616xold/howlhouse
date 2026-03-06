from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient

from howlhouse.api.app import create_app
from howlhouse.core.config import Settings
from howlhouse.platform.identity import IdentityVerificationError, VerifiedIdentity


class StubIdentityVerifier:
    def verify(self, token: str) -> VerifiedIdentity:
        if token.startswith("good-"):
            identity_id = token.removeprefix("good-") or "viewer"
            return VerifiedIdentity(
                identity_id=identity_id,
                handle=identity_id,
                display_name=identity_id,
                feed_url=None,
                raw={"identity_id": identity_id},
            )
        raise IdentityVerificationError("invalid", reason="invalid_token")


def _build_agent_zip(label: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("agent.py", "def act(observation):\n    return {}\n")
        archive.writestr(
            "AGENT.md",
            f"# Agent\n\n## HowlHouse Strategy\nFollow deterministic plan {label}.\n",
        )
    return buffer.getvalue()


def _make_client(settings: Settings, *, use_verifier: bool = False) -> TestClient:
    app = create_app(settings)
    if use_verifier:
        app.state.identity_verifier = StubIdentityVerifier()
    return TestClient(app)


def test_auth_mode_open_allows_mutations_without_identity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(env="test", database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}")

    with _make_client(settings) as client:
        response = client.post("/matches", json={"seed": 1201, "agent_set": "scripted"})
        assert response.status_code == 200, response.text


def test_auth_mode_verified_blocks_mutations_without_identity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
        auth_mode="verified",
        identity_enabled=True,
        identity_verify_url="http://127.0.0.1:9/verify",
    )

    with _make_client(settings, use_verifier=True) as client:
        response = client.post("/matches", json={"seed": 1202, "agent_set": "scripted"})
        assert response.status_code == 401


def test_admin_bypass_allows_mutations_when_verified_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
        auth_mode="verified",
        identity_enabled=True,
        identity_verify_url="http://127.0.0.1:9/verify",
        admin_tokens="ops-secret",
    )

    with _make_client(settings, use_verifier=True) as client:
        denied = client.post("/matches", json={"seed": 1203, "agent_set": "scripted"})
        assert denied.status_code == 401

        allowed = client.post(
            "/matches",
            json={"seed": 1204, "agent_set": "scripted"},
            headers={"X-HowlHouse-Admin": "ops-secret"},
        )
        assert allowed.status_code == 200, allowed.text


def test_auth_mode_admin_blocks_non_admin_token(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
        auth_mode="admin",
        admin_tokens="ops-secret",
    )

    with _make_client(settings) as client:
        denied = client.post("/matches", json={"seed": 1210, "agent_set": "scripted"})
        assert denied.status_code == 403

        allowed = client.post(
            "/matches",
            json={"seed": 1211, "agent_set": "scripted"},
            headers={"X-HowlHouse-Admin": "ops-secret"},
        )
        assert allowed.status_code == 200, allowed.text


def test_quota_enforced_by_identity_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
        auth_mode="verified",
        identity_enabled=True,
        identity_verify_url="http://127.0.0.1:9/verify",
        quota_match_create_max=1,
        quota_match_create_window_s=3600,
    )

    with _make_client(settings, use_verifier=True) as client:
        headers = {"Authorization": "Bearer good-owner"}
        first = client.post(
            "/matches", json={"seed": 1205, "agent_set": "scripted"}, headers=headers
        )
        second = client.post(
            "/matches",
            json={"seed": 1206, "agent_set": "scripted"},
            headers=headers,
        )

        assert first.status_code == 200, first.text
        assert second.status_code == 429
        assert second.headers.get("Retry-After") == "3600"
        detail = second.json()["detail"]
        assert detail["error"] == "rate_limited"
        assert detail["action"] == "match_create"
        assert detail["retry_after_s"] == 3600


def test_quota_enforced_by_ip_when_no_identity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
        auth_mode="open",
        identity_enabled=False,
        quota_match_create_max=1,
        quota_match_create_window_s=3600,
    )

    with _make_client(settings) as client:
        first = client.post("/matches", json={"seed": 1207, "agent_set": "scripted"})
        second = client.post("/matches", json={"seed": 1208, "agent_set": "scripted"})

        assert first.status_code == 200, first.text
        assert second.status_code == 429
        detail = second.json()["detail"]
        assert detail["error"] == "rate_limited"
        assert detail["action"] == "match_create"


def test_ownership_fields_populated_when_identity_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
        data_dir=str(tmp_path / "data"),
        auth_mode="verified",
        identity_enabled=True,
        identity_verify_url="http://127.0.0.1:9/verify",
        admin_tokens="ops-secret",
    )

    with _make_client(settings, use_verifier=True) as client:
        headers = {"Authorization": "Bearer good-owner"}
        admin_headers = {"X-HowlHouse-Admin": "ops-secret"}

        agent_a = client.post(
            "/agents",
            data={"name": "Owner Alpha", "version": "1.0.0", "runtime_type": "local_py_v1"},
            files={"file": ("owner_a.zip", _build_agent_zip("alpha"), "application/zip")},
            headers=headers,
        )
        agent_b = client.post(
            "/agents",
            data={"name": "Owner Bravo", "version": "1.0.0", "runtime_type": "local_py_v1"},
            files={"file": ("owner_b.zip", _build_agent_zip("bravo"), "application/zip")},
            headers=headers,
        )
        assert agent_a.status_code == 200, agent_a.text
        assert agent_b.status_code == 200, agent_b.text
        agent_a_payload = agent_a.json()
        agent_b_payload = agent_b.json()
        assert "created_by_identity_id" not in agent_a_payload
        assert agent_a_payload["created_by_ip"] is None

        match = client.post(
            "/matches", json={"seed": 1209, "agent_set": "scripted"}, headers=headers
        )
        assert match.status_code == 200, match.text
        match_payload = match.json()
        assert "created_by_identity_id" not in match_payload
        assert match_payload["created_by_ip"] is None

        season = client.post(
            "/seasons",
            json={"name": "Owner Season", "initial_rating": 1200, "k_factor": 32, "activate": True},
            headers=headers,
        )
        assert season.status_code == 200, season.text

        tournament = client.post(
            "/tournaments",
            json={
                "season_id": season.json()["season_id"],
                "name": "Owner Cup",
                "seed": 1301,
                "participant_agent_ids": [
                    agent_a_payload["agent_id"],
                    agent_b_payload["agent_id"],
                ],
                "games_per_matchup": 1,
            },
            headers=headers,
        )
        assert tournament.status_code == 200, tournament.text
        tournament_payload = tournament.json()
        assert "created_by_identity_id" not in tournament_payload
        assert tournament_payload["created_by_ip"] is None

        agent_a_admin = client.get(f"/agents/{agent_a_payload['agent_id']}", headers=admin_headers)
        match_admin = client.get(f"/matches/{match_payload['match_id']}", headers=admin_headers)
        tournament_admin = client.get(
            f"/tournaments/{tournament_payload['tournament_id']}",
            headers=admin_headers,
        )
        assert agent_a_admin.status_code == 200, agent_a_admin.text
        assert match_admin.status_code == 200, match_admin.text
        assert tournament_admin.status_code == 200, tournament_admin.text
        assert agent_a_admin.json()["created_by_identity_id"] == "owner"
        assert match_admin.json()["created_by_identity_id"] == "owner"
        assert tournament_admin.json()["created_by_identity_id"] == "owner"
