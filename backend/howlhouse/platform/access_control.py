from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

from fastapi import HTTPException, Request

from howlhouse.platform.client_ip import get_client_ip
from howlhouse.platform.identity import VerifiedIdentity
from howlhouse.platform.observability import (
    increment_abuse_blocked,
    increment_admin_bypass,
    increment_auth_denied,
    increment_quota_denied,
)

logger = logging.getLogger(__name__)

ACTION_AGENT_UPLOAD = "agent_upload"
ACTION_MATCH_CREATE = "match_create"
ACTION_MATCH_RUN = "match_run"
ACTION_PREDICTION_MUTATION = "prediction_mutation"
ACTION_SEASON_MUTATION = "season_mutation"
ACTION_TOURNAMENT_CREATE = "tournament_create"
ACTION_TOURNAMENT_RUN = "tournament_run"
ACTION_RECAP_PUBLISH = "recap_publish"


@dataclass(frozen=True)
class MutationActor:
    identity_id: str | None
    client_ip: str
    is_admin: bool


def get_actor_identity(request: Request) -> str | None:
    value = getattr(request.state, "identity", None)
    if isinstance(value, VerifiedIdentity):
        return value.identity_id
    return None


def require_admin_access(request: Request) -> MutationActor:
    settings = request.app.state.settings
    endpoint = _endpoint_label(request)
    client_ip = get_client_ip(request, settings)
    admin_ok = _has_admin_token(request, settings)
    identity_id = get_actor_identity(request)

    if not admin_ok:
        increment_auth_denied(reason="admin_required", endpoint=endpoint)
        logger.warning(
            "admin_access_denied",
            extra={
                "endpoint": endpoint,
                "client_ip": client_ip,
                "identity_id": identity_id,
                "reason": "admin_required",
            },
        )
        raise HTTPException(status_code=403, detail="Admin token required")

    increment_admin_bypass(endpoint=endpoint)
    return MutationActor(identity_id=identity_id, client_ip=client_ip, is_admin=True)


def is_admin_request(request: Request) -> bool:
    settings = request.app.state.settings
    return _has_admin_token(request, settings)


def require_mutation_access(request: Request, *, action: str) -> MutationActor:
    settings = request.app.state.settings
    store = request.app.state.store
    endpoint = _endpoint_label(request)
    mode = _normalized_auth_mode(settings.auth_mode)

    client_ip = get_client_ip(request, settings)
    identity_id = get_actor_identity(request)
    is_admin = _has_admin_token(request, settings)

    if mode == "admin":
        if not is_admin:
            increment_auth_denied(reason="admin_required", endpoint=endpoint)
            logger.warning(
                "mutation_denied",
                extra={
                    "endpoint": endpoint,
                    "action": action,
                    "client_ip": client_ip,
                    "identity_id": identity_id,
                    "reason": "admin_required",
                },
            )
            raise HTTPException(status_code=403, detail="Admin token required")
    elif mode == "verified" and not (identity_id or is_admin):
        increment_auth_denied(reason="identity_required", endpoint=endpoint)
        logger.warning(
            "mutation_denied",
            extra={
                "endpoint": endpoint,
                "action": action,
                "client_ip": client_ip,
                "identity_id": identity_id,
                "reason": "identity_required",
            },
        )
        raise HTTPException(status_code=401, detail="Verified identity required")

    if is_admin and mode in {"verified", "admin"}:
        increment_admin_bypass(endpoint=endpoint)

    actor = MutationActor(identity_id=identity_id, client_ip=client_ip, is_admin=is_admin)

    if actor.is_admin:
        return actor

    blocked, block_type, block_reason, block_expires_at = store.is_blocked(
        identity_id=actor.identity_id, client_ip=actor.client_ip
    )
    if blocked:
        resolved_block_type = block_type or "unknown"
        increment_abuse_blocked(block_type=resolved_block_type, action=action)
        logger.warning(
            "mutation_blocked",
            extra={
                "endpoint": endpoint,
                "action": action,
                "client_ip": actor.client_ip,
                "identity_id": actor.identity_id,
                "block_type": resolved_block_type,
                "reason": block_reason,
                "expires_at": block_expires_at,
            },
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "blocked",
                "block_type": resolved_block_type,
                "reason": block_reason,
                "expires_at": block_expires_at,
            },
        )

    quota_max, quota_window = _quota_limit_for_action(settings=settings, mode=mode, action=action)
    if quota_max <= 0 or quota_window <= 0:
        return actor

    recent_count = store.count_usage_events(
        identity_id=actor.identity_id,
        client_ip=actor.client_ip,
        action=action,
        window_seconds=quota_window,
    )
    if recent_count >= quota_max:
        retry_after = max(1, int(quota_window))
        increment_quota_denied(action=action)
        logger.warning(
            "quota_denied",
            extra={
                "endpoint": endpoint,
                "action": action,
                "client_ip": actor.client_ip,
                "identity_id": actor.identity_id,
                "retry_after_s": retry_after,
            },
        )
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limited",
                "action": action,
                "retry_after_s": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )

    store.record_usage_event(
        identity_id=actor.identity_id,
        client_ip=actor.client_ip,
        action=action,
    )
    return actor


def quota_config_snapshot(settings) -> dict[str, dict[str, int]]:
    mode = _normalized_auth_mode(settings.auth_mode)
    actions = [
        ACTION_AGENT_UPLOAD,
        ACTION_MATCH_CREATE,
        ACTION_MATCH_RUN,
        ACTION_PREDICTION_MUTATION,
        ACTION_SEASON_MUTATION,
        ACTION_TOURNAMENT_CREATE,
        ACTION_TOURNAMENT_RUN,
        ACTION_RECAP_PUBLISH,
    ]
    payload: dict[str, dict[str, int]] = {}
    for action in actions:
        max_actions, window_s = _quota_limit_for_action(settings=settings, mode=mode, action=action)
        payload[action] = {
            "max": int(max_actions),
            "window_s": int(window_s),
        }
    return payload


def _normalized_auth_mode(mode: str) -> str:
    value = (mode or "").strip().lower()
    if value in {"open", "verified", "admin"}:
        return value
    return "open"


def _endpoint_label(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None) if route is not None else None
    if isinstance(path, str) and path:
        return path
    return request.url.path


def _admin_tokens(settings) -> list[str]:
    raw = str(settings.admin_tokens or "")
    return [token.strip() for token in raw.split(",") if token.strip()]


def _has_admin_token(request: Request, settings) -> bool:
    provided = request.headers.get(str(settings.admin_token_header))
    if not provided:
        return False
    token = provided.strip()
    if not token:
        return False
    return any(secrets.compare_digest(token, candidate) for candidate in _admin_tokens(settings))


def _quota_limit_for_action(*, settings, mode: str, action: str) -> tuple[int, int]:
    if action == ACTION_AGENT_UPLOAD:
        configured_max = int(settings.quota_agent_upload_max)
        configured_window = int(settings.quota_agent_upload_window_s)
        strict_default = (10, 3600)
        open_default = (100, 3600)
    elif action == ACTION_MATCH_CREATE:
        configured_max = int(settings.quota_match_create_max)
        configured_window = int(settings.quota_match_create_window_s)
        strict_default = (20, 60)
        open_default = (200, 60)
    elif action == ACTION_MATCH_RUN:
        configured_max = int(settings.quota_match_run_max)
        configured_window = int(settings.quota_match_run_window_s)
        strict_default = (40, 60)
        open_default = (400, 60)
    elif action == ACTION_PREDICTION_MUTATION:
        configured_max = int(settings.quota_prediction_mutation_max)
        configured_window = int(settings.quota_prediction_mutation_window_s)
        strict_default = (60, 3600)
        open_default = (500, 3600)
    elif action in (ACTION_TOURNAMENT_RUN, ACTION_TOURNAMENT_CREATE):
        if action == ACTION_TOURNAMENT_CREATE:
            configured_max = int(settings.quota_tournament_create_max)
            configured_window = int(settings.quota_tournament_create_window_s)
        else:
            configured_max = int(settings.quota_tournament_run_max)
            configured_window = int(settings.quota_tournament_run_window_s)
        strict_default = (15, 3600)
        open_default = (120, 3600)
    elif action == ACTION_RECAP_PUBLISH:
        configured_max = int(settings.quota_recap_publish_max)
        configured_window = int(settings.quota_recap_publish_window_s)
        strict_default = (40, 3600)
        open_default = (200, 3600)
    else:
        configured_max = 0
        configured_window = 0
        strict_default = (0, 0)
        open_default = (0, 0)

    if configured_max > 0:
        max_actions = configured_max
    else:
        max_actions = open_default[0] if mode == "open" else strict_default[0]

    if configured_window > 0:
        window_s = configured_window
    else:
        window_s = open_default[1] if mode == "open" else strict_default[1]

    return max_actions, window_s
