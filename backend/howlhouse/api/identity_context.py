from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from howlhouse.platform.client_ip import get_client_ip
from howlhouse.platform.identity import (
    IdentityUnavailableError,
    IdentityVerificationError,
    VerifiedIdentity,
)
from howlhouse.platform.observability import increment_identity_verification

logger = logging.getLogger(__name__)


def _extract_token(request: Request, header_name: str) -> str | None:
    header_value = request.headers.get(header_name)
    if not header_value:
        return None
    value = header_value.strip()
    if value.lower().startswith("bearer "):
        token = value[7:].strip()
        return token or None
    return value or None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def _window_start_iso(window_seconds: int) -> str:
    dt = datetime.now(UTC) - timedelta(seconds=max(1, int(window_seconds)))
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def install_identity_middleware(app) -> None:
    @app.middleware("http")
    async def identity_middleware(request: Request, call_next):
        request.state.identity = None
        request.state.identity_error = None

        settings = request.app.state.settings
        if not settings.identity_enabled:
            return await call_next(request)

        token = _extract_token(request, settings.identity_token_header)
        if token is None:
            return await call_next(request)

        client_ip = get_client_ip(request, settings)

        store = request.app.state.store
        failure_count = store.count_recent_identity_failures(
            ip=client_ip,
            since_iso=_window_start_iso(settings.identity_rate_limit_window_s),
        )
        if failure_count >= settings.identity_rate_limit_max_failures:
            request.state.identity_error = "rate_limited"
            increment_identity_verification(ok=False, reason="rate_limited")
            logger.warning(
                "identity_verify_rate_limited",
                extra={"reason": "rate_limited"},
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many recent identity verification failures"},
            )

        token_hash = _token_hash(token)
        verifier = request.app.state.identity_verifier

        try:
            identity = verifier.verify(token)
        except IdentityVerificationError as exc:
            store.record_identity_event(
                ip=client_ip, token_hash=token_hash, ok=False, reason=exc.reason
            )
            request.state.identity_error = "invalid"
            increment_identity_verification(ok=False, reason=exc.reason)
        except IdentityUnavailableError as exc:
            store.record_identity_event(
                ip=client_ip, token_hash=token_hash, ok=False, reason=exc.reason
            )
            request.state.identity_error = "unavailable"
            increment_identity_verification(ok=False, reason=exc.reason)
        else:
            store.record_identity_event(ip=client_ip, token_hash=token_hash, ok=True, reason="ok")
            request.state.identity = identity
            increment_identity_verification(ok=True, reason="ok")

        return await call_next(request)


def get_optional_identity(request: Request) -> VerifiedIdentity | None:
    value = getattr(request.state, "identity", None)
    if isinstance(value, VerifiedIdentity):
        return value
    return None


def require_identity(request: Request) -> VerifiedIdentity:
    identity = get_optional_identity(request)
    if identity is not None:
        return identity

    err = getattr(request.state, "identity_error", None)
    if err == "rate_limited":
        raise HTTPException(status_code=429, detail="Too many identity verification failures")
    if err == "unavailable":
        raise HTTPException(status_code=503, detail="Identity verification service unavailable")
    raise HTTPException(status_code=401, detail="Verified identity required")
