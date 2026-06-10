"""Phase II FR-EXP-04..06 — three new package-level exports.

  * FR-EXP-04 — Stakeholder Summary PDF: non-technical management
    readout. Counts by severity, top 10 findings, rework-reduction
    estimate. Branded. Generated via fpdf2 → bytes; aim < 1 MB.
  * FR-EXP-05 — Version-Diff Report: side-by-side comparison of two
    runs of the same package. Markdown so it diffs cleanly in git/PRs.
  * FR-EXP-06 — OSCAL Package Export: full OSCAL 1.1.x bundle —
    POA&M (open findings) + Assessment Results (closed/attested
    findings) + an SSP shell linking back to the artifacts. Shaped
    against the eMASS ingestion spec (FR-EMS-01).

The boundary rule (P-CORE-01) is preserved everywhere: no field in
any export carries an authorize/deny recommendation. Stakeholder text
explicitly says "QUILL does not make an authorization decision."

These are package-scoped (one run, one package). The existing
single-run exports (`report`, `poam`, `audit` in export_service.py)
are still supported via /runs/{id}/export — those are unchanged.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import logging
import uuid
from typing import Optional

from backend.models.domain import Finding, FindingStatus, Package, Severity
from backend.services.continuous import FindingDiff, diff_findings

logger = logging.getLogger("quill.package_exports")

OSCAL_VERSION = "1.1.2"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _severity_counts(findings: list[Finding]) -> dict[str, int]:
    out = {s.value: 0 for s in Severity}
    for f in findings:
        out[f.severity.value] += 1
    return out


def _attested_count(findings: list[Finding]) -> int:
    return sum(1 for f in findings if f.status in
               (FindingStatus.approved, FindingStatus.edited))


_LATIN1_TRANSLATIONS = str.maketrans({
    "—": "--",     # em dash
    "–": "-",      # en dash
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "•": "*",
    "…": "...",
    "·": "-",      # middle dot
    " ": " ",      # nbsp
})


def _latin1_safe(s: str) -> str:
    """fpdf2's core Helvetica font is latin-1 only — strip / substitute
    common non-latin1 punctuation so we don't crash on findings that
    contain typographic punctuation copied from a PDF. Falls back to
    `?` for anything not representable."""
    if not s:
        return ""
    s = s.translate(_LATIN1_TRANSLATIONS)
    return s.encode("latin-1", errors="replace").decode("latin-1")


def _exportable(findings: list[Finding]) -> list[Finding]:
    """Only attested findings are exported (P-CORE-02). Unattested/rejected
    are excluded from authoritative artifacts. The diff and stakeholder
    PDF use total counts for context but never as authoritative output."""
    return [f for f in findings
            if f.status in (FindingStatus.approved, FindingStatus.edited)]


# --------------------------------------------------------------------------- #
# FR-EXP-04 — Stakeholder Summary PDF
# --------------------------------------------------------------------------- #
def render_stakeholder_pdf(
    *, package: Package, findings: list[Finding],
    baseline: str, run_id: str,
) -> bytes:
    """Return PDF bytes — a one-or-two-page readout for non-technical
    stakeholders. Always usable; explicitly NOT an authorization artifact.

    Sections:
      1. Header (program / package / generated date)
      2. The boundary statement
      3. Severity histogram
      4. Top 10 findings (control + severity + one-line summary)
      5. Rework-reduction estimate (counts × per-finding labor savings)
      6. Provenance footer
    """
    try:
        from fpdf import FPDF
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("fpdf2 not installed; cannot render stakeholder PDF") from e

    sev_counts = _severity_counts(findings)
    total = len(findings)
    attested = _attested_count(findings)
    # Conservative rework-reduction estimate (carryover from the Phase I
    # rework-reduction analysis): each finding caught up-front saves a
    # ~30-min cycle (4-week ADP loop avg). Floor at 0 for empty packages.
    rework_hours_saved = max(0.0, total * 0.5)

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def _txt(s: str) -> str:
        return _latin1_safe(s)

    # Header.
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(0, 10, _txt("QUILL -- Stakeholder Summary"), ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 6, _txt(f"Package: {package.name} ({package.id})"), ln=True)
    pdf.cell(0, 6, _txt(f"Program: {package.tenant}  |  Baseline: {baseline.upper()}  |  Run: {run_id}"), ln=True)
    pdf.cell(0, 6, _txt(f"Generated: {_now()}"), ln=True)
    pdf.ln(4)

    # Boundary statement (P-CORE-01).
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(
        0, 5,
        _txt("QUILL does not make or recommend an authorization decision. "
             "This report identifies documentation deficiencies that human "
             "attesters have reviewed and signed. Authorization remains a "
             "human responsibility under the Risk Management Framework."),
    )
    pdf.ln(2)

    # Severity histogram.
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(0, 8, _txt("Findings by severity"), ln=True)
    pdf.set_font("Helvetica", "", 11)
    colors = {"critical": (192, 64, 64), "high": (220, 130, 60),
              "medium": (220, 180, 60), "low": (120, 160, 120)}
    bar_max_mm = 120.0
    max_count = max(sev_counts.values()) or 1
    for sev in ("critical", "high", "medium", "low"):
        n = sev_counts[sev]
        bar_len = (n / max_count) * bar_max_mm
        r, g, b = colors[sev]
        pdf.set_fill_color(r, g, b)
        pdf.cell(20, 6, _txt(sev.title()), border=0)
        pdf.cell(max(bar_len, 0.5), 6, "", border=0, fill=True)
        pdf.cell(0, 6, f"  {n}", ln=True)
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, _txt(f"Total: {total}  |  Attested: {attested}"), ln=True)
    pdf.ln(2)

    # Top 10 attested findings (sorted by severity then control).
    exportable = _exportable(findings)
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    top = sorted(exportable, key=lambda f: (sev_order.get(f.severity.value, 9),
                                            f.control_id))[:10]
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, _txt("Top findings (attested)"), ln=True)
    pdf.set_font("Helvetica", "", 10)
    if not top:
        pdf.set_text_color(140, 140, 140)
        pdf.multi_cell(0, 5, _txt("No attested findings yet. Open the Attestation Gate "
                       "to review the analysis output."))
        pdf.set_text_color(40, 40, 40)
    for f in top:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 5, _txt(f"{f.control_id} -- {f.severity.value.upper()} ({f.type.value})"), ln=True)
        pdf.set_font("Helvetica", "", 10)
        summary = (f.recommendation or f.rationale or "")[:200]
        pdf.multi_cell(0, 4.5, _txt(summary))
        pdf.ln(1)

    # Rework reduction estimate.
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, _txt("Estimated rework reduction"), ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(
        0, 5,
        _txt(f"Catching {total} documentation deficiency(ies) before ADP submission "
             f"saves an estimated {rework_hours_saved:.1f} engineer-hours of "
             f"adjudication-cycle rework (~0.5 hours per finding, conservative). "
             f"Real savings vary by program and reviewer cadence."),
    )

    # Footer.
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 4, _txt(f"QUILL | run {run_id} | {len(findings)} total finding(s) considered"), ln=True)

    out = pdf.output(dest="S")
    if isinstance(out, str):
        return out.encode("latin-1")
    return bytes(out)


# --------------------------------------------------------------------------- #
# FR-EXP-05 — Version-Diff Report
# --------------------------------------------------------------------------- #
def render_version_diff_markdown(
    *, package: Package, from_run_id: str, to_run_id: str,
    from_findings: list[Finding], to_findings: list[Finding],
) -> str:
    """Markdown report comparing two runs of the same package.

    Markdown so it diffs cleanly in git, in a PR review, in Slack
    preview. The version-diff is the artifact reviewers ask for during
    pre-submission ("what changed since last week?").
    """
    prev_attested = {f.id for f in from_findings
                     if f.status in (FindingStatus.approved, FindingStatus.edited)}
    d = diff_findings(from_findings, to_findings, prev_attested=prev_attested)
    c = d.counts()

    lines = [
        f"# Version-diff report — {package.name}",
        "",
        f"- **Package:** `{package.id}`",
        f"- **From run:** `{from_run_id}`",
        f"- **To run:** `{to_run_id}`",
        f"- **Generated:** {_now()}",
        "",
        f"> **{c['new']}** new · **{c['resolved']}** resolved · **{c['stale']}** stale · **{c['unchanged']}** unchanged",
        "",
        "> _QUILL does not make an authorization decision._",
        "",
        "---",
    ]

    def _format_finding(f: Finding) -> list[str]:
        out = [f"### {f.control_id} — {f.severity.value.upper()} — {f.type.value}",
               "",
               f"- **Status:** {f.status.value}  · **Confidence:** {f.confidence:.2f}  · **Tier:** {f.tier.value}",
               f"- **Recommendation:** {f.recommendation}",
               ]
        if f.evidence_spans:
            s = f.evidence_spans[0]
            quote = (s.quoted_text or "").strip()[:240]
            if s.artifact_id.startswith("catalog:"):
                out.append(f"- _Catalog reference:_ `{s.locator}` — {quote}")
            else:
                out.append(f'- _Source:_ `{s.artifact_id}` @ `{s.locator}` — "{quote}"')
        out.append("")
        return out

    def _section(title: str, items: list[Finding], hint: str) -> list[str]:
        out = [f"## {title} ({len(items)})", ""]
        if not items:
            out += [f"_{hint}_", ""]
        for f in items:
            out += _format_finding(f)
        return out

    lines += _section("New", d.new, "No new findings since the prior run.")
    lines += _section("Resolved", d.resolved,
                      "No previously-emitted findings have gone away in this run.")
    lines += _section("Stale — re-confirm required", d.stale,
                      "No previously-attested findings have become stale.")
    lines += _section("Unchanged", d.unchanged,
                      "No findings carried through from the prior run.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# FR-EXP-06 — OSCAL Package Export
# --------------------------------------------------------------------------- #
def render_oscal_package(
    *, package: Package, run_id: str, baseline: str, findings: list[Finding],
    artifact_filenames: dict[str, str],
) -> dict:
    """Full OSCAL 1.1.x bundle in eMASS-conformant shape.

    Three top-level OSCAL documents under a single JSON envelope:

      * `system-security-plan` — minimal shell pointing at the package's
        artifacts (intentionally minimal — QUILL does NOT author SSPs;
        FR-OOS-01 in DECISIONS-014 — but a connector needs an SSP root
        to anchor POA&M + AR references to).
      * `plan-of-action-and-milestones` — open findings.
      * `assessment-results` — attested findings, both approved (closed
        out by remediation) and rejected (assessor said this isn't a
        deficiency). No `authorize-action`, no `system-security-plan-result`
        with an ATO state — those would violate P-CORE-01.

    Returns a JSON-ready dict (caller decides to bytes/file).
    """
    exportable = _exportable(findings)
    # We also surface rejected findings in the AR (they're an assessor's
    # signed "this is not a deficiency" statement — useful audit trail).
    rejected = [f for f in findings if f.status == FindingStatus.rejected]

    # ---- SSP shell ----------------------------------------------------- #
    ssp_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"quill:ssp:{package.id}"))
    ssp = {
        "system-security-plan": {
            "uuid": ssp_uuid,
            "metadata": {
                "title": f"{package.name} — SSP package",
                "last-modified": _now(),
                "version": "0.1",
                "oscal-version": OSCAL_VERSION,
                "props": [
                    {"name": "produced-by", "value": "quill"},
                    {"name": "package-id", "value": package.id},
                    {"name": "baseline", "value": baseline},
                ],
            },
            "import-profile": {
                "href": f"#nist-sp-800-53-rev5-{baseline}",
            },
            "system-characteristics": {
                "system-name": package.name,
                "description": package.description or
                               "QUILL-managed RMF package.",
                "system-ids": [{"id": package.id, "identifier-type": "https://idiaz-io/QUILL"}],
                # No system-information block — that would imply we know
                # what the system processes. We don't.
            },
            "system-implementation": {
                "components": [
                    {
                        "uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"quill:component:{aid}")),
                        "type": "documentation",
                        "title": fname,
                        "description": "Artifact analyzed by QUILL.",
                        "status": {"state": "operational"},
                        "props": [{"name": "artifact-id", "value": aid}],
                    }
                    for aid, fname in artifact_filenames.items()
                ],
            },
            # control-implementation is intentionally absent — QUILL is a
            # READER of SSPs, not an authoring tool.
        }
    }

    # ---- POA&M --------------------------------------------------------- #
    observations = []
    poam_items = []
    for f in exportable:
        obs_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"quill:obs:{f.id}"))
        item_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"quill:poam-item:{f.id}"))
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
                {"name": "attestation-status", "value": f.status.value},
            ],
            "relevant-evidence": [
                {"href": f"#{s.artifact_id}/{s.locator}",
                 "description": (s.quoted_text or "")[:280]}
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
    poam = {
        "plan-of-action-and-milestones": {
            "uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"quill:poam:run:{run_id}")),
            "metadata": {
                "title": f"{package.name} — POA&M",
                "last-modified": _now(),
                "version": "0.1",
                "oscal-version": OSCAL_VERSION,
                "props": [{"name": "produced-by", "value": "quill"},
                          {"name": "run-id", "value": run_id},
                          {"name": "package-id", "value": package.id}],
            },
            "import-ssp": {"href": f"#{ssp_uuid}"},
            "observations": observations,
            "poam-items": poam_items,
        }
    }

    # ---- Assessment Results ------------------------------------------- #
    ar_findings = []
    for f in exportable + rejected:
        ar_findings.append({
            "uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"quill:finding:{f.id}")),
            "title": f"{f.control_id} · {f.type.value}",
            "description": f.rationale or f.recommendation,
            "target": {
                "type": "objective-id",
                "target-id": f.objective_id or f.control_id,
                "status": {
                    "state": "satisfied" if f.status == FindingStatus.rejected
                             else "not-satisfied",
                    "reason": f.status.value,
                },
            },
            "props": [
                {"name": "control-id", "value": f.control_id},
                {"name": "severity", "value": f.severity.value},
                {"name": "attestation-status", "value": f.status.value},
                {"name": "tier", "value": f.tier.value},
            ],
        })
    ar = {
        "assessment-results": {
            "uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"quill:ar:run:{run_id}")),
            "metadata": {
                "title": f"{package.name} — Assessment Results",
                "last-modified": _now(),
                "version": "0.1",
                "oscal-version": OSCAL_VERSION,
                "props": [{"name": "produced-by", "value": "quill"},
                          {"name": "run-id", "value": run_id}],
            },
            "import-ap": {"href": f"#{ssp_uuid}"},
            "results": [{
                "uuid": str(uuid.uuid5(uuid.NAMESPACE_URL,
                                       f"quill:result:run:{run_id}")),
                "title": f"QUILL run {run_id}",
                "description": "Pre-adjudication assessment by QUILL — "
                               "human-attested findings only.",
                "start": _now(),
                "findings": ar_findings,
            }],
        }
    }

    return {
        "quill-oscal-package": {
            "version": 1,
            "package-id": package.id,
            "run-id": run_id,
            "generated-at": _now(),
            "documents": [ssp, poam, ar],
        }
    }


def render_oscal_package_json(**kw) -> str:
    """Convenience: pretty-printed JSON of the OSCAL bundle."""
    return json.dumps(render_oscal_package(**kw), indent=2, sort_keys=True)
