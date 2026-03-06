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
            f"# Agent\n\n## HowlHouse Strategy\nPlay deterministic {label}.\n",
        )
    return buffer.getvalue()


def _upload_agent(client: TestClient, name: str, token: str | None = None, **headers):
    request_headers = dict(headers)
    if token is not None:
        request_headers["Authorization"] = f"Bearer {token}"
    return client.post(
        "/agents",
        data={"name": name, "version": "1.0.0", "runtime_type": "local_py_v1"},
        files={"file": (f"{name}.zip", _build_agent_zip(name), "application/zip")},
        headers=request_headers,
    )


def _create_client(settings: Settings, *, with_verifier: bool = False) -> TestClient:
    app = create_app(settings)
    if with_verifier:
        app.state.identity_verifier = StubIdentityVerifier()
    return TestClient(app, client=("127.0.0.1", 50000))


def _create_tournament_with_agents(client: TestClient, *, prefix: str) -> tuple[str, str, str, str]:
    agent_a = _upload_agent(client, f"{prefix}AgentA")
    agent_b = _upload_agent(client, f"{prefix}AgentB")
    assert agent_a.status_code == 200, agent_a.text
    assert agent_b.status_code == 200, agent_b.text
    agent_a_id = agent_a.json()["agent_id"]
    agent_b_id = agent_b.json()["agent_id"]

    season = client.post(
        "/seasons",
        json={"name": f"{prefix}Season", "initial_rating": 1200, "k_factor": 32, "activate": True},
    )
    assert season.status_code == 200, season.text
    season_id = season.json()["season_id"]

    tournament = client.post(
        "/tournaments",
        json={
            "season_id": season_id,
            "name": f"{prefix}Tournament",
            "seed": 1317,
            "participant_agent_ids": [agent_a_id, agent_b_id],
            "games_per_matchup": 1,
        },
    )
    assert tournament.status_code == 200, tournament.text
    return agent_a_id, agent_b_id, season_id, tournament.json()["tournament_id"]


def test_created_by_ip_is_redacted_for_non_admin(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
        auth_mode="open",
        admin_tokens="ops-secret",
    )

    with _create_client(settings) as client:
        agent_a_id, _agent_b_id, _season_id, tournament_id = _create_tournament_with_agents(
            client, prefix="Redacted"
        )
        match = client.post("/matches", json={"seed": 1401, "agent_set": "scripted"})
        assert match.status_code == 200, match.text
        match_id = match.json()["match_id"]

        agent_detail = client.get(f"/agents/{agent_a_id}")
        match_detail = client.get(f"/matches/{match_id}")
        tournament_detail = client.get(f"/tournaments/{tournament_id}")
        assert agent_detail.status_code == 200
        assert match_detail.status_code == 200
        assert tournament_detail.status_code == 200

        assert agent_detail.json()["created_by_ip"] is None
        assert match_detail.json()["created_by_ip"] is None
        assert tournament_detail.json()["created_by_ip"] is None


def test_created_by_ip_visible_for_admin(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
        auth_mode="open",
        admin_tokens="ops-secret",
    )
    admin_headers = {"X-HowlHouse-Admin": "ops-secret"}

    with _create_client(settings) as client:
        agent_a_id, _agent_b_id, _season_id, tournament_id = _create_tournament_with_agents(
            client, prefix="Visible"
        )
        match = client.post("/matches", json={"seed": 1402, "agent_set": "scripted"})
        assert match.status_code == 200, match.text
        match_id = match.json()["match_id"]

        agent_detail = client.get(f"/agents/{agent_a_id}", headers=admin_headers)
        match_detail = client.get(f"/matches/{match_id}", headers=admin_headers)
        tournament_detail = client.get(f"/tournaments/{tournament_id}", headers=admin_headers)
        assert agent_detail.status_code == 200
        assert match_detail.status_code == 200
        assert tournament_detail.status_code == 200

        assert isinstance(agent_detail.json()["created_by_ip"], str)
        assert isinstance(match_detail.json()["created_by_ip"], str)
        assert isinstance(tournament_detail.json()["created_by_ip"], str)


def test_hidden_match_detail_returns_404_for_non_admin_and_200_for_admin(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
        auth_mode="open",
        admin_tokens="ops-secret",
    )
    admin_headers = {"X-HowlHouse-Admin": "ops-secret"}

    with _create_client(settings) as client:
        created = client.post("/matches", json={"seed": 1403, "agent_set": "scripted"})
        assert created.status_code == 200, created.text
        match_id = created.json()["match_id"]

        hide = client.post(
            "/admin/hide",
            json={
                "resource_type": "match",
                "resource_id": match_id,
                "hidden": True,
                "reason": "moderation",
            },
            headers=admin_headers,
        )
        assert hide.status_code == 200, hide.text

        non_admin = client.get(f"/matches/{match_id}")
        admin = client.get(f"/matches/{match_id}", headers=admin_headers)
        assert non_admin.status_code == 404
        assert admin.status_code == 200


def test_hidden_agent_detail_returns_404_for_non_admin_and_200_for_admin(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
        auth_mode="open",
        admin_tokens="ops-secret",
    )
    admin_headers = {"X-HowlHouse-Admin": "ops-secret"}

    with _create_client(settings) as client:
        agent = _upload_agent(client, "HiddenAgentDetail")
        assert agent.status_code == 200, agent.text
        agent_id = agent.json()["agent_id"]

        hide = client.post(
            "/admin/hide",
            json={
                "resource_type": "agent",
                "resource_id": agent_id,
                "hidden": True,
                "reason": "moderation",
            },
            headers=admin_headers,
        )
        assert hide.status_code == 200, hide.text

        non_admin = client.get(f"/agents/{agent_id}")
        admin = client.get(f"/agents/{agent_id}", headers=admin_headers)
        assert non_admin.status_code == 404
        assert admin.status_code == 200


def test_hidden_tournament_detail_returns_404_for_non_admin_and_200_for_admin(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
        auth_mode="open",
        admin_tokens="ops-secret",
    )
    admin_headers = {"X-HowlHouse-Admin": "ops-secret"}

    with _create_client(settings) as client:
        _agent_a_id, _agent_b_id, _season_id, tournament_id = _create_tournament_with_agents(
            client, prefix="HiddenDetail"
        )

        hide = client.post(
            "/admin/hide",
            json={
                "resource_type": "tournament",
                "resource_id": tournament_id,
                "hidden": True,
                "reason": "moderation",
            },
            headers=admin_headers,
        )
        assert hide.status_code == 200, hide.text

        non_admin = client.get(f"/tournaments/{tournament_id}")
        admin = client.get(f"/tournaments/{tournament_id}", headers=admin_headers)
        assert non_admin.status_code == 404
        assert admin.status_code == 200


def test_hidden_match_replay_returns_404_for_non_admin(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
        auth_mode="open",
        admin_tokens="ops-secret",
    )
    admin_headers = {"X-HowlHouse-Admin": "ops-secret"}

    with _create_client(settings) as client:
        created = client.post("/matches", json={"seed": 1404, "agent_set": "scripted"})
        assert created.status_code == 200, created.text
        match_id = created.json()["match_id"]

        run = client.post(f"/matches/{match_id}/run?sync=true")
        assert run.status_code == 200, run.text
        assert run.json()["status"] == "finished"

        hide = client.post(
            "/admin/hide",
            json={
                "resource_type": "match",
                "resource_id": match_id,
                "hidden": True,
                "reason": "moderation",
            },
            headers=admin_headers,
        )
        assert hide.status_code == 200, hide.text

        replay_non_admin = client.get(f"/matches/{match_id}/replay?visibility=all")
        replay_admin = client.get(
            f"/matches/{match_id}/replay?visibility=all", headers=admin_headers
        )
        assert replay_non_admin.status_code == 404
        assert replay_admin.status_code == 200


def test_public_dtos_redact_internal_fields_for_non_admin(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
        auth_mode="open",
        admin_tokens="ops-secret",
    )
    admin_headers = {"X-HowlHouse-Admin": "ops-secret"}

    with _create_client(settings) as client:
        agent_a = _upload_agent(client, "RedactAgentA")
        agent_b = _upload_agent(client, "RedactAgentB")
        assert agent_a.status_code == 200, agent_a.text
        assert agent_b.status_code == 200, agent_b.text

        season = client.post(
            "/seasons",
            json={
                "name": "Redact Season",
                "initial_rating": 1200,
                "k_factor": 32,
                "activate": True,
            },
        )
        assert season.status_code == 200, season.text

        tournament = client.post(
            "/tournaments",
            json={
                "season_id": season.json()["season_id"],
                "name": "Redact Cup",
                "seed": 1410,
                "participant_agent_ids": [agent_a.json()["agent_id"], agent_b.json()["agent_id"]],
                "games_per_matchup": 1,
            },
        )
        assert tournament.status_code == 200, tournament.text

        created = client.post("/matches", json={"seed": 1411, "agent_set": "scripted"})
        assert created.status_code == 200, created.text
        match_id = created.json()["match_id"]
        run = client.post(f"/matches/{match_id}/run?sync=true")
        assert run.status_code == 200, run.text

        agent_public = client.get(f"/agents/{agent_a.json()['agent_id']}").json()
        match_public = client.get(f"/matches/{match_id}").json()
        tournament_public = client.get(f"/tournaments/{tournament.json()['tournament_id']}").json()

        assert "package_path" not in agent_public
        assert "entrypoint" not in agent_public
        assert "created_by_identity_id" not in agent_public
        assert "replay_path" not in match_public
        assert "replay_key" not in match_public
        assert "replay_uri" not in match_public
        assert "postprocess_error" not in match_public
        assert "created_by_identity_id" not in match_public
        assert "created_by_identity_id" not in tournament_public

        agent_admin = client.get(
            f"/agents/{agent_a.json()['agent_id']}", headers=admin_headers
        ).json()
        match_admin = client.get(f"/matches/{match_id}", headers=admin_headers).json()
        tournament_admin = client.get(
            f"/tournaments/{tournament.json()['tournament_id']}",
            headers=admin_headers,
        ).json()

        assert "package_path" in agent_admin
        assert "entrypoint" in agent_admin
        assert "created_by_identity_id" in agent_admin
        assert "replay_path" in match_admin
        assert "replay_key" in match_admin
        assert "replay_uri" in match_admin
        assert "postprocess_error" in match_admin
        assert "created_by_identity_id" in match_admin
        assert "created_by_identity_id" in tournament_admin


def test_blocked_identity_cannot_create_match_in_verified_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
        auth_mode="verified",
        identity_enabled=True,
        identity_verify_url="http://127.0.0.1:9/verify",
        admin_tokens="ops-secret",
    )

    with _create_client(settings, with_verifier=True) as client:
        block_response = client.post(
            "/admin/blocks",
            json={"block_type": "identity", "value": "owner", "reason": "abuse"},
            headers={"X-HowlHouse-Admin": "ops-secret"},
        )
        assert block_response.status_code == 200, block_response.text

        create_response = client.post(
            "/matches",
            json={"seed": 1301, "agent_set": "scripted"},
            headers={"Authorization": "Bearer good-owner"},
        )
        assert create_response.status_code == 403, create_response.text
        detail = create_response.json()["detail"]
        assert detail["error"] == "blocked"
        assert detail["block_type"] == "identity"


def test_blocked_ip_cannot_upload_agent_in_open_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
        auth_mode="open",
        identity_enabled=False,
        admin_tokens="ops-secret",
        trust_proxy_headers=True,
        trusted_proxy_hops=1,
        trusted_proxy_cidrs="127.0.0.0/8",
    )

    with _create_client(settings) as client:
        block_response = client.post(
            "/admin/blocks",
            json={
                "block_type": "ip",
                "value": "203.0.113.10",
                "reason": "upload spam",
            },
            headers={"X-HowlHouse-Admin": "ops-secret"},
        )
        assert block_response.status_code == 200, block_response.text

        upload_response = _upload_agent(
            client,
            "BlockedIPAgent",
            **{"X-Forwarded-For": "203.0.113.10"},
        )
        assert upload_response.status_code == 403, upload_response.text
        detail = upload_response.json()["detail"]
        assert detail["error"] == "blocked"
        assert detail["block_type"] == "ip"


def test_admin_can_create_and_delete_block(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
        auth_mode="open",
        admin_tokens="ops-secret",
    )

    with _create_client(settings) as client:
        created = client.post(
            "/admin/blocks",
            json={"block_type": "ip", "value": "203.0.113.14", "reason": "manual"},
            headers={"X-HowlHouse-Admin": "ops-secret"},
        )
        assert created.status_code == 200, created.text
        block_id = created.json()["block_id"]

        listed = client.get("/admin/blocks", headers={"X-HowlHouse-Admin": "ops-secret"})
        assert listed.status_code == 200
        assert any(item["block_id"] == block_id for item in listed.json()["blocks"])

        deleted = client.delete(
            f"/admin/blocks/{block_id}", headers={"X-HowlHouse-Admin": "ops-secret"}
        )
        assert deleted.status_code == 200, deleted.text

        listed_after = client.get("/admin/blocks", headers={"X-HowlHouse-Admin": "ops-secret"})
        assert listed_after.status_code == 200
        assert all(item["block_id"] != block_id for item in listed_after.json()["blocks"])


def test_hidden_resources_filtered_from_list_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
        auth_mode="open",
        admin_tokens="ops-secret",
    )

    with _create_client(settings) as client:
        agent_a = _upload_agent(client, "HiddenAgentA")
        agent_b = _upload_agent(client, "HiddenAgentB")
        assert agent_a.status_code == 200, agent_a.text
        assert agent_b.status_code == 200, agent_b.text
        agent_a_id = agent_a.json()["agent_id"]

        match = client.post("/matches", json={"seed": 1302, "agent_set": "scripted"})
        assert match.status_code == 200, match.text
        match_id = match.json()["match_id"]

        season = client.post(
            "/seasons",
            json={"name": "HiddenSeason", "initial_rating": 1200, "k_factor": 32, "activate": True},
        )
        assert season.status_code == 200, season.text
        season_id = season.json()["season_id"]

        tournament = client.post(
            "/tournaments",
            json={
                "season_id": season_id,
                "name": "HiddenTournament",
                "seed": 1303,
                "participant_agent_ids": [agent_a_id, agent_b.json()["agent_id"]],
                "games_per_matchup": 1,
            },
        )
        assert tournament.status_code == 200, tournament.text
        tournament_id = tournament.json()["tournament_id"]

        admin_headers = {"X-HowlHouse-Admin": "ops-secret"}
        hide_agent = client.post(
            "/admin/hide",
            json={
                "resource_type": "agent",
                "resource_id": agent_a_id,
                "hidden": True,
                "reason": "moderation",
            },
            headers=admin_headers,
        )
        hide_match = client.post(
            "/admin/hide",
            json={
                "resource_type": "match",
                "resource_id": match_id,
                "hidden": True,
                "reason": "moderation",
            },
            headers=admin_headers,
        )
        hide_tournament = client.post(
            "/admin/hide",
            json={
                "resource_type": "tournament",
                "resource_id": tournament_id,
                "hidden": True,
                "reason": "moderation",
            },
            headers=admin_headers,
        )
        assert hide_agent.status_code == 200
        assert hide_match.status_code == 200
        assert hide_tournament.status_code == 200

        listed_agents = client.get("/agents")
        listed_matches = client.get("/matches")
        listed_tournaments = client.get("/tournaments")
        assert listed_agents.status_code == 200
        assert listed_matches.status_code == 200
        assert listed_tournaments.status_code == 200
        assert all(item["agent_id"] != agent_a_id for item in listed_agents.json())
        assert all(item["match_id"] != match_id for item in listed_matches.json())
        assert all(item["tournament_id"] != tournament_id for item in listed_tournaments.json())


def test_include_hidden_requires_admin(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
        auth_mode="open",
        admin_tokens="ops-secret",
    )

    with _create_client(settings) as client:
        agent = _upload_agent(client, "HiddenAccessAgent")
        assert agent.status_code == 200, agent.text
        agent_id = agent.json()["agent_id"]

        created = client.post("/matches", json={"seed": 1304, "agent_set": "scripted"})
        assert created.status_code == 200, created.text
        match_id = created.json()["match_id"]

        hide = client.post(
            "/admin/hide",
            json={
                "resource_type": "match",
                "resource_id": match_id,
                "hidden": True,
                "reason": "investigation",
            },
            headers={"X-HowlHouse-Admin": "ops-secret"},
        )
        assert hide.status_code == 200, hide.text

        hide_agent = client.post(
            "/admin/hide",
            json={
                "resource_type": "agent",
                "resource_id": agent_id,
                "hidden": True,
                "reason": "investigation",
            },
            headers={"X-HowlHouse-Admin": "ops-secret"},
        )
        assert hide_agent.status_code == 200, hide_agent.text

        denied = client.get("/matches?include_hidden=1")
        assert denied.status_code == 403
        denied_agents = client.get("/agents?include_hidden=1")
        assert denied_agents.status_code == 403

        allowed = client.get(
            "/matches?include_hidden=1", headers={"X-HowlHouse-Admin": "ops-secret"}
        )
        assert allowed.status_code == 200
        assert any(item["match_id"] == match_id for item in allowed.json())
        allowed_agents = client.get(
            "/agents?include_hidden=1", headers={"X-HowlHouse-Admin": "ops-secret"}
        )
        assert allowed_agents.status_code == 200
        assert any(item["agent_id"] == agent_id for item in allowed_agents.json())


def test_prune_deletes_old_usage_events_and_jobs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(env="test", database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}")

    with _create_client(settings) as client:
        store = client.app.state.store

        old_usage = store.record_usage_event(
            identity_id=None, client_ip="127.0.0.1", action="match_create"
        )
        _new_usage = store.record_usage_event(
            identity_id="viewer", client_ip="127.0.0.1", action="match_create"
        )

        done_job = store.enqueue_job(job_type="match_run", resource_id="res_done")
        store.complete_job(job_id=done_job.job_id, status="succeeded")

        queued_job = store.enqueue_job(job_type="match_run", resource_id="res_running")
        running_job = store.claim_next_job(worker_id="worker-1", lease_seconds=30)
        assert running_job is not None

        with store._lock, store._write_guard_locked():
            store._exec(
                "UPDATE usage_events SET created_at = ? WHERE event_id = ?",
                ("2000-01-01T00:00:00Z", old_usage.event_id),
            )
            store._exec(
                "UPDATE jobs SET updated_at = ? WHERE job_id = ?",
                ("2000-01-01T00:00:00Z", done_job.job_id),
            )
            store._exec(
                "UPDATE jobs SET updated_at = ? WHERE job_id = ?",
                ("2000-01-01T00:00:00Z", queued_job.job_id),
            )
            store._commit()

        deleted_usage = store.prune_usage_events(older_than_iso="2020-01-01T00:00:00Z")
        deleted_jobs = store.prune_jobs(older_than_iso="2020-01-01T00:00:00Z")

        assert deleted_usage == 1
        assert deleted_jobs == 1
        assert store.get_job(done_job.job_id) is None
        assert store.get_job(queued_job.job_id) is not None
