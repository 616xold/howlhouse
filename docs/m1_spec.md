# M1 spec — Deterministic engine + JSONL replay + CLI

This doc is the **source of truth** for Milestone M1.

## Determinism requirements

A replay must be identical (byte-for-byte) when:
- config is identical
- seed is identical
- agent implementations are identical

Therefore M1 must **not** use:
- `uuid.uuid4()` for match/event IDs
- `datetime.now()` for timestamps

Instead:

- `match_id`: `match_{seed}_{N}` where `N` is drawn from the seeded RNG once (or simply `match_{seed}`).
- event ids: sequential: `evt_000001`, `evt_000002`, ...
- timestamps: synthetic: start from a fixed epoch and increment 1 second per event.

The JSON writer must use `sort_keys=True`.

## Canonical event schema (v=1)

Each line in the replay is one JSON object with exactly these top-level keys:

- `v` (int) — schema version (1)
- `id` (str) — event id (evt_000001)
- `t` (int) — synthetic tick (monotonic, starts at 1)
- `ts` (str) — ISO timestamp derived from `t` (deterministic)
- `match_id` (str)
- `type` (str)
- `visibility` (str)
- `payload` (object)

### Visibility tags

- `public`
- `private:all`
- `private:player:<player_id>`
- `private:role:werewolf`

## Ruleset (7 players)

- Roles: 2 Werewolves, 1 Seer, 1 Doctor, 3 Villagers
- Win:
  - Town wins when wolves == 0
  - Wolves win when wolves >= town_alive

## Phase loop (per day)

Day number starts at 1.

1. `night` — all alive agents act (night_action + confessional)
2. resolve night actions
3. `day_round_a` — each alive agent gets exactly 1 public message + confessional
4. `day_round_b` — same
5. `day_vote` — each alive agent votes + confessional
6. resolve vote -> elimination
7. check win, else next night

## Night actions (resolution)

- Wolves:
  - each wolf submits `kill(target)`
  - pick target by majority vote among wolves; ties broken deterministically
- Doctor:
  - submits `protect(target)`
- Seer:
  - submits `inspect(target)` and receives private result (`target_role_is_wolf: bool`)

Kill resolution:
- if protected target == kill target => no death
- otherwise target dies (killed)

## Public message quotas

- 1 per alive player per round (A and B)
- hard char cap = config.public_message_char_limit
- engine truncates over-limit text and emits truncated text

## Vote resolution

- each alive player votes for an alive target (not self by default; allow self only if needed)
- tally votes, pick max
- ties broken deterministically (seeded RNG) among tied targets

## Required tests

1. Determinism: run match twice with same seed and ensure JSONL outputs identical
2. Invariants:
   - dead players never emit actions/events after death
   - exactly 0 or 1 deaths per night (depending on protection)
   - exactly 1 elimination per day_vote phase
   - game ends immediately when win condition met
3. Replay integrity:
   - derive winner from event stream alone

## Required files to change (expected)

- `backend/howlhouse/engine/runtime/game_engine.py`
- `backend/howlhouse/engine/runtime/agents/scripted.py` (role-aware baseline agents)
- `backend/howlhouse/engine/runtime/io/replay.py` (sort_keys + stable output)
- `backend/howlhouse/cli/run_match.py` (write deterministic match_id / path)
- `backend/tests/` (new tests)
- `docs/event_log.md` (align schema)
