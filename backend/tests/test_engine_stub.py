import json
from collections import Counter

from howlhouse.cli.run_match import build_scripted_agents
from howlhouse.engine.domain.enums import Phase
from howlhouse.engine.domain.models import GameConfig
from howlhouse.engine.runtime.game_engine import GameEngine
from howlhouse.engine.runtime.replay_integrity import (
    derive_replay_outcome,
    derive_winner_from_events,
)


def _run_scripted_match(seed: int = 123, **overrides: int):
    cfg = GameConfig(rng_seed=seed, **overrides)
    engine = GameEngine(cfg)
    agents = build_scripted_agents(cfg)
    result = engine.run_match(agents=agents)
    return cfg, result


def _stable_jsonl(events: list[dict]) -> str:
    return "".join(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n" for event in events)


def _roles_map(events: list[dict]) -> dict[str, str]:
    for event in events:
        if event["type"] == "roles_assigned":
            return event["payload"]["roles"]
    raise AssertionError("roles_assigned event missing")


def test_determinism_byte_for_byte():
    _, result_a = _run_scripted_match(seed=123)
    _, result_b = _run_scripted_match(seed=123)

    assert result_a.match_id == result_b.match_id
    assert result_a.winning_team == result_b.winning_team
    assert _stable_jsonl(result_a.events) == _stable_jsonl(result_b.events)


def test_invariant_dead_players_do_not_act_after_death():
    _, result = _run_scripted_match(seed=123)

    death_tick: dict[str, int] = {}
    for event in result.events:
        if event["type"] in {"player_killed", "player_eliminated"}:
            player_id = event["payload"]["player_id"]
            death_tick.setdefault(player_id, event["t"])

    for event in result.events:
        if event["type"] == "public_message":
            actor_id = event["payload"]["player_id"]
        elif event["type"] == "vote_cast":
            actor_id = event["payload"]["voter_id"]
        elif event["type"] == "night_action":
            actor_id = event["payload"]["actor_id"]
        else:
            continue

        if actor_id in death_tick:
            assert event["t"] <= death_tick[actor_id], (
                f"{actor_id} acted after death at tick {death_tick[actor_id]}"
            )


def test_invariant_max_one_night_death_per_day():
    _, result = _run_scripted_match(seed=123)

    kills_by_day = Counter(
        event["payload"]["day"]
        for event in result.events
        if event["type"] == "player_killed" and not event["payload"].get("prevented", False)
    )
    assert kills_by_day
    assert all(count <= 1 for count in kills_by_day.values())


def test_invariant_exactly_one_elimination_per_vote_phase():
    _, result = _run_scripted_match(seed=123)

    vote_days = [
        event["payload"]["day"]
        for event in result.events
        if event["type"] == "phase_started"
        and event["payload"].get("phase") == Phase.DAY_VOTE.value
    ]
    elimination_counts = Counter(
        event["payload"]["day"] for event in result.events if event["type"] == "player_eliminated"
    )

    assert vote_days
    for day in vote_days:
        assert elimination_counts[day] == 1
    assert set(elimination_counts).issubset(set(vote_days))


def test_invariant_game_ends_immediately_when_condition_met():
    _, result = _run_scripted_match(seed=123)
    events = result.events
    role_map = _roles_map(events)
    alive = set(role_map.keys())

    condition_met_index: int | None = None
    for idx, event in enumerate(events):
        if event["type"] in {"player_killed", "player_eliminated"}:
            alive.discard(event["payload"]["player_id"])

        wolves_alive = sum(1 for player_id in alive if role_map[player_id] == "werewolf")
        town_alive = len(alive) - wolves_alive
        if condition_met_index is None and (wolves_alive == 0 or wolves_alive >= town_alive):
            condition_met_index = idx

    assert condition_met_index is not None
    assert condition_met_index + 2 == len(events) - 1
    assert events[condition_met_index + 1]["type"] == "phase_started"
    assert events[condition_met_index + 1]["payload"]["phase"] == Phase.GAME_OVER.value
    assert events[condition_met_index + 2]["type"] == "match_ended"


def test_invariant_votes_target_alive_players():
    _, result = _run_scripted_match(seed=123)
    alive = set(_roles_map(result.events).keys())

    for event in result.events:
        if event["type"] == "vote_cast":
            payload = event["payload"]
            assert payload["voter_id"] in alive
            assert payload["target_id"] in alive
        if event["type"] in {"player_killed", "player_eliminated"}:
            alive.discard(event["payload"]["player_id"])


def test_invariant_public_message_quota_and_char_cap():
    cfg, result = _run_scripted_match(seed=123)

    by_round_player = Counter()
    for event in result.events:
        if event["type"] != "public_message":
            continue
        payload = event["payload"]
        key = (payload["day"], payload["round"], payload["player_id"])
        by_round_player[key] += 1
        assert len(payload["text"]) <= cfg.public_message_char_limit

    assert by_round_player
    assert all(count == 1 for count in by_round_player.values())


def test_replay_winner_derivation():
    _, result = _run_scripted_match(seed=456)

    replay_outcome = derive_replay_outcome(result.events)
    assert replay_outcome.match_id == result.match_id
    assert replay_outcome.winning_team == result.winning_team
    assert derive_winner_from_events(result.events) == result.winning_team
