from __future__ import annotations

import enum


class Role(enum.StrEnum):
    WEREWOLF = "werewolf"
    SEER = "seer"
    DOCTOR = "doctor"
    VILLAGER = "villager"


class Phase(enum.StrEnum):
    SETUP = "setup"
    NIGHT = "night"
    DAY_ROUND_A = "day_round_a"
    DAY_ROUND_B = "day_round_b"
    DAY_VOTE = "day_vote"
    GAME_OVER = "game_over"


class Visibility(enum.StrEnum):
    PUBLIC = "public"
    PRIVATE_ALL = "private:all"
    # More granular privacy tags are strings like:
    # private:player:<player_id>
    # private:role:werewolf
