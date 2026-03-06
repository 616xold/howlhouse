from __future__ import annotations

from typing import Literal, TypedDict


class GeneratedFrom(TypedDict):
    last_event_id: str
    last_event_ts: str


class WinnerSummary(TypedDict):
    team: Literal["town", "werewolves"]
    reason: str
    day: int


class RecapStats(TypedDict):
    days: int
    public_messages: int
    votes: int
    night_kills: int
    eliminations: int


class QuoteSummary(TypedDict):
    event_id: str
    player_id: str
    text: str
    day: int
    phase: str


class ConfessionalHighlight(TypedDict):
    event_id: str
    player_id: str
    text: str
    phase: str


class ClipSuggestion(TypedDict):
    clip_id: str
    kind: Literal["death", "vote", "close_vote", "contradiction", "claim", "ending"]
    title: str
    reason: str
    start_event_id: str
    end_event_id: str
    score: int


class RecapPayload(TypedDict):
    v: int
    match_id: str
    generated_from: GeneratedFrom
    winner: WinnerSummary
    stats: RecapStats
    roles: dict[str, str]
    bullets: list[str]
    narration_15s: str
    key_quotes: list[QuoteSummary]
    confessional_highlights: list[ConfessionalHighlight]
    clips: list[ClipSuggestion]
