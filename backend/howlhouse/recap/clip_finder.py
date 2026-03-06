from __future__ import annotations

import re
from typing import Any

from .models import ClipSuggestion

CLAIM_PATTERN = re.compile(
    r"\b(?:i\s+am|i'm|as)\s+(?:the\s+)?(seer|doctor|villager|werewolf)\b|\bclaim(?:ing|ed)?\b",
    re.IGNORECASE,
)
SUSPECT_PATTERN = re.compile(r"\bsuspect\s+(p\d+)\b", re.IGNORECASE)


class _ClipCandidate(dict[str, Any]):
    pass


def _as_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return default


def _slugify(text: str) -> str:
    lowered = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    return slug or "segment"


def _add_candidate(
    candidates: list[_ClipCandidate],
    seen: set[tuple[str, str, str, str]],
    *,
    kind: str,
    title: str,
    reason: str,
    start_event_id: str,
    end_event_id: str,
    score: int,
) -> None:
    key = (kind, start_event_id, end_event_id, title)
    if key in seen:
        return
    seen.add(key)
    candidates.append(
        {
            "kind": kind,
            "title": title,
            "reason": reason,
            "start_event_id": start_event_id,
            "end_event_id": end_event_id,
            "score": max(0, min(100, int(score))),
            "slug": _slugify(title),
        }
    )


def _safe_excerpt(text: str, *, limit: int = 72) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3]}..."


def _finalize(candidates: list[_ClipCandidate]) -> list[ClipSuggestion]:
    sorted_candidates = sorted(
        candidates,
        key=lambda item: (
            -int(item["score"]),
            str(item["slug"]),
            str(item["start_event_id"]),
            str(item["end_event_id"]),
        ),
    )[:10]
    result: list[ClipSuggestion] = []
    for index, item in enumerate(sorted_candidates, start=1):
        clip_id = f"clip_{index:03d}_{item['slug']}"
        result.append(
            {
                "clip_id": clip_id,
                "kind": str(item["kind"]),
                "title": str(item["title"]),
                "reason": str(item["reason"]),
                "start_event_id": str(item["start_event_id"]),
                "end_event_id": str(item["end_event_id"]),
                "score": int(item["score"]),
            }
        )
    return result


def _backfill_minimum(
    *,
    events: list[dict[str, Any]],
    candidates: list[_ClipCandidate],
    seen: set[tuple[str, str, str, str]],
    first_kill_event: dict[str, Any] | None,
    first_night_phase_event: dict[str, Any] | None,
    first_vote_result_event: dict[str, Any] | None,
    ending_event: dict[str, Any] | None,
) -> None:
    if len(candidates) >= 3:
        return

    if first_kill_event is not None:
        payload = _as_payload(first_kill_event)
        player_id = str(payload.get("player_id", "unknown"))
        _add_candidate(
            candidates,
            seen,
            kind="death",
            title="Night kill",
            reason=f"{player_id} died during the night.",
            start_event_id=str(first_kill_event.get("id", "")),
            end_event_id=str(first_kill_event.get("id", "")),
            score=72,
        )
    elif first_night_phase_event is not None:
        _add_candidate(
            candidates,
            seen,
            kind="death",
            title="No death night",
            reason="An early night resolved without a public kill.",
            start_event_id=str(first_night_phase_event.get("id", "")),
            end_event_id=str(first_night_phase_event.get("id", "")),
            score=55,
        )

    if len(candidates) < 3 and first_vote_result_event is not None:
        payload = _as_payload(first_vote_result_event)
        eliminated = str(payload.get("eliminated", "unknown"))
        _add_candidate(
            candidates,
            seen,
            kind="vote",
            title="First vote result",
            reason=f"The table removed {eliminated} in the first vote result.",
            start_event_id=str(first_vote_result_event.get("id", "")),
            end_event_id=str(first_vote_result_event.get("id", "")),
            score=68,
        )

    if len(candidates) < 3 and ending_event is not None:
        payload = _as_payload(ending_event)
        winner = str(payload.get("winning_team", "unknown"))
        _add_candidate(
            candidates,
            seen,
            kind="ending",
            title="Final reveal",
            reason=f"The match ended with {winner} victory.",
            start_event_id=str(ending_event.get("id", "")),
            end_event_id=str(ending_event.get("id", "")),
            score=95,
        )

    if len(candidates) < 3 and events:
        fallback_event = events[0]
        _add_candidate(
            candidates,
            seen,
            kind="vote",
            title="Opening moment",
            reason="Use this segment as a deterministic fallback clip.",
            start_event_id=str(fallback_event.get("id", "")),
            end_event_id=str(fallback_event.get("id", "")),
            score=40,
        )


def find_clips(events: list[dict[str, Any]]) -> list[ClipSuggestion]:
    if not events:
        return []

    candidates: list[_ClipCandidate] = []
    seen: set[tuple[str, str, str, str]] = set()

    suspicion_by_player_day: dict[tuple[str, int], tuple[str, str]] = {}
    first_kill_event: dict[str, Any] | None = None
    first_night_phase_event: dict[str, Any] | None = None
    first_vote_result_event: dict[str, Any] | None = None
    ending_event: dict[str, Any] | None = None

    for event in events:
        event_id = str(event.get("id", ""))
        event_type = str(event.get("type", ""))
        payload = _as_payload(event)

        if (
            event_type == "phase_started"
            and first_night_phase_event is None
            and str(payload.get("phase", "")) == "night"
        ):
            first_night_phase_event = event

        if event_type == "public_message":
            player_id = str(payload.get("player_id", ""))
            day = _as_int(payload.get("day"), default=0)
            text = str(payload.get("text", ""))
            text_excerpt = _safe_excerpt(text)

            if CLAIM_PATTERN.search(text):
                _add_candidate(
                    candidates,
                    seen,
                    kind="claim",
                    title=f"Claim from {player_id}",
                    reason=f'{player_id} made a notable claim: "{text_excerpt}"',
                    start_event_id=event_id,
                    end_event_id=event_id,
                    score=70,
                )

            suspect_match = SUSPECT_PATTERN.search(text)
            if suspect_match:
                suspect_target = suspect_match.group(1).lower()
                suspicion_by_player_day[(player_id, day)] = (suspect_target, event_id)

        if event_type == "vote_cast":
            voter_id = str(payload.get("voter_id", ""))
            target_id = str(payload.get("target_id", ""))
            day = _as_int(payload.get("day"), default=0)
            suspicion = suspicion_by_player_day.get((voter_id, day))
            if suspicion is not None:
                suspected_target, suspicion_event_id = suspicion
                if suspected_target != target_id:
                    _add_candidate(
                        candidates,
                        seen,
                        kind="contradiction",
                        title=f"Vote contradiction by {voter_id}",
                        reason=(
                            f"{voter_id} said they suspected {suspected_target} "
                            f"but voted {target_id}."
                        ),
                        start_event_id=suspicion_event_id,
                        end_event_id=event_id,
                        score=82,
                    )

        if event_type == "vote_result":
            if first_vote_result_event is None:
                first_vote_result_event = event

            day = _as_int(payload.get("day"), default=0)
            eliminated = str(payload.get("eliminated", ""))
            tally = payload.get("tally")
            tally_pairs: list[tuple[str, int]] = []
            if isinstance(tally, dict):
                for player_id, raw_count in tally.items():
                    tally_pairs.append((str(player_id), _as_int(raw_count, default=0)))
            tally_pairs.sort(key=lambda item: (-item[1], item[0]))

            _add_candidate(
                candidates,
                seen,
                kind="vote",
                title=f"Day {day} vote result",
                reason=f"The vote eliminated {eliminated}.",
                start_event_id=event_id,
                end_event_id=event_id,
                score=66,
            )

            if len(tally_pairs) >= 2:
                diff = tally_pairs[0][1] - tally_pairs[1][1]
                if diff <= 1:
                    leader, lead_votes = tally_pairs[0]
                    runner_up, runner_up_votes = tally_pairs[1]
                    _add_candidate(
                        candidates,
                        seen,
                        kind="close_vote",
                        title=f"Close vote on day {day}",
                        reason=(
                            f"{leader} ({lead_votes}) barely beat {runner_up} ({runner_up_votes})."
                        ),
                        start_event_id=event_id,
                        end_event_id=event_id,
                        score=78,
                    )

        if event_type == "player_killed":
            if first_kill_event is None:
                first_kill_event = event
            player_id = str(payload.get("player_id", ""))
            day = _as_int(payload.get("day"), default=0)
            _add_candidate(
                candidates,
                seen,
                kind="death",
                title=f"Night {day} kill",
                reason=f"{player_id} was killed overnight.",
                start_event_id=event_id,
                end_event_id=event_id,
                score=74,
            )

        if event_type == "match_ended":
            ending_event = event
            winner = str(payload.get("winning_team", ""))
            reason = str(payload.get("reason", ""))
            _add_candidate(
                candidates,
                seen,
                kind="ending",
                title="Match ending",
                reason=f"{winner} won by {reason}.",
                start_event_id=event_id,
                end_event_id=event_id,
                score=98,
            )

    _backfill_minimum(
        events=events,
        candidates=candidates,
        seen=seen,
        first_kill_event=first_kill_event,
        first_night_phase_event=first_night_phase_event,
        first_vote_result_event=first_vote_result_event,
        ending_event=ending_event,
    )

    return _finalize(candidates)
