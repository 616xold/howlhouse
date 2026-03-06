from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response

from howlhouse.api.identity_context import get_optional_identity
from howlhouse.platform.access_control import (
    ACTION_RECAP_PUBLISH,
    is_admin_request,
    require_mutation_access,
)
from howlhouse.platform.observability import increment_recap_publish
from howlhouse.platform.store import MatchRecord, RecapRecord

router = APIRouter(prefix="/matches/{match_id}", tags=["recap"])
logger = logging.getLogger(__name__)


def _get_match_or_404(request: Request, match_id: str) -> MatchRecord:
    store = request.app.state.store
    record = store.get_match(match_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Match not found: {match_id}")
    if record.hidden_at is not None and not is_admin_request(request):
        raise HTTPException(status_code=404, detail=f"Match not found: {match_id}")
    return record


def _get_recap_or_409(request: Request, match: MatchRecord) -> RecapRecord:
    store = request.app.state.store
    recap_record = store.get_recap(match.match_id)
    if recap_record is None:
        raise HTTPException(
            status_code=409,
            detail={"status": match.status, "message": "recap not ready"},
        )
    return recap_record


def _filtered_recap(recap: dict[str, Any], visibility: str) -> dict[str, Any]:
    filtered = copy.deepcopy(recap)
    if visibility == "public":
        filtered.pop("roles", None)
        filtered.pop("confessional_highlights", None)
    elif visibility == "spoilers":
        filtered.pop("confessional_highlights", None)
    return filtered


@router.get("/recap")
def get_recap(
    match_id: str,
    request: Request,
    visibility: Literal["public", "spoilers", "all"] = Query(default="public"),
) -> dict[str, Any]:
    match = _get_match_or_404(request, match_id)
    recap_record = _get_recap_or_409(request, match)
    return _filtered_recap(recap_record.recap, visibility)


@router.get("/share-card")
def get_share_card(
    match_id: str,
    request: Request,
    visibility: Literal["public", "spoilers"] = Query(default="public"),
):
    match = _get_match_or_404(request, match_id)
    recap_record = _get_recap_or_409(request, match)

    target_path = (
        Path(recap_record.share_card_public_path)
        if visibility == "public"
        else Path(recap_record.share_card_spoilers_path)
    )
    if not target_path.exists():
        blob_store = request.app.state.blob_store
        target_key = (
            recap_record.share_card_public_key
            if visibility == "public"
            else recap_record.share_card_spoilers_key
        )
        if not target_key or not blob_store.exists(target_key):
            raise HTTPException(
                status_code=409,
                detail={"status": match.status, "message": "share card not ready"},
            )
        return Response(content=blob_store.get_bytes(target_key), media_type="image/png")
    return FileResponse(target_path, media_type="image/png")


@router.post("/publish")
def publish_recap(match_id: str, request: Request) -> dict[str, Any]:
    actor = require_mutation_access(request, action=ACTION_RECAP_PUBLISH)
    settings = request.app.state.settings
    if not settings.distribution_enabled:
        increment_recap_publish("disabled")
        raise HTTPException(status_code=409, detail="distribution is disabled")

    identity = get_optional_identity(request)
    if settings.identity_enabled and identity is None and not actor.is_admin:
        raise HTTPException(status_code=401, detail="Verified identity required")

    match = _get_match_or_404(request, match_id)
    recap_record = _get_recap_or_409(request, match)
    logger.info(
        "recap_publish_started",
        extra={
            "match_id": match_id,
            "identity_id": identity.identity_id if identity is not None else None,
        },
    )
    publisher = request.app.state.publisher
    try:
        receipt = publisher.publish(
            identity=identity,
            match_id=match_id,
            recap=recap_record.recap,
        )
    except RuntimeError as exc:
        increment_recap_publish("failed")
        logger.exception(
            "recap_publish_failed",
            extra={
                "match_id": match_id,
                "identity_id": identity.identity_id if identity is not None else None,
            },
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    increment_recap_publish("success")
    logger.info(
        "recap_publish_succeeded",
        extra={
            "match_id": match_id,
            "identity_id": identity.identity_id if identity is not None else None,
        },
    )

    return {
        "match_id": match_id,
        "published": True,
        "receipt": receipt,
    }
