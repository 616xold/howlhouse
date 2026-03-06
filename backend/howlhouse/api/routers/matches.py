from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from howlhouse.engine.domain.models import GameConfig
from howlhouse.platform.access_control import (
    ACTION_MATCH_CREATE,
    ACTION_MATCH_RUN,
    is_admin_request,
    require_admin_access,
    require_mutation_access,
)
from howlhouse.platform.observability import increment_matches_created, increment_matches_run
from howlhouse.platform.store import MatchRecord

router = APIRouter(prefix="/matches", tags=["matches"])
logger = logging.getLogger(__name__)


class MatchRosterEntry(BaseModel):
    player_id: str
    agent_type: Literal["scripted", "registered"]
    agent_id: str | None = None
    name: str | None = None


class CreateMatchRequest(BaseModel):
    seed: int
    agent_set: Literal["scripted"] = "scripted"
    names: dict[str, str] = Field(default_factory=dict)
    config_overrides: dict[str, Any] = Field(default_factory=dict)
    roster: list[MatchRosterEntry] | None = None
    season_id: str | None = None


def _build_links(match_id: str) -> dict[str, str]:
    return {
        "self": f"/matches/{match_id}",
        "run": f"/matches/{match_id}/run",
        "replay": f"/matches/{match_id}/replay",
        "events": f"/matches/{match_id}/events",
        "recap": f"/matches/{match_id}/recap",
        "publish": f"/matches/{match_id}/publish",
        "share_card_public": f"/matches/{match_id}/share-card?visibility=public",
        "share_card_spoilers": f"/matches/{match_id}/share-card?visibility=spoilers",
    }


def _record_to_dto(record: MatchRecord, *, admin_view: bool) -> dict[str, Any]:
    return {
        "match_id": record.match_id,
        "seed": record.seed,
        "agent_set": record.agent_set,
        "config": record.config,
        "names": record.names,
        "season_id": record.season_id,
        "tournament_id": record.tournament_id,
        "created_by_identity_id": record.created_by_identity_id,
        "created_by_ip": record.created_by_ip if admin_view else None,
        "hidden_at": record.hidden_at,
        "hidden_reason": record.hidden_reason,
        "status": record.status,
        "created_at": record.created_at,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        "replay_path": record.replay_path,
        "replay_key": record.replay_key,
        "replay_uri": record.replay_uri,
        "winner": record.winner,
        "error": record.error,
        "postprocess_error": record.postprocess_error,
        "links": _build_links(record.match_id),
    }


def _get_match_or_404(request: Request, match_id: str) -> MatchRecord:
    store = request.app.state.store
    record = store.get_match(match_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Match not found: {match_id}")
    if record.hidden_at is not None and not is_admin_request(request):
        raise HTTPException(status_code=404, detail=f"Match not found: {match_id}")
    return record


def _job_to_dto(job) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "job_type": job.job_type,
        "resource_id": job.resource_id,
        "status": job.status,
        "priority": job.priority,
        "attempts": job.attempts,
        "error": job.error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def _validate_config_overrides(overrides: dict[str, Any], seed: int) -> GameConfig:
    allowed_fields = set(GameConfig.__dataclass_fields__.keys())
    unknown_fields = sorted(set(overrides) - allowed_fields)
    if unknown_fields:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown config_overrides keys: {', '.join(unknown_fields)}",
        )

    if "rng_seed" in overrides and overrides["rng_seed"] != seed:
        raise HTTPException(status_code=422, detail="config_overrides.rng_seed must equal seed")

    cfg_kwargs = dict(overrides)
    cfg_kwargs["rng_seed"] = seed
    try:
        return GameConfig(**cfg_kwargs)
    except TypeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _expected_player_ids(player_count: int) -> list[str]:
    return [f"p{i}" for i in range(player_count)]


def _normalize_name(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def _resolve_roster_and_names(
    *,
    body: CreateMatchRequest,
    config: GameConfig,
    store,
) -> tuple[list[dict[str, Any]], dict[str, str], list[dict[str, str]] | None]:
    expected_player_ids = _expected_player_ids(config.player_count)
    names_input = {player_id: str(name) for player_id, name in body.names.items()}

    if body.roster is None:
        roster_rows = [
            {"player_id": player_id, "agent_type": "scripted", "agent_id": None}
            for player_id in expected_player_ids
        ]
        resolved_names = {
            player_id: names_input.get(player_id, player_id) for player_id in expected_player_ids
        }
        return roster_rows, resolved_names, None

    if len(body.roster) != config.player_count:
        raise HTTPException(
            status_code=422,
            detail=(
                f"roster must include exactly one entry per player_id ({config.player_count} total)"
            ),
        )

    roster_by_player_id: dict[str, MatchRosterEntry] = {}
    for entry in body.roster:
        if entry.player_id in roster_by_player_id:
            raise HTTPException(
                status_code=422,
                detail=f"Duplicate roster entry for {entry.player_id}",
            )
        roster_by_player_id[entry.player_id] = entry

    missing = [
        player_id for player_id in expected_player_ids if player_id not in roster_by_player_id
    ]
    extra = sorted(set(roster_by_player_id) - set(expected_player_ids))
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if extra:
            details.append(f"extra: {', '.join(extra)}")
        raise HTTPException(
            status_code=422, detail=f"Invalid roster player_ids ({'; '.join(details)})"
        )

    roster_rows: list[dict[str, Any]] = []
    resolved_names: dict[str, str] = {}
    normalized_roster_for_hash: list[dict[str, str]] = []

    for player_id in expected_player_ids:
        entry = roster_by_player_id[player_id]
        selected_name = _normalize_name(entry.name)

        if entry.agent_type == "registered":
            if not entry.agent_id:
                raise HTTPException(
                    status_code=422,
                    detail=f"roster entry for {player_id} requires agent_id",
                )
            agent_record = store.get_agent(entry.agent_id)
            if agent_record is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown agent_id in roster: {entry.agent_id}",
                )
            resolved_name = selected_name or agent_record.name
            normalized_agent_id = agent_record.agent_id
        else:
            if entry.agent_id:
                raise HTTPException(
                    status_code=422,
                    detail=f"scripted roster entry for {player_id} must not include agent_id",
                )
            resolved_name = selected_name or names_input.get(player_id, player_id)
            normalized_agent_id = ""

        roster_rows.append(
            {
                "player_id": player_id,
                "agent_type": entry.agent_type,
                "agent_id": normalized_agent_id or None,
            }
        )
        resolved_names[player_id] = resolved_name
        normalized_roster_for_hash.append(
            {
                "player_id": player_id,
                "agent_type": entry.agent_type,
                "agent_id": normalized_agent_id,
                "name": selected_name or "",
            }
        )

    return roster_rows, resolved_names, normalized_roster_for_hash


def _match_id_for_request(
    *,
    body: CreateMatchRequest,
    normalized_roster: list[dict[str, str]] | None,
) -> str:
    if normalized_roster is None:
        return f"match_{body.seed}"

    payload = {
        "seed": body.seed,
        "config_overrides": body.config_overrides,
        "roster": normalized_roster,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:10]
    return f"match_{body.seed}_{digest}"


def _is_visible_event(event: dict[str, Any], visibility: str) -> bool:
    event_visibility = str(event.get("visibility", ""))
    event_type = str(event.get("type", ""))
    if visibility == "all":
        return True
    if visibility == "public":
        return event_visibility == "public"
    if visibility == "spoilers":
        return event_visibility == "public" or event_type == "roles_assigned"
    return False


def _iter_replay_lines_from_text(text: str, visibility: str):
    for raw_line in text.splitlines(keepends=True):
        if not raw_line.strip():
            continue
        event = json.loads(raw_line)
        if _is_visible_event(event, visibility):
            yield raw_line


def _iter_replay_lines(path: Path, visibility: str):
    with path.open("r", encoding="utf-8") as replay_file:
        yield from _iter_replay_lines_from_text(replay_file.read(), visibility)


def _sse_message(json_line: str, visibility: str) -> str | None:
    event = json.loads(json_line)
    if not _is_visible_event(event, visibility):
        return None
    event_id = str(event.get("id", ""))
    return f"id: {event_id}\ndata: {json_line}\n\n"


@router.post("")
def create_match(body: CreateMatchRequest, request: Request) -> dict[str, Any]:
    store = request.app.state.store
    actor = require_mutation_access(request, action=ACTION_MATCH_CREATE)

    config = _validate_config_overrides(body.config_overrides, body.seed)
    if body.season_id is not None and store.get_season(body.season_id) is None:
        raise HTTPException(status_code=422, detail=f"Unknown season_id: {body.season_id}")
    roster_rows, resolved_names, normalized_roster = _resolve_roster_and_names(
        body=body,
        config=config,
        store=store,
    )
    match_id = _match_id_for_request(body=body, normalized_roster=normalized_roster)
    replay_path = str(Path("replays") / f"{match_id}.jsonl")

    record = store.create_match_if_missing(
        match_id=match_id,
        seed=body.seed,
        agent_set=body.agent_set,
        config_json=json.dumps(asdict(config), sort_keys=True, ensure_ascii=False),
        names_json=json.dumps(resolved_names, sort_keys=True, ensure_ascii=False),
        replay_path=replay_path,
        season_id=body.season_id,
        created_by_identity_id=actor.identity_id,
        created_by_ip=actor.client_ip,
    )
    store.set_match_players(match_id, roster_rows)
    increment_matches_created()
    logger.info(
        "match_created",
        extra={
            "match_id": match_id,
            "seed": body.seed,
            "status": record.status,
        },
    )
    return _record_to_dto(record, admin_view=is_admin_request(request))


@router.get("")
def list_matches(
    request: Request,
    include_hidden: int = Query(default=0, ge=0, le=1),
) -> list[dict[str, Any]]:
    store = request.app.state.store
    if include_hidden:
        require_admin_access(request)
    admin_view = is_admin_request(request)
    return [
        _record_to_dto(record, admin_view=admin_view)
        for record in store.list_matches(include_hidden=bool(include_hidden))
    ]


@router.get("/{match_id}")
def get_match(match_id: str, request: Request) -> dict[str, Any]:
    record = _get_match_or_404(request, match_id)
    return _record_to_dto(record, admin_view=is_admin_request(request))


@router.post("/{match_id}/run")
def run_match(
    match_id: str,
    request: Request,
    sync: bool = Query(default=False),
) -> dict[str, Any]:
    store = request.app.state.store
    runner = request.app.state.runner
    require_mutation_access(request, action=ACTION_MATCH_RUN)
    if not sync:
        record = _get_match_or_404(request, match_id)
        if record.status == "finished":
            return _record_to_dto(record, admin_view=is_admin_request(request))
        if record.status not in {"created", "failed", "running"}:
            raise HTTPException(
                status_code=409,
                detail={"status": record.status, "message": "match cannot be queued"},
            )

        existing_job = store.get_active_job(job_type="match_run", resource_id=match_id)
        if existing_job is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "status": record.status,
                    "message": "match run already queued or running",
                    "job_id": existing_job.job_id,
                },
            )

        if record.status != "running":
            record = store.mark_running(match_id)
            increment_matches_run("running")
            logger.info(
                "match_run_started",
                extra={
                    "match_id": match_id,
                    "seed": record.seed,
                    "status": "running",
                },
            )

        job = store.enqueue_job(job_type="match_run", resource_id=match_id)
        payload = _record_to_dto(record, admin_view=is_admin_request(request))
        payload["job"] = _job_to_dto(job)
        return payload

    _get_match_or_404(request, match_id)
    try:
        record = runner.run(match_id, sync=sync)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Match not found: {match_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _record_to_dto(record, admin_view=is_admin_request(request))


@router.get("/{match_id}/replay")
def get_replay(
    match_id: str,
    request: Request,
    visibility: Literal["all", "public", "spoilers"] = Query(default="all"),
):
    record = _get_match_or_404(request, match_id)

    if record.status != "finished" or not record.replay_path:
        raise HTTPException(
            status_code=409,
            detail={"status": record.status, "message": "replay not ready"},
        )

    replay_path = Path(record.replay_path)
    if not replay_path.exists():
        blob_store = request.app.state.blob_store
        if not record.replay_key or not blob_store.exists(record.replay_key):
            raise HTTPException(
                status_code=409,
                detail={"status": record.status, "message": "replay file missing"},
            )
        replay_bytes = blob_store.get_bytes(record.replay_key)
        if visibility == "all":
            return Response(content=replay_bytes, media_type="application/x-ndjson")
        replay_text = replay_bytes.decode("utf-8")
        return StreamingResponse(
            _iter_replay_lines_from_text(replay_text, visibility),
            media_type="application/x-ndjson",
        )

    return StreamingResponse(
        _iter_replay_lines(replay_path, visibility),
        media_type="application/x-ndjson",
    )


@router.get("/{match_id}/events")
async def stream_events(
    match_id: str,
    request: Request,
    visibility: Literal["all", "public", "spoilers"] = Query(default="all"),
):
    bus = request.app.state.bus

    _get_match_or_404(request, match_id)

    history, queue = bus.subscribe(match_id)

    async def event_stream():
        try:
            for json_line in history:
                message = _sse_message(json_line, visibility)
                if message is not None:
                    yield message

            while True:
                item = await queue.get()
                if item is None:
                    break
                message = _sse_message(item, visibility)
                if message is not None:
                    yield message
        finally:
            bus.unsubscribe(match_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
