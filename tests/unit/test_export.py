"""Export service tests (FR-EXP-01..03)."""
import json
import os

import pytest

from backend.models.domain import (EvidenceSpan, Finding, FindingStatus, FindingType, Severity, Tier)
from backend.services.audit_service import AuditLedger
from backend.services.export_service import (ExportSchemeError, make_export, render_human_report,
                                              render_oscal_poam, verify_export)
from backend.services.gpg_signer import HmacSigner


def _finding(status, fid="f1", ctrl="AC-2", tier=Tier.t2):
    return Finding(id=fid, run_id="r1", control_id=ctrl, type=FindingType.insufficient_evidence,
                   severity=Severity.high, confidence=0.9, recommendation="Specify accounts.",
                   rationale="Generic restatement.", missing_elements=["responsible_role"],
                   evidence_spans=[EvidenceSpan(artifact_id="art0", locator="¶2", quoted_text="manages accounts")],
                   tier=tier, status=status)


def _findings_mix():
    return [_finding(FindingStatus.approved, "fa"),
            _finding(FindingStatus.rejected, "fr"),
            _finding(FindingStatus.unattested, "fu"),
            _finding(FindingStatus.edited, "fe", "AU-2")]


def test_only_attested_findings_exported():
    # Distinct controls so we can identify which findings landed in the export.
    fs = [
        _finding(FindingStatus.approved, "fa", ctrl="AC-2"),       # included
        _finding(FindingStatus.rejected, "fr", ctrl="SI-4"),       # excluded
        _finding(FindingStatus.unattested, "fu", ctrl="CM-2"),     # excluded
        _finding(FindingStatus.edited, "fe", ctrl="AU-2"),         # included
    ]
    md = render_human_report(run_id="r", artifact_filename="x.md", baseline="moderate", findings=fs)
    # The MD report has a "## <control_id>" heading for each included finding.
    assert "## AC-2" in md and "## AU-2" in md
    assert "## SI-4" not in md and "## CM-2" not in md       # FR-ATT-02
    poam = render_oscal_poam(run_id="r", artifact_id="art0", findings=fs)
    items = poam["plan-of-action-and-milestones"]["poam-items"]
    assert len(items) == 2     # only approved + edited
    titles = "\n".join(i["title"] for i in items)
    assert "AC-2" in titles and "AU-2" in titles
    assert "SI-4" not in titles and "CM-2" not in titles


def test_oscal_poam_has_no_authorization_field():
    fs = _findings_mix()
    poam = render_oscal_poam(run_id="r", artifact_id="art0", findings=fs)
    body = json.dumps(poam).lower()
    forbidden = ["authorize", "authorization", "ato", "accreditation", "system-authorized"]
    for word in forbidden:
        assert word not in body, f"export must not contain '{word}' (FR-EXP-02 / FR-ATT-05)"


def test_export_signature_verifies_and_detects_tamper():
    signer = HmacSigner()
    ex = make_export(fmt="report", run_id="r1", tenant="t", artifact_filename="x.md",
                     artifact_id="art0", baseline="moderate",
                     findings=_findings_mix(), audit=AuditLedger(), signer=signer)
    assert verify_export(ex.content, ex.signature, signer) is True
    assert verify_export(ex.content + "extra", ex.signature, signer) is False


def test_prod_blocks_hmac_signing(monkeypatch):
    monkeypatch.setenv("QUILL_DEV_MODE", "0")
    with pytest.raises(ExportSchemeError):
        make_export(fmt="report", run_id="r", tenant="t", artifact_filename="x.md",
                    artifact_id="a", baseline="moderate", findings=_findings_mix(),
                    audit=AuditLedger(), signer=HmacSigner())


def test_audit_artifact_contains_chain():
    audit = AuditLedger()
    audit.append(tenant="t", actor="u", action="x", target_type="r", target_id="r1")
    ex = make_export(fmt="audit", run_id="r1", tenant="t", artifact_filename="x.md",
                     artifact_id="a", baseline="moderate", findings=[], audit=audit, signer=HmacSigner())
    data = json.loads(ex.content)
    assert data["quill_audit_artifact"]["chain_valid"] is True
    assert data["quill_audit_artifact"]["events"]
