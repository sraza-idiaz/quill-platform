"""Phase II FR-XA-03/FR-CONT extension — GET /packages/{id}/map (integration).

Covers:
  * 2-node map with at least 1 contradiction edge (cross-artifact AC-2
    inconsistency between ssp_good_ac2.md and arch_ac2_conflict.md)
  * map without any runs returns 200 with empty edges (not a 404)
  * 404 for unknown package
  * cross-tenant 404 (different tenant gets 404, not another tenant's data)
  * contradiction edge quotes are non-empty and from distinct artifacts
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

ENG = {"X-QUILL-Role": "engineer", "X-QUILL-Tenant": "default"}
ATT = {"X-QUILL-Role": "attester", "X-QUILL-Tenant": "default"}
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
# Helpers
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


def _create_pkg(client, headers: dict) -> str:
    r = client.post("/packages", json={"name": "Map test pkg"}, headers=headers)
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
# Test 1 — map without any runs returns 200 with empty edges
# --------------------------------------------------------------------------- #
def test_map_no_runs_returns_200_with_empty_edges(client):
    """Before any analysis run the map endpoint must return 200, not 404.

    The nodes are derived from artifacts already attached; there are no
    findings yet, so edges must be empty.
    """
    pid = _create_pkg(client, ENG)
    aid = _upload(client, FIXTURES / "ssp_good_ac2.md", ENG)
    _attach(client, pid, aid, ENG)

    r = client.get(f"/packages/{pid}/map", headers=ENG)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["edges"] == []
    assert len(body["nodes"]) == 1
    assert body["run_id"] is None


# --------------------------------------------------------------------------- #
# Test 2 — 404 for unknown package
# --------------------------------------------------------------------------- #
def test_map_404_for_unknown_package(client):
    r = client.get("/packages/pkg-does-not-exist/map", headers=ENG)
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Test 3 — cross-tenant 404
# --------------------------------------------------------------------------- #
def test_map_cross_tenant_returns_404(client):
    """A package created in tenant 'default' must not be accessible from
    'other-tenant' (returns 404, not the package data)."""
    pid = _create_pkg(client, ENG)
    r = client.get(f"/packages/{pid}/map", headers=OTHER)
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Test 4 — map with 2 artifacts and a run: 2 nodes + contradiction edge
# --------------------------------------------------------------------------- #
def test_map_two_artifacts_has_nodes_and_contradiction_edge(client):
    """ssp_good_ac2.md + arch_ac2_conflict.md produce a cross-artifact AC-2
    inconsistency (quarterly vs annually). After a run the map must contain
    exactly 2 nodes and at least 1 contradiction edge.
    """
    pid = _create_pkg(client, ENG)
    aid_ssp  = _upload(client, FIXTURES / "ssp_good_ac2.md",    ENG)
    aid_arch = _upload(client, FIXTURES / "arch_ac2_conflict.md", ENG)
    _attach(client, pid, aid_ssp,  ENG)
    _attach(client, pid, aid_arch, ENG)
    _run_analysis(client, pid, ENG)

    r = client.get(f"/packages/{pid}/map", headers=ENG)
    assert r.status_code == 200, r.text
    body = r.json()

    # Package id is filled by the route.
    assert body["package_id"] == pid
    assert body["run_id"] is not None

    # Exactly 2 nodes.
    assert len(body["nodes"]) == 2
    node_ids = {n["artifact_id"] for n in body["nodes"]}
    assert node_ids == {aid_ssp, aid_arch}

    # At least 1 contradiction edge.
    contradiction_edges = [e for e in body["edges"] if e["kind"] == "contradiction"]
    assert len(contradiction_edges) >= 1


# --------------------------------------------------------------------------- #
# Test 5 — contradiction edge quotes are non-empty and from distinct artifacts
# --------------------------------------------------------------------------- #
def test_contradiction_edge_quotes_non_empty_and_distinct_artifacts(client):
    """Each contradiction edge must carry non-empty quote text on both sides,
    and the two sides must reference different artifact ids."""
    pid = _create_pkg(client, ENG)
    aid_ssp  = _upload(client, FIXTURES / "ssp_good_ac2.md",    ENG)
    aid_arch = _upload(client, FIXTURES / "arch_ac2_conflict.md", ENG)
    _attach(client, pid, aid_ssp,  ENG)
    _attach(client, pid, aid_arch, ENG)
    _run_analysis(client, pid, ENG)

    r = client.get(f"/packages/{pid}/map", headers=ENG)
    assert r.status_code == 200, r.text
    body = r.json()

    contradiction_edges = [e for e in body["edges"] if e["kind"] == "contradiction"]
    assert contradiction_edges, "expected at least one contradiction edge"

    for edge in contradiction_edges:
        detail = edge["detail"]
        left  = detail["left"]
        right = detail["right"]

        # Both quotes must be non-empty strings.
        assert left["quote"],  f"left quote is empty for edge {edge['id']}"
        assert right["quote"], f"right quote is empty for edge {edge['id']}"

        # Both artifact ids must be set and distinct.
        assert left["artifact_id"],  f"left artifact_id missing for edge {edge['id']}"
        assert right["artifact_id"], f"right artifact_id missing for edge {edge['id']}"
        assert left["artifact_id"] != right["artifact_id"], (
            f"both sides of contradiction edge {edge['id']} point to the same artifact"
        )
