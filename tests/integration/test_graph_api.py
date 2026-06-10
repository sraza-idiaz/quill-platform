"""Phase II FR-XA-03 — graph endpoints (integration tests)."""
import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import build_context, create_app  # noqa: E402
from tests.conftest import MockAnalyzer              # noqa: E402

ENG = {"X-QUILL-Role": "engineer", "X-QUILL-Tenant": "default"}
VIEWER = {"X-QUILL-Role": "viewer", "X-QUILL-Tenant": "default"}


@pytest.fixture
def client():
    ctx = build_context(analyzer=MockAnalyzer())
    return TestClient(create_app(ctx))


def _upload(client, name: str, body: str) -> str:
    r = client.post("/artifacts",
                    files={"file": (name, io.BytesIO(body.encode()), "text/markdown")},
                    headers=ENG)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_artifact_graph_returns_nodes_and_edges(client):
    aid = _upload(client, "ssp.md",
        "# SSP\n## AC-2 Account Management\nAccount events are logged per AU-2.\n"
        "## AU-2 Event Logging\nRecords include AC-2 lifecycle events.\n"
    )
    r = client.get(f"/artifacts/{aid}/graph", headers=VIEWER)
    assert r.status_code == 200
    body = r.json()
    ids = {n["control_id"] for n in body["nodes"]}
    assert {"AC-2", "AU-2"}.issubset(ids)
    # AC-2 <-> AU-2 bidirectional reference
    edges = body["edges"]
    assert any(e["from_control"] == "AC-2" and e["to_control"] == "AU-2" for e in edges)
    assert any(e["from_control"] == "AU-2" and e["to_control"] == "AC-2" for e in edges)


def test_package_graph_spans_multiple_artifacts(client):
    pkg = client.post("/packages", json={"name": "Multi"}, headers=ENG).json()
    a1 = _upload(client, "ssp.md",
        "# SSP\n## AC-2 Account Management\nLogged per AU-2.\n"
    )
    a2 = _upload(client, "arch.md",
        "# Arch\n## AU-2 Event Logging\nReviews include AC-2 anomalies.\n"
    )
    client.post(f"/packages/{pkg['id']}/artifacts/{a1}", headers=ENG)
    client.post(f"/packages/{pkg['id']}/artifacts/{a2}", headers=ENG)

    r = client.get(f"/packages/{pkg['id']}/graph", headers=VIEWER)
    assert r.status_code == 200
    edges = r.json()["edges"]
    ac2_to_au2 = [e for e in edges if e["from_control"] == "AC-2" and e["to_control"] == "AU-2"]
    au2_to_ac2 = [e for e in edges if e["from_control"] == "AU-2" and e["to_control"] == "AC-2"]
    assert ac2_to_au2 and ac2_to_au2[0]["artifact_id"] == a1
    assert au2_to_ac2 and au2_to_ac2[0]["artifact_id"] == a2


def test_graph_404_for_unknown_package(client):
    r = client.get("/packages/nope/graph", headers=VIEWER)
    assert r.status_code == 404


def test_graph_in_baseline_flag_matches_program_baseline(client):
    # The default program runs `moderate` baseline; CM-2 is moderate/high only.
    aid = _upload(client, "ssp.md",
        "# SSP\n## CM-2 Baseline Configuration\nReferenced by AC-2 in the SSP.\n"
        "## AC-2 Account Management\nUses CM-2 baselines.\n"
    )
    r = client.get(f"/artifacts/{aid}/graph", headers=VIEWER)
    nodes = {n["control_id"]: n for n in r.json()["nodes"]}
    assert nodes["CM-2"]["in_baseline"] is True   # moderate baseline includes CM-2
    assert nodes["AC-2"]["in_baseline"] is True
