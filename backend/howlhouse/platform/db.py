from __future__ import annotations

from enum import StrEnum


class DatabaseKind(StrEnum):
    SQLITE = "sqlite"
    POSTGRES = "postgresql"


def detect_database_kind(database_url: str) -> DatabaseKind:
    if database_url.startswith("sqlite:///"):
        return DatabaseKind.SQLITE
    if database_url.startswith("postgresql://") or database_url.startswith("postgres://"):
        return DatabaseKind.POSTGRES
    raise ValueError("Unsupported database URL scheme. Expected sqlite:///... or postgresql://...")
