"""QUILL auth (DECISION-002: QUILL is standalone; no external auth).

Two modes:
  * **Production / non-dev:** a valid JWT (Bearer token) is required. Roles are
    encoded in the token claims; `require_role(...)` enforces RBAC.
  * **Dev mode** (`QUILL_DEV_MODE=1` env var): for local testing only. Auth
    falls back to reading role/user/tenant from `X-QUILL-*` headers so the API
    is usable without a token. DEV_MODE is off by default and MUST be off in
    any deployed environment (NFR-SEC-02).

Roles: admin / engineer / attester / viewer (FR-API-02). `attester` is the role
required for approve/edit/reject; `admin` is not auto-granted attestation.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

try:  # Optional in early dev; required outside DEV_MODE.
    import jwt  # PyJWT
except Exception:  # noqa: BLE001
    jwt = None  # type: ignore[assignment]


class Role(str, Enum):
    admin = "admin"
    engineer = "engineer"
    attester = "attester"
    viewer = "viewer"


def dev_mode() -> bool:
    return os.environ.get("QUILL_DEV_MODE", "1") == "1"  # default ON locally; flip OFF in deploy


def _jwt_secret() -> str:
    s = os.environ.get("QUILL_JWT_SECRET")
    if not s and not dev_mode():
        raise RuntimeError("QUILL_JWT_SECRET must be set when DEV_MODE is off")
    return s or "dev-only-secret-do-not-use-in-prod"


def _decode_jwt(token: str) -> dict:
    if jwt is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "PyJWT not installed")
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
    x_quill_user: Optional[str] = Header(default=None),
    x_quill_role: Optional[str] = Header(default=None),
    x_quill_tenant: Optional[str] = Header(default=None),
) -> dict:
    if authorization and authorization.lower().startswith("bearer "):
        claims = _decode_jwt(authorization.split(" ", 1)[1])
        role = claims.get("role")
        if role not in Role._value2member_map_:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown role in token")
        return {
            "user": claims.get("sub") or claims.get("user") or "unknown",
            "role": role,
            "tenant": claims.get("tenant") or "default",
        }

    if dev_mode():
        role = x_quill_role or "engineer"
        if role not in Role._value2member_map_:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown role")
        return {"user": x_quill_user or "dev-user", "role": role, "tenant": x_quill_tenant or "default"}

    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")


def require_role(*allowed_roles: str):
    """Dependency factory. `admin` is NOT auto-granted attestation — it must be
    listed explicitly to be allowed."""
    async def _check(current_user: dict = Depends(get_current_user)) -> dict:
        role = current_user["role"]
        if role in allowed_roles or (role == "admin" and "attester" not in allowed_roles):
            return current_user
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Insufficient permissions. Required role: {', '.join(allowed_roles)}",
        )
    return _check
