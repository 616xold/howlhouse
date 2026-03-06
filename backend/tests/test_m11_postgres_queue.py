from __future__ import annotations

import os
import threading
import uuid

import pytest

from howlhouse.platform.store import MatchStore

PG_URL_ENV = "HOWLHOUSE_PG_TEST_URL"


def _clear_jobs(store: MatchStore) -> None:
    with store._lock:  # noqa: SLF001 - test-only cleanup helper
        store._exec("DELETE FROM jobs")  # noqa: SLF001 - test-only cleanup helper
        store._commit()  # noqa: SLF001 - test-only cleanup helper


@pytest.mark.skipif(
    not os.getenv(PG_URL_ENV),
    reason=f"{PG_URL_ENV} is not set",
)
def test_m11_postgres_enqueue_race_is_safe():
    db_url = os.environ[PG_URL_ENV]
    store_a = MatchStore(db_url)
    store_b = MatchStore(db_url)
    stores = [store_a, store_b]

    for store in stores:
        store.init_schema()

    _clear_jobs(store_a)

    resource_id = f"race_{uuid.uuid4().hex}"
    barrier = threading.Barrier(3)
    errors: list[Exception] = []
    results = [None, None]

    def enqueue(store: MatchStore, slot: int) -> None:
        try:
            barrier.wait(timeout=5)
            results[slot] = store.enqueue_job(job_type="match_run", resource_id=resource_id)
        except Exception as exc:  # pragma: no cover - defensive for threaded path
            errors.append(exc)

    first = threading.Thread(target=enqueue, args=(store_a, 0), daemon=True)
    second = threading.Thread(target=enqueue, args=(store_b, 1), daemon=True)
    first.start()
    second.start()
    barrier.wait(timeout=5)
    first.join(timeout=5)
    second.join(timeout=5)

    try:
        assert not errors
        assert results[0] is not None
        assert results[1] is not None
        assert results[0].job_id == results[1].job_id

        active = [
            job
            for job in store_a.list_jobs(job_type="match_run")
            if job.resource_id == resource_id and job.status in {"queued", "running"}
        ]
        assert len(active) == 1
        assert active[0].job_id == results[0].job_id
    finally:
        for store in stores:
            store.close()


@pytest.mark.skipif(
    not os.getenv(PG_URL_ENV),
    reason=f"{PG_URL_ENV} is not set",
)
def test_m11_postgres_claim_is_atomic_between_two_connections():
    db_url = os.environ[PG_URL_ENV]
    store_a = MatchStore(db_url)
    store_b = MatchStore(db_url)
    stores = [store_a, store_b]

    for store in stores:
        store.init_schema()

    _clear_jobs(store_a)

    prefix = f"claim_{uuid.uuid4().hex}"
    for index in range(1, 4):
        store_a.enqueue_job(job_type="match_run", resource_id=f"{prefix}_{index}", priority=10)

    barrier = threading.Barrier(3)
    errors: list[Exception] = []
    claimed = [None, None]

    def claim(store: MatchStore, slot: int) -> None:
        try:
            barrier.wait(timeout=5)
            claimed[slot] = store.claim_next_job(worker_id=f"worker_{slot}", lease_seconds=30)
        except Exception as exc:  # pragma: no cover - defensive for threaded path
            errors.append(exc)

    first = threading.Thread(target=claim, args=(store_a, 0), daemon=True)
    second = threading.Thread(target=claim, args=(store_b, 1), daemon=True)
    first.start()
    second.start()
    barrier.wait(timeout=5)
    first.join(timeout=5)
    second.join(timeout=5)

    try:
        assert not errors
        assert claimed[0] is not None
        assert claimed[1] is not None
        assert claimed[0].job_id != claimed[1].job_id

        running = [job for job in store_a.list_jobs(status="running", job_type="match_run")]
        running_ids = {job.job_id for job in running}
        assert claimed[0].job_id in running_ids
        assert claimed[1].job_id in running_ids
    finally:
        for store in stores:
            store.close()
