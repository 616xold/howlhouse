from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from howlhouse.league.ratings import compute_agent_profile, compute_leaderboard
from howlhouse.platform.access_control import ACTION_SEASON_MUTATION, require_mutation_access
from howlhouse.platform.store import SeasonRecord

router = APIRouter(prefix="/seasons", tags=["seasons"])


class CreateSeasonRequest(BaseModel):
    name: str
    initial_rating: int = Field(default=1200, ge=1)
    k_factor: int = Field(default=32, ge=1)
    activate: bool = True


def _season_to_dto(record: SeasonRecord) -> dict[str, Any]:
    return {
        "season_id": record.season_id,
        "name": record.name,
        "status": record.status,
        "initial_rating": record.initial_rating,
        "k_factor": record.k_factor,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _season_id_for_request(payload: CreateSeasonRequest) -> str:
    stable_payload = {
        "name": payload.name.strip(),
        "initial_rating": int(payload.initial_rating),
        "k_factor": int(payload.k_factor),
    }
    digest = hashlib.sha256(
        json.dumps(stable_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:10]
    return f"season_{digest}"


def _get_season_or_404(store, season_id: str) -> SeasonRecord:
    record = store.get_season(season_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Season not found: {season_id}")
    return record


@router.post("")
def create_season(body: CreateSeasonRequest, request: Request) -> dict[str, Any]:
    require_mutation_access(request, action=ACTION_SEASON_MUTATION)
    store = request.app.state.store
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name must not be empty")

    season_id = _season_id_for_request(body)
    record = store.create_season_if_missing(
        season_id=season_id,
        name=name,
        status="active" if body.activate else "archived",
        initial_rating=body.initial_rating,
        k_factor=body.k_factor,
    )
    if body.activate:
        record = store.set_active_season(record.season_id)
    return _season_to_dto(record)


@router.get("")
def list_seasons(request: Request) -> list[dict[str, Any]]:
    store = request.app.state.store
    return [_season_to_dto(record) for record in store.list_seasons()]


@router.get("/active")
def get_active_season(request: Request) -> dict[str, Any]:
    store = request.app.state.store
    record = store.get_active_season()
    if record is None:
        raise HTTPException(status_code=404, detail="No active season")
    return _season_to_dto(record)


@router.post("/{season_id}/activate")
def activate_season(season_id: str, request: Request) -> dict[str, Any]:
    require_mutation_access(request, action=ACTION_SEASON_MUTATION)
    store = request.app.state.store
    try:
        record = store.set_active_season(season_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Season not found: {season_id}") from exc
    return _season_to_dto(record)


@router.get("/{season_id}/leaderboard")
def get_season_leaderboard(season_id: str, request: Request) -> dict[str, Any]:
    store = request.app.state.store
    season = _get_season_or_404(store, season_id)

    season_rows = store.list_agent_match_results_for_season(season_id)
    computed_entries = compute_leaderboard(
        initial_rating=season.initial_rating,
        k_factor=season.k_factor,
        rows=season_rows,
    )
    computed_by_agent = {entry["agent_id"]: entry for entry in computed_entries}

    for agent in store.list_agents():
        computed_by_agent.setdefault(
            agent.agent_id,
            {
                "agent_id": agent.agent_id,
                "rating": float(season.initial_rating),
                "games": 0,
                "wins": 0,
                "losses": 0,
            },
        )

    ordered = sorted(
        computed_by_agent.values(),
        key=lambda entry: (-float(entry["rating"]), -int(entry["games"]), str(entry["agent_id"])),
    )

    agents_by_id = {agent.agent_id: agent for agent in store.list_agents()}
    entries: list[dict[str, Any]] = []
    for index, entry in enumerate(ordered, start=1):
        agent_record = agents_by_id.get(str(entry["agent_id"]))
        entries.append(
            {
                "rank": index,
                "agent_id": str(entry["agent_id"]),
                "name": agent_record.name if agent_record else str(entry["agent_id"]),
                "version": agent_record.version if agent_record else "-",
                "rating": round(float(entry["rating"]), 2),
                "games": int(entry["games"]),
                "wins": int(entry["wins"]),
                "losses": int(entry["losses"]),
            }
        )

    return {
        "season_id": season_id,
        "entries": entries,
    }


@router.get("/{season_id}/agents/{agent_id}")
def get_agent_profile(season_id: str, agent_id: str, request: Request) -> dict[str, Any]:
    store = request.app.state.store
    _get_season_or_404(store, season_id)

    agent = store.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    profile = compute_agent_profile(store=store, season_id=season_id, agent_id=agent_id)
    profile["name"] = agent.name
    profile["version"] = agent.version
    return profile
