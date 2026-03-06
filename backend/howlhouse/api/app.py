from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from howlhouse.api.identity_context import install_identity_middleware
from howlhouse.api.routers.admin import router as admin_router
from howlhouse.api.routers.agents import router as agents_router
from howlhouse.api.routers.health import router as health_router
from howlhouse.api.routers.identity import router as identity_router
from howlhouse.api.routers.matches import router as matches_router
from howlhouse.api.routers.moderation import router as moderation_router
from howlhouse.api.routers.predictions import router as predictions_router
from howlhouse.api.routers.recap import router as recap_router
from howlhouse.api.routers.seasons import router as seasons_router
from howlhouse.api.routers.tournaments import router as tournaments_router
from howlhouse.core.config import Settings
from howlhouse.core.logging import configure_logging
from howlhouse.league import TournamentRunner
from howlhouse.platform.blob_store import create_blob_store
from howlhouse.platform.distribution import HttpRecapPublisher, NoOpRecapPublisher
from howlhouse.platform.event_bus import EventBus
from howlhouse.platform.identity import HttpIdentityVerifier, NoOpIdentityVerifier
from howlhouse.platform.job_worker import JobWorker
from howlhouse.platform.observability import (
    install_metrics_endpoint,
    install_request_observability_middleware,
    setup_tracing,
)
from howlhouse.platform.outbound_policy import validate_outbound_url
from howlhouse.platform.runner import MatchRunner
from howlhouse.platform.runtime_policy import is_production_like_env
from howlhouse.platform.sandbox import docker_available
from howlhouse.platform.store import MatchStore

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings()
    configure_logging(resolved_settings)

    store = MatchStore(resolved_settings.database_url)
    blob_store = create_blob_store(resolved_settings)
    bus = EventBus(history_limit=max(1, int(resolved_settings.event_bus_history_limit)))
    runner = MatchRunner(
        settings=resolved_settings,
        store=store,
        blob_store=blob_store,
        bus=bus,
        replay_dir=Path("./replays"),
    )
    job_worker = JobWorker(
        settings=resolved_settings,
        store=store,
        match_runner=runner,
        worker_id=resolved_settings.worker_id or None,
    )
    tournament_runner = TournamentRunner(store=store, match_runner=runner)
    if resolved_settings.identity_enabled:
        if not resolved_settings.identity_verify_url:
            raise ValueError("HOWLHOUSE_IDENTITY_VERIFY_URL is required when identity_enabled=true")
        validate_outbound_url(
            resolved_settings.identity_verify_url,
            purpose="HOWLHOUSE_IDENTITY_VERIFY_URL",
            env=resolved_settings.env,
            hostname_allowlist=resolved_settings.identity_verify_host_allowlist,
        )
        identity_verifier = HttpIdentityVerifier(resolved_settings.identity_verify_url)
    else:
        identity_verifier = NoOpIdentityVerifier()

    if resolved_settings.distribution_enabled:
        if not resolved_settings.distribution_post_url:
            raise ValueError(
                "HOWLHOUSE_DISTRIBUTION_POST_URL is required when distribution_enabled=true"
            )
        validate_outbound_url(
            resolved_settings.distribution_post_url,
            purpose="HOWLHOUSE_DISTRIBUTION_POST_URL",
            env=resolved_settings.env,
            hostname_allowlist=resolved_settings.distribution_post_host_allowlist,
        )
        publisher = HttpRecapPublisher(resolved_settings.distribution_post_url)
    else:
        publisher = NoOpRecapPublisher()

    if is_production_like_env(resolved_settings.env) and not docker_available():
        logger.warning(
            "docker_unavailable_in_production_like_env",
            extra={
                "reason": "registered_docker_agents_will_fail",
            },
        )

    embedded_worker_thread: threading.Thread | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal embedded_worker_thread
        store.init_schema()
        runner.set_event_loop(asyncio.get_running_loop())
        env = resolved_settings.env.strip().lower()
        if resolved_settings.embedded_worker_enabled and env in {"dev", "local"}:
            embedded_worker_thread = threading.Thread(
                target=job_worker.run_forever,
                daemon=True,
                name="howlhouse-embedded-worker",
            )
            embedded_worker_thread.start()
        try:
            yield
        finally:
            job_worker.stop()
            if embedded_worker_thread is not None:
                embedded_worker_thread.join(timeout=2)
            store.close()

    app = FastAPI(title="HowlHouse API", version="0.3.0", lifespan=lifespan)

    app.state.settings = resolved_settings
    app.state.store = store
    app.state.bus = bus
    app.state.blob_store = blob_store
    app.state.runner = runner
    app.state.job_worker = job_worker
    app.state.tournament_runner = tournament_runner
    app.state.identity_verifier = identity_verifier
    app.state.publisher = publisher

    cors_origins = [
        origin.strip() for origin in resolved_settings.cors_origins.split(",") if origin.strip()
    ]
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=False,
        )
    install_identity_middleware(app)
    # Register observability after identity middleware so it wraps all responses,
    # including identity early returns (e.g. rate-limited 429).
    install_request_observability_middleware(app, resolved_settings)
    install_metrics_endpoint(app, resolved_settings)
    setup_tracing(app, resolved_settings)

    app.include_router(health_router)
    app.include_router(identity_router)
    app.include_router(agents_router)
    app.include_router(matches_router)
    app.include_router(predictions_router)
    app.include_router(recap_router)
    app.include_router(seasons_router)
    app.include_router(tournaments_router)
    app.include_router(admin_router)
    app.include_router(moderation_router)

    return app
