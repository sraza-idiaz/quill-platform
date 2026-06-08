"""Tamper-evident audit trail (FR-ATT-04 / NFR-AUD).

Append-only event ledger. Each event carries SHA-256 of the prior event's hash
+ this event's payload, forming a hash chain — any tampering breaks the chain
and `verify_chain()` returns False. Artifact content is NEVER stored here
(NFR-OBS-01); events reference ids only.

Storage is pluggable via the same Repository pattern (in-memory for dev/test;
Postgres adapter at WP-4 tail). This module is the chain + serialization logic.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Optional


GENESIS = "0" * 64


@dataclass
class AuditEvent:
    id: str
    tenant: str
    actor: str               # user id or 'system'
    action: str              # e.g. 'artifact.ingested', 'finding.attested'
    target_type: str         # e.g. 'artifact','run','finding'
    target_id: str
    metadata: dict           # MUST NOT contain artifact content (NFR-OBS-01)
    prev_hash: str
    event_hash: str
    at: str                  # ISO-8601 UTC

    @staticmethod
    def compute_hash(prev_hash: str, payload: dict) -> str:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(prev_hash.encode() + body).hexdigest()


class AuditLedger:
    """In-memory ledger. Production wires the same ops over Postgres."""

    _FORBIDDEN_KEYS = {"quoted_text", "artifact_text", "narrative", "content"}

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    # ------------------------------------------------------------------ #
    def _redact(self, metadata: Optional[dict]) -> dict:
        m = dict(metadata or {})
        for k in list(m.keys()):
            if k in self._FORBIDDEN_KEYS:
                m[k] = "<redacted>"
        return m

    def append(self, *, tenant: str, actor: str, action: str,
               target_type: str, target_id: str, metadata: Optional[dict] = None) -> AuditEvent:
        prev = self._events[-1].event_hash if self._events else GENESIS
        payload = {
            "tenant": tenant, "actor": actor, "action": action,
            "target_type": target_type, "target_id": target_id,
            "metadata": self._redact(metadata),
            "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        h = AuditEvent.compute_hash(prev, payload)
        event = AuditEvent(
            id=f"ae-{uuid.uuid4().hex[:12]}",
            prev_hash=prev, event_hash=h, **payload,
        )
        self._events.append(event)
        return event

    def list(self, tenant: str, target_id: Optional[str] = None) -> list[AuditEvent]:
        return [e for e in self._events if e.tenant == tenant and (target_id is None or e.target_id == target_id)]

    def verify_chain(self) -> bool:
        """Integrity check (NFR-AUD-02) — any tamper breaks the chain."""
        prev = GENESIS
        for e in self._events:
            payload = {
                "tenant": e.tenant, "actor": e.actor, "action": e.action,
                "target_type": e.target_type, "target_id": e.target_id,
                "metadata": e.metadata, "at": e.at,
            }
            expected = AuditEvent.compute_hash(prev, payload)
            if e.prev_hash != prev or e.event_hash != expected:
                return False
            prev = e.event_hash
        return True

    def export(self) -> list[dict]:
        """Integrity-verifiable audit artifact (FR-EXP-03)."""
        return [asdict(e) for e in self._events]
