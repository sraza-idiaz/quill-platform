"""Phase II FR-XA-03/FR-CONT extension — package map.

Builds the visual Package Map: a graph where every node is an artifact and
every edge describes how two artifacts relate — either through a cross-artifact
inconsistency finding (contradiction), a finding that was present in the
previous run but is now gone (resolved), or by sharing one or more control
coverage areas (shared_controls).

The builder is **pure** (no I/O, no side-effects). The route in
`backend/routes/api.py` is responsible for data assembly; this module is
responsible only for the transformation.

Design sketch
─────────────
* Nodes  — one per artifact in the package, with per-artifact finding counts
           and the sorted list of controls that artifact's segments mention.
* Contradiction edges — one per cross-artifact inconsistent finding from the
           current run. Source/target are sorted for determinism so the same
           pair always appears in the same direction.
* Resolved edges — one per cross-artifact inconsistent finding that was in
           the previous run but has disappeared (resolved or stale). Built
           from the OLD finding's spans so the UI can show what was fixed.
* Shared-control edges — one per unordered artifact pair whose control sets
           intersect. Always emitted; the frontend layers them under
           contradiction edges visually.

Edge ids are stable sha-256 hashes so the same conceptual edge always gets
the same id across independent calls with identical input.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from backend.models.domain import Artifact, Finding, FindingType, NormalizedSegment, Severity
from backend.services.continuous import diff_findings


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def build_package_map(
    *,
    artifacts: list[Artifact],
    segments_by_artifact: dict[str, list[NormalizedSegment]],
    current_findings: list[Finding],
    prev_findings: Optional[list[Finding]],
    run_id: Optional[str],
    prev_run_id: Optional[str],
    package_id: Optional[str] = None,
) -> dict:
    """Build the JSON-ready Package Map for a package run.

    Parameters
    ----------
    artifacts:
        All member artifacts of the package (order does not matter; nodes are
        sorted by filename in the output).
    segments_by_artifact:
        Mapping from artifact_id → list of NormalizedSegment for that artifact.
        Used to derive per-node control coverage. May be sparse; missing
        artifact_ids are treated as having no segments.
    current_findings:
        All findings from the latest analysis run of this package.
    prev_findings:
        All findings from the immediately prior run, or None if no prior run
        exists. Required only for resolved-edge derivation.
    run_id:
        The run id for the current (latest) run. May be None if no runs exist.
    prev_run_id:
        The run id for the prior run. May be None.
    package_id:
        Optional; filled by the route. Appears as-is in the output.

    Returns
    -------
    dict
        JSON-ready dict conforming to the Package Map schema (see module
        docstring for the full shape).
    """
    artifact_map: dict[str, Artifact] = {a.id: a for a in artifacts}

    # --- 1. Per-artifact control sets ----------------------------------------
    # Controls are derived from the NormalizedSegments (deterministic Tier-0).
    controls_by_artifact: dict[str, list[str]] = {}
    for a in artifacts:
        segs = segments_by_artifact.get(a.id, [])
        seen: set[str] = set()
        ctrls: list[str] = []
        for s in segs:
            if s.control_hint and s.control_hint not in seen:
                seen.add(s.control_hint)
                ctrls.append(s.control_hint)
        controls_by_artifact[a.id] = sorted(ctrls)

    # --- 2. Finding attribution + per-artifact severity counts ---------------
    # A finding is attributed to the first non-catalog evidence span's artifact.
    # If ALL spans are catalog spans, the finding goes to package_level_findings.
    zero_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    artifact_findings: dict[str, dict[str, int]] = {
        a.id: dict(zero_counts) for a in artifacts
    }
    pkg_level_counts: dict[str, int] = dict(zero_counts)

    for f in current_findings:
        attributed_art: Optional[str] = None
        for span in f.evidence_spans:
            if not span.artifact_id.startswith("catalog:"):
                attributed_art = span.artifact_id
                break
        sev = f.severity.value
        if attributed_art and attributed_art in artifact_findings:
            artifact_findings[attributed_art][sev] += 1
        else:
            # All spans are catalog refs, or the artifact isn't in this package
            pkg_level_counts[sev] += 1

    # --- 3. Nodes (sorted by filename for determinism) -----------------------
    nodes: list[dict] = []
    for a in sorted(artifacts, key=lambda x: x.filename):
        nodes.append({
            "artifact_id": a.id,
            "filename": a.filename,
            "type": a.type.value,
            "status": a.status.value,
            "findings": artifact_findings.get(a.id, dict(zero_counts)),
            "controls": controls_by_artifact.get(a.id, []),
        })

    # --- 4. Contradiction edges (current cross-artifact inconsistencies) -----
    contradiction_edges: list[dict] = []
    for f in current_findings:
        edge = _contradiction_edge_for(f, artifact_map, state="active")
        if edge:
            contradiction_edges.append(edge)

    # --- 5. Resolved edges (was cross-artifact inconsistent, now gone) -------
    resolved_edges: list[dict] = []
    if prev_findings is not None:
        d = diff_findings(prev_findings, current_findings)
        for f in (*d.resolved, *d.stale):
            edge = _contradiction_edge_for(f, artifact_map, state="resolved")
            if edge:
                edge["kind"] = "resolved"
                resolved_edges.append(edge)

    # --- 6. Shared-control edges (every pair with non-empty intersection) ----
    shared_edges: list[dict] = []
    artifact_ids = [a.id for a in sorted(artifacts, key=lambda x: x.filename)]
    for i, aid1 in enumerate(artifact_ids):
        for aid2 in artifact_ids[i + 1:]:
            c1 = set(controls_by_artifact.get(aid1, []))
            c2 = set(controls_by_artifact.get(aid2, []))
            common = sorted(c1 & c2)
            if not common:
                continue
            src, tgt = sorted([aid1, aid2])
            eid = _edge_id("shared_controls", src, tgt, "|".join(common), "")
            shared_edges.append({
                "id": eid,
                "source": src,
                "target": tgt,
                "kind": "shared_controls",
                "controls": common,
                "count": len(common),
            })

    # Deterministic ordering: contradiction → resolved → shared_controls,
    # then by id within each group.
    contradiction_edges.sort(key=lambda e: e["id"])
    resolved_edges.sort(key=lambda e: e["id"])
    shared_edges.sort(key=lambda e: e["id"])
    all_edges = contradiction_edges + resolved_edges + shared_edges

    return {
        "package_id": package_id,
        "run_id": run_id,
        "prev_run_id": prev_run_id,
        "nodes": nodes,
        "package_level_findings": pkg_level_counts,
        "edges": all_edges,
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _non_catalog_artifact_ids(finding: Finding) -> list[str]:
    """Return the ordered list of distinct non-catalog artifact ids across
    the finding's evidence spans (first-seen order)."""
    seen: set[str] = set()
    out: list[str] = []
    for span in finding.evidence_spans:
        if not span.artifact_id.startswith("catalog:") and span.artifact_id not in seen:
            seen.add(span.artifact_id)
            out.append(span.artifact_id)
    return out


def _edge_id(kind: str, source: str, target: str, control_part: str, finding_part: str) -> str:
    """Stable sha-256 derived edge id.

    The id is a function of the *conceptual identity* of the edge, not of the
    run. Two independent calls with the same kind/source/target/control/finding
    will always produce the same id. That lets the frontend do stable keying.
    """
    raw = f"{kind}|{source}|{target}|{control_part}|{finding_part}"
    return "edge-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _span_detail(finding: Finding, artifact_id: str) -> dict:
    """Return the detail sub-object for one side of a contradiction edge.

    Picks the first evidence span that belongs to `artifact_id`.
    """
    for span in finding.evidence_spans:
        if span.artifact_id == artifact_id:
            art_obj = None  # resolved later via artifact_map in the caller
            return {
                "artifact_id": span.artifact_id,
                "filename": None,  # filled by caller
                "locator": span.locator,
                "quote": span.quoted_text,
            }
    # No span found — return a placeholder so the edge is still emitted.
    return {
        "artifact_id": artifact_id,
        "filename": None,
        "locator": "",
        "quote": "",
    }


def _contradiction_edge_for(
    finding: Finding,
    artifact_map: dict[str, Artifact],
    *,
    state: str,
) -> Optional[dict]:
    """Build a contradiction / resolved edge dict for *finding*, or return
    None if the finding is not a cross-artifact inconsistency.

    A finding qualifies when:
      - type == FindingType.inconsistent
      - the set of distinct non-catalog artifact ids in its spans has >= 2
        members that are actually in the package (present in artifact_map).

    Source and target are the first two sorted distinct artifact ids so the
    edge direction is deterministic and canonical.
    """
    if finding.type != FindingType.inconsistent:
        return None

    non_cat = _non_catalog_artifact_ids(finding)
    # Keep only artifact ids that belong to this package.
    in_pkg = [aid for aid in non_cat if aid in artifact_map]
    # Deduplicate while preserving first-seen order.
    seen: set[str] = set()
    distinct: list[str] = []
    for aid in in_pkg:
        if aid not in seen:
            seen.add(aid)
            distinct.append(aid)

    if len(distinct) < 2:
        return None

    # Sort for determinism, then use the first two.
    source, target = sorted(distinct[:2])

    # Detail sub-objects — quotes come from the finding's own spans.
    left_detail = _span_detail(finding, source)
    right_detail = _span_detail(finding, target)

    # Fill filenames from the artifact map.
    if source in artifact_map:
        left_detail["filename"] = artifact_map[source].filename
    if target in artifact_map:
        right_detail["filename"] = artifact_map[target].filename

    summary = (finding.recommendation or finding.rationale)[:200]
    eid = _edge_id("contradiction", source, target, finding.control_id, finding.id)

    return {
        "id": eid,
        "source": source,
        "target": target,
        "kind": "contradiction" if state == "active" else "resolved",
        "control_id": finding.control_id,
        "severity": finding.severity.value,
        "state": state,
        "finding_id": finding.id,
        "detail": {
            "summary": summary,
            "left": left_detail,
            "right": right_detail,
        },
    }
