from __future__ import annotations

import contextvars
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "howlhouse_request_id", default=None
)
trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "howlhouse_trace_id", default=None
)

logger = logging.getLogger(__name__)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)

MATCHES_CREATED_TOTAL = Counter("matches_created_total", "Total matches created")
MATCHES_RUN_TOTAL = Counter("matches_run_total", "Total match runs", ["status"])
TOURNAMENTS_RUN_TOTAL = Counter("tournaments_run_total", "Total tournament runs", ["status"])
IDENTITY_VERIFICATIONS_TOTAL = Counter(
    "identity_verifications_total",
    "Identity verification attempts",
    ["ok", "reason"],
)
RECAP_PUBLISHES_TOTAL = Counter(
    "recap_publishes_total",
    "Recap publish attempts",
    ["status"],
)
JOBS_RUN_TOTAL = Counter(
    "jobs_run_total",
    "Background job executions",
    ["job_type", "status"],
)
AUTH_DENIED_TOTAL = Counter(
    "auth_denied_total",
    "Access denials for mutation endpoints",
    ["reason", "endpoint"],
)
QUOTA_DENIED_TOTAL = Counter(
    "quota_denied_total",
    "Quota denials",
    ["action"],
)
ADMIN_BYPASS_TOTAL = Counter(
    "admin_bypass_total",
    "Admin token bypass usage",
    ["endpoint"],
)
ABUSE_BLOCKED_TOTAL = Counter(
    "abuse_blocked_total",
    "Blocked mutation attempts",
    ["block_type", "action"],
)
PRUNE_DELETED_TOTAL = Counter(
    "prune_deleted_total",
    "Rows deleted by retention pruning",
    ["table"],
)


_RESERVED_FIELDS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
}


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        record.trace_id = trace_id_var.get() or "-"
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        request_id = getattr(record, "request_id", None)
        if request_id and request_id != "-":
            payload["request_id"] = request_id

        trace_id = getattr(record, "trace_id", None)
        if trace_id and trace_id != "-":
            payload["trace_id"] = trace_id

        for key in [
            "method",
            "path",
            "status_code",
            "duration_ms",
            "match_id",
            "tournament_id",
            "identity_id",
            "reason",
            "seed",
            "status",
        ]:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        for key, value in record.__dict__.items():
            if key in _RESERVED_FIELDS or key in payload:
                continue
            if key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def configure_logging(settings) -> None:
    root = logging.getLogger()
    root.handlers.clear()

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root.setLevel(level)

    handler = logging.StreamHandler()
    if settings.log_json:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s [request_id=%(request_id)s] %(message)s"
            )
        )
    handler.addFilter(_ContextFilter())
    root.addHandler(handler)


def _path_template(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            return path
    return request.url.path


def _parse_traceparent(value: str | None) -> str | None:
    if not value:
        return None
    parts = value.strip().split("-")
    if len(parts) != 4:
        return None
    trace_id = parts[1]
    if len(trace_id) != 32:
        return None
    return trace_id


def install_request_observability_middleware(app: FastAPI, settings) -> None:
    @app.middleware("http")
    async def request_observability_middleware(request: Request, call_next):
        incoming = request.headers.get("X-Request-ID")
        request_id = incoming.strip() if incoming else str(uuid.uuid4())
        trace_id = _parse_traceparent(request.headers.get("traceparent"))

        request.state.request_id = request_id
        request.state.trace_id = trace_id

        rid_token = request_id_var.set(request_id)
        tid_token = trace_id_var.set(trace_id)

        start = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000.0
            path = _path_template(request)
            HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                path=path,
                status=str(status_code),
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(method=request.method, path=path).observe(
                duration_ms / 1000.0
            )
            logger.exception(
                "request_failed",
                extra={
                    "method": request.method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": round(duration_ms, 3),
                },
            )
            raise
        else:
            duration_ms = (time.perf_counter() - start) * 1000.0
            path = _path_template(request)
            HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                path=path,
                status=str(status_code),
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(method=request.method, path=path).observe(
                duration_ms / 1000.0
            )
            response.headers["X-Request-ID"] = request_id
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Referrer-Policy", "same-origin")
            logger.info(
                "request_completed",
                extra={
                    "method": request.method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": round(duration_ms, 3),
                },
            )
            return response
        finally:
            request_id_var.reset(rid_token)
            trace_id_var.reset(tid_token)


def install_metrics_endpoint(app: FastAPI, settings) -> None:
    if not settings.metrics_enabled:
        return

    @app.get(settings.metrics_path, include_in_schema=False)
    def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


_TRACING_INITIALIZED = False


def setup_tracing(app: FastAPI, settings) -> None:
    if not settings.tracing_enabled:
        return

    global _TRACING_INITIALIZED
    if _TRACING_INITIALIZED:
        return

    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

    resource = Resource.create({SERVICE_NAME: settings.tracing_service_name})
    sample_rate = max(0.0, min(1.0, float(settings.tracing_sample_rate)))
    sampler = ParentBased(TraceIdRatioBased(sample_rate))
    provider = TracerProvider(resource=resource, sampler=sampler)

    if settings.tracing_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter(endpoint=settings.tracing_otlp_endpoint)
    else:
        exporter = ConsoleSpanExporter()

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    _TRACING_INITIALIZED = True


def increment_matches_created() -> None:
    MATCHES_CREATED_TOTAL.inc()


def increment_matches_run(status: str) -> None:
    MATCHES_RUN_TOTAL.labels(status=status).inc()


def increment_tournaments_run(status: str) -> None:
    TOURNAMENTS_RUN_TOTAL.labels(status=status).inc()


def increment_identity_verification(*, ok: bool, reason: str) -> None:
    IDENTITY_VERIFICATIONS_TOTAL.labels(ok="true" if ok else "false", reason=reason).inc()


def increment_recap_publish(status: str) -> None:
    RECAP_PUBLISHES_TOTAL.labels(status=status).inc()


def increment_jobs_run(*, job_type: str, status: str) -> None:
    JOBS_RUN_TOTAL.labels(job_type=job_type, status=status).inc()


def increment_auth_denied(*, reason: str, endpoint: str) -> None:
    AUTH_DENIED_TOTAL.labels(reason=reason, endpoint=endpoint).inc()


def increment_quota_denied(*, action: str) -> None:
    QUOTA_DENIED_TOTAL.labels(action=action).inc()


def increment_admin_bypass(*, endpoint: str) -> None:
    ADMIN_BYPASS_TOTAL.labels(endpoint=endpoint).inc()


def increment_abuse_blocked(*, block_type: str, action: str) -> None:
    ABUSE_BLOCKED_TOTAL.labels(block_type=block_type, action=action).inc()


def increment_prune_deleted(*, table: str, count: int) -> None:
    if int(count) <= 0:
        return
    PRUNE_DELETED_TOTAL.labels(table=table).inc(int(count))
