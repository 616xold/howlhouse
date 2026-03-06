import pytest
from fastapi.testclient import TestClient

from howlhouse.api.app import create_app
from howlhouse.core.config import Settings
from howlhouse.platform.identity import IdentityVerificationError, VerifiedIdentity


class StubIdentityVerifier:
    def __init__(self):
        self.calls: list[str] = []

    def verify(self, token: str) -> VerifiedIdentity:
        self.calls.append(token)
        if token != "good-token":
            raise IdentityVerificationError("bad token", reason="invalid_token")
        return VerifiedIdentity(
            identity_id="viewer_123",
            handle="viewer",
            display_name="Viewer",
            feed_url="https://example.test/viewer",
            raw={"identity_id": "viewer_123"},
        )


class StubPublisher:
    def __init__(self):
        self.calls: list[dict] = []

    def publish(self, *, identity, match_id: str, recap: dict):
        self.calls.append({"identity": identity, "match_id": match_id, "recap": recap})
        return {"ok": True, "remote_id": "post_001"}


@pytest.fixture
def client_identity_disabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    settings = Settings(env="test", database_url=f"sqlite:///{db_path}")
    app = create_app(settings)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client_identity_enabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{db_path}",
        identity_enabled=True,
        identity_verify_url="http://127.0.0.1:9/verify",
    )
    app = create_app(settings)
    verifier = StubIdentityVerifier()
    app.state.identity_verifier = verifier
    with TestClient(app) as client:
        yield client, verifier


@pytest.fixture
def client_identity_and_distribution_enabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{db_path}",
        identity_enabled=True,
        identity_verify_url="http://127.0.0.1:9/verify",
        distribution_enabled=True,
        distribution_post_url="http://127.0.0.1:9/publish",
    )
    app = create_app(settings)
    verifier = StubIdentityVerifier()
    publisher = StubPublisher()
    app.state.identity_verifier = verifier
    app.state.publisher = publisher
    with TestClient(app) as client:
        yield client, verifier, publisher


def _create_and_run_sync(client: TestClient, seed: int) -> str:
    create_response = client.post("/matches", json={"seed": seed, "agent_set": "scripted"})
    assert create_response.status_code == 200, create_response.text
    match_id = create_response.json()["match_id"]

    run_response = client.post(f"/matches/{match_id}/run?sync=true")
    assert run_response.status_code == 200, run_response.text
    assert run_response.json()["status"] == "finished"
    return match_id


def test_identity_disabled_me_endpoint_and_core_flow(client_identity_disabled: TestClient):
    me_response = client_identity_disabled.get("/identity/me")
    assert me_response.status_code == 404

    create_match = client_identity_disabled.post(
        "/matches", json={"seed": 111, "agent_set": "scripted"}
    )
    assert create_match.status_code == 200


def test_identity_enabled_me_endpoint_auth_required_and_valid(client_identity_enabled):
    client, verifier = client_identity_enabled

    missing = client.get("/identity/me")
    assert missing.status_code == 401

    invalid = client.get("/identity/me", headers={"Authorization": "Bearer bad-token"})
    assert invalid.status_code == 401

    valid = client.get("/identity/me", headers={"Authorization": "Bearer good-token"})
    assert valid.status_code == 200
    payload = valid.json()
    assert payload["identity_id"] == "viewer_123"
    assert verifier.calls[-1] == "good-token"


def test_identity_rate_limit_exceeded_returns_429(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{db_path}",
        identity_enabled=True,
        identity_verify_url="http://127.0.0.1:9/verify",
        identity_rate_limit_window_s=3600,
        identity_rate_limit_max_failures=2,
    )
    app = create_app(settings)
    app.state.identity_verifier = StubIdentityVerifier()

    with TestClient(app) as client:
        first = client.get("/identity/me", headers={"Authorization": "Bearer bad-token"})
        second = client.get("/identity/me", headers={"Authorization": "Bearer bad-token"})
        third = client.get("/identity/me", headers={"Authorization": "Bearer bad-token"})

    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429


def test_publish_recap_with_verified_identity(client_identity_and_distribution_enabled):
    client, _verifier, publisher = client_identity_and_distribution_enabled

    match_id = _create_and_run_sync(client, seed=505)
    publish_response = client.post(
        f"/matches/{match_id}/publish",
        headers={"Authorization": "Bearer good-token"},
    )
    assert publish_response.status_code == 200, publish_response.text
    payload = publish_response.json()
    assert payload["published"] is True
    assert payload["match_id"] == match_id
    assert payload["receipt"]["ok"] is True

    assert publisher.calls
    call = publisher.calls[-1]
    assert call["match_id"] == match_id
    assert call["identity"].identity_id == "viewer_123"
    assert call["recap"]["match_id"] == match_id


def test_production_requires_https_for_identity_and_distribution_urls(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"

    with pytest.raises(ValueError, match="HOWLHOUSE_IDENTITY_VERIFY_URL must use https"):
        create_app(
            Settings(
                env="production",
                database_url=f"sqlite:///{db_path}",
                identity_enabled=True,
                identity_verify_url="http://identity.example/verify",
                allow_degraded_start_without_docker=True,
            )
        )

    with pytest.raises(ValueError, match="HOWLHOUSE_DISTRIBUTION_POST_URL must use https"):
        create_app(
            Settings(
                env="production",
                database_url=f"sqlite:///{db_path}",
                distribution_enabled=True,
                distribution_post_url="http://publisher.example/post",
                allow_degraded_start_without_docker=True,
            )
        )


def test_outbound_hostname_allowlists_are_enforced(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"

    with pytest.raises(ValueError, match="not in the configured hostname allowlist"):
        create_app(
            Settings(
                env="production",
                database_url=f"sqlite:///{db_path}",
                identity_enabled=True,
                identity_verify_url="https://identity.example/verify",
                identity_verify_host_allowlist="other.example",
                allow_degraded_start_without_docker=True,
            )
        )

    app = create_app(
        Settings(
            env="production",
            database_url=f"sqlite:///{db_path}",
            identity_enabled=True,
            identity_verify_url="https://identity.example/verify",
            identity_verify_host_allowlist="identity.example",
            distribution_enabled=True,
            distribution_post_url="https://publisher.example/post",
            distribution_post_host_allowlist="publisher.example",
            allow_degraded_start_without_docker=True,
        )
    )
    assert app is not None
