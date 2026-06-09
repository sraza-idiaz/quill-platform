"""Phase II — Packages (FR-PKG-01..06).

Covers:
  * create / list / get
  * id auto-generation in PKG-YYYY-XXXX format
  * artifact attach / detach
  * status state machine (legal + illegal transitions)
  * package-level analysis runs the orchestrator across all member artifacts
  * archived packages are read-only
"""
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import build_context, create_app  # noqa: E402
from tests.conftest import MockAnalyzer              # noqa: E402

ADMIN_DEFAULT = {"X-QUILL-Role": "admin",    "X-QUILL-Tenant": "default"}
ENG_DEFAULT   = {"X-QUILL-Role": "engineer", "X-QUILL-Tenant": "default"}
VIEWER_DEF    = {"X-QUILL-Role": "viewer",   "X-QUILL-Tenant": "default"}

FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture
def client():
    ctx = build_context(analyzer=MockAnalyzer())
    return TestClient(create_app(ctx))


def _upload(client, filename: str, headers=ENG_DEFAULT) -> str:
    with open(FIXTURES / filename, "rb") as fh:
        r = client.post("/artifacts",
                        files={"file": (filename, fh, "text/markdown")},
                        headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------- create / list / get ---------- #

def test_engineer_can_create_package_with_auto_id(client):
    r = client.post("/packages", json={"name": "Aerospace SSP Package"},
                    headers=ENG_DEFAULT)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Aerospace SSP Package"
    assert body["status"] == "draft"
    # FR-PKG-06: PKG-YYYY-XXXX format
    assert re.match(r"^PKG-\d{4}-[A-F0-9]{6}$", body["id"]), body["id"]
    assert body["tenant"] == "default"


def test_user_supplied_package_id_accepted(client):
    r = client.post("/packages",
                    json={"id": "logistics-bundle-001", "name": "Logistics Bundle"},
                    headers=ENG_DEFAULT)
    assert r.status_code == 201
    assert r.json()["id"] == "logistics-bundle-001"


def test_duplicate_package_id_rejected(client):
    payload = {"id": "dup-pkg", "name": "Dup"}
    assert client.post("/packages", json=payload, headers=ENG_DEFAULT).status_code == 201
    assert client.post("/packages", json=payload, headers=ENG_DEFAULT).status_code == 409


def test_viewer_cannot_create_package(client):
    r = client.post("/packages", json={"name": "x"}, headers=VIEWER_DEF)
    assert r.status_code == 403


def test_list_packages(client):
    for n in ("A", "B", "C"):
        client.post("/packages", json={"name": n}, headers=ENG_DEFAULT)
    r = client.get("/packages", headers=VIEWER_DEF)
    assert r.status_code == 200
    assert len(r.json()) == 3
    # FR-PKG-* — each package carries an artifact_count
    assert all("artifact_count" in p for p in r.json())


def test_get_package_includes_artifacts(client):
    pkg = client.post("/packages", json={"id": "pkg-x", "name": "X"},
                      headers=ENG_DEFAULT).json()
    aid = _upload(client, "ssp_weak_ac2.md")
    client.post(f"/packages/{pkg['id']}/artifacts/{aid}", headers=ENG_DEFAULT)

    r = client.get(f"/packages/{pkg['id']}", headers=VIEWER_DEF)
    assert r.status_code == 200
    body = r.json()
    assert len(body["artifacts"]) == 1
    assert body["artifacts"][0]["id"] == aid
    assert body["artifacts"][0]["package_id"] == "pkg-x"


# ---------- attach / detach ---------- #

def test_attach_artifact_to_package(client):
    pkg = client.post("/packages", json={"name": "P"}, headers=ENG_DEFAULT).json()
    aid = _upload(client, "ssp_weak_ac2.md")
    r = client.post(f"/packages/{pkg['id']}/artifacts/{aid}", headers=ENG_DEFAULT)
    assert r.status_code == 200, r.text


def test_detach_artifact_from_package(client):
    pkg = client.post("/packages", json={"name": "P"}, headers=ENG_DEFAULT).json()
    aid = _upload(client, "ssp_weak_ac2.md")
    client.post(f"/packages/{pkg['id']}/artifacts/{aid}", headers=ENG_DEFAULT)
    r = client.delete(f"/packages/{pkg['id']}/artifacts/{aid}", headers=ENG_DEFAULT)
    assert r.status_code == 200
    # Verify the artifact is no longer in the package
    art = client.get(f"/artifacts/{aid}", headers=VIEWER_DEF).json()
    assert art["package_id"] is None


def test_attach_to_archived_package_rejected(client):
    pkg = client.post("/packages", json={"name": "P"}, headers=ENG_DEFAULT).json()
    # draft -> archived is a legal direct transition
    client.patch(f"/packages/{pkg['id']}/status",
                 json={"status": "archived"}, headers=ENG_DEFAULT)
    aid = _upload(client, "ssp_weak_ac2.md")
    r = client.post(f"/packages/{pkg['id']}/artifacts/{aid}", headers=ENG_DEFAULT)
    assert r.status_code == 409
    assert "archived" in r.json()["detail"].lower()


# ---------- status state machine ---------- #

def test_legal_status_transitions(client):
    pkg = client.post("/packages", json={"name": "Lifecycle"},
                      headers=ENG_DEFAULT).json()
    # draft -> under_review
    r = client.patch(f"/packages/{pkg['id']}/status",
                     json={"status": "under_review"}, headers=ENG_DEFAULT)
    assert r.status_code == 200 and r.json()["status"] == "under_review"
    # under_review -> submitted
    r = client.patch(f"/packages/{pkg['id']}/status",
                     json={"status": "submitted"}, headers=ENG_DEFAULT)
    assert r.status_code == 200
    # submitted -> archived
    r = client.patch(f"/packages/{pkg['id']}/status",
                     json={"status": "archived"}, headers=ENG_DEFAULT)
    assert r.status_code == 200


def test_illegal_status_transition_rejected(client):
    pkg = client.post("/packages", json={"name": "Bad"}, headers=ENG_DEFAULT).json()
    # draft -> submitted is illegal (must go through under_review)
    r = client.patch(f"/packages/{pkg['id']}/status",
                     json={"status": "submitted"}, headers=ENG_DEFAULT)
    assert r.status_code == 409
    assert "illegal transition" in r.json()["detail"].lower()


def test_archived_is_terminal(client):
    pkg = client.post("/packages", json={"name": "Term"}, headers=ENG_DEFAULT).json()
    client.patch(f"/packages/{pkg['id']}/status",
                 json={"status": "archived"}, headers=ENG_DEFAULT)
    # archived -> anything is rejected
    for target in ("draft", "under_review", "submitted"):
        r = client.patch(f"/packages/{pkg['id']}/status",
                         json={"status": target}, headers=ENG_DEFAULT)
        assert r.status_code == 409


# ---------- package-level analysis ---------- #

def test_package_run_analyzes_all_member_artifacts(client):
    # ssp_good_ac2.md says AC-2 reviewed "quarterly"; arch_ac2_conflict.md
    # says "annually". Together they're a real cross-artifact contradiction.
    pkg = client.post("/packages", json={"name": "Multi"}, headers=ENG_DEFAULT).json()
    a1 = _upload(client, "ssp_good_ac2.md")
    a2 = _upload(client, "arch_ac2_conflict.md")
    client.post(f"/packages/{pkg['id']}/artifacts/{a1}", headers=ENG_DEFAULT)
    client.post(f"/packages/{pkg['id']}/artifacts/{a2}", headers=ENG_DEFAULT)

    r = client.post(f"/packages/{pkg['id']}/runs", headers=ENG_DEFAULT)
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["status"] == "completed"
    # T0 + T1 + T2 because MockAnalyzer is wired in the fixture
    assert "T0" in run["tier_path"] and "T1" in run["tier_path"]

    # Cross-artifact contradiction (AC-2 quarterly vs annually) must be detected
    fs = client.get(f"/runs/{run['id']}/findings", headers=VIEWER_DEF).json()
    inconsistent = [f for f in fs if f["type"] == "inconsistent"]
    assert any(f["control_id"] == "AC-2" for f in inconsistent), \
        f"expected cross-artifact AC-2 contradiction; got types={[f['type'] for f in fs]}"


def test_package_run_with_no_artifacts_fails_cleanly(client):
    pkg = client.post("/packages", json={"name": "Empty"}, headers=ENG_DEFAULT).json()
    r = client.post(f"/packages/{pkg['id']}/runs", headers=ENG_DEFAULT)
    assert r.status_code == 409
    assert "no artifacts" in r.json()["detail"].lower()


def test_archived_package_cannot_be_analyzed(client):
    pkg = client.post("/packages", json={"name": "Arc"}, headers=ENG_DEFAULT).json()
    client.patch(f"/packages/{pkg['id']}/status",
                 json={"status": "archived"}, headers=ENG_DEFAULT)
    r = client.post(f"/packages/{pkg['id']}/runs", headers=ENG_DEFAULT)
    assert r.status_code == 409


# ---------- tenant isolation ---------- #

def test_package_tenant_isolation(client):
    # Create two programs
    client.post("/programs", json={"id": "pgm-a", "name": "A"}, headers=ADMIN_DEFAULT)
    client.post("/programs", json={"id": "pgm-b", "name": "B"}, headers=ADMIN_DEFAULT)
    # Create a package in pgm-a
    client.post("/packages", json={"id": "secret-pkg", "name": "Secret"},
                headers={"X-QUILL-Role": "engineer", "X-QUILL-Tenant": "pgm-a"})
    # pgm-b can't see it
    listed = client.get("/packages",
                        headers={"X-QUILL-Role": "viewer", "X-QUILL-Tenant": "pgm-b"}).json()
    assert all(p["id"] != "secret-pkg" for p in listed)
    # Direct fetch returns 404 for the wrong tenant
    r = client.get("/packages/secret-pkg",
                   headers={"X-QUILL-Role": "viewer", "X-QUILL-Tenant": "pgm-b"})
    assert r.status_code == 404
