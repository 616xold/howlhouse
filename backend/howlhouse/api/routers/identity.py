from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from howlhouse.api.identity_context import require_identity
from howlhouse.platform.identity import VerifiedIdentity

router = APIRouter(prefix="/identity", tags=["identity"])


def _identity_to_dto(identity: VerifiedIdentity) -> dict[str, Any]:
    return {
        "identity_id": identity.identity_id,
        "handle": identity.handle,
        "display_name": identity.display_name,
        "feed_url": identity.feed_url,
    }


@router.get("/me")
def get_identity_me(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    if not settings.identity_enabled:
        raise HTTPException(status_code=404, detail="Identity integration is disabled")

    identity = require_identity(request)
    return _identity_to_dto(identity)
