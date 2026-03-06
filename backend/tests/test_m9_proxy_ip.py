from __future__ import annotations

from fastapi.testclient import TestClient

from howlhouse.api.app import create_app
from howlhouse.core.config import Settings
from howlhouse.platform.identity import IdentityVerificationError


class AlwaysInvalidVerifier:
    def verify(self, token: str):
        raise IdentityVerificationError("bad token", reason="invalid_token")


def _call_identity_me(client: TestClient, *, token: str, xff: str) -> int:
    response = client.get(
        "/identity/me",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Forwarded-For": xff,
        },
    )
    return response.status_code


def test_identity_rate_limit_uses_real_client_ip_when_proxy_trust_enabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{db_path}",
        identity_enabled=True,
        identity_verify_url="http://127.0.0.1:9/verify",
        identity_rate_limit_window_s=3600,
        identity_rate_limit_max_failures=2,
        trust_proxy_headers=True,
        trusted_proxy_hops=1,
        trusted_proxy_cidrs="127.0.0.0/8",
    )
    app = create_app(settings)
    app.state.identity_verifier = AlwaysInvalidVerifier()

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        assert _call_identity_me(client, token="bad-token", xff="203.0.113.10") == 401
        assert _call_identity_me(client, token="bad-token", xff="203.0.113.10") == 401
        assert _call_identity_me(client, token="bad-token", xff="203.0.113.10") == 429

        # Different real client IP should have an independent bucket.
        assert _call_identity_me(client, token="bad-token", xff="203.0.113.11") == 401


def test_identity_rate_limit_ignores_xff_when_proxy_trust_disabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{db_path}",
        identity_enabled=True,
        identity_verify_url="http://127.0.0.1:9/verify",
        identity_rate_limit_window_s=3600,
        identity_rate_limit_max_failures=2,
        trust_proxy_headers=False,
        trusted_proxy_hops=1,
        trusted_proxy_cidrs="127.0.0.0/8",
    )
    app = create_app(settings)
    app.state.identity_verifier = AlwaysInvalidVerifier()

    with TestClient(app) as client:
        assert _call_identity_me(client, token="bad-token", xff="203.0.113.10") == 401
        assert _call_identity_me(client, token="bad-token", xff="203.0.113.10") == 401

        # With trust disabled, forwarded client IP does not change the bucket.
        assert _call_identity_me(client, token="bad-token", xff="203.0.113.11") == 429


def test_identity_rate_limit_ignores_xff_from_untrusted_proxy_peer(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{db_path}",
        identity_enabled=True,
        identity_verify_url="http://127.0.0.1:9/verify",
        identity_rate_limit_window_s=3600,
        identity_rate_limit_max_failures=2,
        trust_proxy_headers=True,
        trusted_proxy_hops=1,
        trusted_proxy_cidrs="10.0.0.0/8",
    )
    app = create_app(settings)
    app.state.identity_verifier = AlwaysInvalidVerifier()

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        assert _call_identity_me(client, token="bad-token", xff="203.0.113.10") == 401
        assert _call_identity_me(client, token="bad-token", xff="203.0.113.11") == 401
        assert _call_identity_me(client, token="bad-token", xff="198.51.100.12") == 429
