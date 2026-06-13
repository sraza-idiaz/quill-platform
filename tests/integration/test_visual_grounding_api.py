"""Phase II FR-XA extension — GET /packages/{id}/grounding (integration).

Covers:
  * 200 with empty groundings when the package has no runs
  * 404 for an unknown package id
  * cross-tenant 404 (different tenant must not see another tenant's package)
  * end-to-end: upload ssp_good_ac2.md + arch_ac2_conflict.md, analyze, GET
    /grounding → at least one inconsistent grounding with conflicts_with and a
    non-empty regulatory.objective_summary
  * 401 (or 403) without auth headers when basic-auth is OFF (sanity check)
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import build_context, create_app   # noqa: E402
from tests.conftest import MockAnalyzer               # noqa: E402

ENG   = {"X-QUILL-Role": "engineer", "X-QUILL-Tenant": "default"}
OTHER = {"X-QUILL-Role": "engineer", "X-QUILL-Tenant": "other-tenant"}

FIXTURES = ROOT / "tests" / "fixtures"


# --------------------------------------------------------------------------- #
# Shared client fixture
# --------------------------------------------------------------------------- #
@pytest.fixture
def client():
    os.environ["QUILL_WATCHER_ENABLED"] = "0"
    ctx = build_context(analyzer=MockAnalyzer())
    return TestClient(create_app(ctx))


# --------------------------------------------------------------------------- #
# Helpers (mirror the map API test helpers)
# --------------------------------------------------------------------------- #
def _upload(client, path: Path, headers: dict) -> str:
    data = path.read_bytes()
    r = client.post(
        "/artifacts",
        files={"file": (path.name, io.BytesIO(data), "text/markdown")},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_pkg(client, headers: dict, name: str = "Grounding test pkg") -> str:
    r = client.post("/packages", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _attach(client, pkg_id: str, art_id: str, headers: dict) -> None:
    r = client.post(f"/packages/{pkg_id}/artifacts/{art_id}", headers=headers)
    assert r.status_code == 200, r.text


def _run_analysis(client, pkg_id: str, headers: dict) -> dict:
    r = client.post(f"/packages/{pkg_id}/runs", headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# Test 1 — 200 with empty groundings when package has no runs
# --------------------------------------------------------------------------- #
def test_grounding_no_runs_returns_200_with_empty_groundings(client):
    """Before any analysis run the grounding endpoint must return 200 with
    groundings == [] and the artifacts list populated (NOT 404)."""
    pid = _create_pkg(client, ENG)
    aid = _upload(client, FIXTURES / "ssp_good_ac2.md", ENG)
    _attach(client, pid, aid, ENG)

    r = client.get(f"/packages/{pid}/grounding", headers=ENG)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["package_id"] == pid
    assert body["run_id"] is None
    assert body["groundings"] == []
    # Artifact pass-through must still be present.
    assert len(body["artifacts"]) == 1
    assert body["artifacts"][0]["filename"] == "ssp_good_ac2.md"


# --------------------------------------------------------------------------- #
# Test 2 — 404 for unknown package id
# --------------------------------------------------------------------------- #
def test_grounding_404_for_unknown_package(client):
    r = client.get("/packages/pkg-does-not-exist/grounding", headers=ENG)
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Test 3 — cross-tenant 404
# --------------------------------------------------------------------------- #
def test_grounding_cross_tenant_returns_404(client):
    """A package created in tenant 'default' must not be accessible from
    'other-tenant' — the endpoint must return 404, not the grounding data."""
    pid = _create_pkg(client, ENG)
    r = client.get(f"/packages/{pid}/grounding", headers=OTHER)
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Test 4 — end-to-end: inconsistent grounding with conflicts_with non-empty
# --------------------------------------------------------------------------- #
def test_grounding_end_to_end_inconsistent_finding(client):
    """Upload ssp_good_ac2.md + arch_ac2_conflict.md, run analysis, then GET
    /grounding and assert:
      - at least one grounding with type='inconsistent'
      - that grounding has >= 1 entry in conflicts_with
      - primary.filename matches one of the two source documents
      - regulatory.objective_summary is non-empty
      - package_id is filled by the route
    """
    pid = _create_pkg(client, ENG)
    aid_ssp  = _upload(client, FIXTURES / "ssp_good_ac2.md",    ENG)
    aid_arch = _upload(client, FIXTURES / "arch_ac2_conflict.md", ENG)
    _attach(client, pid, aid_ssp,  ENG)
    _attach(client, pid, aid_arch, ENG)
    _run_analysis(client, pid, ENG)

    r = client.get(f"/packages/{pid}/grounding", headers=ENG)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["package_id"] == pid
    assert body["run_id"] is not None

    # Must have at least one grounding.
    assert len(body["groundings"]) >= 1

    # Find an inconsistent grounding with conflicts.
    inconsistent = [g for g in body["groundings"] if g["type"] == "inconsistent"]
    assert inconsistent, (
        "Expected at least one inconsistent grounding from the quarterly/annually conflict"
    )

    g = inconsistent[0]
    assert len(g["conflicts_with"]) >= 1, "inconsistent grounding must have >= 1 conflict"

    # primary.filename must be one of the two uploaded docs.
    source_filenames = {"ssp_good_ac2.md", "arch_ac2_conflict.md"}
    assert g["primary"]["filename"] in source_filenames, (
        f"primary.filename '{g['primary']['filename']}' not in {source_filenames}"
    )

    # regulatory.objective_summary must be non-empty (AC-2 has objectives in catalog).
    assert g["regulatory"]["objective_summary"], (
        "regulatory.objective_summary must be non-empty for AC-2"
    )

    # Artifact list must contain both uploaded docs.
    artifact_filenames = {a["filename"] for a in body["artifacts"]}
    assert "ssp_good_ac2.md"    in artifact_filenames
    assert "arch_ac2_conflict.md" in artifact_filenames


# --------------------------------------------------------------------------- #
# Test 5 — auth sanity: DEV_MODE on / basic-auth OFF behavior
# --------------------------------------------------------------------------- #
def test_grounding_no_explicit_auth_headers_returns_200_in_dev_mode(client):
    """When basic-auth is OFF (QUILL_BASIC_AUTH_USER not set) and DEV_MODE is
    ON (default), calling the endpoint without explicit X-QUILL-Role headers
    still returns 200 — the server falls back to the 'engineer' default role.
    This is the expected DEV_MODE behaviour (see backend/services/auth.py).

    If basic-auth were enabled, the same call would return 401; that path is
    covered by tests/integration/test_basic_auth.py.
    """
    import os as _os
    # Confirm basic-auth is indeed OFF (no QUILL_BASIC_AUTH_USER set).
    assert not _os.environ.get("QUILL_BASIC_AUTH_USER"), (
        "QUILL_BASIC_AUTH_USER is set — this test assumes basic-auth is OFF"
    )

    pid = _create_pkg(client, ENG)
    # No auth headers — DEV_MODE falls back to default engineer/default tenant.
    r = client.get(f"/packages/{pid}/grounding")
    # Should succeed (200) because DEV_MODE is on.
    assert r.status_code == 200, (
        f"Expected 200 in DEV_MODE without auth headers, got {r.status_code}"
    )
    # But the tenant is 'default', so the package IS found.
    assert r.json()["package_id"] == pid
