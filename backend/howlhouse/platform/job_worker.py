from __future__ import annotations

import logging
import os
import socket
import threading
from dataclasses import dataclass

from howlhouse.core.config import Settings
from howlhouse.league.tournament import run_tournament_sync
from howlhouse.platform.observability import increment_jobs_run
from howlhouse.platform.runner import MatchRunner
from howlhouse.platform.store import JobRecord, MatchStore, utc_now_iso

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobExecutionResult:
    job_id: str
    status: str
    error: str | None


class JobWorker:
    def __init__(
        self,
        *,
        settings: Settings,
        store: MatchStore,
        match_runner: MatchRunner,
        worker_id: str | None = None,
    ):
        self.settings = settings
        self.store = store
        self.match_runner = match_runner
        self.worker_id = worker_id or _default_worker_id()
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run_once(self) -> JobExecutionResult | None:
        self.store.requeue_stale_jobs(
            now_iso=utc_now_iso(),
            stale_after_seconds=int(self.settings.worker_stale_after_seconds),
        )
        job = self.store.claim_next_job(
            worker_id=self.worker_id,
            lease_seconds=int(self.settings.worker_lease_seconds),
        )
        if job is None:
            return None

        heartbeat_stop = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(job.job_id, heartbeat_stop),
            daemon=True,
            name=f"job-heartbeat-{job.job_id}",
        )
        heartbeat_thread.start()

        increment_jobs_run(job_type=job.job_type, status="running")
        logger.info(
            "job_run_started",
            extra={
                "job_id": job.job_id,
                "job_type": job.job_type,
                "resource_id": job.resource_id,
                "status": "running",
            },
        )

        try:
            self._execute_job(job)
        except Exception as exc:  # pragma: no cover - defensive
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=1)
            failed = self.store.complete_job(job_id=job.job_id, status="failed", error=str(exc))
            increment_jobs_run(job_type=job.job_type, status="failed")
            logger.exception(
                "job_run_failed",
                extra={
                    "job_id": job.job_id,
                    "job_type": job.job_type,
                    "resource_id": job.resource_id,
                    "status": failed.status,
                },
            )
            return JobExecutionResult(job_id=job.job_id, status=failed.status, error=failed.error)

        heartbeat_stop.set()
        heartbeat_thread.join(timeout=1)
        succeeded = self.store.complete_job(job_id=job.job_id, status="succeeded")
        increment_jobs_run(job_type=job.job_type, status="succeeded")
        logger.info(
            "job_run_finished",
            extra={
                "job_id": job.job_id,
                "job_type": job.job_type,
                "resource_id": job.resource_id,
                "status": succeeded.status,
            },
        )
        return JobExecutionResult(job_id=job.job_id, status=succeeded.status, error=None)

    def run_forever(self) -> None:
        logger.info(
            "worker_started",
            extra={
                "worker_id": self.worker_id,
                "concurrency": int(self.settings.worker_concurrency),
            },
        )
        if int(self.settings.worker_concurrency) <= 1:
            self._run_loop()
            return

        threads: list[threading.Thread] = []
        for index in range(int(self.settings.worker_concurrency)):
            thread = threading.Thread(
                target=self._run_loop,
                daemon=True,
                name=f"howlhouse-worker-{index + 1}",
            )
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

    def _run_loop(self) -> None:
        poll_interval = max(0.05, int(self.settings.worker_poll_interval_ms) / 1000.0)
        while not self._stop_event.is_set():
            result = self.run_once()
            if result is None:
                self._stop_event.wait(poll_interval)

    def _heartbeat_loop(self, job_id: str, stop_event: threading.Event) -> None:
        interval = max(0.5, int(self.settings.worker_lease_seconds) / 2)
        while not stop_event.wait(interval):
            self.store.heartbeat_job(job_id=job_id, worker_id=self.worker_id)

    def _execute_job(self, job: JobRecord) -> None:
        if job.job_type == "match_run":
            self._run_match(job.resource_id)
            return
        if job.job_type == "tournament_run":
            self._run_tournament(job.resource_id)
            return
        raise ValueError(f"Unsupported job_type: {job.job_type}")

    def _run_match(self, match_id: str) -> None:
        record = self.store.get_match(match_id)
        if record is None:
            raise KeyError(f"unknown match_id in job: {match_id}")
        if record.status == "finished":
            return
        if record.status not in {"created", "failed", "running"}:
            raise ValueError(f"match {match_id} cannot run from status {record.status!r}")

        updated = self.match_runner.run(match_id, sync=True, allow_running=True)
        if updated.status != "finished":
            raise RuntimeError(f"match job did not finish: {match_id} ({updated.status})")

    def _run_tournament(self, tournament_id: str) -> None:
        record = self.store.get_tournament(tournament_id)
        if record is None:
            raise KeyError(f"unknown tournament_id in job: {tournament_id}")
        if record.status == "completed":
            return
        if record.status not in {"created", "failed", "running"}:
            raise ValueError(f"tournament {tournament_id} cannot run from status {record.status!r}")

        final = run_tournament_sync(
            store=self.store,
            match_runner=self.match_runner,
            tournament_id=tournament_id,
        )
        if final.status != "completed":
            raise RuntimeError(f"tournament job did not complete: {tournament_id} ({final.status})")


def _default_worker_id() -> str:
    return f"worker-{socket.gethostname()}-{os.getpid()}"
