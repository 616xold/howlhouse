from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from howlhouse.platform.access_control import (
    ACTION_AGENT_UPLOAD,
    ACTION_MATCH_CREATE,
    ACTION_MATCH_RUN,
    ACTION_RECAP_PUBLISH,
    ACTION_TOURNAMENT_CREATE,
    ACTION_TOURNAMENT_RUN,
    quota_config_snapshot,
    require_admin_access,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _usage_row_to_dto(row) -> dict[str, Any]:
    return {
        "event_id": row.event_id,
        "identity_id": row.identity_id,
        "client_ip": row.client_ip,
        "action": row.action,
        "created_at": row.created_at,
    }


@router.get("/quotas")
def get_quota_state(request: Request) -> dict[str, Any]:
    require_admin_access(request)
    settings = request.app.state.settings
    store = request.app.state.store
    snapshot = quota_config_snapshot(settings)

    tracked_actions = [
        ACTION_AGENT_UPLOAD,
        ACTION_MATCH_CREATE,
        ACTION_MATCH_RUN,
        ACTION_TOURNAMENT_CREATE,
        ACTION_TOURNAMENT_RUN,
        ACTION_RECAP_PUBLISH,
    ]

    usage_last_hour: dict[str, int] = {}
    usage_last_day: dict[str, int] = {}
    for action in tracked_actions:
        usage_last_hour[action] = store.count_usage_events_total(action=action, window_seconds=3600)
        usage_last_day[action] = store.count_usage_events_total(action=action, window_seconds=86400)

    return {
        "auth_mode": str(settings.auth_mode),
        "quotas": snapshot,
        "usage_last_hour": usage_last_hour,
        "usage_last_day": usage_last_day,
    }


@router.get("/abuse/recent")
def get_recent_usage_events(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    require_admin_access(request)
    store = request.app.state.store
    rows = store.list_usage_events(limit=limit)
    return {
        "count": len(rows),
        "events": [_usage_row_to_dto(row) for row in rows],
    }
