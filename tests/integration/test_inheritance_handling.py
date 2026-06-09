"""Phase II FR-XA-02 — Tier 0 inheritance-aware behavior (integration tests).

Proves the end-to-end behavior:
  * A properly-attributed inherited control produces NO 'missing required
    fields' finding (this is the false-positive Tier 0 used to emit).
  * An incomplete inheritance claim DOES produce a focused finding telling
    the team exactly what attribution to add.
  * A normal (non-inherited) narrative is unchanged.
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

ENG = {"X-QUILL-Role": "engineer", "X-QUILL-Tenant": "default"}
VIEWER = {"X-QUILL-Role": "viewer", "X-QUILL-Tenant": "default"}


@pytest.fixture
def client():
    ctx = build_context(analyzer=MockAnalyzer())
    return TestClient(create_app(ctx))


def _upload_text(client, name: str, body: str) -> str:
    import io
    r = client.post(
        "/artifacts",
        files={"file": (name, io.BytesIO(body.encode()), "text/markdown")},
        headers=ENG,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _run_and_get_findings(client, aid: str):
    run = client.post(f"/artifacts/{aid}/runs", headers=ENG).json()
    return client.get(f"/runs/{run['id']}/findings", headers=VIEWER).json()


def _t0_required_fields_findings(findings, control_id: str):
    """Tier 0 findings on `control_id` that are about local implementation
    fields (the false-positive class we want to suppress on inherited controls).
    """
    return [
        f for f in findings
        if f["control_id"] == control_id
        and f["tier"] == "T0"
        and f["type"] == "insufficient_evidence"
        and any(e not in ("organization_defined_parameter",
                          "inheritance_provider",
                          "inheritance_attestation")
                for e in f.get("missing_elements") or [])
    ]


def _t0_inheritance_findings(findings, control_id: str):
    return [
        f for f in findings
        if f["control_id"] == control_id
        and f["tier"] == "T0"
        and any(e in ("inheritance_provider", "inheritance_attestation")
                for e in f.get("missing_elements") or [])
    ]


def test_properly_attributed_inheritance_suppresses_required_field_findings(client):
    """The classic case: 'AC-2 is inherited from Azure AD's SOC 2 Type II audit.'
    Tier 0 must NOT emit 'missing required fields' here — it's not the team's job."""
    aid = _upload_text(client, "ssp.md", (
        "# SSP\n\n## AC-2 Account Management\n\n"
        "AC-2 is inherited from Azure Active Directory; coverage is backed by "
        "their current SOC 2 Type II audit and FedRAMP High authorization. "
        "Provider attestation is renewed annually.\n"
    ))
    fs = _run_and_get_findings(client, aid)

    impl = _t0_required_fields_findings(fs, "AC-2")
    inh = _t0_inheritance_findings(fs, "AC-2")
    assert not impl, f"expected no T0 impl-field findings on inherited AC-2; got {impl}"
    assert not inh, f"expected no inheritance-attribution findings on a complete claim; got {inh}"


def test_incomplete_inheritance_emits_focused_finding(client):
    """'AC-2 is inherited from the IAM provider' — provider parsed, no attestation.
    The team needs to be told to add the SOC 2 / FedRAMP / etc. attribution."""
    aid = _upload_text(client, "ssp.md", (
        "# SSP\n\n## AC-2 Account Management\n\n"
        "AC-2 is inherited from the enterprise IAM platform.\n"
    ))
    fs = _run_and_get_findings(client, aid)

    inh = _t0_inheritance_findings(fs, "AC-2")
    assert inh, f"expected an inheritance-attribution finding; got none. all={fs}"
    missing = inh[0]["missing_elements"]
    assert "inheritance_attestation" in missing


def test_non_inherited_narrative_is_unchanged(client):
    """A normal (not-inherited) narrative still goes through the standard
    required-fields check. This is the regression guard."""
    aid = _upload_text(client, "ssp.md", (
        "# SSP\n\n## AC-2 Account Management\n\n"
        "The organization manages information system accounts.\n"
    ))
    fs = _run_and_get_findings(client, aid)
    # Either the legacy field-absence finding OR an ODP placeholder finding —
    # either way, there should be at least one T0 insufficient_evidence on AC-2.
    impl_or_odp = [
        f for f in fs
        if f["control_id"] == "AC-2"
        and f["tier"] == "T0"
        and f["type"] == "insufficient_evidence"
    ]
    assert impl_or_odp, "non-inherited narrative should still produce normal T0 findings"
