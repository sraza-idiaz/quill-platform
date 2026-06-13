"""Phase II FR-XA extension — visual grounding builder.

Builds the Visual Grounding payload: a flat, JSON-ready structure that ties
every finding to the specific document spans that support or contradict it,
together with the relevant regulatory context (800-53A objectives).

The builder is **pure** (no I/O, no side-effects, async-free). The route in
``backend/routes/api.py`` is responsible for data assembly; this module is
responsible only for the transformation.

Design sketch
─────────────
* artifacts   — pass-through list sorted by filename ASC.
* groundings  — one entry per finding that has at least one non-catalog span.
                Catalog-only findings (e.g. missing-control coverage findings
                whose only span is ``catalog:...``) are excluded — they have
                no document location to render.
* primary     — first non-catalog span on the finding.
* conflicts_with — every OTHER non-catalog span, deduped by (artifact_id,
                   locator), ordered by filename then locator.
* regulatory  — 800-53A objective summary derived from the catalog, capped at
                280 chars with trailing ellipsis if truncated.
* Output ordering: severity priority → type priority → control_id ASC →
                   finding_id ASC (fully deterministic).
"""

from __future__ import annotations

import logging
from typing import Optional

from backend.models.domain import Artifact, Finding, FindingType, Severity
from backend.services.catalog_loader import Catalog

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Ordering tables
# --------------------------------------------------------------------------- #

_SEV_PRIORITY: dict[str, int] = {
    Severity.critical.value: 0,
    Severity.high.value:     1,
    Severity.medium.value:   2,
    Severity.low.value:      3,
}

_TYPE_PRIORITY: dict[str, int] = {
    FindingType.inconsistent.value:                      0,
    FindingType.weak_narrative.value:                    1,
    FindingType.narrative_present_evidence_unclear.value: 2,
    FindingType.insufficient_evidence.value:             3,
    FindingType.missing.value:                           4,
}

_OBJ_SUMMARY_MAX = 280
_OBJ_SUMMARY_JOIN = " · "
_OBJ_SUMMARY_MAX_COUNT = 3


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def build_grounding(
    *,
    artifacts: list[Artifact],
    artifact_texts: dict[str, str],
    findings: list[Finding],
    catalog: Catalog,
    run_id: Optional[str],
) -> dict:
    """Build the JSON-ready Visual Grounding payload for a package run.

    Parameters
    ----------
    artifacts:
        All member artifacts of the package (order does not matter; output is
        sorted by filename ASC).
    artifact_texts:
        Mapping from artifact_id → full normalized text. Sourced by the route
        via ``get_artifact_text_async`` (Postgres) with sync fallback.
    findings:
        All findings from the latest analysis run of this package.
    catalog:
        The loaded NIST 800-53 catalog, used to resolve objective summaries
        and control titles.
    run_id:
        The run id for the latest run. May be None if no runs exist yet.

    Returns
    -------
    dict
        JSON-ready dict conforming to the Visual Grounding schema. The
        ``package_id`` key is always ``None`` in the pure builder; the route
        fills it after calling this function.
    """
    # Build artifact lookup (id → Artifact) for O(1) filename resolution.
    artifact_map: dict[str, Artifact] = {a.id: a for a in artifacts}

    # Artifacts pass-through, sorted by filename for determinism.
    sorted_artifacts = sorted(artifacts, key=lambda a: a.filename)

    artifact_out = [
        {
            "id": a.id,
            "filename": a.filename,
            "type": a.type.value,
            "text": artifact_texts.get(a.id, ""),
        }
        for a in sorted_artifacts
    ]

    groundings: list[dict] = []
    for finding in findings:
        entry = _grounding_for(finding, artifact_map, catalog)
        if entry is not None:
            groundings.append(entry)

    # Sort groundings: severity → type → control_id → finding_id.
    groundings.sort(key=lambda g: (
        _SEV_PRIORITY.get(g["severity"], 99),
        _TYPE_PRIORITY.get(g["type"], 99),
        g["control_id"],
        g["finding_id"],
    ))

    return {
        "package_id": None,
        "run_id": run_id,
        "artifacts": artifact_out,
        "groundings": groundings,
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _non_catalog_spans(finding: Finding) -> list:
    """Return the ordered list of EvidenceSpan objects whose artifact_id does
    NOT start with ``catalog:``. Ordering is first-seen (preserving the span
    list order from the finding)."""
    return [s for s in finding.evidence_spans if not s.artifact_id.startswith("catalog:")]


def _span_detail(span, artifact_map: dict[str, Artifact]) -> dict:
    """Convert a single EvidenceSpan to the primary/conflict detail sub-object."""
    art = artifact_map.get(span.artifact_id)
    return {
        "artifact_id": span.artifact_id,
        "filename": art.filename if art else None,
        "locator": span.locator,
        "quote": span.quoted_text,
        "char_start": span.char_start,
        "char_end": span.char_end,
    }


def _objective_summary(control_id: str, catalog: Catalog) -> tuple[str, str]:
    """Return (control_title, objective_summary) for the given control_id.

    objective_summary logic (per spec):
      1. Take the first 1-3 objectives' text fields, join with ' · ',
         cap at 280 chars with trailing '...' if truncated.
      2. If no objectives → fall back to control title.
      3. If control not in catalog → ('', '') with a warning log.

    Returns
    -------
    tuple[str, str]
        (control_title, objective_summary)
    """
    ctrl = catalog.get_control(control_id)
    if ctrl is None:
        logger.warning("visual_grounding: control '%s' not found in catalog", control_id)
        return ("", "")

    control_title = ctrl.title
    objectives = catalog.objectives_for(control_id)

    if not objectives:
        return (control_title, control_title)

    parts: list[str] = []
    total = 0
    for obj in objectives[:_OBJ_SUMMARY_MAX_COUNT]:
        parts.append(obj.text)
        total += len(obj.text)

    raw = _OBJ_SUMMARY_JOIN.join(parts)
    if len(raw) > _OBJ_SUMMARY_MAX:
        summary = raw[:_OBJ_SUMMARY_MAX - 3] + "..."
    else:
        summary = raw

    return (control_title, summary)


def _grounding_for(
    finding: Finding,
    artifact_map: dict[str, Artifact],
    catalog: Catalog,
) -> Optional[dict]:
    """Build the grounding entry dict for *finding*, or return None if the
    finding has no non-catalog evidence spans (catalog-only findings are
    excluded — they have no document location to render).
    """
    non_cat = _non_catalog_spans(finding)
    if not non_cat:
        return None

    # Primary span: first non-catalog span.
    primary_span = non_cat[0]
    primary = _span_detail(primary_span, artifact_map)

    # Conflicts: every OTHER non-catalog span, deduped by (artifact_id, locator).
    seen_keys: set[tuple[str, str]] = {(primary_span.artifact_id, primary_span.locator)}
    conflict_raw: list[dict] = []
    for span in non_cat[1:]:
        key = (span.artifact_id, span.locator)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        conflict_raw.append(_span_detail(span, artifact_map))

    # Sort conflicts by filename, then locator. Unresolved artifact ids (not in
    # artifact_map) sort to the front under an empty-string filename.
    conflict_raw.sort(key=lambda d: (d["filename"] or "", d["locator"]))

    control_title, obj_summary = _objective_summary(finding.control_id, catalog)

    return {
        "finding_id": finding.id,
        "control_id": finding.control_id,
        "control_title": control_title,
        "type": finding.type.value,
        "severity": finding.severity.value,
        "tier": finding.tier.value,
        "status": finding.status.value,
        "rationale": finding.rationale,
        "recommendation": finding.recommendation,
        "primary": primary,
        "conflicts_with": conflict_raw,
        "regulatory": {
            "control_id": finding.control_id,
            "title": control_title,
            "objective_summary": obj_summary,
        },
    }
