"""Export service (FR-EXP-01..03).

Three deliverables, all signed via the QUILL signer:
  * **Human report** — Markdown summary of attested findings with source spans.
  * **OSCAL POA&M** — open-finding plan-of-action in NIST OSCAL POA&M shape.
    Contains NO authorization field (FR-EXP-02 / FR-ATT-05).
  * **Audit artifact** — integrity-verifiable export of the audit chain.

Only **attested** findings (approved/edited) are exported (FR-ATT-02). Rejected
findings are excluded; unattested findings are excluded by definition.

Production guardrail: in non-dev mode the export requires GPG signing
(`scheme=="gpg"`); HMAC-signed exports are blocked outside DEV_MODE.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import uuid
from dataclasses import asdict, dataclass
from typing import Optional

from backend.models.domain import Finding, FindingStatus
from backend.services.audit_service import AuditLedger
from backend.services.gpg_signer import Signature, Signer

EXPORTABLE = {FindingStatus.approved, FindingStatus.edited}


class ExportSchemeError(Exception):
    pass


@dataclass
class Export:
    id: str
    format: str               # 'report' | 'poam' | 'audit'
    content: str              # text payload (md or JSON)
    signature: Signature
    created_at: str


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _ensure_prod_signing(signer: Signer) -> None:
    if os.environ.get("QUILL_DEV_MODE", "1") != "1" and signer.scheme != "gpg":
        raise ExportSchemeError(
            f"production exports must use scheme='gpg' (got '{signer.scheme}'). "
            "Configure QUILL_GPG_KEY_ID."
        )


def _filter_exportable(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.status in EXPORTABLE]


# --------------------------------------------------------------------------- #
def render_human_report(*, run_id: str, artifact_filename: str, baseline: str,
                        findings: list[Finding]) -> str:
    """Markdown report (FR-EXP-01). No authorization recommendation anywhere."""
    findings = _filter_exportable(findings)
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings = sorted(findings, key=lambda f: (sev_order.get(f.severity.value, 9), f.control_id))
    lines = [
        f"# QUILL Pre-Adjudication Report",
        f"",
        f"- **Run:** `{run_id}`",
        f"- **Artifact:** {artifact_filename}",
        f"- **Baseline:** {baseline}",
        f"- **Generated:** {_now()}",
        f"- **Findings (attested):** {len(findings)}",
        f"",
        f"> This report identifies documentation deficiencies. **QUILL does not make an authorization decision.**",
        f"> All findings have been reviewed and signed by a human attester before inclusion.",
        f"",
        f"---",
    ]
    if not findings:
        lines.append("\n_No attested findings to report._")
    for f in findings:
        lines += [
            f"\n## {f.control_id} — {f.severity.value.upper()} — {f.type.value}",
            f"",
            f"**Status:** {f.status.value}  ·  **Confidence:** {f.confidence:.2f}  ·  **Tier:** {f.tier.value}",
            f"",
            f"**Recommendation:** {f.recommendation}",
            f"",
        ]
        if f.missing_elements:
            lines.append(f"**Missing elements:** {', '.join(f.missing_elements)}\n")
        if f.evidence_spans:
            lines.append("**Source span(s):**\n")
            for s in f.evidence_spans:
                if s.artifact_id.startswith("catalog:"):
                    lines.append(f"- _Catalog requirement:_ `{s.locator}` — {s.quoted_text[:140]}")
                else:
                    lines.append(f"- `{s.artifact_id}` @ `{s.locator}`: \"{s.quoted_text[:200].strip()}\"")
        lines.append("")
    return "\n".join(lines)


def render_oscal_poam(*, run_id: str, artifact_id: str, findings: list[Finding]) -> dict:
    """OSCAL-shape POA&M (FR-EXP-02). No authorization field exists by design.

    Open-finding shape uses 'poam-items' with 'related-observations'. Keeps the
    field set minimal but valid against the OSCAL POA&M model (NIST 1.1.x).
    """
    findings = _filter_exportable(findings)
    observations = []
    poam_items = []
    for f in findings:
        obs_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"quill:obs:{f.id}"))
        item_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"quill:poam:{f.id}"))
        observations.append({
            "uuid": obs_uuid,
            "title": f"{f.control_id}: {f.type.value}",
            "description": f.rationale or f.recommendation,
            "methods": ["EXAMINE"],
            "types": ["control-objective"],
            "props": [
                {"name": "control-id", "value": f.control_id},
                {"name": "severity", "value": f.severity.value},
                {"name": "confidence", "value": f"{f.confidence:.2f}"},
                {"name": "finding-type", "value": f.type.value},
            ],
            "relevant-evidence": [
                {"href": f"#{s.artifact_id}/{s.locator}", "description": s.quoted_text[:280]}
                for s in f.evidence_spans
            ],
        })
        poam_items.append({
            "uuid": item_uuid,
            "title": f"Remediate documentation deficiency on {f.control_id}",
            "description": f.recommendation,
            "props": [{"name": "control-id", "value": f.control_id},
                      {"name": "severity", "value": f.severity.value}],
            "related-observations": [{"observation-uuid": obs_uuid}],
        })
    return {
        "plan-of-action-and-milestones": {
            "uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"quill:poam:run:{run_id}")),
            "metadata": {
                "title": "QUILL Documentation Deficiency POA&M",
                "last-modified": _now(),
                "version": "0.1",
                "oscal-version": "1.1.2",
                "props": [{"name": "produced-by", "value": "quill"},
                          {"name": "run-id", "value": run_id},
                          {"name": "artifact-id", "value": artifact_id}],
            },
            "import-ssp": {"href": f"#{artifact_id}"},
            "observations": observations,
            "poam-items": poam_items,
        }
    }


def render_audit_artifact(audit: AuditLedger, tenant: str) -> dict:
    """Integrity-verifiable audit artifact (FR-EXP-03)."""
    events = [e for e in audit.export() if e["tenant"] == tenant]
    return {
        "quill_audit_artifact": {
            "version": 1,
            "generated_at": _now(),
            "tenant": tenant,
            "chain_valid": audit.verify_chain(),
            "events": events,
        }
    }


# --------------------------------------------------------------------------- #
def make_export(
    *, fmt: str, run_id: str, tenant: str, artifact_filename: str, artifact_id: str,
    baseline: str, findings: list[Finding], audit: AuditLedger, signer: Signer,
    signer_name: str = "system",
) -> Export:
    _ensure_prod_signing(signer)
    if fmt == "report":
        content = render_human_report(
            run_id=run_id, artifact_filename=artifact_filename, baseline=baseline,
            findings=findings,
        )
    elif fmt == "poam":
        content = json.dumps(
            render_oscal_poam(run_id=run_id, artifact_id=artifact_id, findings=findings),
            indent=2, sort_keys=True,
        )
    elif fmt == "audit":
        content = json.dumps(render_audit_artifact(audit, tenant), indent=2, sort_keys=True)
    else:
        raise ValueError(f"unknown export format: {fmt}")
    sig = signer.sign(content.encode("utf-8"), signer=signer_name)
    return Export(
        id=f"ex-{uuid.uuid4().hex[:12]}",
        format=fmt, content=content, signature=sig, created_at=_now(),
    )


def verify_export(content: str, signature: Signature, signer: Signer) -> bool:
    return signer.verify(content.encode("utf-8"), signature)
