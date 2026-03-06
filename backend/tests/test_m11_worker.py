import io
import json
import threading
import time
import zipfile

from fastapi.testclient import TestClient

from howlhouse.api.app import create_app
from howlhouse.core.config import Settings
from howlhouse.platform.store import MatchStore


def _build_agent_zip(token: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr(
            "agent.py",
            f'def act(observation):\n    return {{"confessional": "{token}"}}\n',
        )
        zip_file.writestr(
            "AGENT.md",
            f"# Agent\n\n## HowlHouse Strategy\nPlay as {token} with deterministic discipline.\n",
        )
    return buffer.getvalue()


def _upload_agent(client: TestClient, name: str, token: str) -> dict:
    response = client.post(
        "/agents",
        data={"name": name, "version": "1.0.0", "runtime_type": "local_py_v1"},
        files={"file": (f"{name}.zip", _build_agent_zip(token), "application/zip")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_active_season(client: TestClient, name: str = "Season") -> dict:
    response = client.post(
        "/seasons",
        json={"name": name, "initial_rating": 1200, "k_factor": 32, "activate": True},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_match_async_run_enqueues_job_and_worker_processes_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        created = client.post("/matches", json={"seed": 811, "agent_set": "scripted"})
        assert created.status_code == 200, created.text
        match_id = created.json()["match_id"]

        queued = client.post(f"/matches/{match_id}/run?sync=false")
        assert queued.status_code == 200, queued.text
        payload = queued.json()
        assert payload["status"] == "running"
        assert payload["job"]["job_type"] == "match_run"

        worker = client.app.state.job_worker
        processed = worker.run_once()
        assert processed is not None
        assert processed.status == "succeeded"

        done = client.get(f"/matches/{match_id}")
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "finished"

        replay = client.get(f"/matches/{match_id}/replay?visibility=all")
        assert replay.status_code == 200, replay.text
        events = [json.loads(line) for line in replay.text.splitlines() if line.strip()]
        assert any(event["type"] == "match_ended" for event in events)


def test_tournament_async_run_enqueues_job_and_worker_processes_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
        sandbox_allow_local_fallback=True,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        season = _create_active_season(client, name="M11 Season")
        first = _upload_agent(client, "M11Alpha", "m11_alpha")
        second = _upload_agent(client, "M11Bravo", "m11_bravo")

        created = client.post(
            "/tournaments",
            json={
                "season_id": season["season_id"],
                "name": "M11 Cup",
                "seed": 1234,
                "participant_agent_ids": [first["agent_id"], second["agent_id"]],
                "games_per_matchup": 1,
            },
        )
        assert created.status_code == 200, created.text
        tournament_id = created.json()["tournament_id"]

        queued = client.post(f"/tournaments/{tournament_id}/run?sync=false")
        assert queued.status_code == 200, queued.text
        assert queued.json()["status"] == "running"
        assert queued.json()["job"]["job_type"] == "tournament_run"

        worker = client.app.state.job_worker
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            worker.run_once()
            current = client.get(f"/tournaments/{tournament_id}")
            assert current.status_code == 200, current.text
            if current.json()["status"] in {"completed", "failed"}:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("tournament did not finish")

        final = client.get(f"/tournaments/{tournament_id}").json()
        assert final["status"] == "completed"
        assert final["champion_agent_id"] in {first["agent_id"], second["agent_id"]}


def test_claim_is_atomic(tmp_path):
    store = MatchStore(f"sqlite:///{tmp_path / 'howlhouse.db'}")
    store.init_schema()
    try:
        job = store.enqueue_job(job_type="match_run", resource_id="match_atomic", priority=0)
        assert job.status == "queued"

        start = threading.Barrier(3)
        results: list[str | None] = []
        lock = threading.Lock()

        def claim(worker_id: str) -> None:
            start.wait()
            claimed = store.claim_next_job(worker_id=worker_id, lease_seconds=30)
            with lock:
                results.append(claimed.job_id if claimed is not None else None)

        t1 = threading.Thread(target=claim, args=("worker-1",))
        t2 = threading.Thread(target=claim, args=("worker-2",))
        t1.start()
        t2.start()
        start.wait()
        t1.join(timeout=2)
        t2.join(timeout=2)

        claimed_ids = [value for value in results if value is not None]
        assert len(claimed_ids) == 1
        assert claimed_ids[0] == job.job_id
    finally:
        store.close()
