"""Citation validation tests (FR-T2-03) — the hard traceability rule."""
from backend.models.domain import EvidenceSpan, Finding, FindingType, Severity, Tier
from backend.services.analysis.citation_validator import span_is_valid, validate_findings


def _finding(span_artifact, quoted, fid="x"):
    return Finding(
        id=fid, run_id="r", control_id="AC-2", type=FindingType.insufficient_evidence,
        severity=Severity.medium, confidence=0.9, recommendation="fix",
        evidence_spans=[EvidenceSpan(artifact_id=span_artifact, locator="¶1", quoted_text=quoted)],
        tier=Tier.t2,
    )


ARTIFACT = {"art0": "The organization manages information system accounts. Reviewed quarterly."}


def test_valid_span_passes():
    f = _finding("art0", "manages information system accounts")
    valid, rejected = validate_findings([f], ARTIFACT)
    assert len(valid) == 1 and not rejected


def test_fabricated_span_rejected():
    # Model "hallucinated" a quote that isn't in the artifact -> dropped (FR-T2-03).
    f = _finding("art0", "this exact sentence does not appear anywhere")
    valid, rejected = validate_findings([f], ARTIFACT)
    assert not valid and len(rejected) == 1


def test_finding_without_span_rejected():
    f = _finding("art0", "manages information system accounts")
    f.evidence_spans = []
    valid, rejected = validate_findings([f], ARTIFACT)
    assert not valid and len(rejected) == 1


def test_whitespace_insensitive():
    assert span_is_valid("manages   information\nsystem accounts", ARTIFACT["art0"])


def test_catalog_ref_validated_against_refset():
    f = _finding("catalog:moderate", "AC-2 Account Management (required by moderate baseline)")
    # Not in ref set -> rejected.
    valid, rejected = validate_findings([f], ARTIFACT, catalog_refs=set())
    assert not valid
    # In ref set -> accepted.
    valid, rejected = validate_findings([f], ARTIFACT, catalog_refs={"catalog:moderate"})
    assert len(valid) == 1
