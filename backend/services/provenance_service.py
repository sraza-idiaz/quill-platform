"""Provenance ledger (NFR-AUD-04). Signed records capturing the chain:
  AI proposal → (optional edit) → human attestation → cryptographic signature.

Reuses the signer abstraction (gpg_signer.Signer). Every record is integrity-
verifiable via the signer; the audit ledger separately records the *fact* of
each provenance write (so deleting a record from prov is still detectable via
the audit chain).
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Optional

from backend.services.gpg_signer import Signature, Signer


@dataclass
class ProvenanceRecord:
    id: str
    tenant: str
    finding_id: str
    ai_model: str
    ai_model_version: str
    proposed: dict                # the original AI-proposed finding fields
    decision: str                 # 'approved' | 'edited' | 'rejected'
    edited: Optional[dict]        # edited fields, if any
    attester: str
    note: str
    signature: str
    signature_key_id: str
    signature_scheme: str
    signed_at: str
    created_at: str

    @staticmethod
    def canonical_payload(*, tenant: str, finding_id: str, ai_model: str, ai_model_version: str,
                          proposed: dict, decision: str, edited: Optional[dict],
                          attester: str, note: str) -> bytes:
        return json.dumps({
            "tenant": tenant, "finding_id": finding_id,
            "ai_model": ai_model, "ai_model_version": ai_model_version,
            "proposed": proposed, "decision": decision, "edited": edited,
            "attester": attester, "note": note,
        }, sort_keys=True, separators=(",", ":"), default=str).encode()


class ProvenanceLedger:
    def __init__(self, signer: Signer) -> None:
        self._records: list[ProvenanceRecord] = []
        self._signer = signer

    @property
    def signer(self) -> Signer:
        return self._signer

    def write(self, *, tenant: str, finding_id: str, ai_model: str, ai_model_version: str,
              proposed: dict, decision: str, edited: Optional[dict],
              attester: str, note: str) -> ProvenanceRecord:
        payload = ProvenanceRecord.canonical_payload(
            tenant=tenant, finding_id=finding_id, ai_model=ai_model,
            ai_model_version=ai_model_version, proposed=proposed, decision=decision,
            edited=edited, attester=attester, note=note,
        )
        sig: Signature = self._signer.sign(payload, signer=attester)
        rec = ProvenanceRecord(
            id=f"pr-{uuid.uuid4().hex[:12]}",
            tenant=tenant, finding_id=finding_id,
            ai_model=ai_model, ai_model_version=ai_model_version,
            proposed=proposed, decision=decision, edited=edited,
            attester=attester, note=note,
            signature=sig.signature, signature_key_id=sig.key_id,
            signature_scheme=sig.scheme,
            signed_at=sig.signed_at.isoformat(),
            created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        )
        self._records.append(rec)
        return rec

    def verify(self, record: ProvenanceRecord) -> bool:
        payload = ProvenanceRecord.canonical_payload(
            tenant=record.tenant, finding_id=record.finding_id,
            ai_model=record.ai_model, ai_model_version=record.ai_model_version,
            proposed=record.proposed, decision=record.decision, edited=record.edited,
            attester=record.attester, note=record.note,
        )
        sig = Signature(
            signature=record.signature, key_id=record.signature_key_id,
            scheme=record.signature_scheme,
            signed_at=dt.datetime.fromisoformat(record.signed_at),
            signer=record.attester,
        )
        return self._signer.verify(payload, sig)

    def for_finding(self, finding_id: str, tenant: str) -> list[ProvenanceRecord]:
        return [r for r in self._records if r.finding_id == finding_id and r.tenant == tenant]

    def all(self, tenant: str) -> list[ProvenanceRecord]:
        return [r for r in self._records if r.tenant == tenant]
