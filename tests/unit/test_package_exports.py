"""Phase II FR-EXP-04..06 — unit tests for the new package-level exports.

Covers shape + boundary-rule compliance (no authorization language
anywhere in any export).
"""
import json

import pytest

from backend.models.domain import (
    EvidenceSpan, Finding, FindingStatus, FindingType, Package,
    PackageStatus, Severity, Tier,
)
from backend.services.package_exports import (
    render_oscal_package,
    render_stakeholder_pdf,
    render_version_diff_markdown,
)


def _pkg(name="Demo Pkg", pid="PKG-2026-ABCDEF") -> Package:
    return Package(id=pid, tenant="default", name=name,
                   status=PackageStatus.under_review,
                   description="Test package")


def _f(*, id, control, status=FindingStatus.approved,
       ftype=FindingType.weak_narrative,
       sev=Severity.medium, conf=0.8, quote="evidence sample"):
    return Finding(
        id=id, run_id="r1", control_id=control, type=ftype,
        severity=sev, confidence=conf,
        recommendation=f"Strengthen {control}",
        rationale="why",
        evidence_spans=[EvidenceSpan(artifact_id="ssp.md", locator="¶1",
                                      quoted_text=quote)],
        tier=Tier.t2, status=status,
    )


# ─── Stakeholder PDF ──────────────────────────────────────────────── #

def test_stakeholder_pdf_returns_bytes_under_1mb():
    findings = [_f(id=f"f{i}", control=f"AC-{i+1}") for i in range(15)]
    data = render_stakeholder_pdf(
        package=_pkg(), findings=findings, baseline="moderate", run_id="run-abc",
    )
    assert isinstance(data, bytes)
    assert data.startswith(b"%PDF"), "PDF magic header missing"
    assert len(data) < 1_000_000, "FR-EXP-04 size gate: must be < 1 MB"


def test_stakeholder_pdf_empty_findings_renders_cleanly():
    data = render_stakeholder_pdf(
        package=_pkg(), findings=[], baseline="moderate", run_id="run-empty",
    )
    assert data.startswith(b"%PDF")
    assert len(data) > 200   # non-trivial page


# ─── Version-diff markdown ────────────────────────────────────────── #

def test_version_diff_markdown_classifies_correctly():
    prev = [
        _f(id="p1", control="AC-2", status=FindingStatus.approved, quote="alpha"),
        _f(id="p2", control="AU-2", status=FindingStatus.unattested, quote="beta"),
    ]
    new = [
        _f(id="n1", control="AC-2", quote="alpha"),       # unchanged
        _f(id="n2", control="CM-2", quote="gamma"),       # new
        # AU-2 disappeared and was not attested → resolved.
    ]
    md = render_version_diff_markdown(
        package=_pkg(), from_run_id="run-1", to_run_id="run-2",
        from_findings=prev, to_findings=new,
    )
    assert "Version-diff report" in md
    assert "AC-2" in md     # unchanged section
    assert "CM-2" in md     # new section
    assert "AU-2" in md     # resolved section
    # Boundary statement appears.
    assert "QUILL does not make an authorization decision" in md


def test_version_diff_attested_disappearance_is_stale():
    prev = [_f(id="p1", control="AC-2", status=FindingStatus.approved, quote="alpha")]
    md = render_version_diff_markdown(
        package=_pkg(), from_run_id="r1", to_run_id="r2",
        from_findings=prev, to_findings=[],
    )
    # Stale section gets a count of 1.
    assert "Stale — re-confirm required (1)" in md


# ─── OSCAL package ────────────────────────────────────────────────── #

def test_oscal_package_has_required_top_level_documents():
    findings = [_f(id="f1", control="AC-2", status=FindingStatus.approved)]
    bundle = render_oscal_package(
        package=_pkg(), run_id="run-1", baseline="moderate",
        findings=findings, artifact_filenames={"art-1": "ssp.md"},
    )
    docs = bundle["quill-oscal-package"]["documents"]
    keys = [list(d.keys())[0] for d in docs]
    assert keys == ["system-security-plan",
                    "plan-of-action-and-milestones",
                    "assessment-results"]


def test_oscal_package_has_no_authorization_field():
    """P-CORE-01 — no authorize/deny anywhere in the OSCAL bundle."""
    findings = [_f(id="f1", control="AC-2", status=FindingStatus.approved)]
    bundle = render_oscal_package(
        package=_pkg(), run_id="r1", baseline="moderate",
        findings=findings, artifact_filenames={},
    )
    payload = json.dumps(bundle)
    for forbidden in ("authorize", "ato_granted", "ato-state",
                      "approve_system", "authorization-status"):
        assert forbidden.lower() not in payload.lower(), \
            f"forbidden field '{forbidden}' leaked into OSCAL export"


def test_oscal_package_omits_unattested_findings_from_poam():
    findings = [
        _f(id="approved", control="AC-2", status=FindingStatus.approved),
        _f(id="unatt",    control="AU-2", status=FindingStatus.unattested),
    ]
    bundle = render_oscal_package(
        package=_pkg(), run_id="r1", baseline="moderate",
        findings=findings, artifact_filenames={},
    )
    poam = bundle["quill-oscal-package"]["documents"][1] \
        ["plan-of-action-and-milestones"]
    item_titles = [i["title"] for i in poam["poam-items"]]
    assert any("AC-2" in t for t in item_titles)
    assert not any("AU-2" in t for t in item_titles), \
        "Unattested findings must not appear in POA&M (P-CORE-02)"


def test_oscal_package_versioned_at_1_1_2():
    bundle = render_oscal_package(
        package=_pkg(), run_id="r1", baseline="moderate",
        findings=[], artifact_filenames={},
    )
    for doc in bundle["quill-oscal-package"]["documents"]:
        inner = next(iter(doc.values()))
        assert inner["metadata"]["oscal-version"] == "1.1.2"


def test_oscal_assessment_results_includes_rejected_findings():
    """Rejected findings still appear in Assessment Results (assessor's
    signed 'this is not a deficiency' statement)."""
    findings = [
        _f(id="ok", control="AC-2", status=FindingStatus.approved),
        _f(id="no", control="AU-2", status=FindingStatus.rejected),
    ]
    bundle = render_oscal_package(
        package=_pkg(), run_id="r1", baseline="moderate",
        findings=findings, artifact_filenames={},
    )
    ar = bundle["quill-oscal-package"]["documents"][2]["assessment-results"]
    titles = [f["title"] for f in ar["results"][0]["findings"]]
    assert any("AC-2" in t for t in titles)
    assert any("AU-2" in t for t in titles)
