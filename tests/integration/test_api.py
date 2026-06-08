"""End-to-end API tests (FR-API, FR-ING, FR-RES, integration of all tiers).

Exercises upload -> analyze -> findings through the real FastAPI app with the
in-memory repo and the deterministic mock analyzer. No DB/LLM needed.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import build_context, create_app  # noqa: E402
from tests.conftest import MockAnalyzer  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture
def client():
    ctx = build_context(analyzer=MockAnalyzer())
    return TestClient(create_app(ctx))


ENG = {"X-QUILL-Role": "engineer"}
VIEWER = {"X-QUILL-Role": "viewer"}


def _upload(client, name, headers=ENG):
    p = FIXTURES / name
    with open(p, "rb") as fh:
        return client.post("/artifacts", files={"file": (name, fh, "text/markdown")}, headers=headers)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["circuit_breaker_threshold"] == 3  # non-negotiable surfaced


def test_full_pipeline_upload_analyze_findings(client):
    up = _upload(client, "ssp_weak_ac2.md")
    assert up.status_code == 201
    artifact_id = up.json()["id"]
    assert len(up.json()["hash"]) == 64

    run = client.post(f"/artifacts/{artifact_id}/runs", headers=ENG)
    assert run.status_code == 201
    run_body = run.json()
    assert run_body["status"] == "completed"
    assert "T0" in run_body["tier_path"] and "T2" in run_body["tier_path"]

    findings = client.get(f"/runs/{run_body['id']}/findings", headers=ENG)
    assert findings.status_code == 200
    data = findings.json()
    assert data, "expected findings on a weak SSP"
    # Every finding traceable to a source span (NFR-AUD-03)
    for f in data:
        assert f["evidence_spans"], f"finding {f['id']} has no span"
        assert f["confidence"] is not None
    # missing baseline controls detected (Tier 0)
    assert any(f["type"] == "missing" for f in data)


def test_viewer_cannot_upload(client):
    r = _upload(client, "ssp_weak_ac2.md", headers=VIEWER)
    assert r.status_code == 403  # FR-API-02 role enforcement


def test_unsupported_type_rejected(client, tmp_path):
    f = tmp_path / "x.zip"
    f.write_text("nope")
    with open(f, "rb") as fh:
        r = client.post("/artifacts", files={"file": ("x.zip", fh, "application/zip")}, headers=ENG)
    assert r.status_code == 400


def test_tenant_isolation(client):
    # Upload as tenant A; tenant B cannot see the artifact (FR-API-03).
    up = _upload(client, "ssp_weak_ac2.md", headers={"X-QUILL-Role": "engineer", "X-QUILL-Tenant": "A"})
    aid = up.json()["id"]
    r = client.get(f"/artifacts/{aid}", headers={"X-QUILL-Role": "engineer", "X-QUILL-Tenant": "B"})
    assert r.status_code == 404


def test_corrupted_artifact_does_not_crash(client, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid")
    with open(bad, "rb") as fh:
        up = client.post("/artifacts", files={"file": ("bad.json", fh, "application/json")}, headers=ENG)
    aid = up.json()["id"]
    run = client.post(f"/artifacts/{aid}/runs", headers=ENG)
    assert run.status_code == 201
    assert run.json()["status"] == "failed"        # FR-ING-05: clean failure, no crash
    assert run.json()["failure_reason"]
