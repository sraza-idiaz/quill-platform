"""Attestation gate tests (FR-ATT-01..06)."""
import pytest

from backend.db.repository import InMemoryRepository
from backend.models.domain import (EvidenceSpan, Finding, FindingStatus, FindingType, Severity, Tier)
from backend.services.audit_service import AuditLedger
from backend.services.change_request_service import AttestationError, ChangeRequestService
from backend.services.gpg_signer import HmacSigner
from backend.services.provenance_service import ProvenanceLedger


def _finding(fid="f1"):
    return Finding(
        id=fid, run_id="r1", control_id="AC-2", type=FindingType.insufficient_evidence,
        severity=Severity.medium, confidence=0.9, recommendation="fix",
        evidence_spans=[EvidenceSpan(artifact_id="a", locator="l", quoted_text="q")],
        tier=Tier.t2, status=FindingStatus.unattested,
    )


@pytest.fixture
def svc():
    repo = InMemoryRepository()
    prov = ProvenanceLedger(HmacSigner())
    audit = AuditLedger()
    return repo, ChangeRequestService(repo, prov, audit, model="mock", model_version="1"), prov, audit


@pytest.mark.asyncio
async def test_approve_writes_signed_provenance_and_audit(svc):
    repo, cr, prov, audit = svc
    f = _finding(); await repo.replace_findings("r1", "default", [f])
    rec = await cr.attest(
        finding_id=f.id, tenant="default",
        attester_user={"user": "alice", "role": "attester", "tenant": "default"},
        decision=FindingStatus.approved, note="looks right",
    )
    assert rec.signature and prov.verify(rec)                # signed + verifies
    fresh = await repo.get_finding(f.id, "default")
    assert fresh.status == FindingStatus.approved             # FR-ATT-01
    assert audit.verify_chain() and len(audit.list("default")) == 1


@pytest.mark.asyncio
async def test_non_attester_rejected(svc):
    repo, cr, *_ = svc
    f = _finding(); await repo.replace_findings("r1", "default", [f])
    with pytest.raises(AttestationError):                     # FR-ATT-03
        await cr.attest(finding_id=f.id, tenant="default",
                        attester_user={"user": "b", "role": "engineer", "tenant": "default"},
                        decision=FindingStatus.approved)


@pytest.mark.asyncio
async def test_edit_preserves_original(svc):
    repo, cr, prov, _ = svc
    f = _finding(); await repo.replace_findings("r1", "default", [f])
    rec = await cr.attest(
        finding_id=f.id, tenant="default",
        attester_user={"user": "alice", "role": "attester", "tenant": "default"},
        decision=FindingStatus.edited, note="clearer wording",
        edited_fields={"recommendation": "Specify account types + review frequency"},
    )
    assert rec.proposed["recommendation"] == "fix"            # FR-ATT-06 (original preserved)
    assert rec.edited["recommendation"].startswith("Specify")
    fresh = await repo.get_finding(f.id, "default")
    assert fresh.recommendation.startswith("Specify")
    assert fresh.status == FindingStatus.edited


@pytest.mark.asyncio
async def test_cannot_attest_twice(svc):
    repo, cr, *_ = svc
    f = _finding(); await repo.replace_findings("r1", "default", [f])
    user = {"user": "alice", "role": "attester", "tenant": "default"}
    await cr.attest(finding_id=f.id, tenant="default", attester_user=user, decision=FindingStatus.approved)
    with pytest.raises(AttestationError):                     # FR-ATT-01 illegal transition
        await cr.attest(finding_id=f.id, tenant="default", attester_user=user, decision=FindingStatus.rejected)


@pytest.mark.asyncio
async def test_provenance_signature_invalid_if_payload_changed(svc):
    repo, cr, prov, _ = svc
    f = _finding(); await repo.replace_findings("r1", "default", [f])
    rec = await cr.attest(
        finding_id=f.id, tenant="default",
        attester_user={"user": "alice", "role": "attester", "tenant": "default"},
        decision=FindingStatus.approved,
    )
    # Mutate the recorded note -> verification must fail.
    rec.note = "manipulated"
    assert prov.verify(rec) is False


@pytest.mark.asyncio
async def test_edit_requires_edited_fields(svc):
    repo, cr, *_ = svc
    f = _finding(); await repo.replace_findings("r1", "default", [f])
    with pytest.raises(AttestationError):
        await cr.attest(finding_id=f.id, tenant="default",
                        attester_user={"user": "alice", "role": "attester", "tenant": "default"},
                        decision=FindingStatus.edited)
