from __future__ import annotations

from howlhouse.platform.observability import configure_logging as _configure_observability_logging

from .config import Settings
from .config import settings as global_settings


def configure_logging(settings: Settings | None = None) -> None:
    resolved = settings or global_settings
    _configure_observability_logging(resolved)
