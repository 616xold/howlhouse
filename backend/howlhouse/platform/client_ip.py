from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:  # pragma: no cover
    from howlhouse.core.config import Settings


def _parse_ip(value: str | None) -> str | None:
    if not value:
        return None
    token = value.strip().strip('"')
    if not token:
        return None

    # IPv6 with brackets, optionally with port: [2001:db8::1]:1234
    if token.startswith("[") and "]" in token:
        bracket_end = token.find("]")
        token = token[1:bracket_end]

    try:
        return str(ipaddress.ip_address(token))
    except ValueError:
        pass

    # IPv4 with port: 203.0.113.10:1234
    if token.count(":") == 1:
        host, port = token.rsplit(":", 1)
        if port.isdigit():
            try:
                return str(ipaddress.ip_address(host))
            except ValueError:
                return None

    return None


def get_client_ip(request: Request, settings: Settings) -> str:
    direct_ip = _parse_ip(request.client.host if request.client else None)

    if not settings.trust_proxy_headers:
        return direct_ip or "unknown"

    raw_xff = request.headers.get("x-forwarded-for")
    if not raw_xff:
        return direct_ip or "unknown"

    forwarded_ips = [
        parsed for parsed in (_parse_ip(part) for part in raw_xff.split(",")) if parsed is not None
    ]
    if not forwarded_ips:
        return direct_ip or "unknown"

    hops = max(1, int(settings.trusted_proxy_hops))
    index = len(forwarded_ips) - hops
    if index < 0:
        index = 0

    return forwarded_ips[index] or direct_ip or "unknown"
