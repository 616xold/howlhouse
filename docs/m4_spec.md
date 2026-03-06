# M4 spec — Town Crier recap, Clip Finder, Share Cards

This document is the source of truth for Milestone M4.

## Constraints

- Engine event schema remains JSONL envelope `v=1`.
- Deterministic replay generation remains unchanged.
- Recap and clip generation are pure functions of replay events.
- Replay JSONL is canonical source of truth.

## Recap generation

`generate_recap(events: list[dict]) -> dict` produces a deterministic payload:

```json
{
  "v": 1,
  "match_id": "match_123",
  "generated_from": {
    "last_event_id": "evt_000123",
    "last_event_ts": "2026-01-01T00:02:03Z"
  },
  "winner": {"team": "town", "reason": "all_werewolves_eliminated", "day": 2},
  "stats": {"days": 2, "public_messages": 28, "votes": 12, "night_kills": 1, "eliminations": 2},
  "roles": {"p0": "villager", "p1": "werewolf"},
  "bullets": ["...", "...", "...", "...", "..."],
  "narration_15s": "...",
  "key_quotes": [{"event_id": "...", "player_id": "...", "text": "...", "day": 1, "phase": "day_round_a"}],
  "confessional_highlights": [{"event_id": "...", "player_id": "...", "text": "...", "phase": "night"}],
  "clips": [{"clip_id": "clip_001_match_ending", "kind": "ending", "title": "...", "reason": "...", "start_event_id": "...", "end_event_id": "...", "score": 98}]
}
```

Rules:

- `bullets` is always exactly length 5.
- `key_quotes` contains up to 3 deterministic public-message quotes.
- `confessional_highlights` contains up to 5 deterministic confessional excerpts.
- `generated_from.last_event_ts` comes from replay last event `ts`.

## Clip Finder

`find_clips(events: list[dict]) -> list[dict]` returns between 3 and 10 deterministic clips.

Clip schema:

```json
{
  "clip_id": "clip_001_close_vote_on_day_1",
  "kind": "close_vote",
  "title": "Close vote on day 1",
  "reason": "p4 (2) barely beat p5 (1).",
  "start_event_id": "evt_000040",
  "end_event_id": "evt_000040",
  "score": 78
}
```

Supported kinds:

- `death`
- `vote`
- `close_vote`
- `contradiction`
- `claim`
- `ending`

Heuristics:

- claim: regex detection in `public_message`
- contradiction: player says `suspect <pid>` then votes another target on the same day
- close vote: top-two tally difference `<= 1` in `vote_result`
- death, vote, and ending moments from core events

Deterministic guarantees:

- if heuristics produce fewer than 3 clips, deterministic backfills are added
- final sort: score descending, then stable slug/event tie-breakers
- `clip_id` is assigned after ordering: `clip_{index:03d}_{slug}`

## Share cards

`generate_share_cards(match_id, recap, output_dir)` creates deterministic PNG files:

- `replays/share_cards/<match_id>_public.png`
- `replays/share_cards/<match_id>_spoilers.png`

Rules:

- fixed canvas size `1080x1080`
- fixed palette and text positions
- deterministic character-count line wrapping
- no random identifiers, no dynamic timestamps
- public card is teaser mode (no winner/roles)
- spoilers card includes winner context and recap bullets

## Persistence

SQLite table:

```sql
CREATE TABLE IF NOT EXISTS recaps (
  match_id TEXT PRIMARY KEY,
  recap_json TEXT NOT NULL,
  share_card_public_path TEXT NOT NULL,
  share_card_spoilers_path TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
)
```

Notes:

- `recap_json` is stored with stable JSON serialization (`sort_keys=True`).
- `created_at/updated_at` are store timestamps; recap content remains deterministic.

## Runtime wiring

After a successful match run:

1. mark match `finished`
2. close SSE bus immediately
3. read canonical replay NDJSON
4. generate recap + share cards
5. upsert recap record

If recap/share-card generation fails, match is marked `failed` with error.

## API

### `GET /matches/{match_id}/recap?visibility=public|spoilers|all`

Default: `public`

- `public`: omits `roles`, omits `confessional_highlights`
- `spoilers`: includes `roles`, omits `confessional_highlights`
- `all`: full recap payload

If recap is not ready: `409` with status/message.

### `GET /matches/{match_id}/share-card?visibility=public|spoilers`

Returns `image/png`.

- `public` returns public teaser card
- `spoilers` returns spoilers card

If card is not ready: `409` with status/message.
