"""Audit-trail tests (NFR-AUD-01..02 / FR-RES-03 / NFR-OBS-01)."""
from backend.services.audit_service import AuditLedger


def test_chain_starts_at_genesis_and_links():
    led = AuditLedger()
    e1 = led.append(tenant="t", actor="a", action="x", target_type="r", target_id="r1")
    e2 = led.append(tenant="t", actor="a", action="y", target_type="r", target_id="r1")
    assert e1.prev_hash == "0" * 64
    assert e2.prev_hash == e1.event_hash
    assert led.verify_chain()


def test_tamper_detected():
    led = AuditLedger()
    led.append(tenant="t", actor="a", action="x", target_type="r", target_id="r1")
    led.append(tenant="t", actor="a", action="y", target_type="r", target_id="r1")
    # Tamper with the middle event's metadata.
    led._events[0].metadata["sneaky"] = True
    assert led.verify_chain() is False                   # NFR-AUD-02


def test_no_artifact_content_in_metadata():
    led = AuditLedger()
    e = led.append(tenant="t", actor="a", action="x", target_type="art", target_id="a1",
                   metadata={"quoted_text": "secret CUI line", "filename": "x.md"})
    assert e.metadata["quoted_text"] == "<redacted>"     # FR-RES-03 / NFR-OBS-01
    assert e.metadata["filename"] == "x.md"


def test_tenant_isolation():
    led = AuditLedger()
    led.append(tenant="A", actor="a", action="x", target_type="r", target_id="r1")
    led.append(tenant="B", actor="b", action="y", target_type="r", target_id="r2")
    assert len(led.list("A")) == 1
    assert led.list("A")[0].target_id == "r1"
