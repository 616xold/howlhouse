from __future__ import annotations

from collections import Counter
from typing import Any

from howlhouse.engine.runtime.replay_integrity import derive_replay_outcome

from .clip_finder import find_clips
from .models import RecapPayload


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


def _build_bullets(
    *,
    winner_team: str,
    winner_reason: str,
    winner_day: int,
    days: int,
    public_messages: int,
    votes: int,
    night_kills: int,
    eliminations: int,
    loudest_player: str | None,
    loudest_count: int,
    most_accused_player: str | None,
    most_accused_count: int,
) -> list[str]:
    bullets = [
        f"Winner: {winner_team} ({winner_reason}) on day {winner_day}.",
        f"The game ran for {days} day(s) and produced {public_messages} public message(s).",
        (
            f"Night kills: {night_kills}; daytime eliminations: {eliminations}; "
            f"total votes cast: {votes}."
        ),
    ]

    if loudest_player is not None:
        bullets.append(f"Most talkative player: {loudest_player} with {loudest_count} message(s).")
    else:
        bullets.append("Most talkative player: none (no public messages were logged).")

    if most_accused_player is not None:
        bullets.append(
            f"Most accused player: {most_accused_player} with {most_accused_count} vote(s) against."
        )
    else:
        bullets.append("Most accused player: none (no vote_cast events were logged).")

    while len(bullets) < 5:
        bullets.append(f"Deterministic recap note: {len(bullets) + 1}.")
    return bullets[:5]


def generate_recap(events: list[dict[str, Any]]) -> RecapPayload:
    if not events:
        raise ValueError("Cannot generate recap from an empty event list")

    match_id = str(events[0].get("match_id", ""))
    last_event = events[-1]
    generated_from = {
        "last_event_id": str(last_event.get("id", "")),
        "last_event_ts": str(last_event.get("ts", "")),
    }

    public_messages = 0
    votes = 0
    night_kills = 0
    eliminations = 0
    days = 1

    current_phase = "setup"
    roles: dict[str, str] = {}
    key_quotes: list[dict[str, Any]] = []
    confessional_highlights: list[dict[str, Any]] = []

    message_count_by_player: Counter[str] = Counter()
    vote_targets: Counter[str] = Counter()

    winner_team = "town"
    winner_reason = "all_werewolves_eliminated"
    winner_day = 1

    for event in events:
        event_id = str(event.get("id", ""))
        event_type = str(event.get("type", ""))
        payload = _as_payload(event)

        event_day = _as_int(payload.get("day"), default=0)
        if event_day > 0:
            days = max(days, event_day)

        if event_type == "phase_started":
            phase_value = payload.get("phase")
            if isinstance(phase_value, str) and phase_value:
                current_phase = phase_value
            continue

        if event_type == "roles_assigned":
            roles_raw = payload.get("roles")
            if isinstance(roles_raw, dict):
                roles = {
                    str(player_id): str(role)
                    for player_id, role in roles_raw.items()
                    if isinstance(player_id, str)
                }
            continue

        if event_type == "public_message":
            public_messages += 1
            player_id = str(payload.get("player_id", ""))
            text = str(payload.get("text", ""))
            message_count_by_player[player_id] += 1
            if len(key_quotes) < 3 and text:
                key_quotes.append(
                    {
                        "event_id": event_id,
                        "player_id": player_id,
                        "text": text,
                        "day": _as_int(payload.get("day"), default=days),
                        "phase": current_phase,
                    }
                )
            continue

        if event_type == "vote_cast":
            votes += 1
            target_id = str(payload.get("target_id", ""))
            if target_id:
                vote_targets[target_id] += 1
            continue

        if event_type == "player_killed":
            night_kills += 1
            continue

        if event_type == "player_eliminated":
            eliminations += 1
            continue

        if event_type == "confessional":
            if len(confessional_highlights) < 5:
                confessional_highlights.append(
                    {
                        "event_id": event_id,
                        "player_id": str(payload.get("player_id", "")),
                        "text": str(payload.get("text", "")),
                        "phase": str(payload.get("phase", current_phase)),
                    }
                )
            continue

        if event_type == "match_ended":
            winner_team = str(payload.get("winning_team", winner_team))
            winner_reason = str(payload.get("reason", winner_reason))
            winner_day = _as_int(payload.get("day"), default=days)
            continue

    # Ensure winner_team aligns with replay-derived outcome when possible.
    try:
        outcome = derive_replay_outcome(events)
        winner_team = outcome.winning_team
    except ValueError:
        pass

    loudest_player: str | None = None
    loudest_count = 0
    if message_count_by_player:
        loudest_player, loudest_count = sorted(
            message_count_by_player.items(), key=lambda item: (-item[1], item[0])
        )[0]

    most_accused_player: str | None = None
    most_accused_count = 0
    if vote_targets:
        most_accused_player, most_accused_count = sorted(
            vote_targets.items(), key=lambda item: (-item[1], item[0])
        )[0]

    bullets = _build_bullets(
        winner_team=winner_team,
        winner_reason=winner_reason,
        winner_day=winner_day,
        days=days,
        public_messages=public_messages,
        votes=votes,
        night_kills=night_kills,
        eliminations=eliminations,
        loudest_player=loudest_player,
        loudest_count=loudest_count,
        most_accused_player=most_accused_player,
        most_accused_count=most_accused_count,
    )

    narration_15s = (
        f"Day {winner_day} ended with {winner_team} in control. "
        f"The village exchanged {public_messages} public messages, cast {votes} votes, "
        f"and saw {night_kills} night kill(s) with {eliminations} elimination(s)."
    )

    recap: RecapPayload = {
        "v": 1,
        "match_id": match_id,
        "generated_from": generated_from,
        "winner": {
            "team": winner_team,
            "reason": winner_reason,
            "day": winner_day,
        },
        "stats": {
            "days": days,
            "public_messages": public_messages,
            "votes": votes,
            "night_kills": night_kills,
            "eliminations": eliminations,
        },
        "roles": {player_id: roles[player_id] for player_id in sorted(roles)},
        "bullets": bullets,
        "narration_15s": narration_15s,
        "key_quotes": key_quotes,
        "confessional_highlights": confessional_highlights,
        "clips": find_clips(events),
    }
    return recap
