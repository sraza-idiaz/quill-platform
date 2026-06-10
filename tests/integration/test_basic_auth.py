"""HTTP Basic Auth perimeter gate (Render demo deployments).

When QUILL_BASIC_AUTH_USER + QUILL_BASIC_AUTH_PASSWORD are both set, every
request except /health must carry a valid Basic header. When either is
unset, the middleware is fully transparent (current dev behavior).
"""
import base64
import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _auth_header(user: str, pw: str) -> dict:
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def client_with_auth(monkeypatch):
    monkeypatch.setenv("QUILL_BASIC_AUTH_USER", "demo")
    monkeypatch.setenv("QUILL_BASIC_AUTH_PASSWORD", "s3cret")
    import backend.main as bm
    importlib.reload(bm)
    # TestClient doesn't auto-run lifespan, so build a context explicitly.
    from tests.conftest import MockAnalyzer
    ctx = bm.build_context(analyzer=MockAnalyzer())
    return TestClient(bm.create_app(ctx))


@pytest.fixture
def client_no_auth(monkeypatch):
    monkeypatch.delenv("QUILL_BASIC_AUTH_USER", raising=False)
    monkeypatch.delenv("QUILL_BASIC_AUTH_PASSWORD", raising=False)
    import backend.main as bm
    importlib.reload(bm)
    from tests.conftest import MockAnalyzer
    ctx = bm.build_context(analyzer=MockAnalyzer())
    return TestClient(bm.create_app(ctx))


# ─── auth disabled (default dev mode) ─────────────────────────────── #

def test_no_env_no_auth_required(client_no_auth):
    r = client_no_auth.get("/health")
    assert r.status_code == 200


def test_no_env_ui_is_open(client_no_auth):
    # /ui/ is open; mounted static dir resolves index.html or 404. Either
    # way it must NOT be 401 when auth is off.
    r = client_no_auth.get("/ui/")
    assert r.status_code != 401


# ─── auth enabled ─────────────────────────────────────────────────── #

def test_health_is_open_even_with_auth_enabled(client_with_auth):
    """Render's load-balancer probes /health without auth."""
    r = client_with_auth.get("/health")
    assert r.status_code == 200


def test_missing_credentials_returns_401_with_www_authenticate(client_with_auth):
    r = client_with_auth.get("/programs")
    assert r.status_code == 401
    assert r.headers.get("www-authenticate", "").startswith("Basic")


def test_wrong_password_returns_401(client_with_auth):
    r = client_with_auth.get("/programs", headers=_auth_header("demo", "wrong"))
    assert r.status_code == 401


def test_wrong_user_returns_401(client_with_auth):
    r = client_with_auth.get("/programs", headers=_auth_header("other", "s3cret"))
    assert r.status_code == 401


def test_malformed_header_returns_401(client_with_auth):
    r = client_with_auth.get("/programs",
                              headers={"Authorization": "NotBasic abc"})
    assert r.status_code == 401


def test_valid_credentials_allow_request_through(client_with_auth):
    r = client_with_auth.get("/health", headers=_auth_header("demo", "s3cret"))
    assert r.status_code == 200
    # Hit a tenant-scoped endpoint to prove the X-QUILL-* identity layer
    # still applies AFTER Basic Auth passes.
    r2 = client_with_auth.get(
        "/artifacts",
        headers={**_auth_header("demo", "s3cret"),
                 "X-QUILL-Role": "engineer", "X-QUILL-Tenant": "default"},
    )
    assert r2.status_code == 200


def test_ui_static_files_also_gated(client_with_auth):
    r = client_with_auth.get("/ui/index.html")
    assert r.status_code == 401
    r2 = client_with_auth.get("/ui/index.html",
                               headers=_auth_header("demo", "s3cret"))
    assert r2.status_code == 200
