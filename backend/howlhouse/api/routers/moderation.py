from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from howlhouse.platform.access_control import require_admin_access
from howlhouse.platform.store import BlockRecord

router = APIRouter(prefix="/admin", tags=["moderation"])


class CreateBlockRequest(BaseModel):
    block_type: Literal["identity", "ip", "cidr"]
    value: str
    reason: str | None = None
    expires_at: str | None = None


class HideResourceRequest(BaseModel):
    resource_type: Literal["agent", "match", "tournament"]
    resource_id: str
    hidden: bool
    reason: str | None = None


def _block_to_dto(record: BlockRecord) -> dict[str, Any]:
    return {
        "block_id": record.block_id,
        "block_type": record.block_type,
        "value": record.value,
        "reason": record.reason,
        "created_at": record.created_at,
        "expires_at": record.expires_at,
        "created_by_identity_id": record.created_by_identity_id,
    }


@router.post("/blocks")
def create_block(body: CreateBlockRequest, request: Request) -> dict[str, Any]:
    actor = require_admin_access(request)
    store = request.app.state.store
    try:
        record = store.create_block(
            block_type=body.block_type,
            value=body.value,
            reason=body.reason,
            expires_at=body.expires_at,
            created_by_identity_id=actor.identity_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _block_to_dto(record)


@router.get("/blocks")
def list_blocks(
    request: Request,
    include_expired: int = Query(default=0, ge=0, le=1),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict[str, Any]:
    require_admin_access(request)
    store = request.app.state.store
    rows = store.list_blocks(include_expired=bool(include_expired), limit=limit)
    return {
        "count": len(rows),
        "blocks": [_block_to_dto(row) for row in rows],
    }


@router.delete("/blocks/{block_id}")
def delete_block(block_id: str, request: Request) -> dict[str, Any]:
    require_admin_access(request)
    store = request.app.state.store
    deleted = store.delete_block(block_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Block not found: {block_id}")
    return {"deleted": True, "block_id": block_id}


@router.post("/hide")
def hide_resource(body: HideResourceRequest, request: Request) -> dict[str, Any]:
    require_admin_access(request)
    store = request.app.state.store

    try:
        if body.resource_type == "match":
            record = store.set_match_hidden(
                match_id=body.resource_id,
                hidden=body.hidden,
                reason=body.reason,
            )
            hidden_at = record.hidden_at
            hidden_reason = record.hidden_reason
        elif body.resource_type == "agent":
            record = store.set_agent_hidden(
                agent_id=body.resource_id,
                hidden=body.hidden,
                reason=body.reason,
            )
            hidden_at = record.hidden_at
            hidden_reason = record.hidden_reason
        else:
            record = store.set_tournament_hidden(
                tournament_id=body.resource_id,
                hidden=body.hidden,
                reason=body.reason,
            )
            hidden_at = record.hidden_at
            hidden_reason = record.hidden_reason
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"{body.resource_type} not found: {body.resource_id}"
        ) from exc

    return {
        "resource_type": body.resource_type,
        "resource_id": body.resource_id,
        "hidden": body.hidden,
        "hidden_at": hidden_at,
        "hidden_reason": hidden_reason,
    }


@router.get("/hidden")
def list_hidden_resources(
    request: Request,
    resource_type: Literal["agent", "match", "tournament"] = Query(...),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict[str, Any]:
    require_admin_access(request)
    store = request.app.state.store
    try:
        rows = store.list_hidden_resources(resource_type=resource_type, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "resource_type": resource_type,
        "count": len(rows),
        "items": rows,
    }
