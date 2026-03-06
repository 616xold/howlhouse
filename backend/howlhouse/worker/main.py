from __future__ import annotations

import logging
import signal
from pathlib import Path

from prometheus_client import start_http_server

from howlhouse.core.config import Settings
from howlhouse.core.logging import configure_logging
from howlhouse.platform.blob_store import create_blob_store
from howlhouse.platform.event_bus import EventBus
from howlhouse.platform.job_worker import JobWorker
from howlhouse.platform.runner import MatchRunner
from howlhouse.platform.store import MatchStore

logger = logging.getLogger(__name__)


def main() -> None:
    settings = Settings()
    configure_logging(settings)

    store = MatchStore(settings.database_url)
    store.init_schema()

    runner = MatchRunner(
        settings=settings,
        store=store,
        blob_store=create_blob_store(settings),
        bus=EventBus(),
        replay_dir=Path("./replays"),
    )
    worker = JobWorker(
        settings=settings,
        store=store,
        match_runner=runner,
        worker_id=settings.worker_id or None,
    )

    if settings.worker_metrics_enabled:
        start_http_server(int(settings.worker_metrics_port), addr="0.0.0.0")
        logger.info(
            "worker_metrics_started",
            extra={"port": int(settings.worker_metrics_port)},
        )

    def _stop(_signum, _frame) -> None:
        logger.info(
            "worker_stopping",
            extra={
                "worker_id": worker.worker_id,
            },
        )
        worker.stop()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    try:
        logger.info(
            "worker_ready",
            extra={
                "worker_id": worker.worker_id,
            },
        )
        worker.run_forever()
    finally:
        store.close()


if __name__ == "__main__":
    main()
