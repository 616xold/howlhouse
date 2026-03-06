from __future__ import annotations

from datetime import UTC, datetime, timedelta

from howlhouse.core.config import Settings
from howlhouse.core.logging import configure_logging
from howlhouse.platform.observability import increment_prune_deleted
from howlhouse.platform.store import MatchStore


def _to_iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    settings = Settings()
    configure_logging(settings)

    store = MatchStore(settings.database_url)
    try:
        store.init_schema()

        if not settings.retention_enabled:
            print("retention disabled: no rows pruned")
            return 0

        now = datetime.now(UTC)
        usage_cutoff = _to_iso(
            now - timedelta(days=max(1, int(settings.retention_usage_events_days)))
        )
        jobs_cutoff = _to_iso(now - timedelta(days=max(1, int(settings.retention_jobs_days))))

        usage_deleted = store.prune_usage_events(older_than_iso=usage_cutoff)
        jobs_deleted = store.prune_jobs(older_than_iso=jobs_cutoff)

        increment_prune_deleted(table="usage_events", count=usage_deleted)
        increment_prune_deleted(table="jobs", count=jobs_deleted)

        print(
            f"pruned usage_events={usage_deleted} (cutoff={usage_cutoff}), "
            f"jobs={jobs_deleted} (cutoff={jobs_cutoff})"
        )
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
