import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from howlhouse.api.app import create_app
from howlhouse.core.config import Settings
from howlhouse.platform.agent_ingest import extract_strategy_section
from howlhouse.platform.sandbox import HARNESS_PATH

ADMIN_HEADERS = {"X-HowlHouse-Admin": "ops-secret"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{db_path}",
        data_dir=str(tmp_path / "data"),
        sandbox_allow_local_fallback=True,
        admin_tokens="ops-secret",
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _build_agent_zip(
    *, agent_py: str | None, agent_md: str | None, extra: dict[str, str] | None = None
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        if agent_py is not None:
            zip_file.writestr("agent.py", agent_py)
        if agent_md is not None:
            zip_file.writestr("AGENT.md", agent_md)
        if extra:
            for path, content in extra.items():
                zip_file.writestr(path, content)
    return buffer.getvalue()


def _upload_agent(
    client: TestClient, zip_bytes: bytes, *, runtime_type: str = "local_py_v1"
) -> dict:
    response = client.post(
        "/agents",
        data={"name": "Sample Agent", "version": "1.0.0", "runtime_type": runtime_type},
        files={"file": ("agent.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_agent_strategy_section_parsing():
    markdown = """
# Agent

## Intro
hi

## HowlHouse Strategy
Focus on readable accusations.
Vote consistently with public claims.

## Notes
bye
"""
    strategy = extract_strategy_section(markdown)
    assert strategy == "Focus on readable accusations.\nVote consistently with public claims."


def test_agent_upload_validation_zip_slip(client: TestClient):
    zip_bytes = _build_agent_zip(
        agent_py="def act(observation):\n    return {}\n",
        agent_md="## HowlHouse Strategy\nStay calm.\n",
        extra={"../evil.txt": "nope"},
    )

    response = client.post(
        "/agents",
        data={"name": "Unsafe", "version": "1.0.0", "runtime_type": "local_py_v1"},
        files={"file": ("unsafe.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "agent_py,agent_md,expected",
    [
        (None, "## HowlHouse Strategy\ntext\n", "agent.py"),
        ("def act(observation):\n    return {}\n", None, "AGENT.md"),
        ("def act(observation):\n    return {}\n", "# Missing section\n", "HowlHouse Strategy"),
    ],
)
def test_agent_upload_requires_files(
    client: TestClient,
    agent_py: str | None,
    agent_md: str | None,
    expected: str,
):
    zip_bytes = _build_agent_zip(agent_py=agent_py, agent_md=agent_md)
    response = client.post(
        "/agents",
        data={"name": "Broken", "version": "0.0.1", "runtime_type": "local_py_v1"},
        files={"file": ("broken.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 422
    assert expected in response.text


def test_create_match_with_roster_and_run(client: TestClient):
    zip_bytes = _build_agent_zip(
        agent_py="def act(observation):\n    return {}\n",
        agent_md="## HowlHouse Strategy\nUse concise logic and avoid noise.\n",
    )
    uploaded = _upload_agent(client, zip_bytes, runtime_type="local_py_v1")
    agent_id = uploaded["agent_id"]

    roster = [
        {
            "player_id": "p0",
            "agent_type": "registered",
            "agent_id": agent_id,
            "name": "Guest Agent",
        }
    ]
    roster.extend({"player_id": f"p{i}", "agent_type": "scripted"} for i in range(1, 7))

    create_response = client.post(
        "/matches",
        json={
            "seed": 777,
            "agent_set": "scripted",
            "roster": roster,
        },
    )
    assert create_response.status_code == 200
    match = create_response.json()
    match_id = match["match_id"]
    assert match_id.startswith("match_777_")
    assert match["names"]["p0"] == "Guest Agent"

    run_response = client.post(f"/matches/{match_id}/run?sync=true")
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["status"] == "finished"

    fetched = client.get(f"/matches/{match_id}")
    assert fetched.status_code == 200
    fetched_match = fetched.json()
    assert fetched_match["names"]["p0"] == "Guest Agent"

    roster_rows = client.app.state.store.list_match_players(match_id)
    assert len(roster_rows) == 7
    assert roster_rows[0].player_id == "p0"
    assert roster_rows[0].agent_type == "registered"
    assert roster_rows[0].agent_id == agent_id

    replay = client.get(f"/matches/{match_id}/replay?visibility=all", headers=ADMIN_HEADERS)
    assert replay.status_code == 200
    events = [json.loads(line) for line in replay.text.splitlines() if line.strip()]
    assert events, "Expected replay events"
    assert any(event["type"] == "match_ended" for event in events)
    assert all(event["match_id"] == match_id for event in events)

    recap = client.get(f"/matches/{match_id}/recap?visibility=public")
    assert recap.status_code == 200
    assert recap.json()["match_id"] == match_id


def test_hidden_agent_cannot_be_used_in_new_match_or_tournament(client: TestClient):
    hidden_zip = _build_agent_zip(
        agent_py="def act(observation):\n    return {}\n",
        agent_md="## HowlHouse Strategy\nStay hidden.\n",
    )
    visible_zip = _build_agent_zip(
        agent_py="def act(observation):\n    return {}\n",
        agent_md="## HowlHouse Strategy\nStay visible.\n",
    )
    hidden_agent_id = _upload_agent(client, hidden_zip, runtime_type="local_py_v1")["agent_id"]
    visible_agent_id = _upload_agent(client, visible_zip, runtime_type="local_py_v1")["agent_id"]

    hide_response = client.post(
        "/admin/hide",
        json={
            "resource_type": "agent",
            "resource_id": hidden_agent_id,
            "hidden": True,
            "reason": "moderation",
        },
        headers=ADMIN_HEADERS,
    )
    assert hide_response.status_code == 200, hide_response.text

    roster = [{"player_id": "p0", "agent_type": "registered", "agent_id": hidden_agent_id}]
    roster.extend({"player_id": f"p{i}", "agent_type": "scripted"} for i in range(1, 7))
    match_response = client.post(
        "/matches",
        json={"seed": 778, "agent_set": "scripted", "roster": roster},
    )
    assert match_response.status_code == 422
    assert "Hidden agent_id cannot be used in new matches" in match_response.text

    season_response = client.post(
        "/seasons",
        json={
            "name": "Hidden Agent Season",
            "initial_rating": 1200,
            "k_factor": 32,
            "activate": True,
        },
    )
    assert season_response.status_code == 200, season_response.text

    tournament_response = client.post(
        "/tournaments",
        json={
            "season_id": season_response.json()["season_id"],
            "name": "Blocked Cup",
            "seed": 101,
            "participant_agent_ids": [hidden_agent_id, visible_agent_id],
            "games_per_matchup": 1,
        },
    )
    assert tournament_response.status_code == 422


def test_identical_agent_upload_is_immutable(client: TestClient):
    zip_bytes = _build_agent_zip(
        agent_py="def act(observation):\n    return {}\n",
        agent_md="## HowlHouse Strategy\nStay consistent.\n",
    )
    first = client.post(
        "/agents",
        data={"name": "First Name", "version": "1.0.0", "runtime_type": "local_py_v1"},
        files={"file": ("agent.zip", zip_bytes, "application/zip")},
    )
    assert first.status_code == 200, first.text
    first_payload = first.json()

    second = client.post(
        "/agents",
        data={"name": "Changed Name", "version": "9.9.9", "runtime_type": "docker_py_v1"},
        files={"file": ("agent.zip", zip_bytes, "application/zip")},
    )
    assert second.status_code == 200, second.text
    second_payload = second.json()

    assert second_payload["agent_id"] == first_payload["agent_id"]
    assert second_payload["name"] == first_payload["name"]
    assert second_payload["version"] == first_payload["version"]
    assert second_payload["runtime_type"] == first_payload["runtime_type"]

    listed = client.get("/agents")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_local_runtime_upload_rejected_in_production(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app(
        Settings(
            env="production",
            database_url=f"sqlite:///{tmp_path / 'howlhouse.db'}",
            data_dir=str(tmp_path / "data"),
        )
    )
    with TestClient(app) as client:
        zip_bytes = _build_agent_zip(
            agent_py="def act(observation):\n    return {}\n",
            agent_md="## HowlHouse Strategy\nUnsafe.\n",
        )
        response = client.post(
            "/agents",
            data={"name": "Unsafe", "version": "1.0.0", "runtime_type": "local_py_v1"},
            files={"file": ("unsafe.zip", zip_bytes, "application/zip")},
        )
        assert response.status_code == 422
        assert "local_py_v1 is not allowed" in response.text


def test_local_runtime_registered_agent_rejected_for_match_execution_in_production(
    tmp_path: Path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "howlhouse.db"
    data_dir = tmp_path / "data"

    with TestClient(
        create_app(
            Settings(
                env="test",
                database_url=f"sqlite:///{db_path}",
                data_dir=str(data_dir),
                admin_tokens="ops-secret",
            )
        )
    ) as setup_client:
        zip_bytes = _build_agent_zip(
            agent_py="def act(observation):\n    return {}\n",
            agent_md="## HowlHouse Strategy\nLocal only.\n",
        )
        uploaded = _upload_agent(setup_client, zip_bytes, runtime_type="local_py_v1")
        agent_id = uploaded["agent_id"]

    with TestClient(
        create_app(
            Settings(
                env="production",
                database_url=f"sqlite:///{db_path}",
                data_dir=str(data_dir),
                admin_tokens="ops-secret",
            )
        )
    ) as prod_client:
        roster = [{"player_id": "p0", "agent_type": "registered", "agent_id": agent_id}]
        roster.extend({"player_id": f"p{i}", "agent_type": "scripted"} for i in range(1, 7))

        create_response = prod_client.post(
            "/matches",
            json={"seed": 1701, "agent_set": "scripted", "roster": roster},
        )
        assert create_response.status_code == 422
        assert "local_py_v1 is not allowed" in create_response.text


def test_sandbox_harness_supports_package_imports_outside_agent_cwd(tmp_path: Path):
    package_dir = tmp_path / "agent_pkg"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "helper.py").write_text(
        'def build_action():\n    return {"confessional": "helper import ok"}\n',
        encoding="utf-8",
    )
    (package_dir / "agent.py").write_text(
        "import helper\n\ndef act(observation):\n    return helper.build_action()\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["HOWLHOUSE_AGENT_PATH"] = str((package_dir / "agent.py").resolve())

    proc = subprocess.Popen(
        [sys.executable, "-u", str(HARNESS_PATH)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(tmp_path),
        env=env,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None

    try:
        proc.stdin.write(
            json.dumps(
                {
                    "type": "init",
                    "player_id": "p0",
                    "seed": 123,
                    "match_id": "match_123_hash",
                    "config": {"player_count": 7},
                },
                sort_keys=True,
            )
            + "\n"
        )
        proc.stdin.flush()
        init_line = proc.stdout.readline().strip()
        assert init_line
        init_payload = json.loads(init_line)
        assert init_payload["type"] == "init_ok"

        proc.stdin.write(
            json.dumps(
                {
                    "type": "act",
                    "turn": 1,
                    "observation": {
                        "match_id": "match_123_hash",
                        "phase": "night",
                        "player_id": "p0",
                        "public_state": {"alive_players": ["p0"]},
                        "private_state": {"role": "villager"},
                        "recent_events": [],
                    },
                },
                sort_keys=True,
            )
            + "\n"
        )
        proc.stdin.flush()
        act_line = proc.stdout.readline().strip()
        assert act_line
        act_payload = json.loads(act_line)
        assert act_payload["type"] == "act_result"
        assert isinstance(act_payload["action"], dict)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


def _docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@pytest.mark.docker
def test_create_match_with_roster_and_run_docker_runtime(client: TestClient):
    if os.environ.get("HOWLHOUSE_RUN_DOCKER_TESTS") != "1":
        pytest.skip("docker integration tests disabled")
    if not _docker_available():
        pytest.skip("docker is not available")

    zip_bytes = _build_agent_zip(
        agent_py="def act(observation):\\n    return {}\\n",
        agent_md="## HowlHouse Strategy\\nPlay deterministically.\\n",
    )
    uploaded = _upload_agent(client, zip_bytes, runtime_type="docker_py_v1")
    agent_id = uploaded["agent_id"]

    roster = [
        {"player_id": "p0", "agent_type": "registered", "agent_id": agent_id},
    ]
    roster.extend({"player_id": f"p{i}", "agent_type": "scripted"} for i in range(1, 7))

    create_response = client.post(
        "/matches",
        json={"seed": 1001, "agent_set": "scripted", "roster": roster},
    )
    assert create_response.status_code == 200
    match_id = create_response.json()["match_id"]

    run_response = client.post(f"/matches/{match_id}/run?sync=true")
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "finished"
