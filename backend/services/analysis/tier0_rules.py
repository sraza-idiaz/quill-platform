"""Tier 0 — deterministic rule/KB engine (FR-T0-01..05). NO LLM.

Checks:
  1. Control coverage vs baseline      (FR-T0-01)  -> `missing`
  2. Required-field / unfilled-ODP gaps (FR-T0-02) -> `insufficient_evidence`
  3. Cross-artifact consistency        (FR-T0-03)  -> `inconsistent`
  4. OSCAL structural validation       (FR-T0-04)  -> `insufficient_evidence` (schema)

Fully deterministic & reproducible (FR-T0-05): identical input -> identical
findings, in a stable order, with stable ids.

Traceability note: artifact-derived findings carry a verbatim artifact span.
A `missing` finding has no artifact text to cite, so its evidence span is a
*catalog reference* (artifact_id='catalog:<baseline>'), recording the requirement
and the set of artifacts searched. The citation validator treats catalog refs
distinctly from artifact spans.
"""

from __future__ import annotations

import hashlib
import re

from backend.models.domain import (
    EvidenceSpan,
    Finding,
    FindingType,
    NormalizedSegment,
    Tier,
)
from backend.services.catalog_loader import Catalog, Rubric
from backend.services.analysis.severity import compute_severity

# Recurrence/frequency tokens for cross-artifact consistency.
FREQ_RE = re.compile(
    r"\b(annually|yearly|quarterly|monthly|weekly|daily|biannually|semi-?annually"
    r"|every\s+\d+\s+(?:days?|weeks?|months?|years?))\b",
    re.IGNORECASE,
)

# Coarse keyword expansion for required-field presence (deterministic net;
# Tier 2 does the real judgment). Field name -> accepted keyword fragments.
_FIELD_SYNONYMS: dict[str, list[str]] = {
    "account_types": ["account type", "types of account"],
    "responsible_role": ["role", "responsible", "administrator", "isso", "issm"],
    "review_frequency": ["review", "annually", "quarterly", "monthly", "frequency", "periodic"],
    "enforcement_mechanism": ["enforce", "mechanism", "automated", "tool", "policy"],
    "event_types": ["event type", "log type", "auditable event"],
    "retention_period": ["retention", "retain", "days", "months", "years"],
    "review_mechanism": ["review", "alert", "monitor"],
    "authenticator_types": ["authenticator", "credential", "token", "certificate", "password"],
    "mfa_scope": ["mfa", "multi-factor", "multifactor", "two-factor"],
    "baseline_reference": ["baseline", "configuration baseline", "golden image"],
    "change_control": ["change control", "change management", "ccb", "change request"],
    "boundary_components": ["firewall", "gateway", "boundary", "dmz", "proxy"],
    "monitoring_mechanism": ["monitor", "ids", "ips", "siem", "sensor"],
    "monitoring_objectives": ["monitor", "detect", "objective"],
    "alerting_mechanism": ["alert", "notify", "siem", "notification"],
}


def _field_keywords(field: str) -> list[str]:
    kws = list(_FIELD_SYNONYMS.get(field, []))
    kws.append(field.replace("_", " "))
    return [k.lower() for k in kws]


def _stable_id(*parts: str) -> str:
    return "f0-" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _segments_by_control(segments: list[NormalizedSegment]) -> dict[str, list[NormalizedSegment]]:
    out: dict[str, list[NormalizedSegment]] = {}
    for s in segments:
        if s.control_hint:
            out.setdefault(s.control_hint, []).append(s)
    return out


def _make_finding(
    run_id: str,
    control_id: str,
    ftype: FindingType,
    recommendation: str,
    rationale: str,
    spans: list[EvidenceSpan],
    catalog: Catalog,
    rubric: Rubric,
    missing_elements: list[str] | None = None,
) -> Finding:
    severity, factors = compute_severity(control_id, ftype, catalog, rubric)
    return Finding(
        id=_stable_id(control_id, ftype.value, recommendation),
        run_id=run_id,
        control_id=control_id,
        type=ftype,
        severity=severity,
        confidence=1.0,  # deterministic checks are certain
        recommendation=recommendation,
        rationale=rationale + f" [severity factors: {', '.join(factors)}]",
        missing_elements=missing_elements or [],
        evidence_spans=spans,
        tier=Tier.t0,
    )


def check_coverage(
    run_id: str, segments: list[NormalizedSegment], catalog: Catalog, rubric: Rubric
) -> list[Finding]:
    """FR-T0-01: baseline controls with no implementation statement."""
    present = set(_segments_by_control(segments).keys())
    searched = sorted({s.artifact_id for s in segments})
    findings: list[Finding] = []
    for control in catalog.baseline_controls():
        if control.control_id not in present:
            ref_span = EvidenceSpan(
                artifact_id=f"catalog:{catalog.baseline}",
                locator=control.control_id,
                quoted_text=f"{control.control_id} {control.title} (required by {catalog.baseline} baseline)",
            )
            findings.append(
                _make_finding(
                    run_id,
                    control.control_id,
                    FindingType.missing,
                    recommendation=f"Add an implementation statement for {control.control_id} ({control.title}).",
                    rationale=(
                        f"{control.control_id} is required by the {catalog.baseline} baseline but no "
                        f"implementation statement was found. Artifacts searched: {searched}."
                    ),
                    spans=[ref_span],
                    catalog=catalog,
                    rubric=rubric,
                )
            )
    return findings


def check_required_fields(
    run_id: str, segments: list[NormalizedSegment], catalog: Catalog, rubric: Rubric
) -> list[Finding]:
    """FR-T0-02: required-field absence + unfilled ODP placeholders."""
    by_control = _segments_by_control(segments)
    findings: list[Finding] = []
    odp_patterns = [p.lower() for p in rubric.odp_unfilled_patterns]

    for control_id, segs in by_control.items():
        if catalog.get_control(control_id) is None:
            continue
        combined = "\n".join(s.text for s in segs)
        combined_l = combined.lower()

        def _span_for(seg: NormalizedSegment) -> EvidenceSpan:
            return EvidenceSpan(
                artifact_id=seg.artifact_id, locator=seg.locator,
                quoted_text=seg.text[:300], char_start=seg.char_start, char_end=seg.char_end,
            )

        # Prefer the most substantive narrative segment over a bare heading.
        narrative = max(segs, key=lambda s: len(s.text))
        span = _span_for(narrative)

        # (a) unfilled ODP placeholders (C3, deterministic) — cite the segment that holds it.
        hit = next((p for p in odp_patterns if p in combined_l), None)
        if hit:
            holder = next((s for s in segs if hit in s.text.lower()), narrative)
            findings.append(
                _make_finding(
                    run_id, control_id, FindingType.insufficient_evidence,
                    recommendation=f"Fill the organization-defined parameter for {control_id} (found placeholder '{hit}').",
                    rationale=f"{control_id} contains an unfilled organization-defined parameter ('{hit}').",
                    spans=[_span_for(holder)], catalog=catalog, rubric=rubric,
                    missing_elements=["organization_defined_parameter"],
                )
            )

        # (b) required-field absence
        missing = [
            f for f in catalog.required_fields(control_id)
            if not any(kw in combined_l for kw in _field_keywords(f))
        ]
        if missing:
            findings.append(
                _make_finding(
                    run_id, control_id, FindingType.insufficient_evidence,
                    recommendation=f"Address the required elements for {control_id}: {', '.join(missing)}.",
                    rationale=f"{control_id} narrative does not address required field(s): {', '.join(missing)}.",
                    spans=[span], catalog=catalog, rubric=rubric, missing_elements=missing,
                )
            )
    return findings


def check_cross_artifact_consistency(
    run_id: str, segments: list[NormalizedSegment], catalog: Catalog, rubric: Rubric
) -> list[Finding]:
    """FR-T0-03: same control, conflicting frequency values across artifacts."""
    findings: list[Finding] = []
    # control_id -> { artifact_id -> set(freq tokens) }
    by_control: dict[str, dict[str, set[str]]] = {}
    span_by: dict[tuple[str, str], EvidenceSpan] = {}
    for s in segments:
        if not s.control_hint:
            continue
        freqs = {m.lower().replace("yearly", "annually") for m in FREQ_RE.findall(s.text)}
        # findall returns the captured group; normalize tuples->str handled by regex single group
        freqs = {f if isinstance(f, str) else f[0] for f in freqs}
        if freqs:
            by_control.setdefault(s.control_hint, {}).setdefault(s.artifact_id, set()).update(freqs)
            span_by.setdefault(
                (s.control_hint, s.artifact_id),
                EvidenceSpan(artifact_id=s.artifact_id, locator=s.locator,
                             quoted_text=s.text[:300], char_start=s.char_start, char_end=s.char_end),
            )

    for control_id, per_artifact in by_control.items():
        distinct = {frozenset(v) for v in per_artifact.values()}
        if len(per_artifact) >= 2 and len(distinct) > 1:
            spans = [span_by[(control_id, aid)] for aid in sorted(per_artifact)]
            detail = "; ".join(f"{aid}: {sorted(v)}" for aid, v in sorted(per_artifact.items()))
            findings.append(
                _make_finding(
                    run_id, control_id, FindingType.inconsistent,
                    recommendation=f"Reconcile conflicting frequency values for {control_id} across artifacts.",
                    rationale=f"{control_id} states conflicting frequencies across artifacts ({detail}).",
                    spans=spans, catalog=catalog, rubric=rubric,
                )
            )
    return findings


def run_tier0(
    run_id: str, segments: list[NormalizedSegment], catalog: Catalog, rubric: Rubric
) -> list[Finding]:
    """Run all Tier 0 checks. Deterministic order (FR-T0-05)."""
    findings: list[Finding] = []
    findings += check_coverage(run_id, segments, catalog, rubric)
    findings += check_required_fields(run_id, segments, catalog, rubric)
    findings += check_cross_artifact_consistency(run_id, segments, catalog, rubric)
    findings.sort(key=lambda f: (f.control_id, f.type.value, f.id))
    return findings
