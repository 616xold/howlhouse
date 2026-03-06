from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib import error, request


@dataclass(frozen=True)
class VerifiedIdentity:
    identity_id: str
    handle: str | None
    display_name: str | None
    feed_url: str | None
    raw: dict[str, Any]


class IdentityVerifier(Protocol):
    def verify(self, token: str) -> VerifiedIdentity: ...


class IdentityVerificationError(Exception):
    def __init__(self, message: str, *, reason: str = "invalid_token"):
        super().__init__(message)
        self.reason = reason


class IdentityUnavailableError(Exception):
    def __init__(self, message: str, *, reason: str = "verifier_unavailable"):
        super().__init__(message)
        self.reason = reason


class NoOpIdentityVerifier:
    def verify(self, token: str) -> VerifiedIdentity:
        raise IdentityVerificationError(
            "identity verification is disabled", reason="identity_disabled"
        )


class HttpIdentityVerifier:
    def __init__(self, verify_url: str, *, timeout_seconds: float = 3.0):
        self.verify_url = verify_url
        self.timeout_seconds = timeout_seconds

    def verify(self, token: str) -> VerifiedIdentity:
        body = json.dumps({"token": token}, sort_keys=True, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            self.verify_url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                payload_raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            code = int(exc.code)
            if code in {401, 403}:
                raise IdentityVerificationError("token rejected by identity provider") from exc
            if 400 <= code < 500:
                raise IdentityVerificationError(
                    "identity request invalid", reason="verify_request_invalid"
                ) from exc
            raise IdentityUnavailableError("identity provider unavailable") from exc
        except (error.URLError, TimeoutError) as exc:
            raise IdentityUnavailableError("identity provider unavailable") from exc

        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError as exc:
            raise IdentityUnavailableError("identity provider returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise IdentityUnavailableError("identity provider returned unexpected payload")

        identity_id = payload.get("identity_id") or payload.get("id") or payload.get("user_id")
        if not isinstance(identity_id, str) or not identity_id.strip():
            raise IdentityVerificationError(
                "identity payload missing identity_id", reason="invalid_response"
            )

        handle = payload.get("handle") if isinstance(payload.get("handle"), str) else None
        display_name = (
            payload.get("display_name") if isinstance(payload.get("display_name"), str) else None
        )
        feed_url = payload.get("feed_url") if isinstance(payload.get("feed_url"), str) else None

        return VerifiedIdentity(
            identity_id=identity_id.strip(),
            handle=handle,
            display_name=display_name,
            feed_url=feed_url,
            raw=payload,
        )
