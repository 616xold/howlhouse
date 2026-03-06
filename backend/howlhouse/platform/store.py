from __future__ import annotations

import ipaddress
import json
import sqlite3
import threading
import uuid
from collections.abc import Iterable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from howlhouse.platform.db import DatabaseKind, detect_database_kind

try:  # pragma: no cover - optional runtime dependency for postgres mode
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover
    psycopg = None
    dict_row = None


@dataclass(frozen=True)
class MatchRecord:
    match_id: str
    seed: int
    agent_set: str
    config_json: str
    names_json: str
    season_id: str | None
    tournament_id: str | None
    status: str
    created_at: str
    started_at: str | None
    finished_at: str | None
    replay_path: str | None
    replay_key: str | None
    replay_uri: str | None
    winner: str | None
    error: str | None
    postprocess_error: str | None
    created_by_identity_id: str | None
    created_by_ip: str | None
    hidden_at: str | None
    hidden_reason: str | None

    @property
    def config(self) -> dict:
        return json.loads(self.config_json)

    @property
    def names(self) -> dict:
        return json.loads(self.names_json)


@dataclass(frozen=True)
class PredictionRecord:
    match_id: str
    viewer_id: str
    wolves_json: str
    created_at: str
    updated_at: str

    @property
    def wolves(self) -> list[str]:
        return json.loads(self.wolves_json)


@dataclass(frozen=True)
class RecapRecord:
    match_id: str
    recap_json: str
    share_card_public_path: str
    share_card_spoilers_path: str
    recap_key: str | None
    share_card_public_key: str | None
    share_card_spoilers_key: str | None
    created_at: str
    updated_at: str

    @property
    def recap(self) -> dict:
        return json.loads(self.recap_json)


@dataclass(frozen=True)
class AgentRecord:
    agent_id: str
    name: str
    version: str
    runtime_type: str
    strategy_text: str
    package_path: str
    entrypoint: str
    created_at: str
    updated_at: str
    created_by_identity_id: str | None
    created_by_ip: str | None
    hidden_at: str | None
    hidden_reason: str | None


@dataclass(frozen=True)
class MatchPlayerRecord:
    match_id: str
    player_id: str
    agent_type: str
    agent_id: str | None


@dataclass(frozen=True)
class SeasonRecord:
    season_id: str
    name: str
    status: str
    initial_rating: int
    k_factor: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class TournamentRecord:
    tournament_id: str
    season_id: str
    name: str
    seed: int
    status: str
    bracket_json: str
    champion_agent_id: str | None
    error: str | None
    created_at: str
    updated_at: str
    created_by_identity_id: str | None
    created_by_ip: str | None
    hidden_at: str | None
    hidden_reason: str | None

    @property
    def bracket(self) -> dict:
        return json.loads(self.bracket_json)


@dataclass(frozen=True)
class AgentMatchResultRecord:
    match_id: str
    season_id: str | None
    tournament_id: str | None
    agent_id: str
    player_id: str
    role: str
    team: str
    winning_team: str
    won: int
    died: int
    death_t: int
    votes_against: int
    votes_cast: int
    created_at: str


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    job_type: str
    resource_id: str
    status: str
    priority: int
    created_at: str
    updated_at: str
    locked_by: str | None
    locked_at: str | None
    attempts: int
    error: str | None


@dataclass(frozen=True)
class UsageEventRecord:
    event_id: str
    identity_id: str | None
    client_ip: str
    action: str
    created_at: str


@dataclass(frozen=True)
class BlockRecord:
    block_id: str
    block_type: str
    value: str
    reason: str | None
    created_at: str
    expires_at: str | None
    created_by_identity_id: str | None


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sqlite_path_from_database_url(database_url: str) -> str:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        msg = f"Expected sqlite:/// database URL; got: {database_url}"
        raise ValueError(msg)
    raw = database_url[len(prefix) :]
    if not raw:
        raise ValueError("sqlite database URL path is empty")
    if raw == ":memory:":
        return raw
    return str(Path(raw))


def postgres_url_from_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url
    if database_url.startswith("postgres://"):
        return "postgresql://" + database_url[len("postgres://") :]
    msg = f"Only postgresql:// database URLs are supported for postgres mode; got: {database_url}"
    raise ValueError(msg)


class MatchStore:
    def __init__(self, database_url: str):
        self._database_url = database_url
        self._database_path: str | None = None
        self._dialect = detect_database_kind(database_url).value
        if self._dialect == DatabaseKind.SQLITE.value:
            self._database_path = sqlite_path_from_database_url(database_url)
            if self._database_path != ":memory:":
                Path(self._database_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._database_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        elif self._dialect == DatabaseKind.POSTGRES.value:
            if psycopg is None or dict_row is None:
                raise RuntimeError(
                    "psycopg is required for postgresql database URLs. Install backend requirements."
                )
            self._conn = psycopg.connect(
                postgres_url_from_database_url(database_url),
                row_factory=dict_row,
            )
        self._lock = threading.Lock()

    @property
    def database_url(self) -> str:
        return self._database_url

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _exec(self, query: str, params: tuple[Any, ...] | list[Any] | None = None):
        if self._dialect == "postgresql":
            translated = query.replace("?", "%s")
            return self._conn.execute(translated, params or ())
        return self._conn.execute(query, params or ())

    def _commit(self) -> None:
        try:
            self._conn.commit()
        except Exception:
            self._rollback()
            raise

    def _rollback(self) -> None:
        self._conn.rollback()

    @contextmanager
    def _write_guard_locked(self):
        try:
            yield
        except Exception:
            self._rollback()
            raise

    def _columns_for_table_locked(self, table_name: str) -> set[str]:
        if self._dialect == "postgresql":
            rows = self._exec(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = ?
                """,
                (table_name,),
            ).fetchall()
            return {str(row["column_name"]) for row in rows}

        rows = self._exec(f"PRAGMA table_info({table_name})").fetchall()
        return {str(row["name"]) for row in rows}

    def init_schema(self) -> None:
        matches_query = """
        CREATE TABLE IF NOT EXISTS matches (
          match_id TEXT PRIMARY KEY,
          seed INTEGER NOT NULL,
          agent_set TEXT NOT NULL,
          config_json TEXT NOT NULL,
          names_json TEXT NOT NULL,
          created_by_identity_id TEXT,
          created_by_ip TEXT,
          hidden_at TEXT,
          hidden_reason TEXT,
          season_id TEXT,
          tournament_id TEXT,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          started_at TEXT,
          finished_at TEXT,
          replay_path TEXT,
          replay_key TEXT,
          replay_uri TEXT,
          winner TEXT,
          error TEXT,
          postprocess_error TEXT
        )
        """
        predictions_query = """
        CREATE TABLE IF NOT EXISTS predictions (
          match_id TEXT NOT NULL,
          viewer_id TEXT NOT NULL,
          wolves_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (match_id, viewer_id)
        )
        """
        recaps_query = """
        CREATE TABLE IF NOT EXISTS recaps (
          match_id TEXT PRIMARY KEY,
          recap_json TEXT NOT NULL,
          share_card_public_path TEXT NOT NULL,
          share_card_spoilers_path TEXT NOT NULL,
          recap_key TEXT,
          share_card_public_key TEXT,
          share_card_spoilers_key TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
        agents_query = """
        CREATE TABLE IF NOT EXISTS agents (
          agent_id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          version TEXT NOT NULL,
          runtime_type TEXT NOT NULL,
          strategy_text TEXT NOT NULL,
          package_path TEXT NOT NULL,
          entrypoint TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          created_by_identity_id TEXT,
          created_by_ip TEXT,
          hidden_at TEXT,
          hidden_reason TEXT
        )
        """
        match_players_query = """
        CREATE TABLE IF NOT EXISTS match_players (
          match_id TEXT NOT NULL,
          player_id TEXT NOT NULL,
          agent_type TEXT NOT NULL,
          agent_id TEXT,
          PRIMARY KEY (match_id, player_id)
        )
        """
        seasons_query = """
        CREATE TABLE IF NOT EXISTS seasons (
          season_id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          status TEXT NOT NULL,
          initial_rating INTEGER NOT NULL,
          k_factor INTEGER NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
        tournaments_query = """
        CREATE TABLE IF NOT EXISTS tournaments (
          tournament_id TEXT PRIMARY KEY,
          season_id TEXT NOT NULL,
          name TEXT NOT NULL,
          seed INTEGER NOT NULL,
          created_by_identity_id TEXT,
          created_by_ip TEXT,
          hidden_at TEXT,
          hidden_reason TEXT,
          status TEXT NOT NULL,
          bracket_json TEXT NOT NULL,
          champion_agent_id TEXT,
          error TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
        agent_match_results_query = """
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
        """
        identity_events_query = (
            """
            CREATE TABLE IF NOT EXISTS identity_events (
              id BIGSERIAL PRIMARY KEY,
              ip TEXT NOT NULL,
              token_hash TEXT NOT NULL,
              ok INTEGER NOT NULL,
              reason TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
            if self._dialect == "postgresql"
            else """
            CREATE TABLE IF NOT EXISTS identity_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ip TEXT NOT NULL,
              token_hash TEXT NOT NULL,
              ok INTEGER NOT NULL,
              reason TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
        jobs_query = """
        CREATE TABLE IF NOT EXISTS jobs (
          job_id TEXT PRIMARY KEY,
          job_type TEXT NOT NULL,
          resource_id TEXT NOT NULL,
          status TEXT NOT NULL,
          priority INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          locked_by TEXT,
          locked_at TEXT,
          attempts INTEGER NOT NULL DEFAULT 0,
          error TEXT
        )
        """
        jobs_status_index_query = """
        CREATE INDEX IF NOT EXISTS jobs_status_idx
        ON jobs(status, priority DESC, created_at ASC, job_id ASC)
        """
        jobs_resource_index_query = """
        CREATE INDEX IF NOT EXISTS jobs_resource_idx
        ON jobs(job_type, resource_id, created_at DESC, job_id DESC)
        """
        jobs_active_unique_index_query = """
        CREATE UNIQUE INDEX IF NOT EXISTS jobs_active_unique_idx
        ON jobs(job_type, resource_id)
        WHERE status IN ('queued', 'running')
        """
        usage_events_query = """
        CREATE TABLE IF NOT EXISTS usage_events (
          event_id TEXT PRIMARY KEY,
          identity_id TEXT,
          client_ip TEXT NOT NULL,
          action TEXT NOT NULL,
          created_at TEXT NOT NULL
        )
        """
        usage_events_action_index_query = """
        CREATE INDEX IF NOT EXISTS usage_events_action_created_idx
        ON usage_events(action, created_at)
        """
        usage_events_identity_index_query = """
        CREATE INDEX IF NOT EXISTS usage_events_identity_action_created_idx
        ON usage_events(identity_id, action, created_at)
        """
        usage_events_ip_index_query = """
        CREATE INDEX IF NOT EXISTS usage_events_ip_action_created_idx
        ON usage_events(client_ip, action, created_at)
        """
        abuse_blocks_query = """
        CREATE TABLE IF NOT EXISTS abuse_blocks (
          block_id TEXT PRIMARY KEY,
          block_type TEXT NOT NULL,
          value TEXT NOT NULL,
          reason TEXT,
          created_at TEXT NOT NULL,
          expires_at TEXT,
          created_by_identity_id TEXT
        )
        """
        abuse_blocks_type_value_index_query = """
        CREATE INDEX IF NOT EXISTS abuse_blocks_type_value_idx
        ON abuse_blocks(block_type, value)
        """
        abuse_blocks_expires_index_query = """
        CREATE INDEX IF NOT EXISTS abuse_blocks_expires_idx
        ON abuse_blocks(expires_at)
        """
        with self._lock, self._write_guard_locked():
            self._exec(matches_query)
            self._ensure_matches_column_locked("created_by_identity_id", "TEXT")
            self._ensure_matches_column_locked("created_by_ip", "TEXT")
            self._ensure_matches_column_locked("hidden_at", "TEXT")
            self._ensure_matches_column_locked("hidden_reason", "TEXT")
            self._ensure_matches_column_locked("season_id", "TEXT")
            self._ensure_matches_column_locked("tournament_id", "TEXT")
            self._ensure_matches_column_locked("replay_key", "TEXT")
            self._ensure_matches_column_locked("replay_uri", "TEXT")
            self._ensure_matches_column_locked("postprocess_error", "TEXT")
            self._exec(predictions_query)
            self._exec(recaps_query)
            self._ensure_recaps_column_locked("recap_key", "TEXT")
            self._ensure_recaps_column_locked("share_card_public_key", "TEXT")
            self._ensure_recaps_column_locked("share_card_spoilers_key", "TEXT")
            self._exec(agents_query)
            self._ensure_agents_column_locked("created_by_identity_id", "TEXT")
            self._ensure_agents_column_locked("created_by_ip", "TEXT")
            self._ensure_agents_column_locked("hidden_at", "TEXT")
            self._ensure_agents_column_locked("hidden_reason", "TEXT")
            self._exec(match_players_query)
            self._exec(seasons_query)
            self._exec(tournaments_query)
            self._ensure_tournaments_column_locked("created_by_identity_id", "TEXT")
            self._ensure_tournaments_column_locked("created_by_ip", "TEXT")
            self._ensure_tournaments_column_locked("hidden_at", "TEXT")
            self._ensure_tournaments_column_locked("hidden_reason", "TEXT")
            self._exec(agent_match_results_query)
            self._exec(identity_events_query)
            self._exec(jobs_query)
            self._exec(jobs_status_index_query)
            self._exec(jobs_resource_index_query)
            self._exec(jobs_active_unique_index_query)
            self._exec(usage_events_query)
            self._exec(usage_events_action_index_query)
            self._exec(usage_events_identity_index_query)
            self._exec(usage_events_ip_index_query)
            self._exec(abuse_blocks_query)
            self._exec(abuse_blocks_type_value_index_query)
            self._exec(abuse_blocks_expires_index_query)
            self._commit()

    def create_match_if_missing(
        self,
        *,
        match_id: str,
        seed: int,
        agent_set: str,
        config_json: str,
        names_json: str,
        replay_path: str,
        created_by_identity_id: str | None = None,
        created_by_ip: str | None = None,
        replay_key: str | None = None,
        replay_uri: str | None = None,
        season_id: str | None = None,
        tournament_id: str | None = None,
    ) -> MatchRecord:
        with self._lock, self._write_guard_locked():
            existing = self._select_match_locked(match_id)
            if existing is not None:
                return existing

            created_at = utc_now_iso()
            self._exec(
                """
                INSERT INTO matches (
                  match_id, seed, agent_set, config_json, names_json,
                  created_by_identity_id, created_by_ip,
                  hidden_at, hidden_reason,
                  season_id, tournament_id,
                  status, created_at, started_at, finished_at, replay_path, replay_key, replay_uri,
                  winner, error, postprocess_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match_id,
                    seed,
                    agent_set,
                    config_json,
                    names_json,
                    created_by_identity_id,
                    created_by_ip,
                    None,
                    None,
                    season_id,
                    tournament_id,
                    "created",
                    created_at,
                    None,
                    None,
                    replay_path,
                    replay_key,
                    replay_uri,
                    None,
                    None,
                    None,
                ),
            )
            self._commit()
            created = self._select_match_locked(match_id)
            if created is None:
                raise RuntimeError(f"failed to create match {match_id}")
            return created

    def get_match(self, match_id: str) -> MatchRecord | None:
        with self._lock:
            return self._select_match_locked(match_id)

    def list_matches(self, *, include_hidden: bool = False) -> list[MatchRecord]:
        with self._lock:
            if include_hidden:
                rows = self._exec(
                    "SELECT * FROM matches ORDER BY created_at DESC, match_id DESC"
                ).fetchall()
            else:
                rows = self._exec(
                    "SELECT * FROM matches WHERE hidden_at IS NULL ORDER BY created_at DESC, match_id DESC"
                ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def mark_running(self, match_id: str, *, started_at: str | None = None) -> MatchRecord:
        started = started_at or utc_now_iso()
        with self._lock, self._write_guard_locked():
            self._exec(
                """
                    UPDATE matches
                    SET status = ?, started_at = ?, finished_at = ?, winner = ?, error = ?,
                        postprocess_error = ?
                    WHERE match_id = ?
                    """,
                ("running", started, None, None, None, None, match_id),
            )
            self._commit()
            updated = self._select_match_locked(match_id)
            if updated is None:
                raise KeyError(match_id)
            return updated

    def mark_finished(
        self,
        match_id: str,
        *,
        winner: str,
        replay_path: str,
        replay_key: str | None = None,
        replay_uri: str | None = None,
        finished_at: str | None = None,
    ) -> MatchRecord:
        finished = finished_at or utc_now_iso()
        with self._lock, self._write_guard_locked():
            self._exec(
                """
                    UPDATE matches
                    SET status = ?, finished_at = ?, winner = ?, replay_path = ?,
                        replay_key = ?, replay_uri = ?, error = ?, postprocess_error = ?
                    WHERE match_id = ?
                    """,
                (
                    "finished",
                    finished,
                    winner,
                    replay_path,
                    replay_key,
                    replay_uri,
                    None,
                    None,
                    match_id,
                ),
            )
            self._commit()
            updated = self._select_match_locked(match_id)
            if updated is None:
                raise KeyError(match_id)
            return updated

    def mark_failed(
        self,
        match_id: str,
        *,
        error: str,
        replay_path: str | None = None,
        finished_at: str | None = None,
    ) -> MatchRecord:
        finished = finished_at or utc_now_iso()
        with self._lock, self._write_guard_locked():
            self._exec(
                """
                    UPDATE matches
                    SET status = ?, finished_at = ?, replay_path = ?, winner = ?, error = ?,
                        postprocess_error = ?
                    WHERE match_id = ?
                    """,
                ("failed", finished, replay_path, None, error, None, match_id),
            )
            self._commit()
            updated = self._select_match_locked(match_id)
            if updated is None:
                raise KeyError(match_id)
            return updated

    def mark_postprocess_error(self, match_id: str, *, error: str) -> MatchRecord:
        with self._lock, self._write_guard_locked():
            self._exec(
                """
                    UPDATE matches
                    SET postprocess_error = ?
                    WHERE match_id = ?
                    """,
                (error, match_id),
            )
            self._commit()
            updated = self._select_match_locked(match_id)
            if updated is None:
                raise KeyError(match_id)
            return updated

    def _select_match_locked(self, match_id: str) -> MatchRecord | None:
        row = self._exec("SELECT * FROM matches WHERE match_id = ?", (match_id,)).fetchone()
        return self._row_to_record(row) if row is not None else None

    def upsert_prediction(
        self,
        *,
        match_id: str,
        viewer_id: str,
        wolves: list[str],
    ) -> PredictionRecord:
        wolves_json = serialize_json(wolves)
        now = utc_now_iso()
        with self._lock, self._write_guard_locked():
            self._exec(
                """
                INSERT INTO predictions (match_id, viewer_id, wolves_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(match_id, viewer_id) DO UPDATE SET
                    wolves_json = excluded.wolves_json,
                    updated_at = excluded.updated_at
                """,
                (match_id, viewer_id, wolves_json, now, now),
            )
            self._commit()
            row = self._exec(
                "SELECT * FROM predictions WHERE match_id = ? AND viewer_id = ?",
                (match_id, viewer_id),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"failed to upsert prediction for {match_id}/{viewer_id}")
            return self._prediction_row_to_record(row)

    def list_predictions(self, match_id: str) -> list[PredictionRecord]:
        with self._lock:
            rows = self._exec(
                "SELECT * FROM predictions WHERE match_id = ? ORDER BY updated_at DESC, viewer_id ASC",
                (match_id,),
            ).fetchall()
            return [self._prediction_row_to_record(row) for row in rows]

    def upsert_recap(
        self,
        *,
        match_id: str,
        recap: dict[str, Any],
        share_card_public_path: str,
        share_card_spoilers_path: str,
        recap_key: str | None = None,
        share_card_public_key: str | None = None,
        share_card_spoilers_key: str | None = None,
    ) -> RecapRecord:
        recap_json = serialize_json(recap)
        now = utc_now_iso()
        with self._lock, self._write_guard_locked():
            self._exec(
                """
                    INSERT INTO recaps (
                      match_id, recap_json, share_card_public_path, share_card_spoilers_path,
                      recap_key, share_card_public_key, share_card_spoilers_key,
                      created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(match_id) DO UPDATE SET
                      recap_json = excluded.recap_json,
                      share_card_public_path = excluded.share_card_public_path,
                      share_card_spoilers_path = excluded.share_card_spoilers_path,
                      recap_key = excluded.recap_key,
                      share_card_public_key = excluded.share_card_public_key,
                      share_card_spoilers_key = excluded.share_card_spoilers_key,
                      updated_at = excluded.updated_at
                    """,
                (
                    match_id,
                    recap_json,
                    share_card_public_path,
                    share_card_spoilers_path,
                    recap_key,
                    share_card_public_key,
                    share_card_spoilers_key,
                    now,
                    now,
                ),
            )
            self._commit()
            row = self._exec(
                "SELECT * FROM recaps WHERE match_id = ?",
                (match_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"failed to upsert recap for {match_id}")
            return self._recap_row_to_record(row)

    def get_recap(self, match_id: str) -> RecapRecord | None:
        with self._lock:
            row = self._exec("SELECT * FROM recaps WHERE match_id = ?", (match_id,)).fetchone()
            return self._recap_row_to_record(row) if row is not None else None

    def upsert_agent(
        self,
        *,
        agent_id: str,
        name: str,
        version: str,
        runtime_type: str,
        strategy_text: str,
        package_path: str,
        entrypoint: str,
        created_by_identity_id: str | None = None,
        created_by_ip: str | None = None,
    ) -> AgentRecord:
        now = utc_now_iso()
        with self._lock, self._write_guard_locked():
            existing = self._exec(
                "SELECT * FROM agents WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
            if existing is not None:
                return self._agent_row_to_record(existing)
            self._exec(
                """
                INSERT INTO agents (
                  agent_id, name, version, runtime_type, strategy_text,
                  package_path, entrypoint, created_at, updated_at,
                  created_by_identity_id, created_by_ip
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    name,
                    version,
                    runtime_type,
                    strategy_text,
                    package_path,
                    entrypoint,
                    now,
                    now,
                    created_by_identity_id,
                    created_by_ip,
                ),
            )
            self._commit()
            row = self._exec(
                "SELECT * FROM agents WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"failed to upsert agent {agent_id}")
            return self._agent_row_to_record(row)

    def get_agent(self, agent_id: str) -> AgentRecord | None:
        with self._lock:
            row = self._exec("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
            return self._agent_row_to_record(row) if row is not None else None

    def list_agents(self, *, include_hidden: bool = False) -> list[AgentRecord]:
        with self._lock:
            if include_hidden:
                rows = self._exec(
                    "SELECT * FROM agents ORDER BY updated_at DESC, agent_id ASC"
                ).fetchall()
            else:
                rows = self._exec(
                    """
                    SELECT * FROM agents
                    WHERE hidden_at IS NULL
                    ORDER BY updated_at DESC, agent_id ASC
                    """
                ).fetchall()
            return [self._agent_row_to_record(row) for row in rows]

    def set_match_players(self, match_id: str, roster_rows: list[dict[str, Any]]) -> None:
        ordered_rows = sorted(roster_rows, key=lambda row: str(row["player_id"]))
        with self._lock, self._write_guard_locked():
            self._exec("DELETE FROM match_players WHERE match_id = ?", (match_id,))
            for row in ordered_rows:
                self._exec(
                    """
                        INSERT INTO match_players (match_id, player_id, agent_type, agent_id)
                        VALUES (?, ?, ?, ?)
                        """,
                    (
                        match_id,
                        str(row["player_id"]),
                        str(row["agent_type"]),
                        str(row["agent_id"]) if row.get("agent_id") is not None else None,
                    ),
                )
            self._commit()

    def list_match_players(self, match_id: str) -> list[MatchPlayerRecord]:
        with self._lock:
            rows = self._exec(
                "SELECT * FROM match_players WHERE match_id = ? ORDER BY player_id ASC",
                (match_id,),
            ).fetchall()
            return [self._match_player_row_to_record(row) for row in rows]

    def create_season_if_missing(
        self,
        *,
        season_id: str,
        name: str,
        status: str,
        initial_rating: int,
        k_factor: int,
    ) -> SeasonRecord:
        with self._lock, self._write_guard_locked():
            existing = self._select_season_locked(season_id)
            if existing is not None:
                return existing
            now = utc_now_iso()
            self._exec(
                """
                    INSERT INTO seasons (
                      season_id, name, status, initial_rating, k_factor, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                (
                    season_id,
                    name,
                    status,
                    initial_rating,
                    k_factor,
                    now,
                    now,
                ),
            )
            self._commit()
            created = self._select_season_locked(season_id)
            if created is None:
                raise RuntimeError(f"failed to create season {season_id}")
            return created

    def list_seasons(self) -> list[SeasonRecord]:
        with self._lock:
            rows = self._exec(
                """
                SELECT * FROM seasons
                ORDER BY
                  CASE WHEN status = 'active' THEN 0 ELSE 1 END ASC,
                  created_at DESC,
                  season_id ASC
                """
            ).fetchall()
            return [self._season_row_to_record(row) for row in rows]

    def get_season(self, season_id: str) -> SeasonRecord | None:
        with self._lock:
            return self._select_season_locked(season_id)

    def get_active_season(self) -> SeasonRecord | None:
        with self._lock:
            row = self._exec(
                """
                SELECT * FROM seasons
                WHERE status = 'active'
                ORDER BY updated_at DESC, season_id ASC
                LIMIT 1
                """
            ).fetchone()
            return self._season_row_to_record(row) if row is not None else None

    def set_active_season(self, season_id: str) -> SeasonRecord:
        with self._lock, self._write_guard_locked():
            if self._select_season_locked(season_id) is None:
                raise KeyError(season_id)
            now = utc_now_iso()
            self._exec(
                "UPDATE seasons SET status = 'archived', updated_at = ?",
                (now,),
            )
            self._exec(
                "UPDATE seasons SET status = 'active', updated_at = ? WHERE season_id = ?",
                (now, season_id),
            )
            self._commit()
            updated = self._select_season_locked(season_id)
            if updated is None:
                raise KeyError(season_id)
            return updated

    def upsert_tournament(
        self,
        *,
        tournament_id: str,
        season_id: str,
        name: str,
        seed: int,
        status: str,
        bracket: dict[str, Any],
        champion_agent_id: str | None = None,
        error: str | None = None,
        created_by_identity_id: str | None = None,
        created_by_ip: str | None = None,
    ) -> TournamentRecord:
        now = utc_now_iso()
        bracket_json = serialize_json(bracket)
        with self._lock, self._write_guard_locked():
            self._exec(
                """
                INSERT INTO tournaments (
                  tournament_id, season_id, name, seed, created_by_identity_id, created_by_ip,
                  status, bracket_json, champion_agent_id, error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tournament_id) DO UPDATE SET
                  season_id = excluded.season_id,
                  name = excluded.name,
                  seed = excluded.seed,
                  created_by_identity_id = COALESCE(tournaments.created_by_identity_id, excluded.created_by_identity_id),
                  created_by_ip = COALESCE(tournaments.created_by_ip, excluded.created_by_ip),
                  status = excluded.status,
                  bracket_json = excluded.bracket_json,
                  champion_agent_id = excluded.champion_agent_id,
                  error = excluded.error,
                      updated_at = excluded.updated_at
                    """,
                (
                    tournament_id,
                    season_id,
                    name,
                    seed,
                    created_by_identity_id,
                    created_by_ip,
                    status,
                    bracket_json,
                    champion_agent_id,
                    error,
                    now,
                    now,
                ),
            )
            self._commit()
            row = self._exec(
                "SELECT * FROM tournaments WHERE tournament_id = ?",
                (tournament_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"failed to upsert tournament {tournament_id}")
            return self._tournament_row_to_record(row)

    def list_tournaments(
        self, season_id: str | None = None, *, include_hidden: bool = False
    ) -> list[TournamentRecord]:
        with self._lock:
            if season_id is None:
                if include_hidden:
                    rows = self._exec(
                        "SELECT * FROM tournaments ORDER BY created_at DESC, tournament_id DESC"
                    ).fetchall()
                else:
                    rows = self._exec(
                        """
                        SELECT * FROM tournaments
                        WHERE hidden_at IS NULL
                        ORDER BY created_at DESC, tournament_id DESC
                        """
                    ).fetchall()
            else:
                if include_hidden:
                    rows = self._exec(
                        """
                        SELECT * FROM tournaments
                        WHERE season_id = ?
                        ORDER BY created_at DESC, tournament_id DESC
                        """,
                        (season_id,),
                    ).fetchall()
                else:
                    rows = self._exec(
                        """
                        SELECT * FROM tournaments
                        WHERE season_id = ? AND hidden_at IS NULL
                        ORDER BY created_at DESC, tournament_id DESC
                        """,
                        (season_id,),
                    ).fetchall()
            return [self._tournament_row_to_record(row) for row in rows]

    def get_tournament(self, tournament_id: str) -> TournamentRecord | None:
        with self._lock:
            row = self._exec(
                "SELECT * FROM tournaments WHERE tournament_id = ?",
                (tournament_id,),
            ).fetchone()
            return self._tournament_row_to_record(row) if row is not None else None

    def upsert_agent_match_results(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        ordered_rows = sorted(
            rows,
            key=lambda row: (str(row["match_id"]), str(row["agent_id"]), str(row["player_id"])),
        )
        with self._lock, self._write_guard_locked():
            for row in ordered_rows:
                created_at = str(row.get("created_at") or utc_now_iso())
                self._exec(
                    """
                        INSERT INTO agent_match_results (
                          match_id, season_id, tournament_id, agent_id, player_id,
                          role, team, winning_team, won, died, death_t,
                          votes_against, votes_cast, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(match_id, agent_id, player_id) DO UPDATE SET
                          season_id = excluded.season_id,
                          tournament_id = excluded.tournament_id,
                          role = excluded.role,
                          team = excluded.team,
                          winning_team = excluded.winning_team,
                          won = excluded.won,
                          died = excluded.died,
                          death_t = excluded.death_t,
                          votes_against = excluded.votes_against,
                          votes_cast = excluded.votes_cast,
                          created_at = excluded.created_at
                        """,
                    (
                        str(row["match_id"]),
                        str(row["season_id"]) if row.get("season_id") is not None else None,
                        (
                            str(row["tournament_id"])
                            if row.get("tournament_id") is not None
                            else None
                        ),
                        str(row["agent_id"]),
                        str(row["player_id"]),
                        str(row["role"]),
                        str(row["team"]),
                        str(row["winning_team"]),
                        int(row["won"]),
                        int(row["died"]),
                        int(row["death_t"]),
                        int(row["votes_against"]),
                        int(row["votes_cast"]),
                        created_at,
                    ),
                )
            self._commit()

    def list_agent_match_results_for_season(self, season_id: str) -> list[AgentMatchResultRecord]:
        with self._lock:
            rows = self._exec(
                """
                SELECT * FROM agent_match_results
                WHERE season_id = ?
                ORDER BY match_id ASC, agent_id ASC, player_id ASC
                """,
                (season_id,),
            ).fetchall()
            return [self._agent_match_result_row_to_record(row) for row in rows]

    def list_agent_match_results_for_agent(
        self, season_id: str, agent_id: str, limit: int
    ) -> list[AgentMatchResultRecord]:
        with self._lock:
            rows = self._exec(
                """
                SELECT * FROM agent_match_results
                WHERE season_id = ? AND agent_id = ?
                ORDER BY created_at DESC, match_id DESC
                LIMIT ?
                """,
                (season_id, agent_id, int(limit)),
            ).fetchall()
            return [self._agent_match_result_row_to_record(row) for row in rows]

    def list_agent_match_results_for_match(self, match_id: str) -> list[AgentMatchResultRecord]:
        with self._lock:
            rows = self._exec(
                """
                SELECT * FROM agent_match_results
                WHERE match_id = ?
                ORDER BY agent_id ASC, player_id ASC
                """,
                (match_id,),
            ).fetchall()
            return [self._agent_match_result_row_to_record(row) for row in rows]

    def record_identity_event(self, *, ip: str, token_hash: str, ok: bool, reason: str) -> None:
        with self._lock, self._write_guard_locked():
            self._exec(
                """
                    INSERT INTO identity_events (ip, token_hash, ok, reason, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                (ip, token_hash, 1 if ok else 0, reason, utc_now_iso()),
            )
            self._commit()

    def count_recent_identity_failures(self, *, ip: str, since_iso: str) -> int:
        with self._lock:
            row = self._exec(
                """
                SELECT COUNT(*) AS c
                FROM identity_events
                WHERE ip = ? AND ok = 0 AND created_at >= ?
                """,
                (ip, since_iso),
            ).fetchone()
            if row is None:
                return 0
            return int(row["c"])

    def record_usage_event(
        self, *, identity_id: str | None, client_ip: str, action: str
    ) -> UsageEventRecord:
        event_id = f"use_{uuid.uuid4().hex}"
        created_at = utc_now_iso()
        with self._lock, self._write_guard_locked():
            self._exec(
                """
                INSERT INTO usage_events (event_id, identity_id, client_ip, action, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    identity_id,
                    client_ip,
                    action,
                    created_at,
                ),
            )
            self._commit()
            row = self._exec(
                "SELECT * FROM usage_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"failed to record usage event {event_id}")
            return self._usage_event_row_to_record(row)

    def count_usage_events(
        self,
        *,
        identity_id: str | None,
        client_ip: str,
        action: str,
        window_seconds: int,
    ) -> int:
        since_iso = _offset_iso_seconds(utc_now_iso(), -max(1, int(window_seconds)))
        with self._lock:
            if identity_id:
                row = self._exec(
                    """
                    SELECT COUNT(*) AS c
                    FROM usage_events
                    WHERE identity_id = ? AND action = ? AND created_at >= ?
                    """,
                    (identity_id, action, since_iso),
                ).fetchone()
            else:
                row = self._exec(
                    """
                    SELECT COUNT(*) AS c
                    FROM usage_events
                    WHERE client_ip = ? AND action = ? AND created_at >= ?
                    """,
                    (client_ip, action, since_iso),
                ).fetchone()
            if row is None:
                return 0
            return int(row["c"])

    def count_usage_events_total(self, *, action: str, window_seconds: int) -> int:
        since_iso = _offset_iso_seconds(utc_now_iso(), -max(1, int(window_seconds)))
        with self._lock:
            row = self._exec(
                """
                SELECT COUNT(*) AS c
                FROM usage_events
                WHERE action = ? AND created_at >= ?
                """,
                (action, since_iso),
            ).fetchone()
            if row is None:
                return 0
            return int(row["c"])

    def list_usage_events(self, *, limit: int = 100) -> list[UsageEventRecord]:
        with self._lock:
            rows = self._exec(
                """
                SELECT * FROM usage_events
                ORDER BY created_at DESC, event_id DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
            return [self._usage_event_row_to_record(row) for row in rows]

    def create_block(
        self,
        *,
        block_type: str,
        value: str,
        reason: str | None = None,
        expires_at: str | None = None,
        created_by_identity_id: str | None = None,
    ) -> BlockRecord:
        normalized_type = str(block_type).strip().lower()
        if normalized_type not in {"identity", "ip", "cidr"}:
            raise ValueError(f"Unsupported block_type: {block_type!r}")
        normalized_value = str(value).strip()
        if not normalized_value:
            raise ValueError("block value must not be empty")
        if normalized_type == "ip":
            ipaddress.ip_address(normalized_value)
        if normalized_type == "cidr":
            ipaddress.ip_network(normalized_value, strict=False)
        normalized_expires_at = expires_at
        if expires_at is not None:
            try:
                dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("expires_at must be ISO-8601 UTC") from exc
            normalized_expires_at = (
                dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            )

        block_id = f"blk_{uuid.uuid4().hex}"
        created_at = utc_now_iso()
        with self._lock, self._write_guard_locked():
            self._exec(
                """
                INSERT INTO abuse_blocks (
                  block_id, block_type, value, reason, created_at, expires_at, created_by_identity_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    block_id,
                    normalized_type,
                    normalized_value,
                    reason,
                    created_at,
                    normalized_expires_at,
                    created_by_identity_id,
                ),
            )
            self._commit()
            row = self._exec(
                "SELECT * FROM abuse_blocks WHERE block_id = ?",
                (block_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"failed to create block {block_id}")
            return self._block_row_to_record(row)

    def delete_block(self, block_id: str) -> bool:
        with self._lock, self._write_guard_locked():
            cursor = self._exec("DELETE FROM abuse_blocks WHERE block_id = ?", (block_id,))
            self._commit()
            return int(cursor.rowcount or 0) > 0

    def list_blocks(self, *, include_expired: bool, limit: int) -> list[BlockRecord]:
        with self._lock:
            rows = self._exec(
                """
                SELECT * FROM abuse_blocks
                ORDER BY created_at DESC, block_id DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()

        now = utc_now_iso()
        blocks = [self._block_row_to_record(row) for row in rows]
        if include_expired:
            return blocks
        return [block for block in blocks if _is_block_active(block, now)]

    def is_blocked(
        self, *, identity_id: str | None, client_ip: str
    ) -> tuple[bool, str | None, str | None, str | None]:
        with self._lock:
            rows = self._exec(
                """
                SELECT * FROM abuse_blocks
                ORDER BY created_at DESC, block_id DESC
                """
            ).fetchall()

        now = utc_now_iso()
        blocks = [self._block_row_to_record(row) for row in rows]
        active_blocks = [block for block in blocks if _is_block_active(block, now)]
        client_ip_parsed: ipaddress.IPv4Address | ipaddress.IPv6Address | None = None
        try:
            client_ip_parsed = ipaddress.ip_address(client_ip)
        except ValueError:
            client_ip_parsed = None

        for block in active_blocks:
            if block.block_type == "identity" and identity_id and block.value == identity_id:
                return True, block.block_type, block.reason, block.expires_at
            if block.block_type == "ip" and block.value == client_ip:
                return True, block.block_type, block.reason, block.expires_at
            if block.block_type == "cidr" and client_ip_parsed is not None:
                try:
                    network = ipaddress.ip_network(block.value, strict=False)
                except ValueError:
                    continue
                if client_ip_parsed in network:
                    return True, block.block_type, block.reason, block.expires_at
        return False, None, None, None

    def set_match_hidden(
        self, *, match_id: str, hidden: bool, reason: str | None = None
    ) -> MatchRecord:
        with self._lock, self._write_guard_locked():
            hidden_at = utc_now_iso() if hidden else None
            hidden_reason = reason if hidden else None
            self._exec(
                """
                UPDATE matches
                SET hidden_at = ?, hidden_reason = ?
                WHERE match_id = ?
                """,
                (hidden_at, hidden_reason, match_id),
            )
            self._commit()
            row = self._exec("SELECT * FROM matches WHERE match_id = ?", (match_id,)).fetchone()
            if row is None:
                raise KeyError(match_id)
            return self._row_to_record(row)

    def set_agent_hidden(
        self, *, agent_id: str, hidden: bool, reason: str | None = None
    ) -> AgentRecord:
        with self._lock, self._write_guard_locked():
            hidden_at = utc_now_iso() if hidden else None
            hidden_reason = reason if hidden else None
            self._exec(
                """
                UPDATE agents
                SET hidden_at = ?, hidden_reason = ?
                WHERE agent_id = ?
                """,
                (hidden_at, hidden_reason, agent_id),
            )
            self._commit()
            row = self._exec("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
            if row is None:
                raise KeyError(agent_id)
            return self._agent_row_to_record(row)

    def set_tournament_hidden(
        self, *, tournament_id: str, hidden: bool, reason: str | None = None
    ) -> TournamentRecord:
        with self._lock, self._write_guard_locked():
            hidden_at = utc_now_iso() if hidden else None
            hidden_reason = reason if hidden else None
            self._exec(
                """
                UPDATE tournaments
                SET hidden_at = ?, hidden_reason = ?
                WHERE tournament_id = ?
                """,
                (hidden_at, hidden_reason, tournament_id),
            )
            self._commit()
            row = self._exec(
                "SELECT * FROM tournaments WHERE tournament_id = ?",
                (tournament_id,),
            ).fetchone()
            if row is None:
                raise KeyError(tournament_id)
            return self._tournament_row_to_record(row)

    def list_hidden_resources(self, *, resource_type: str, limit: int) -> list[dict[str, Any]]:
        normalized = str(resource_type).strip().lower()
        lim = max(1, int(limit))
        with self._lock:
            if normalized == "match":
                rows = self._exec(
                    """
                    SELECT match_id AS resource_id, hidden_at, hidden_reason, created_at
                    FROM matches
                    WHERE hidden_at IS NOT NULL
                    ORDER BY hidden_at DESC, match_id ASC
                    LIMIT ?
                    """,
                    (lim,),
                ).fetchall()
            elif normalized == "agent":
                rows = self._exec(
                    """
                    SELECT agent_id AS resource_id, hidden_at, hidden_reason, created_at
                    FROM agents
                    WHERE hidden_at IS NOT NULL
                    ORDER BY hidden_at DESC, agent_id ASC
                    LIMIT ?
                    """,
                    (lim,),
                ).fetchall()
            elif normalized == "tournament":
                rows = self._exec(
                    """
                    SELECT tournament_id AS resource_id, hidden_at, hidden_reason, created_at
                    FROM tournaments
                    WHERE hidden_at IS NOT NULL
                    ORDER BY hidden_at DESC, tournament_id ASC
                    LIMIT ?
                    """,
                    (lim,),
                ).fetchall()
            else:
                raise ValueError(f"Unsupported resource_type: {resource_type!r}")
        return [dict(row) for row in rows]

    def prune_usage_events(self, *, older_than_iso: str) -> int:
        with self._lock, self._write_guard_locked():
            cursor = self._exec(
                """
                DELETE FROM usage_events
                WHERE created_at < ?
                """,
                (older_than_iso,),
            )
            self._commit()
            return int(cursor.rowcount or 0)

    def prune_jobs(
        self,
        *,
        older_than_iso: str,
        statuses: Sequence[str] = ("succeeded", "failed"),
    ) -> int:
        normalized = tuple(str(status) for status in statuses if str(status))
        if not normalized:
            return 0
        placeholders = ", ".join(["?"] * len(normalized))
        params: tuple[Any, ...] = (older_than_iso, *normalized)
        with self._lock, self._write_guard_locked():
            cursor = self._exec(
                f"""
                DELETE FROM jobs
                WHERE updated_at < ? AND status IN ({placeholders})
                """,
                params,
            )
            self._commit()
            return int(cursor.rowcount or 0)

    def enqueue_job(self, *, job_type: str, resource_id: str, priority: int = 0) -> JobRecord:
        with self._lock, self._write_guard_locked():
            existing = self._select_active_job_locked(job_type=job_type, resource_id=resource_id)
            if existing is not None:
                return existing

            now = utc_now_iso()
            job_id = f"job_{uuid.uuid4().hex}"
            params = (
                job_id,
                job_type,
                resource_id,
                "queued",
                int(priority),
                now,
                now,
                None,
                None,
                0,
                None,
            )
            if self._dialect == "postgresql":
                inserted = self._exec(
                    """
                        INSERT INTO jobs (
                          job_id, job_type, resource_id, status, priority,
                          created_at, updated_at, locked_by, locked_at, attempts, error
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (job_type, resource_id)
                        WHERE status IN ('queued', 'running')
                        DO NOTHING
                        RETURNING *
                        """,
                    params,
                ).fetchone()
                if inserted is not None:
                    self._commit()
                    return self._job_row_to_record(inserted)

                existing = self._select_active_job_locked(
                    job_type=job_type, resource_id=resource_id
                )
                if existing is None:
                    raise RuntimeError(
                        f"failed to fetch active job after conflict for {job_type}/{resource_id}"
                    )
                self._commit()
                return existing

            self._exec(
                """
                    INSERT OR IGNORE INTO jobs (
                      job_id, job_type, resource_id, status, priority,
                      created_at, updated_at, locked_by, locked_at, attempts, error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                params,
            )
            created = self._select_job_locked(job_id)
            if created is not None:
                self._commit()
                return created
            existing = self._select_active_job_locked(job_type=job_type, resource_id=resource_id)
            if existing is None:
                raise RuntimeError(
                    f"failed to enqueue or load active job for {job_type}/{resource_id}"
                )
            self._commit()
            return existing

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._select_job_locked(job_id)

    def get_active_job(self, *, job_type: str, resource_id: str) -> JobRecord | None:
        with self._lock:
            return self._select_active_job_locked(job_type=job_type, resource_id=resource_id)

    def list_jobs(
        self, *, status: str | None = None, job_type: str | None = None
    ) -> list[JobRecord]:
        with self._lock:
            query = "SELECT * FROM jobs"
            clauses: list[str] = []
            params: list[Any] = []
            if status is not None:
                clauses.append("status = ?")
                params.append(status)
            if job_type is not None:
                clauses.append("job_type = ?")
                params.append(job_type)
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY created_at DESC, job_id DESC"
            rows = self._exec(query, tuple(params)).fetchall()
            return [self._job_row_to_record(row) for row in rows]

    def claim_next_job(self, *, worker_id: str, lease_seconds: int) -> JobRecord | None:
        del lease_seconds
        now = utc_now_iso()
        with self._lock, self._write_guard_locked():
            if self._dialect == "postgresql":
                row = self._exec(
                    """
                        WITH candidate AS (
                          SELECT job_id
                          FROM jobs
                          WHERE status = 'queued'
                          ORDER BY priority DESC, created_at ASC, job_id ASC
                          FOR UPDATE SKIP LOCKED
                          LIMIT 1
                        )
                        UPDATE jobs
                        SET status = 'running',
                            locked_by = ?,
                            locked_at = ?,
                            updated_at = ?,
                            attempts = attempts + 1,
                            error = NULL
                        WHERE job_id = (SELECT job_id FROM candidate)
                        RETURNING *
                        """,
                    (worker_id, now, now),
                ).fetchone()
                self._commit()
                return self._job_row_to_record(row) if row is not None else None

            candidate = self._exec(
                """
                    SELECT job_id
                    FROM jobs
                    WHERE status = 'queued'
                    ORDER BY priority DESC, created_at ASC, job_id ASC
                    LIMIT 1
                    """
            ).fetchone()
            if candidate is None:
                self._commit()
                return None
            job_id = str(candidate["job_id"])
            cursor = self._exec(
                """
                    UPDATE jobs
                    SET status = ?, locked_by = ?, locked_at = ?, updated_at = ?,
                        attempts = attempts + 1, error = NULL
                    WHERE job_id = ? AND status = 'queued'
                    """,
                ("running", worker_id, now, now, job_id),
            )
            if cursor.rowcount == 0:
                self._commit()
                return None
            self._commit()
            return self._select_job_locked(job_id)

    def heartbeat_job(self, *, job_id: str, worker_id: str) -> JobRecord | None:
        now = utc_now_iso()
        with self._lock, self._write_guard_locked():
            self._exec(
                """
                    UPDATE jobs
                    SET locked_at = ?, updated_at = ?
                    WHERE job_id = ? AND status = 'running' AND locked_by = ?
                    """,
                (now, now, job_id, worker_id),
            )
            self._commit()
            return self._select_job_locked(job_id)

    def complete_job(self, *, job_id: str, status: str, error: str | None = None) -> JobRecord:
        if status not in {"succeeded", "failed"}:
            raise ValueError(f"Unsupported terminal job status: {status!r}")
        now = utc_now_iso()
        with self._lock, self._write_guard_locked():
            self._exec(
                """
                    UPDATE jobs
                    SET status = ?, updated_at = ?, locked_by = ?, locked_at = ?, error = ?
                    WHERE job_id = ?
                    """,
                (status, now, None, None, error, job_id),
            )
            self._commit()
            updated = self._select_job_locked(job_id)
            if updated is None:
                raise KeyError(job_id)
            return updated

    def requeue_stale_jobs(self, *, now_iso: str, stale_after_seconds: int) -> int:
        cutoff = _offset_iso_seconds(now_iso, -int(stale_after_seconds))
        with self._lock, self._write_guard_locked():
            cursor = self._exec(
                """
                    UPDATE jobs
                    SET status = ?, updated_at = ?, locked_by = ?, locked_at = ?, error = ?
                    WHERE status = 'running' AND locked_at IS NOT NULL AND locked_at < ?
                    """,
                ("queued", now_iso, None, None, "stale_lease_requeued", cutoff),
            )
            self._commit()
            return int(cursor.rowcount or 0)

    def _select_job_locked(self, job_id: str) -> JobRecord | None:
        row = self._exec("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._job_row_to_record(row) if row is not None else None

    def _select_active_job_locked(self, *, job_type: str, resource_id: str) -> JobRecord | None:
        row = self._exec(
            """
            SELECT * FROM jobs
            WHERE job_type = ? AND resource_id = ? AND status IN ('queued', 'running')
            ORDER BY created_at DESC, job_id DESC
            LIMIT 1
            """,
            (job_type, resource_id),
        ).fetchone()
        return self._job_row_to_record(row) if row is not None else None

    def _ensure_matches_column_locked(self, column_name: str, column_type: str) -> None:
        existing_columns = self._columns_for_table_locked("matches")
        if column_name in existing_columns:
            return
        self._exec(f"ALTER TABLE matches ADD COLUMN {column_name} {column_type}")

    def _ensure_recaps_column_locked(self, column_name: str, column_type: str) -> None:
        existing_columns = self._columns_for_table_locked("recaps")
        if column_name in existing_columns:
            return
        self._exec(f"ALTER TABLE recaps ADD COLUMN {column_name} {column_type}")

    def _ensure_agents_column_locked(self, column_name: str, column_type: str) -> None:
        existing_columns = self._columns_for_table_locked("agents")
        if column_name in existing_columns:
            return
        self._exec(f"ALTER TABLE agents ADD COLUMN {column_name} {column_type}")

    def _ensure_tournaments_column_locked(self, column_name: str, column_type: str) -> None:
        existing_columns = self._columns_for_table_locked("tournaments")
        if column_name in existing_columns:
            return
        self._exec(f"ALTER TABLE tournaments ADD COLUMN {column_name} {column_type}")

    def _select_season_locked(self, season_id: str) -> SeasonRecord | None:
        row = self._exec("SELECT * FROM seasons WHERE season_id = ?", (season_id,)).fetchone()
        return self._season_row_to_record(row) if row is not None else None

    @staticmethod
    def _row_to_record(row: Any) -> MatchRecord:
        try:
            season_id = row["season_id"]
        except (KeyError, IndexError):
            season_id = None
        try:
            tournament_id = row["tournament_id"]
        except (KeyError, IndexError):
            tournament_id = None
        try:
            replay_key = row["replay_key"]
        except (KeyError, IndexError):
            replay_key = None
        try:
            replay_uri = row["replay_uri"]
        except (KeyError, IndexError):
            replay_uri = None
        try:
            postprocess_error = row["postprocess_error"]
        except (KeyError, IndexError):
            postprocess_error = None
        try:
            created_by_identity_id = row["created_by_identity_id"]
        except (KeyError, IndexError):
            created_by_identity_id = None
        try:
            created_by_ip = row["created_by_ip"]
        except (KeyError, IndexError):
            created_by_ip = None
        try:
            hidden_at = row["hidden_at"]
        except (KeyError, IndexError):
            hidden_at = None
        try:
            hidden_reason = row["hidden_reason"]
        except (KeyError, IndexError):
            hidden_reason = None
        return MatchRecord(
            match_id=row["match_id"],
            seed=int(row["seed"]),
            agent_set=row["agent_set"],
            config_json=row["config_json"],
            names_json=row["names_json"],
            season_id=season_id,
            tournament_id=tournament_id,
            status=row["status"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            replay_path=row["replay_path"],
            replay_key=replay_key,
            replay_uri=replay_uri,
            winner=row["winner"],
            error=row["error"],
            postprocess_error=postprocess_error,
            created_by_identity_id=created_by_identity_id,
            created_by_ip=created_by_ip,
            hidden_at=hidden_at,
            hidden_reason=hidden_reason,
        )

    @staticmethod
    def _prediction_row_to_record(row: Any) -> PredictionRecord:
        return PredictionRecord(
            match_id=row["match_id"],
            viewer_id=row["viewer_id"],
            wolves_json=row["wolves_json"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _recap_row_to_record(row: Any) -> RecapRecord:
        try:
            recap_key = row["recap_key"]
        except (KeyError, IndexError):
            recap_key = None
        try:
            share_card_public_key = row["share_card_public_key"]
        except (KeyError, IndexError):
            share_card_public_key = None
        try:
            share_card_spoilers_key = row["share_card_spoilers_key"]
        except (KeyError, IndexError):
            share_card_spoilers_key = None
        return RecapRecord(
            match_id=row["match_id"],
            recap_json=row["recap_json"],
            share_card_public_path=row["share_card_public_path"],
            share_card_spoilers_path=row["share_card_spoilers_path"],
            recap_key=recap_key,
            share_card_public_key=share_card_public_key,
            share_card_spoilers_key=share_card_spoilers_key,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _agent_row_to_record(row: Any) -> AgentRecord:
        try:
            created_by_identity_id = row["created_by_identity_id"]
        except (KeyError, IndexError):
            created_by_identity_id = None
        try:
            created_by_ip = row["created_by_ip"]
        except (KeyError, IndexError):
            created_by_ip = None
        try:
            hidden_at = row["hidden_at"]
        except (KeyError, IndexError):
            hidden_at = None
        try:
            hidden_reason = row["hidden_reason"]
        except (KeyError, IndexError):
            hidden_reason = None
        return AgentRecord(
            agent_id=row["agent_id"],
            name=row["name"],
            version=row["version"],
            runtime_type=row["runtime_type"],
            strategy_text=row["strategy_text"],
            package_path=row["package_path"],
            entrypoint=row["entrypoint"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            created_by_identity_id=created_by_identity_id,
            created_by_ip=created_by_ip,
            hidden_at=hidden_at,
            hidden_reason=hidden_reason,
        )

    @staticmethod
    def _match_player_row_to_record(row: Any) -> MatchPlayerRecord:
        return MatchPlayerRecord(
            match_id=row["match_id"],
            player_id=row["player_id"],
            agent_type=row["agent_type"],
            agent_id=row["agent_id"],
        )

    @staticmethod
    def _season_row_to_record(row: Any) -> SeasonRecord:
        return SeasonRecord(
            season_id=row["season_id"],
            name=row["name"],
            status=row["status"],
            initial_rating=int(row["initial_rating"]),
            k_factor=int(row["k_factor"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _tournament_row_to_record(row: Any) -> TournamentRecord:
        try:
            created_by_identity_id = row["created_by_identity_id"]
        except (KeyError, IndexError):
            created_by_identity_id = None
        try:
            created_by_ip = row["created_by_ip"]
        except (KeyError, IndexError):
            created_by_ip = None
        try:
            hidden_at = row["hidden_at"]
        except (KeyError, IndexError):
            hidden_at = None
        try:
            hidden_reason = row["hidden_reason"]
        except (KeyError, IndexError):
            hidden_reason = None
        return TournamentRecord(
            tournament_id=row["tournament_id"],
            season_id=row["season_id"],
            name=row["name"],
            seed=int(row["seed"]),
            status=row["status"],
            bracket_json=row["bracket_json"],
            champion_agent_id=row["champion_agent_id"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            created_by_identity_id=created_by_identity_id,
            created_by_ip=created_by_ip,
            hidden_at=hidden_at,
            hidden_reason=hidden_reason,
        )

    @staticmethod
    def _agent_match_result_row_to_record(row: Any) -> AgentMatchResultRecord:
        return AgentMatchResultRecord(
            match_id=row["match_id"],
            season_id=row["season_id"],
            tournament_id=row["tournament_id"],
            agent_id=row["agent_id"],
            player_id=row["player_id"],
            role=row["role"],
            team=row["team"],
            winning_team=row["winning_team"],
            won=int(row["won"]),
            died=int(row["died"]),
            death_t=int(row["death_t"]),
            votes_against=int(row["votes_against"]),
            votes_cast=int(row["votes_cast"]),
            created_at=row["created_at"],
        )

    @staticmethod
    def _job_row_to_record(row: Any) -> JobRecord:
        return JobRecord(
            job_id=row["job_id"],
            job_type=row["job_type"],
            resource_id=row["resource_id"],
            status=row["status"],
            priority=int(row["priority"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            locked_by=row["locked_by"],
            locked_at=row["locked_at"],
            attempts=int(row["attempts"]),
            error=row["error"],
        )

    @staticmethod
    def _usage_event_row_to_record(row: Any) -> UsageEventRecord:
        return UsageEventRecord(
            event_id=row["event_id"],
            identity_id=row["identity_id"],
            client_ip=row["client_ip"],
            action=row["action"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _block_row_to_record(row: Any) -> BlockRecord:
        return BlockRecord(
            block_id=row["block_id"],
            block_type=row["block_type"],
            value=row["value"],
            reason=row["reason"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            created_by_identity_id=row["created_by_identity_id"],
        )


def serialize_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


def parse_json_lines(lines: Iterable[str]) -> list[dict]:
    return [json.loads(line) for line in lines]


def _is_block_active(block: BlockRecord, now_iso: str) -> bool:
    if block.expires_at is None:
        return True
    try:
        expires_dt = datetime.fromisoformat(str(block.expires_at).replace("Z", "+00:00"))
        now_dt = datetime.fromisoformat(str(now_iso).replace("Z", "+00:00"))
    except ValueError:
        return False
    return expires_dt > now_dt


def _offset_iso_seconds(value: str, delta_seconds: int) -> str:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    adjusted = dt.timestamp() + int(delta_seconds)
    return (
        datetime.fromtimestamp(adjusted, UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
