from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from howlhouse.league.ratings import compute_leaderboard
from howlhouse.league.tournament import (
    _reset_bracket_for_rerun,
    derive_tournament_id,
    generate_bracket,
)
from howlhouse.platform.access_control import (
    ACTION_TOURNAMENT_CREATE,
    ACTION_TOURNAMENT_RUN,
    is_admin_request,
    require_admin_access,
    require_mutation_access,
)
from howlhouse.platform.observability import increment_tournaments_run
from howlhouse.platform.store import TournamentRecord

router = APIRouter(prefix="/tournaments", tags=["tournaments"])
logger = logging.getLogger(__name__)


class CreateTournamentRequest(BaseModel):
    season_id: str
    name: str
    seed: int
    participant_agent_ids: list[str] = Field(min_length=2)
    games_per_matchup: int = Field(default=3, ge=1)


def _tournament_to_dto(record: TournamentRecord, *, admin_view: bool) -> dict[str, Any]:
    return {
        "tournament_id": record.tournament_id,
        "season_id": record.season_id,
        "name": record.name,
        "seed": record.seed,
        "created_by_identity_id": record.created_by_identity_id,
        "created_by_ip": record.created_by_ip if admin_view else None,
        "hidden_at": record.hidden_at,
        "hidden_reason": record.hidden_reason,
        "status": record.status,
        "champion_agent_id": record.champion_agent_id,
        "error": record.error,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "bracket": json.loads(record.bracket_json),
        "links": {
            "self": f"/tournaments/{record.tournament_id}",
            "run": f"/tournaments/{record.tournament_id}/run",
        },
    }


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


def _get_tournament_or_404(store, tournament_id: str) -> TournamentRecord:
    record = store.get_tournament(tournament_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Tournament not found: {tournament_id}")
    return record


@router.post("")
def create_tournament(body: CreateTournamentRequest, request: Request) -> dict[str, Any]:
    store = request.app.state.store
    actor = require_mutation_access(request, action=ACTION_TOURNAMENT_CREATE)
    season = store.get_season(body.season_id)
    if season is None:
        raise HTTPException(status_code=422, detail=f"Unknown season_id: {body.season_id}")

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name must not be empty")

    deduped_participants = sorted(set(body.participant_agent_ids))
    if len(deduped_participants) != len(body.participant_agent_ids):
        raise HTTPException(status_code=422, detail="participant_agent_ids must be unique")

    missing = [agent_id for agent_id in deduped_participants if store.get_agent(agent_id) is None]
    if missing:
        raise HTTPException(
            status_code=422, detail=f"Unknown participant agent_ids: {', '.join(missing)}"
        )

    tournament_id = derive_tournament_id(
        season_id=season.season_id,
        name=name,
        seed=body.seed,
        participant_agent_ids=deduped_participants,
        games_per_matchup=body.games_per_matchup,
    )

    season_rows = store.list_agent_match_results_for_season(season.season_id)
    computed = compute_leaderboard(
        initial_rating=season.initial_rating,
        k_factor=season.k_factor,
        rows=season_rows,
    )
    ratings_by_agent = {entry["agent_id"]: float(entry["rating"]) for entry in computed}
    for agent_id in deduped_participants:
        ratings_by_agent.setdefault(agent_id, float(season.initial_rating))

    bracket = generate_bracket(
        tournament_id=tournament_id,
        season_id=season.season_id,
        seed=body.seed,
        participant_agent_ids=deduped_participants,
        ratings_by_agent=ratings_by_agent,
        games_per_matchup=body.games_per_matchup,
    )

    record = store.upsert_tournament(
        tournament_id=tournament_id,
        season_id=season.season_id,
        name=name,
        seed=body.seed,
        status="created",
        bracket=bracket,
        champion_agent_id=bracket.get("champion_agent_id"),
        error=None,
        created_by_identity_id=actor.identity_id,
        created_by_ip=actor.client_ip,
    )
    return _tournament_to_dto(record, admin_view=is_admin_request(request))


@router.get("")
def list_tournaments(
    request: Request,
    season_id: str | None = Query(default=None),
    include_hidden: int = Query(default=0, ge=0, le=1),
) -> list[dict[str, Any]]:
    store = request.app.state.store
    if season_id is not None and store.get_season(season_id) is None:
        raise HTTPException(status_code=404, detail=f"Season not found: {season_id}")
    if include_hidden:
        require_admin_access(request)
    admin_view = is_admin_request(request)
    return [
        _tournament_to_dto(record, admin_view=admin_view)
        for record in store.list_tournaments(
            season_id=season_id, include_hidden=bool(include_hidden)
        )
    ]


@router.get("/{tournament_id}")
def get_tournament(tournament_id: str, request: Request) -> dict[str, Any]:
    store = request.app.state.store
    record = _get_tournament_or_404(store, tournament_id)
    admin_view = is_admin_request(request)
    if record.hidden_at is not None and not admin_view:
        raise HTTPException(status_code=404, detail=f"Tournament not found: {tournament_id}")
    return _tournament_to_dto(record, admin_view=admin_view)


@router.post("/{tournament_id}/run")
def run_tournament(
    tournament_id: str,
    request: Request,
    sync: bool = Query(default=False),
) -> dict[str, Any]:
    store = request.app.state.store
    require_mutation_access(request, action=ACTION_TOURNAMENT_RUN)
    record = _get_tournament_or_404(store, tournament_id)

    if not sync:
        if record.status == "completed":
            raise HTTPException(
                status_code=409,
                detail={"status": record.status, "message": "tournament already completed"},
            )

        existing_job = store.get_active_job(job_type="tournament_run", resource_id=tournament_id)
        if existing_job is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "status": record.status,
                    "message": "tournament run already queued or running",
                    "job_id": existing_job.job_id,
                },
            )

        if record.status == "running":
            running_record = record
        elif record.status in {"created", "failed"}:
            bracket = (
                _reset_bracket_for_rerun(record.bracket)
                if record.status == "failed"
                else record.bracket
            )
            running_record = store.upsert_tournament(
                tournament_id=record.tournament_id,
                season_id=record.season_id,
                name=record.name,
                seed=record.seed,
                status="running",
                bracket=bracket,
                champion_agent_id=None,
                error=None,
            )
            increment_tournaments_run("running")
            logger.info(
                "tournament_run_started",
                extra={
                    "tournament_id": tournament_id,
                    "status": "running",
                },
            )
        else:
            raise HTTPException(
                status_code=409,
                detail={"status": record.status, "message": "tournament cannot be queued"},
            )

        job = store.enqueue_job(job_type="tournament_run", resource_id=tournament_id)
        payload = _tournament_to_dto(running_record, admin_view=is_admin_request(request))
        payload["job"] = _job_to_dto(job)
        return payload

    if record.status == "completed":
        raise HTTPException(
            status_code=409,
            detail={"status": record.status, "message": "tournament already completed"},
        )
    if record.status == "running":
        raise HTTPException(
            status_code=409,
            detail={"status": record.status, "message": "tournament already running"},
        )

    runner = request.app.state.tournament_runner
    try:
        updated = runner.run(tournament_id, sync=sync)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"Tournament not found: {tournament_id}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return _tournament_to_dto(updated, admin_view=is_admin_request(request))
