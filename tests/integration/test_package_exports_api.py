"""Phase II FR-EXP-04..06 + FR-AI-02 — endpoint integration."""
import os
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import build_context, create_app          # noqa: E402
from tests.conftest import MockAnalyzer                      # noqa: E402

ENG = {"X-QUILL-Role": "engineer", "X-QUILL-Tenant": "default"}
ATT = {"X-QUILL-Role": "attester", "X-QUILL-Tenant": "default"}

FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture
def client():
    os.environ["QUILL_WATCHER_ENABLED"] = "0"
    ctx = build_context(analyzer=MockAnalyzer())
    from backend.services.continuous_runner import handle_watch_event
    ctx.watcher.on_change(lambda ev: handle_watch_event(ctx, ev))
    return TestClient(create_app(ctx))


def _bootstrap_package_with_one_run(client, tmp_path) -> str:
    pkg = client.post("/packages", json={"name": "Export test"},
                      headers=ENG).json()
    pid = pkg["id"]
    client.post(f"/packages/{pid}/watch",
                json={"folder": str(tmp_path)}, headers=ENG)
    shutil.copyfile(FIXTURES / "ssp_weak_ac2.md", tmp_path / "ssp.md")
    client.post(f"/packages/{pid}/watch/poll", headers=ENG)
    return pid


# ─── /packages/{id}/export?format=stakeholder_pdf ─────────────────── #

def test_stakeholder_pdf_returns_pdf_bytes(client, tmp_path):
    pid = _bootstrap_package_with_one_run(client, tmp_path)
    r = client.get(f"/packages/{pid}/export?format=stakeholder_pdf",
                   headers=ENG)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content.startswith(b"%PDF")
    assert len(r.content) < 1_000_000


def test_version_diff_export_is_markdown(client, tmp_path):
    pid = _bootstrap_package_with_one_run(client, tmp_path)
    r = client.get(f"/packages/{pid}/export?format=version_diff",
                   headers=ENG)
    assert r.status_code == 200
    assert "markdown" in r.headers["content-type"]
    assert "QUILL does not make an authorization decision" in r.text


def test_oscal_package_export_is_json_and_passes_boundary_rule(client, tmp_path):
    pid = _bootstrap_package_with_one_run(client, tmp_path)
    r = client.get(f"/packages/{pid}/export?format=oscal_package",
                   headers=ENG)
    assert r.status_code == 200
    body = r.json()
    payload_raw = r.text.lower()
    assert "authorize" not in payload_raw
    assert "ato_granted" not in payload_raw
    docs = body["quill-oscal-package"]["documents"]
    assert len(docs) == 3


def test_export_unknown_format_400(client, tmp_path):
    pid = _bootstrap_package_with_one_run(client, tmp_path)
    r = client.get(f"/packages/{pid}/export?format=invalid", headers=ENG)
    assert r.status_code == 400


def test_export_without_runs_409(client):
    pid = client.post("/packages", json={"name": "Empty"},
                      headers=ENG).json()["id"]
    r = client.get(f"/packages/{pid}/export?format=stakeholder_pdf",
                   headers=ENG)
    assert r.status_code == 409


# ─── /calibration/report ──────────────────────────────────────────── #

def test_calibration_report_initially_empty(client):
    r = client.get("/calibration/report", headers=ENG)
    assert r.status_code == 200
    body = r.json()
    assert body["n_attested"] == 0
    assert body["ece"] == 0.0
    assert len(body["bins"]) == 10
    assert body["phase_ii_gate"]["ece_max"] == 0.20


def test_calibration_report_reflects_attestations(client, tmp_path):
    pid = _bootstrap_package_with_one_run(client, tmp_path)
    versions = client.get(f"/packages/{pid}/versions", headers=ENG).json()
    findings = client.get(f"/runs/{versions[0]['run_id']}/findings",
                          headers=ENG).json()
    if not findings:
        pytest.skip("MockAnalyzer produced no findings on this fixture")
    # Attest a few.
    for f in findings[:3]:
        client.post(f"/findings/{f['id']}/attest",
                    json={"decision": "approved"}, headers=ATT)
    body = client.get("/calibration/report", headers=ENG).json()
    assert body["n_attested"] >= 1


def test_calibration_csv_endpoint_returns_csv(client):
    r = client.get("/calibration/curve.csv", headers=ENG)
    assert r.status_code == 200
    assert "csv" in r.headers["content-type"]
    assert "bin_lo,bin_hi" in r.text
