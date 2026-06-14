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

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.services.analysis.synonyms import Synonyms

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

# Sentence boundary — split on ., !, ? followed by whitespace.
_SENTENCE_END_RE = re.compile(r"[.!?](?:\s|$)")


def _conflict_sentence(text: str) -> tuple[str, int, int]:
    """Narrow a cited segment to the single sentence carrying the conflicting
    cadence token, so the citation (and the UI highlight) points at the
    actual contradiction — not a neighbouring sentence in the same paragraph.

    Returns (sentence_text, char_start_offset, char_end_offset) relative to
    `text`. Falls back to the first 300 chars when no frequency token is found
    (e.g. a synonym-table-only match), preserving prior behaviour.
    """
    m = FREQ_RE.search(text)
    if not m:
        return text[:300], 0, min(len(text), 300)
    # Sentence start: just after the previous sentence terminator.
    start = 0
    for sm in _SENTENCE_END_RE.finditer(text, 0, m.start()):
        start = sm.end()
    # Sentence end: through the next terminator (inclusive of the '.').
    em = _SENTENCE_END_RE.search(text, m.end())
    end = em.start() + 1 if em else len(text)
    return text[start:end].strip(), start, end

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
    run_id: str, segments: list[NormalizedSegment], catalog: Catalog, rubric: Rubric,
    baseline: Optional[str] = None,
) -> list[Finding]:
    """FR-T0-01: baseline controls with no implementation statement.

    `baseline` overrides catalog.baseline at run-time. Phase II uses this so
    each program can have its own baseline (FR-MT-01 / FR-CAT-05).
    """
    active = baseline or catalog.baseline
    present = set(_segments_by_control(segments).keys())
    searched = sorted({s.artifact_id for s in segments})
    findings: list[Finding] = []
    for control in catalog.baseline_controls(active):
        if control.control_id not in present:
            ref_span = EvidenceSpan(
                artifact_id=f"catalog:{active}",
                locator=control.control_id,
                quoted_text=f"{control.control_id} {control.title} (required by {active} baseline)",
            )
            findings.append(
                _make_finding(
                    run_id,
                    control.control_id,
                    FindingType.missing,
                    recommendation=f"Add an implementation statement for {control.control_id} ({control.title}).",
                    rationale=(
                        f"{control.control_id} is required by the {active} baseline but no "
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
    """FR-T0-02: required-field absence + unfilled ODP placeholders.

    Phase II FR-XA-02 — inheritance-aware: when a control narrative is an
    inheritance claim (e.g. "AC-2 is inherited from Azure AD's SOC 2 Type II
    audit"), we don't expect the team to provide local implementation
    details. Instead:
      * Properly-attributed inheritance (provider + attestation) → skip the
        normal required-fields check (no false positive on the implementation).
      * Incomplete inheritance (missing provider OR attestation) → emit a
        focused finding telling the team exactly what attribution to add.
    """
    # Lazy import to keep the module's import graph tight in tests.
    from backend.services.analysis.inheritance import detect_inheritance

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

        # ── Phase II FR-XA-02: inheritance pattern detection ─────────────── #
        inheritance = detect_inheritance(combined)
        if inheritance is not None:
            if inheritance.is_complete:
                # Properly attributed — the team's responsibility is the
                # attribution itself, not the local implementation. Skip the
                # implementation checks; Tier 2 can still examine wording.
                continue
            # Incomplete: helpful, focused finding citing exactly what's missing.
            missing = inheritance.missing_elements
            attribution = []
            if inheritance.provider:    attribution.append(f"provider: {inheritance.provider}")
            if inheritance.attestations: attribution.append(f"attestation(s): {', '.join(inheritance.attestations)}")
            rationale_attrib = " · ".join(attribution) if attribution else "no attribution parsed"
            findings.append(
                _make_finding(
                    run_id, control_id, FindingType.insufficient_evidence,
                    recommendation=(
                        f"{control_id} is claimed as inherited but the attribution is incomplete. "
                        f"Add: {', '.join(missing)}."
                    ),
                    rationale=(
                        f"{control_id} narrative invokes inheritance ('{inheritance.trigger}') "
                        f"but {rationale_attrib}. Inherited controls require both a provider "
                        f"and a recognized attestation (SOC 2 / FedRAMP ATO / Type II / ISO 27001 / etc.)."
                    ),
                    spans=[span], catalog=catalog, rubric=rubric,
                    missing_elements=missing,
                )
            )
            # Still run the ODP-placeholder check on inherited claims — the
            # attribution text itself can have unfilled placeholders.
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
            continue   # don't run the "required local implementation fields" check on inherited controls

        # ── Standard local-implementation checks ─────────────────────────── #
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
    run_id: str, segments: list[NormalizedSegment], catalog: Catalog, rubric: Rubric,
    synonyms: Optional["Synonyms"] = None,
) -> list[Finding]:
    """FR-T0-03 + FR-XA-01/05/06 — same control, conflicting normalized values
    across artifacts.

    Two channels feed the comparison:
      1. Raw frequency-token regex (`FREQ_RE`) — catches phrases the synonym
         table doesn't recognize.
      2. The synonym table's `find_canonical_phrases` — normalizes equivalents
         like "every 90 days" ↔ "quarterly" and "ISSO" ↔ "Information System
         Security Officer", so trivial surface differences don't trigger
         false-positive contradictions.

    Findings are emitted only when at least one artifact disagrees with another
    on a *normalized* value set.
    """
    findings: list[Finding] = []
    # control_id -> { artifact_id -> set(canonical tokens) }
    by_control: dict[str, dict[str, set[str]]] = {}
    span_by: dict[tuple[str, str], EvidenceSpan] = {}
    for s in segments:
        if not s.control_hint:
            continue
        tokens: set[str] = set()
        # Channel 1: legacy frequency regex (kept so unknown phrases still surface).
        for m in FREQ_RE.findall(s.text):
            tok = (m if isinstance(m, str) else m[0]).lower().replace("yearly", "annually")
            # Canonicalize via the synonym table when possible.
            if synonyms is not None:
                tok = synonyms.canonical(tok)
            tokens.add(tok)
        # Channel 2: synonym table catches phrases the regex doesn't (e.g. "every 90 days").
        if synonyms is not None:
            tokens.update(synonyms.find_canonical_phrases(s.text))
        if tokens:
            by_control.setdefault(s.control_hint, {}).setdefault(s.artifact_id, set()).update(tokens)
            # Cite the exact sentence carrying the conflicting cadence, not the
            # whole paragraph — keeps the citation (and UI highlight) on the
            # contradiction itself (FR rule #3: exact quoted text).
            quote, off_s, off_e = _conflict_sentence(s.text)
            span_by.setdefault(
                (s.control_hint, s.artifact_id),
                EvidenceSpan(artifact_id=s.artifact_id, locator=s.locator,
                             quoted_text=quote[:300],
                             char_start=s.char_start + off_s,
                             char_end=s.char_start + off_e),
            )

    for control_id, per_artifact in by_control.items():
        distinct = {frozenset(v) for v in per_artifact.values()}
        if len(per_artifact) >= 2 and len(distinct) > 1:
            spans = [span_by[(control_id, aid)] for aid in sorted(per_artifact)]
            detail = "; ".join(f"{aid}: {sorted(v)}" for aid, v in sorted(per_artifact.items()))
            findings.append(
                _make_finding(
                    run_id, control_id, FindingType.inconsistent,
                    recommendation=f"Reconcile conflicting values for {control_id} across artifacts.",
                    rationale=(
                        f"{control_id} states conflicting values across artifacts after "
                        f"synonym normalization ({detail})."
                    ),
                    spans=spans, catalog=catalog, rubric=rubric,
                )
            )
    return findings


def run_tier0(
    run_id: str, segments: list[NormalizedSegment], catalog: Catalog, rubric: Rubric,
    baseline: Optional[str] = None,
    synonyms: Optional["Synonyms"] = None,
) -> list[Finding]:
    """Run all Tier 0 checks. Deterministic order (FR-T0-05).

    `baseline`  overrides catalog.baseline so per-program baselines work
                (Phase II FR-MT-01 / FR-CAT-05). When omitted, the catalog
                default applies.
    `synonyms`  enables FR-XA-01/05/06 — equivalent expressions normalize to
                a single canonical form before cross-artifact comparison.
                When omitted, only the legacy frequency regex is used.
    """
    findings: list[Finding] = []
    findings += check_coverage(run_id, segments, catalog, rubric, baseline=baseline)
    findings += check_required_fields(run_id, segments, catalog, rubric)
    findings += check_cross_artifact_consistency(
        run_id, segments, catalog, rubric, synonyms=synonyms,
    )
    findings.sort(key=lambda f: (f.control_id, f.type.value, f.id))
    return findings
