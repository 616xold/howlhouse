from __future__ import annotations

from urllib.parse import urlparse

from howlhouse.platform.runtime_policy import is_dev_like_env


def validate_outbound_url(
    url: str,
    *,
    purpose: str,
    env: str,
    hostname_allowlist: str = "",
) -> None:
    parsed = urlparse(url)
    scheme = parsed.scheme.strip().lower()
    hostname = (parsed.hostname or "").strip().lower()

    if scheme not in {"http", "https"}:
        raise ValueError(f"{purpose} must use http or https")
    if not hostname:
        raise ValueError(f"{purpose} must include a hostname")

    if not is_dev_like_env(env) and scheme != "https":
        raise ValueError(f"{purpose} must use https outside local/dev/test")

    allowed_hosts = {
        item.strip().lower() for item in str(hostname_allowlist or "").split(",") if item.strip()
    }
    if allowed_hosts and hostname not in allowed_hosts:
        raise ValueError(f"{purpose} host {hostname!r} is not in the configured hostname allowlist")
