from __future__ import annotations

import json
from typing import Any, Protocol
from urllib import error, request

from howlhouse.platform.identity import VerifiedIdentity


class RecapPublisher(Protocol):
    def publish(
        self,
        *,
        identity: VerifiedIdentity | None,
        match_id: str,
        recap: dict[str, Any],
    ) -> dict[str, Any]: ...


class NoOpRecapPublisher:
    def publish(
        self,
        *,
        identity: VerifiedIdentity | None,
        match_id: str,
        recap: dict[str, Any],
    ) -> dict[str, Any]:
        raise RuntimeError("distribution is disabled")


class HttpRecapPublisher:
    def __init__(self, post_url: str, *, timeout_seconds: float = 3.0):
        self.post_url = post_url
        self.timeout_seconds = timeout_seconds

    def publish(
        self,
        *,
        identity: VerifiedIdentity | None,
        match_id: str,
        recap: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "match_id": match_id,
            "recap": recap,
            "identity": (
                {
                    "identity_id": identity.identity_id,
                    "handle": identity.handle,
                    "display_name": identity.display_name,
                    "feed_url": identity.feed_url,
                }
                if identity is not None
                else None
            ),
        }
        body = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            self.post_url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                status = int(response.status)
        except error.HTTPError as exc:
            raise RuntimeError(f"distribution provider rejected request: {exc.code}") from exc
        except (error.URLError, TimeoutError) as exc:
            raise RuntimeError("distribution provider unavailable") from exc

        try:
            data = json.loads(raw)
            receipt = data if isinstance(data, dict) else {"response": data}
        except json.JSONDecodeError:
            receipt = {"response_text": raw}

        receipt["status"] = status
        return receipt
