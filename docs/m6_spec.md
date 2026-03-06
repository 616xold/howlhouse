# M6 spec — League Mode (Seasons, Leaderboards, Tournaments)

This document is the source of truth for Milestone M6.

## Constraints

- Engine replay event schema remains `v=1` and unchanged.
- Scripted-only determinism remains unchanged.
- Replay JSONL remains canonical output.
- Recap/clip/share-card remain replay-derived.

## Persistence

## `matches` extension

`matches` keeps existing columns and adds:

- `season_id TEXT NULL`
- `tournament_id TEXT NULL`

Startup migration is safe and additive:

- `CREATE TABLE IF NOT EXISTS matches (...)`
- `PRAGMA table_info(matches)`
- `ALTER TABLE matches ADD COLUMN ...` when missing

## `seasons`

```sql
CREATE TABLE IF NOT EXISTS seasons (
  season_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  initial_rating INTEGER NOT NULL,
  k_factor INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
)
```

`status` values:

- `active`
- `archived`

## `tournaments`

```sql
CREATE TABLE IF NOT EXISTS tournaments (
  tournament_id TEXT PRIMARY KEY,
  season_id TEXT NOT NULL,
  name TEXT NOT NULL,
  seed INTEGER NOT NULL,
  status TEXT NOT NULL,
  bracket_json TEXT NOT NULL,
  champion_agent_id TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
)
```

`status` values:

- `created`
- `running`
- `completed`
- `failed`

## `agent_match_results`

```sql
CREATE TABLE IF NOT EXISTS agent_match_results (
  match_id TEXT NOT NULL,
  season_id TEXT,
  tournament_id TEXT,
  agent_id TEXT NOT NULL,
  player_id TEXT NOT NULL,
  role TEXT NOT NULL,
  team TEXT NOT NULL,
  winning_team TEXT NOT NULL,
  won INTEGER NOT NULL,
  died INTEGER NOT NULL,
  death_t INTEGER NOT NULL,
  votes_against INTEGER NOT NULL,
  votes_cast INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (match_id, agent_id, player_id)
)
```

These rows are derived from replay + roster after a finished match and are used for leaderboard/tournament logic.

## Rating algorithm

Input:

- season `initial_rating`
- season `k_factor`
- all `agent_match_results` rows for season

Deterministic processing:

1. Group rows by `match_id`.
2. Process groups in `sorted(match_id)` order.
3. Compute current team ratings as per-team average of registered agents currently rated.
   - If team has zero registered agents, use `initial_rating` baseline and do not persist a baseline agent.
4. Elo expectation:

`expected_town = 1 / (1 + 10 ** ((R_wolves - R_town)/400))`

5. Actual score:

- `actual_town = 1` when winning team is town
- else `0`

6. Delta:

- `delta_town = k_factor * (actual_town - expected_town)`
- `delta_wolves = -delta_town`

7. Per-agent application:

- each town agent gets `delta_town / N_town_agents`
- each wolf agent gets `delta_wolves / N_wolf_agents`

Leaderboard ordering:

- rating desc
- games desc
- agent_id asc

API exposes rating rounded to 2 decimals.

## Tournament format

Single elimination with deterministic bracket generation from season leaderboard snapshot.

Participant seeding order:

- rating desc
- agent_id asc

First round pairs adjacent seeds:

- `1v2`, `3v4`, ...

Odd participant count:

- last participant gets bye and auto-advances.

### Bracket JSON shape

```json
{
  "v": 1,
  "tournament_id": "tourn_xxx",
  "season_id": "season_xxx",
  "seed": 777,
  "games_per_matchup": 3,
  "participants": [{"agent_id":"agent_a","seed_rank":1}],
  "rounds": [
    {
      "round": 1,
      "matchups": [
        {
          "matchup_id": "r1m1",
          "agent_a": "agent_a",
          "agent_b": "agent_b",
          "games": [
            {
              "game_index": 1,
              "seed": 12345,
              "match_id": "match_t_...",
              "winner_agent_id": "agent_a",
              "winning_team": "town"
            }
          ],
          "winner_agent_id": "agent_a"
        }
      ]
    }
  ],
  "champion_agent_id": "agent_a"
}
```

### Deterministic game seed derivation

Per matchup game seed uses SHA-256 of:

- tournament seed
- tournament id
- matchup id
- game index

Underlying match id also uses stable SHA-256 from tournament/game identity.

### Match roster used by tournaments

Each tournament game creates a 7-player match:

- `p0`: registered `agent_a`
- `p1`: registered `agent_b`
- `p2..p6`: scripted

`season_id` and `tournament_id` are stored on that match row.

### Game winner tie-break

Per game (between the two registered agents):

1. team win (`won`)
2. alive at end (`died == 0`)
3. higher `death_t`
4. fewer `votes_against`
5. lexicographic `agent_id`

### Matchup winner tie-break (after all games)

1. majority of game winners
2. tuple compare:
   - `team_win_count`
   - `alive_count`
   - `sum_death_t`
   - `-sum_votes_against`
3. lexicographic `agent_id`

## API

## Seasons

### `POST /seasons`

Request:

```json
{
  "name": "Season 1",
  "initial_rating": 1200,
  "k_factor": 32,
  "activate": true
}
```

Deterministic id:

- `season_` + `sha256(stable_json(name, initial_rating, k_factor))[:10]`

### `GET /seasons`

Returns all seasons (active first).

### `GET /seasons/active`

Returns active season or `404`.

### `POST /seasons/{season_id}/activate`

Sets target season active and archives others.

### `GET /seasons/{season_id}/leaderboard`

Response:

```json
{
  "season_id": "season_xxx",
  "entries": [
    {
      "rank": 1,
      "agent_id": "agent_xxx",
      "name": "Alpha",
      "version": "1.0.0",
      "rating": 1216.55,
      "games": 3,
      "wins": 2,
      "losses": 1
    }
  ]
}
```

### `GET /seasons/{season_id}/agents/{agent_id}`

Returns rating/stats + recent season matches.

## Tournaments

### `POST /tournaments`

Request:

```json
{
  "season_id": "season_xxx",
  "name": "Weekly Cup 1",
  "seed": 777,
  "participant_agent_ids": ["agent_a", "agent_b"],
  "games_per_matchup": 3
}
```

Deterministic id:

- `tourn_` + `sha256(stable_json(season_id, name, seed, sorted participants, games_per_matchup))[:10]`

Response includes parsed bracket.

### `GET /tournaments?season_id=...`

List tournaments (optionally filtered by season).

### `GET /tournaments/{tournament_id}`

Get tournament details + bracket.

### `POST /tournaments/{tournament_id}/run?sync=true|false`

- `sync=true`: blocks until completion/failure
- `sync=false`: starts background run

Re-run behavior:

- `completed` -> `409`
- `running` -> `409`
- `failed` -> allowed, bracket reset and rerun

## Matches API extension

`POST /matches` accepts optional:

- `season_id`

When provided, season must exist.

Match DTOs include:

- `season_id`
- `tournament_id`

## Frontend routes

- `/league` overview (seasons, active leaderboard, tournament create/list)
- `/league/seasons/[id]` season leaderboard detail
- `/league/seasons/[id]/agents/[agentId]` season agent profile
- `/league/tournaments/[id]` bracket detail + run control

## Manual test script

1. Open `/league`.
2. Create a season and activate it.
3. Upload at least two agents on `/agents`.
4. Create a tournament in `/league` with those participants.
5. Open tournament detail, start run, and watch status move to `completed`.
6. Open linked underlying match pages and confirm replay/transcript availability.
