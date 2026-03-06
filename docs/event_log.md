# Event Log (JSONL)

The match output is an append-only JSON Lines file.

## Determinism contract (M1)

For the same config, seed, and agent implementations, replay JSONL output must be byte-for-byte identical.

Deterministic fields:

- `match_id`: `match_<seed>`
- `id`: sequential event id (`evt_000001`, `evt_000002`, ...)
- `t`: synthetic tick starting at `1` and incrementing by `1` per event
- `ts`: synthetic timestamp from a fixed UTC epoch (`2026-01-01T00:00:00Z`) plus `t` seconds

Writers must serialize JSON with `sort_keys=True`.

## Envelope (schema v1)

Each line is one JSON object with these top-level keys:

```json
{
  "v": 1,
  "id": "evt_000001",
  "t": 1,
  "ts": "2026-01-01T00:00:01Z",
  "match_id": "match_123",
  "type": "match_created",
  "visibility": "public",
  "payload": {}
}
```

- `v`: schema version (int)
- `id`: deterministic event id (string, unique within match)
- `t`: synthetic monotonic tick (int)
- `ts`: deterministic ISO UTC timestamp derived from `t` (string)
- `match_id`: deterministic match id
- `type`: event type string
- `visibility`: privacy tag string
- `payload`: event-specific object

## Event types (M1)

- `match_created`
- `roles_assigned` (private)
- `phase_started`
- `public_message`
- `vote_cast`
- `vote_result`
- `night_action` (private)
- `player_killed`
- `player_eliminated`
- `confessional` (private)
- `match_ended`

## Privacy tags

Each event includes `visibility`:

- `public`
- `private:all`
- `private:player:<player_id>`
- `private:role:werewolf`

Public outputs and UI modes must derive access strictly from this tag.
