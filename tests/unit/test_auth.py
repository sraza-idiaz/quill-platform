"""Auth tests (DECISION-002 / DECISION-011) — JWT mode + DEV_MODE fallback."""
import os
import time

import jwt
import pytest
from fastapi import HTTPException

from backend.services.auth import get_current_user, require_role


@pytest.mark.asyncio
async def test_dev_mode_reads_headers_when_no_token(monkeypatch):
    monkeypatch.setenv("QUILL_DEV_MODE", "1")
    user = await get_current_user(
        authorization=None, x_quill_user="alice", x_quill_role="attester", x_quill_tenant="t1"
    )
    assert user == {"user": "alice", "role": "attester", "tenant": "t1"}


@pytest.mark.asyncio
async def test_prod_mode_rejects_missing_token(monkeypatch):
    monkeypatch.setenv("QUILL_DEV_MODE", "0")
    monkeypatch.setenv("QUILL_JWT_SECRET", "shh")
    with pytest.raises(HTTPException) as exc:
        await get_current_user(authorization=None, x_quill_user=None, x_quill_role=None, x_quill_tenant=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_jwt_decodes_and_enforces_role(monkeypatch):
    monkeypatch.setenv("QUILL_DEV_MODE", "0")
    monkeypatch.setenv("QUILL_JWT_SECRET", "shh")
    token = jwt.encode(
        {"sub": "bob", "role": "engineer", "tenant": "t1", "iat": int(time.time())},
        "shh", algorithm="HS256",
    )
    user = await get_current_user(authorization=f"Bearer {token}",
                                  x_quill_user=None, x_quill_role=None, x_quill_tenant=None)
    assert user["role"] == "engineer" and user["user"] == "bob"


@pytest.mark.asyncio
async def test_require_attester_does_not_auto_grant_admin():
    # admin is NOT auto-granted attestation (security-critical separation).
    check = require_role("attester")
    admin = {"user": "a", "role": "admin", "tenant": "t"}
    with pytest.raises(HTTPException) as exc:
        await check(admin)
    assert exc.value.status_code == 403
