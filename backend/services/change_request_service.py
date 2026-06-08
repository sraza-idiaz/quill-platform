"""PR-style change-request / attestation flow (FR-ATT-01..06).

A finding's lifecycle (`unattested → approved | edited | rejected`) is gated by
the `attester` role. Each attestation:
  1. validates state transitions (FR-ATT-01: illegal transitions rejected),
  2. blocks non-attester users (FR-ATT-03),
  3. preserves the AI-proposed original AND the edit, both signed (FR-ATT-06),
  4. writes a signed provenance record (NFR-AUD-04),
  5. emits an audit event (FR-ATT-04 / NFR-AUD-01..02),
  6. updates the finding status.

Findings in `flag_for_review` (low-confidence deferral) are NOT attestable —
they must be re-emitted as findings before they can move to a terminal state.
QUILL never produces an authorize/deny output (FR-ATT-05).
"""

from __future__ import annotations

from typing import Optional

from backend.models.domain import Finding, FindingStatus
from backend.services.audit_service import AuditLedger
from backend.services.provenance_service import ProvenanceLedger, ProvenanceRecord


class AttestationError(Exception):
    pass


TERMINAL = {FindingStatus.approved, FindingStatus.edited, FindingStatus.rejected}
ATTESTABLE_FROM = {FindingStatus.unattested}


class ChangeRequestService:
    def __init__(self, repo, provenance: ProvenanceLedger, audit: AuditLedger,
                 *, model: str = "tier2", model_version: str = "0"):
        self.repo = repo
        self.prov = provenance
        self.audit = audit
        self._model = model
        self._model_version = model_version

    async def attest(
        self, *, finding_id: str, tenant: str, attester_user: dict,
        decision: FindingStatus, note: str = "",
        edited_fields: Optional[dict] = None,
    ) -> ProvenanceRecord:
        """Apply an approve/edit/reject decision to a finding.

        attester_user dict comes from the auth dep; role MUST be 'attester'.
        """
        if attester_user.get("role") != "attester":
            raise AttestationError("role 'attester' required")

        if decision not in TERMINAL:
            raise AttestationError(f"decision must be one of {sorted(t.value for t in TERMINAL)}")

        finding = await self.repo.get_finding(finding_id, tenant)
        if finding is None:
            raise AttestationError("finding not found")
        if finding.status not in ATTESTABLE_FROM:
            raise AttestationError(f"finding in state '{finding.status.value}' cannot be attested")

        # Preserve the AI-proposed original verbatim (FR-ATT-06).
        proposed = finding.model_dump(mode="json")
        edited: Optional[dict] = None
        if decision is FindingStatus.edited:
            if not edited_fields:
                raise AttestationError("'edited' decision requires edited_fields")
            edited = dict(edited_fields)
            # Apply only safe, attester-editable fields to the live finding.
            for k in ("recommendation", "rationale", "severity", "missing_elements"):
                if k in edited:
                    setattr(finding, k, edited[k])

        # Sign + write provenance.
        record = self.prov.write(
            tenant=tenant, finding_id=finding.id,
            ai_model=self._model, ai_model_version=self._model_version,
            proposed=proposed, decision=decision.value, edited=edited,
            attester=attester_user["user"], note=note,
        )

        # Update the finding's status and persist.
        finding.status = decision
        await self.repo.update_finding(finding)

        # Audit (no artifact content).
        self.audit.append(
            tenant=tenant, actor=attester_user["user"],
            action=f"finding.{decision.value}",
            target_type="finding", target_id=finding.id,
            metadata={"control_id": finding.control_id, "provenance_id": record.id,
                      "scheme": record.signature_scheme, "key_id": record.signature_key_id},
        )
        return record

    async def history(self, finding_id: str, tenant: str) -> dict:
        records = self.prov.for_finding(finding_id, tenant)
        events = self.audit.list(tenant, target_id=finding_id)
        return {
            "provenance": [r.__dict__ for r in records],
            "audit": [e.__dict__ for e in events],
            "all_signatures_valid": all(self.prov.verify(r) for r in records),
        }
