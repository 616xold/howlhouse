from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile

from howlhouse.platform.access_control import (
    ACTION_AGENT_UPLOAD,
    is_admin_request,
    require_admin_access,
    require_mutation_access,
)
from howlhouse.platform.agent_ingest import ingest_agent_package
from howlhouse.platform.runtime_policy import ensure_agent_runtime_allowed
from howlhouse.platform.store import AgentRecord

router = APIRouter(prefix="/agents", tags=["agents"])


def _agent_summary(record: AgentRecord, *, admin_view: bool) -> dict[str, Any]:
    payload = {
        "agent_id": record.agent_id,
        "name": record.name,
        "version": record.version,
        "runtime_type": record.runtime_type,
        "strategy_text": record.strategy_text,
        "created_by_ip": record.created_by_ip if admin_view else None,
        "hidden_at": record.hidden_at,
        "hidden_reason": record.hidden_reason,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }
    if admin_view:
        payload["created_by_identity_id"] = record.created_by_identity_id
    return payload


def _agent_detail(record: AgentRecord, *, admin_view: bool) -> dict[str, Any]:
    payload = _agent_summary(record, admin_view=admin_view)
    payload["strategy_text"] = record.strategy_text
    if admin_view:
        payload["package_path"] = record.package_path
        payload["entrypoint"] = record.entrypoint
    return payload


@router.post("")
async def upload_agent(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    name: Annotated[str, Form(...)],
    version: Annotated[str, Form(...)],
    runtime_type: Annotated[Literal["docker_py_v1", "local_py_v1"], Form()] = "docker_py_v1",
) -> dict[str, Any]:
    store = request.app.state.store
    settings = request.app.state.settings
    actor = require_mutation_access(request, action=ACTION_AGENT_UPLOAD)
    try:
        ensure_agent_runtime_allowed(settings, runtime_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    normalized_name = name.strip()
    normalized_version = version.strip()
    if not normalized_name:
        raise HTTPException(status_code=422, detail="name must not be empty")
    if not normalized_version:
        raise HTTPException(status_code=422, detail="version must not be empty")

    zip_bytes = await file.read()
    try:
        ingested = ingest_agent_package(
            zip_bytes=zip_bytes,
            data_dir=Path(settings.data_dir),
            max_zip_bytes=settings.agent_zip_max_bytes,
            max_extract_bytes=settings.agent_extract_max_bytes,
            strategy_max_chars=settings.agent_strategy_max_chars,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    record = store.upsert_agent(
        agent_id=ingested.agent_id,
        name=normalized_name,
        version=normalized_version,
        runtime_type=runtime_type,
        strategy_text=ingested.strategy_text,
        package_path=ingested.package_path,
        entrypoint=ingested.entrypoint,
        created_by_identity_id=actor.identity_id,
        created_by_ip=actor.client_ip,
    )
    return _agent_detail(record, admin_view=is_admin_request(request))


@router.get("")
def list_agents(
    request: Request,
    include_hidden: int = Query(default=0, ge=0, le=1),
) -> list[dict[str, Any]]:
    store = request.app.state.store
    if include_hidden:
        require_admin_access(request)
    admin_view = is_admin_request(request)
    return [
        _agent_summary(record, admin_view=admin_view)
        for record in store.list_agents(include_hidden=bool(include_hidden))
    ]


@router.get("/{agent_id}")
def get_agent(agent_id: str, request: Request) -> dict[str, Any]:
    store = request.app.state.store
    admin_view = is_admin_request(request)
    record = store.get_agent(agent_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    if record.hidden_at is not None and not admin_view:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return _agent_detail(record, admin_view=admin_view)
