"""End-to-end: upload -> analyze -> attest -> audit chain verified."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import build_context, create_app  # noqa: E402
from tests.conftest import MockAnalyzer              # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"

ENG = {"X-QUILL-Role": "engineer"}
ATT = {"X-QUILL-Role": "attester"}
VIEWER = {"X-QUILL-Role": "viewer"}


@pytest.fixture
def client():
    ctx = build_context(analyzer=MockAnalyzer())
    return TestClient(create_app(ctx))


def _seed_finding(client):
    with open(FIXTURES / "ssp_weak_ac2.md", "rb") as fh:
        up = client.post("/artifacts", files={"file": ("ssp.md", fh, "text/markdown")}, headers=ENG)
    aid = up.json()["id"]
    run = client.post(f"/artifacts/{aid}/runs", headers=ENG).json()
    findings = client.get(f"/runs/{run['id']}/findings", headers=ENG).json()
    assert findings, "fixture expected to produce findings"
    return findings[0]


def test_attestation_flow_end_to_end(client):
    f = _seed_finding(client)
    # viewer cannot attest
    r = client.post(f"/findings/{f['id']}/attest", json={"decision": "approved"}, headers=VIEWER)
    assert r.status_code == 403

    # attester approves
    r = client.post(f"/findings/{f['id']}/attest",
                    json={"decision": "approved", "note": "ok"}, headers=ATT)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision"] == "approved" and body["provenance_id"] and body["signature_scheme"]

    # finding now reflects approved status
    after = client.get(f"/findings/{f['id']}", headers=ENG).json()
    assert after["status"] == "approved"

    # history contains the signed provenance + audit entry
    hist = client.get(f"/findings/{f['id']}/history", headers=ENG).json()
    assert hist["provenance"] and hist["audit"]
    assert hist["all_signatures_valid"] is True

    # audit chain verifies
    ver = client.get("/audit/verify", headers=ENG).json()
    assert ver["chain_valid"] is True and ver["events"] >= 3   # ingest + run + attest


def test_edit_requires_edited_fields(client):
    f = _seed_finding(client)
    r = client.post(f"/findings/{f['id']}/attest", json={"decision": "edited"}, headers=ATT)
    assert r.status_code == 409


def test_double_attest_rejected(client):
    f = _seed_finding(client)
    assert client.post(f"/findings/{f['id']}/attest", json={"decision": "approved"}, headers=ATT).status_code == 200
    r2 = client.post(f"/findings/{f['id']}/attest", json={"decision": "rejected"}, headers=ATT)
    assert r2.status_code == 409                                # FR-ATT-01 illegal transition


def test_admin_is_not_auto_attester(client):
    f = _seed_finding(client)
    r = client.post(f"/findings/{f['id']}/attest",
                    json={"decision": "approved"}, headers={"X-QUILL-Role": "admin"})
    assert r.status_code == 403                                  # security-critical separation
