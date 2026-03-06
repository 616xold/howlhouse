from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from howlhouse.platform.access_control import ACTION_PREDICTION_MUTATION, require_mutation_access
from howlhouse.platform.store import MatchRecord

router = APIRouter(prefix="/matches/{match_id}", tags=["predictions"])


class PredictionRequest(BaseModel):
    viewer_id: str
    wolves: list[str]


def _get_match_or_404(request: Request, match_id: str) -> MatchRecord:
    store = request.app.state.store
    record = store.get_match(match_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Match not found: {match_id}")
    return record


def _match_roster_ids(record: MatchRecord) -> list[str]:
    config = record.config
    player_count = int(config.get("player_count", 0))
    return [f"p{i}" for i in range(player_count)]


def _validate_prediction_input(record: MatchRecord, payload: PredictionRequest) -> list[str]:
    viewer_id = payload.viewer_id.strip()
    if len(viewer_id) < 8 or len(viewer_id) > 128:
        raise HTTPException(status_code=422, detail="viewer_id must be between 8 and 128 chars")

    required_wolves = int(record.config.get("werewolves", 2))
    wolves = [str(player_id).strip() for player_id in payload.wolves]
    if len(wolves) != required_wolves:
        raise HTTPException(
            status_code=422,
            detail=f"wolves must contain exactly {required_wolves} player_ids",
        )
    if len(set(wolves)) != len(wolves):
        raise HTTPException(status_code=422, detail="wolves must be unique")

    valid_ids = set(_match_roster_ids(record))
    invalid = sorted(player_id for player_id in wolves if player_id not in valid_ids)
    if invalid:
        raise HTTPException(status_code=422, detail=f"Invalid player_ids: {', '.join(invalid)}")

    return sorted(wolves)


def _build_summary(record: MatchRecord, predictions: list[dict[str, Any]]) -> dict[str, Any]:
    roster = _match_roster_ids(record)
    by_player_counter = Counter({player_id: 0 for player_id in roster})
    pair_counter: Counter[tuple[str, str]] = Counter()

    for item in predictions:
        wolves = [str(player_id) for player_id in item["wolves"]]
        for player_id in wolves:
            by_player_counter[player_id] += 1
        pair_counter[tuple(sorted(wolves))] += 1

    top_pairs = [
        {"pair": list(pair), "count": count}
        for pair, count in sorted(pair_counter.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    ]

    return {
        "match_id": record.match_id,
        "total_predictions": len(predictions),
        "by_player": {player_id: by_player_counter[player_id] for player_id in roster},
        "top_pairs": top_pairs,
    }


def _prediction_rows_for_match(request: Request, match_id: str) -> list[dict[str, Any]]:
    store = request.app.state.store
    rows = store.list_predictions(match_id)
    return [{"viewer_id": row.viewer_id, "wolves": row.wolves} for row in rows]


@router.post("/predictions")
def upsert_prediction(
    match_id: str, payload: PredictionRequest, request: Request
) -> dict[str, Any]:
    require_mutation_access(request, action=ACTION_PREDICTION_MUTATION)
    store = request.app.state.store
    record = _get_match_or_404(request, match_id)

    normalized_wolves = _validate_prediction_input(record, payload)
    store.upsert_prediction(
        match_id=match_id,
        viewer_id=payload.viewer_id.strip(),
        wolves=normalized_wolves,
    )

    predictions = _prediction_rows_for_match(request, match_id)
    return _build_summary(record, predictions)


@router.get("/predictions/summary")
def get_prediction_summary(match_id: str, request: Request) -> dict[str, Any]:
    record = _get_match_or_404(request, match_id)
    predictions = _prediction_rows_for_match(request, match_id)
    return _build_summary(record, predictions)
