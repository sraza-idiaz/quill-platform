"""Phase II — Program (multi-tenant) endpoints (FR-MT-01..06)."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import build_context, create_app  # noqa: E402
from tests.conftest import MockAnalyzer              # noqa: E402

ADMIN = {"X-QUILL-Role": "admin"}
ENG = {"X-QUILL-Role": "engineer"}
VIEWER = {"X-QUILL-Role": "viewer"}


@pytest.fixture
def client():
    ctx = build_context(analyzer=MockAnalyzer())
    return TestClient(create_app(ctx))


def test_default_program_exists_at_startup(client):
    """Phase I back-compat: 'default' program is bootstrapped automatically."""
    r = client.get("/programs", headers=VIEWER)
    assert r.status_code == 200
    progs = r.json()
    assert any(p["id"] == "default" for p in progs)
    default = next(p for p in progs if p["id"] == "default")
    assert default["status"] == "active"
    assert default["baseline"] == "moderate"


def test_admin_can_create_program(client):
    r = client.post("/programs", json={
        "id": "aerospace-r-and-d",
        "name": "Aerospace R&D",
        "baseline": "moderate",
        "framework": "nist-800-53-rev5",
        "description": "R&D program for advanced materials",
    }, headers=ADMIN)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] == "aerospace-r-and-d"
    assert body["name"] == "Aerospace R&D"
    assert body["baseline"] == "moderate"
    assert body["created_at"]


def test_non_admin_cannot_create_program(client):
    r = client.post("/programs", json={
        "id": "logistics-it", "name": "Logistics IT",
    }, headers=ENG)
    assert r.status_code == 403


def test_create_program_validates_id_format(client):
    r = client.post("/programs", json={
        "id": "Bad ID with spaces!", "name": "x",
    }, headers=ADMIN)
    assert r.status_code == 400
    assert "alphanumeric" in r.text


def test_create_program_validates_baseline(client):
    r = client.post("/programs", json={
        "id": "test-pgm", "name": "x", "baseline": "extreme",
    }, headers=ADMIN)
    assert r.status_code == 400


def test_duplicate_program_id_rejected(client):
    payload = {"id": "munitions-it", "name": "Munitions IT"}
    assert client.post("/programs", json=payload, headers=ADMIN).status_code == 201
    r2 = client.post("/programs", json=payload, headers=ADMIN)
    assert r2.status_code == 409


def test_list_programs_sorted_active_first(client):
    client.post("/programs", json={"id": "alpha", "name": "Alpha"}, headers=ADMIN)
    client.post("/programs", json={"id": "beta",  "name": "Beta"},  headers=ADMIN)
    r = client.get("/programs", headers=VIEWER)
    ids = [p["id"] for p in r.json()]
    # default + alpha + beta
    assert "default" in ids and "alpha" in ids and "beta" in ids


def test_get_program_returns_404_for_unknown(client):
    r = client.get("/programs/does-not-exist", headers=VIEWER)
    assert r.status_code == 404
