import io
import time
import zipfile

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


class _NeverCalledVerifier:
    def __init__(self) -> None:
        self.calls = 0

    def verify(self, token: str):
        self.calls += 1
        raise AssertionError(f"identity verifier should not be called, received token={token!r}")


def _counter_value(metrics_text: str, metric_name: str, labels: dict[str, str]) -> float:
    metric_prefix = f"{metric_name}{{"
    for line in metrics_text.splitlines():
        if not line.startswith(metric_prefix):
            continue
        if all(f'{key}="{value}"' in line for key, value in labels.items()):
            value = line.rsplit(" ", 1)[-1].strip()
            return float(value)
    return 0.0


def _build_agent_zip(token: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr(
            "agent.py", f'def act(observation):\n    return {{"confessional":"{token}"}}\n'
        )
        zip_file.writestr(
            "AGENT.md",
            f"# Agent\n\n## HowlHouse Strategy\nPlay as {token} with deterministic discipline.\n",
        )
    return buffer.getvalue()


def _upload_agent(client: TestClient, *, name: str, token: str) -> dict:
    response = client.post(
        "/agents",
        data={"name": name, "version": "1.0.0", "runtime_type": "local_py_v1"},
        files={"file": (f"{name}.zip", _build_agent_zip(token), "application/zip")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_active_season(client: TestClient, *, name: str) -> dict:
    response = client.post(
        "/seasons",
        json={"name": name, "initial_rating": 1200, "k_factor": 32, "activate": True},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_tournament(
    client: TestClient,
    *,
    season_id: str,
    participant_agent_ids: list[str],
    name: str,
    seed: int,
) -> dict:
    response = client.post(
        "/tournaments",
        json={
            "season_id": season_id,
            "name": name,
            "seed": seed,
            "participant_agent_ids": participant_agent_ids,
            "games_per_matchup": 1,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _wait_for_tournament_terminal(client: TestClient, tournament_id: str) -> dict:
    deadline = time.monotonic() + 12.0
    job_worker = client.app.state.job_worker
    while time.monotonic() < deadline:
        job_worker.run_once()
        response = client.get(f"/tournaments/{tournament_id}")
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.05)
    pytest.fail(f"tournament {tournament_id} did not reach terminal status in time")


def test_request_id_header_passthrough_and_generation(client: TestClient):
    provided = client.get("/healthz", headers={"X-Request-ID": "req-abc-123"})
    assert provided.status_code == 200
    assert provided.headers.get("x-request-id") == "req-abc-123"

    generated = client.get("/healthz")
    assert generated.status_code == 200
    generated_id = generated.headers.get("x-request-id")
    assert isinstance(generated_id, str)
    assert generated_id


def test_metrics_endpoint_enabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{db_path}",
        metrics_enabled=True,
        metrics_path="/metrics",
    )
    app = create_app(settings)

    with TestClient(app) as test_client:
        health = test_client.get("/healthz")
        assert health.status_code == 200

        created = test_client.post("/matches", json={"seed": 313, "agent_set": "scripted"})
        assert created.status_code == 200

        metrics = test_client.get("/metrics")
        assert metrics.status_code == 200
        text = metrics.text
        assert "http_requests_total" in text
        assert "matches_created_total" in text


def test_metrics_endpoint_disabled(client: TestClient):
    response = client.get("/metrics")
    assert response.status_code == 404


def test_identity_rate_limited_response_has_observability_headers_and_metrics(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{db_path}",
        identity_enabled=True,
        identity_verify_url="http://127.0.0.1:9/verify",
        identity_rate_limit_window_s=60,
        identity_rate_limit_max_failures=0,
        metrics_enabled=True,
        metrics_path="/metrics",
    )
    app = create_app(settings)
    verifier = _NeverCalledVerifier()
    app.state.identity_verifier = verifier

    with TestClient(app) as test_client:
        response = test_client.get("/identity/me", headers={"Authorization": "Bearer any-token"})
        assert response.status_code == 429
        assert response.headers.get("x-request-id")
        assert response.headers.get("x-content-type-options") == "nosniff"
        assert response.headers.get("x-frame-options") == "DENY"
        assert response.headers.get("referrer-policy") == "same-origin"

        metrics = test_client.get("/metrics")
        assert metrics.status_code == 200
        lines = metrics.text.splitlines()
        assert any(
            line.startswith("http_requests_total{")
            and 'method="GET"' in line
            and 'path="/identity/me"' in line
            and 'status="429"' in line
            for line in lines
        )

    assert verifier.calls == 0


def test_tournament_metrics_running_increment_once_sync(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{db_path}",
        data_dir=str(tmp_path / "data"),
        sandbox_allow_local_fallback=True,
        metrics_enabled=True,
        metrics_path="/metrics",
    )
    app = create_app(settings)

    with TestClient(app) as test_client:
        baseline = test_client.get("/metrics")
        assert baseline.status_code == 200
        before_running = _counter_value(
            baseline.text, "tournaments_run_total", {"status": "running"}
        )
        before_completed = _counter_value(
            baseline.text, "tournaments_run_total", {"status": "completed"}
        )

        first = _upload_agent(test_client, name="M8SyncAlpha", token="sync_alpha")
        second = _upload_agent(test_client, name="M8SyncBravo", token="sync_bravo")
        season = _create_active_season(test_client, name="M8 Sync Season")
        tournament = _create_tournament(
            test_client,
            season_id=season["season_id"],
            participant_agent_ids=[first["agent_id"], second["agent_id"]],
            name="M8 Sync Cup",
            seed=981,
        )

        run = test_client.post(f"/tournaments/{tournament['tournament_id']}/run?sync=true")
        assert run.status_code == 200, run.text
        assert run.json()["status"] == "completed"

        after = test_client.get("/metrics")
        assert after.status_code == 200
        after_running = _counter_value(after.text, "tournaments_run_total", {"status": "running"})
        after_completed = _counter_value(
            after.text, "tournaments_run_total", {"status": "completed"}
        )

        assert after_running - before_running == pytest.approx(1.0)
        assert after_completed - before_completed == pytest.approx(1.0)


def test_tournament_metrics_running_increment_once_async(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{db_path}",
        data_dir=str(tmp_path / "data"),
        sandbox_allow_local_fallback=True,
        metrics_enabled=True,
        metrics_path="/metrics",
    )
    app = create_app(settings)

    with TestClient(app) as test_client:
        baseline = test_client.get("/metrics")
        assert baseline.status_code == 200
        before_running = _counter_value(
            baseline.text, "tournaments_run_total", {"status": "running"}
        )
        before_completed = _counter_value(
            baseline.text, "tournaments_run_total", {"status": "completed"}
        )
        before_failed = _counter_value(baseline.text, "tournaments_run_total", {"status": "failed"})

        first = _upload_agent(test_client, name="M8AsyncAlpha", token="async_alpha")
        second = _upload_agent(test_client, name="M8AsyncBravo", token="async_bravo")
        season = _create_active_season(test_client, name="M8 Async Season")
        tournament = _create_tournament(
            test_client,
            season_id=season["season_id"],
            participant_agent_ids=[first["agent_id"], second["agent_id"]],
            name="M8 Async Cup",
            seed=982,
        )

        run = test_client.post(f"/tournaments/{tournament['tournament_id']}/run?sync=false")
        assert run.status_code == 200, run.text
        assert run.json()["status"] == "running"

        terminal = _wait_for_tournament_terminal(test_client, tournament["tournament_id"])
        assert terminal["status"] in {"completed", "failed"}

        after = test_client.get("/metrics")
        assert after.status_code == 200
        after_running = _counter_value(after.text, "tournaments_run_total", {"status": "running"})
        after_completed = _counter_value(
            after.text, "tournaments_run_total", {"status": "completed"}
        )
        after_failed = _counter_value(after.text, "tournaments_run_total", {"status": "failed"})

        assert after_running - before_running == pytest.approx(1.0)
        terminal_delta = (after_completed - before_completed) + (after_failed - before_failed)
        assert terminal_delta == pytest.approx(1.0)
