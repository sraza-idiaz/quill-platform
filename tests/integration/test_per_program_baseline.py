"""Phase II — per-program baseline (FR-MT-01 / FR-CAT-05).

Proves that the same artifact, ingested into two programs with different
baselines (Low vs. High), produces different `missing` finding sets. This is
the actual *point* of multi-tenancy: each program sees its own required
control set.
"""
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

FIXTURE = ROOT / "tests" / "fixtures" / "ssp_good_ac2.md"


def _hdr(tenant: str, role: str = "engineer"):
    return {"X-QUILL-Role": role, "X-QUILL-Tenant": tenant}


@pytest.fixture
def client():
    ctx = build_context(analyzer=MockAnalyzer())
    return TestClient(create_app(ctx))


def _create_program(client, pid: str, baseline: str):
    r = client.post("/programs", json={"id": pid, "name": pid.title(), "baseline": baseline},
                    headers={"X-QUILL-Role": "admin", "X-QUILL-Tenant": "default"})
    assert r.status_code == 201, r.text


def _upload_and_analyze(client, tenant: str, fixture: Path) -> list[dict]:
    with open(fixture, "rb") as fh:
        up = client.post("/artifacts",
                         files={"file": (fixture.name, fh, "text/markdown")},
                         headers=_hdr(tenant))
    assert up.status_code == 201, up.text
    aid = up.json()["id"]
    run = client.post(f"/artifacts/{aid}/runs", headers=_hdr(tenant)).json()
    return client.get(f"/runs/{run['id']}/findings", headers=_hdr(tenant)).json()


def test_low_baseline_requires_fewer_controls_than_high(client):
    """Same artifact in 'low-pgm' vs 'high-pgm' must produce different
    `missing` sets because Low baseline requires fewer controls than High."""
    _create_program(client, "low-pgm",  "low")
    _create_program(client, "high-pgm", "high")

    low_findings  = _upload_and_analyze(client, "low-pgm",  FIXTURE)
    high_findings = _upload_and_analyze(client, "high-pgm", FIXTURE)

    low_missing  = {f["control_id"] for f in low_findings  if f["type"] == "missing"}
    high_missing = {f["control_id"] for f in high_findings if f["type"] == "missing"}

    # CM-2 and SI-4 are moderate/high-only in our sample catalog — must not
    # appear in the low-baseline run, must appear in the high-baseline run.
    assert "CM-2" not in low_missing
    assert "SI-4" not in low_missing
    assert "CM-2" in high_missing
    assert "SI-4" in high_missing


def test_baseline_recorded_on_the_run(client):
    """Audit metadata records the active baseline so the per-program override
    is visible after the fact."""
    _create_program(client, "audit-pgm", "high")
    findings = _upload_and_analyze(client, "audit-pgm", FIXTURE)

    audit = client.get("/audit", headers=_hdr("audit-pgm", "viewer")).json()
    run_events = [e for e in audit if e["action"].startswith("run.")]
    assert run_events, "expected a run audit event"
    assert any(e["metadata"].get("baseline") == "high" for e in run_events)


def test_tenant_isolation_artifacts(client):
    """Artifacts uploaded to program A must NOT appear in program B's inventory."""
    _create_program(client, "iso-a", "moderate")
    _create_program(client, "iso-b", "moderate")
    _upload_and_analyze(client, "iso-a", FIXTURE)

    arts_a = client.get("/artifacts", headers=_hdr("iso-a")).json()
    arts_b = client.get("/artifacts", headers=_hdr("iso-b")).json()
    assert len(arts_a) == 1
    assert len(arts_b) == 0


def test_missing_finding_quote_reflects_active_baseline(client):
    """The `catalog:` evidence span on `missing` findings carries the active
    baseline so traceability is correct per-program."""
    _create_program(client, "trace-pgm", "high")
    findings = _upload_and_analyze(client, "trace-pgm", FIXTURE)
    missing = [f for f in findings if f["type"] == "missing"]
    assert missing
    for f in missing:
        spans = f["evidence_spans"]
        assert any(s["artifact_id"] == "catalog:high" for s in spans), \
            f"finding for {f['control_id']} should cite catalog:high, got {[s['artifact_id'] for s in spans]}"
