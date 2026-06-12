"""Unit tests for backend/services/analysis/package_map.py.

Phase II FR-XA-03/FR-CONT extension — package map builder.

Tests are pure (no I/O, no FastAPI): they build Finding / Artifact /
NormalizedSegment objects directly and assert on the dict returned by
build_package_map().
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models.domain import (
    Artifact, ArtifactStatus, ArtifactType, EvidenceSpan,
    Finding, FindingStatus, FindingType, NormalizedSegment, Severity, Tier,
)
from backend.services.analysis.package_map import build_package_map


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _artifact(aid: str, filename: str = None, atype: ArtifactType = ArtifactType.ssp) -> Artifact:
    return Artifact(
        id=aid,
        type=atype,
        filename=filename or f"{aid}.md",
        hash="deadbeef",
        status=ArtifactStatus.reviewed,
        tenant="default",
    )


def _span(artifact_id: str, locator: str = "¶1", quote: str = "some text") -> EvidenceSpan:
    return EvidenceSpan(artifact_id=artifact_id, locator=locator, quoted_text=quote)


def _finding(
    fid: str,
    run_id: str = "run-1",
    control_id: str = "AC-2",
    ftype: FindingType = FindingType.inconsistent,
    severity: Severity = Severity.high,
    spans: list[EvidenceSpan] = None,
    status: FindingStatus = FindingStatus.unattested,
    recommendation: str = "Fix the inconsistency.",
) -> Finding:
    return Finding(
        id=fid,
        run_id=run_id,
        control_id=control_id,
        type=ftype,
        severity=severity,
        confidence=0.9,
        recommendation=recommendation,
        evidence_spans=spans or [],
        tier=Tier.t0,
        status=status,
    )


def _seg(artifact_id: str, control_hint: str = "AC-2", text: str = "narrative") -> NormalizedSegment:
    return NormalizedSegment(
        artifact_id=artifact_id,
        text=text,
        locator="¶1",
        char_start=0,
        char_end=len(text),
        control_hint=control_hint,
    )


# --------------------------------------------------------------------------- #
# Test 1 — contradiction edge from a two-artifact inconsistent finding
# --------------------------------------------------------------------------- #
def test_contradiction_edge_two_artifact_finding():
    a1 = _artifact("art-1", "01_SSP.md")
    a2 = _artifact("art-2", "02_Arch.md", ArtifactType.architecture)

    span1 = _span("art-1", "¶12", "SSP says quarterly review")
    span2 = _span("art-2", "¶4", "Arch says annual review")

    f = _finding("f-001", spans=[span1, span2])
    result = build_package_map(
        artifacts=[a1, a2],
        segments_by_artifact={},
        current_findings=[f],
        prev_findings=None,
        run_id="run-1",
        prev_run_id=None,
        package_id="pkg-1",
    )

    edges = [e for e in result["edges"] if e["kind"] == "contradiction"]
    assert len(edges) == 1
    edge = edges[0]
    assert edge["state"] == "active"
    assert edge["control_id"] == "AC-2"
    assert edge["severity"] == "high"
    assert edge["finding_id"] == "f-001"

    # Quotes must land on the correct artifact sides.
    # source/target are sorted, so art-1 < art-2 → source = art-1.
    assert edge["source"] == "art-1"
    assert edge["target"] == "art-2"
    assert edge["detail"]["left"]["artifact_id"] == "art-1"
    assert edge["detail"]["left"]["quote"] == "SSP says quarterly review"
    assert edge["detail"]["left"]["locator"] == "¶12"
    assert edge["detail"]["right"]["artifact_id"] == "art-2"
    assert edge["detail"]["right"]["quote"] == "Arch says annual review"
    assert edge["detail"]["right"]["locator"] == "¶4"

    # Filenames must be populated from the artifact map.
    assert edge["detail"]["left"]["filename"] == "01_SSP.md"
    assert edge["detail"]["right"]["filename"] == "02_Arch.md"


# --------------------------------------------------------------------------- #
# Test 2 — single-artifact inconsistent finding produces NO contradiction edge
# --------------------------------------------------------------------------- #
def test_single_artifact_inconsistent_finding_no_contradiction_edge():
    a1 = _artifact("art-1")
    f = _finding("f-002", spans=[_span("art-1"), _span("art-1")])
    result = build_package_map(
        artifacts=[a1],
        segments_by_artifact={},
        current_findings=[f],
        prev_findings=None,
        run_id="run-1",
        prev_run_id=None,
    )
    contradiction_edges = [e for e in result["edges"] if e["kind"] == "contradiction"]
    assert contradiction_edges == []


# --------------------------------------------------------------------------- #
# Test 3 — resolved edge when prev has the contradiction and current doesn't
# --------------------------------------------------------------------------- #
def test_resolved_edge_when_prev_has_contradiction_and_current_does_not():
    a1 = _artifact("art-1")
    a2 = _artifact("art-2")

    span1 = _span("art-1", "¶1", "old text from art-1")
    span2 = _span("art-2", "¶2", "old text from art-2")
    old_f = _finding("f-old", run_id="run-prev", spans=[span1, span2])

    result = build_package_map(
        artifacts=[a1, a2],
        segments_by_artifact={},
        current_findings=[],         # finding gone from current run
        prev_findings=[old_f],
        run_id="run-2",
        prev_run_id="run-prev",
    )

    resolved = [e for e in result["edges"] if e["state"] == "resolved"]
    assert len(resolved) == 1
    edge = resolved[0]
    assert edge["kind"] == "resolved"
    assert edge["finding_id"] == "f-old"
    # Quotes come from the OLD finding's spans.
    assert edge["detail"]["left"]["quote"] == "old text from art-1"
    assert edge["detail"]["right"]["quote"] == "old text from art-2"


# --------------------------------------------------------------------------- #
# Test 4 — attested (approved) contradiction that disappears yields resolved
# --------------------------------------------------------------------------- #
def test_attested_disappeared_contradiction_yields_resolved():
    """An approved finding whose signature is absent from the new run goes
    into d.stale, and the package map must still emit a resolved edge for it.
    """
    a1 = _artifact("art-1")
    a2 = _artifact("art-2")

    span1 = _span("art-1", "¶3", "approved text art-1")
    span2 = _span("art-2", "¶5", "approved text art-2")
    approved_f = _finding(
        "f-approved", run_id="run-prev", spans=[span1, span2],
        status=FindingStatus.approved,
    )

    result = build_package_map(
        artifacts=[a1, a2],
        segments_by_artifact={},
        current_findings=[],
        prev_findings=[approved_f],
        run_id="run-2",
        prev_run_id="run-prev",
    )

    # approved + disappeared → d.stale → resolved edge in the map
    resolved = [e for e in result["edges"] if e["state"] == "resolved"]
    assert len(resolved) == 1
    assert resolved[0]["finding_id"] == "f-approved"


# --------------------------------------------------------------------------- #
# Test 5 — shared-control edge from overlapping controls; none when no overlap
# --------------------------------------------------------------------------- #
def test_shared_control_edge_with_overlap():
    a1 = _artifact("art-1")
    a2 = _artifact("art-2")

    segs = {
        "art-1": [_seg("art-1", "AC-2"), _seg("art-1", "AU-2")],
        "art-2": [_seg("art-2", "AC-2"), _seg("art-2", "IA-2")],
    }
    result = build_package_map(
        artifacts=[a1, a2],
        segments_by_artifact=segs,
        current_findings=[],
        prev_findings=None,
        run_id="run-1",
        prev_run_id=None,
    )
    shared = [e for e in result["edges"] if e["kind"] == "shared_controls"]
    assert len(shared) == 1
    edge = shared[0]
    assert edge["controls"] == ["AC-2"]
    assert edge["count"] == 1


def test_no_shared_control_edge_when_no_overlap():
    a1 = _artifact("art-1")
    a2 = _artifact("art-2")

    segs = {
        "art-1": [_seg("art-1", "AC-2")],
        "art-2": [_seg("art-2", "IA-2")],
    }
    result = build_package_map(
        artifacts=[a1, a2],
        segments_by_artifact=segs,
        current_findings=[],
        prev_findings=None,
        run_id="run-1",
        prev_run_id=None,
    )
    shared = [e for e in result["edges"] if e["kind"] == "shared_controls"]
    assert shared == []


# --------------------------------------------------------------------------- #
# Test 6 — catalog-only findings counted in package_level_findings, not nodes
# --------------------------------------------------------------------------- #
def test_catalog_only_finding_goes_to_package_level():
    a1 = _artifact("art-1")
    catalog_span = _span("catalog:nist-800-53-rev5/AC-2", "obj.1", "catalog text")
    f = _finding("f-cat", ftype=FindingType.missing, spans=[catalog_span])

    result = build_package_map(
        artifacts=[a1],
        segments_by_artifact={},
        current_findings=[f],
        prev_findings=None,
        run_id="run-1",
        prev_run_id=None,
    )

    pkg = result["package_level_findings"]
    assert pkg["high"] == 1

    node = next(n for n in result["nodes"] if n["artifact_id"] == "art-1")
    assert node["findings"]["high"] == 0


# --------------------------------------------------------------------------- #
# Test 7 — node severity counts are correct
# --------------------------------------------------------------------------- #
def test_node_severity_counts():
    a1 = _artifact("art-1")

    findings = [
        _finding("f-c1", severity=Severity.critical, spans=[_span("art-1")]),
        _finding("f-c2", severity=Severity.critical, spans=[_span("art-1")],
                 ftype=FindingType.missing),
        _finding("f-h1", severity=Severity.high, spans=[_span("art-1")],
                 ftype=FindingType.weak_narrative),
        _finding("f-m1", severity=Severity.medium, spans=[_span("art-1")],
                 ftype=FindingType.insufficient_evidence),
    ]

    result = build_package_map(
        artifacts=[a1],
        segments_by_artifact={},
        current_findings=findings,
        prev_findings=None,
        run_id="run-1",
        prev_run_id=None,
    )

    node = next(n for n in result["nodes"] if n["artifact_id"] == "art-1")
    assert node["findings"]["critical"] == 2
    assert node["findings"]["high"] == 1
    assert node["findings"]["medium"] == 1
    assert node["findings"]["low"] == 0


# --------------------------------------------------------------------------- #
# Test 8 — empty inputs → empty edges, nodes still listed
# --------------------------------------------------------------------------- #
def test_empty_inputs_produces_empty_edges_but_nodes_listed():
    a1 = _artifact("art-1", "01_SSP.md")
    a2 = _artifact("art-2", "02_Arch.md")

    result = build_package_map(
        artifacts=[a1, a2],
        segments_by_artifact={},
        current_findings=[],
        prev_findings=None,
        run_id=None,
        prev_run_id=None,
        package_id="pkg-empty",
    )

    assert result["package_id"] == "pkg-empty"
    assert result["run_id"] is None
    assert result["edges"] == []
    node_ids = {n["artifact_id"] for n in result["nodes"]}
    assert node_ids == {"art-1", "art-2"}
    for node in result["nodes"]:
        assert node["findings"] == {"critical": 0, "high": 0, "medium": 0, "low": 0}


# --------------------------------------------------------------------------- #
# Test 9 — edge ids are stable across two independent invocations
# --------------------------------------------------------------------------- #
def test_edge_ids_stable_across_calls():
    a1 = _artifact("art-1")
    a2 = _artifact("art-2")
    f = _finding("f-stable", spans=[_span("art-1"), _span("art-2")])

    def _run():
        return build_package_map(
            artifacts=[a1, a2],
            segments_by_artifact={},
            current_findings=[f],
            prev_findings=None,
            run_id="run-1",
            prev_run_id=None,
        )

    r1 = _run()
    r2 = _run()
    ids1 = {e["id"] for e in r1["edges"]}
    ids2 = {e["id"] for e in r2["edges"]}
    assert ids1 == ids2
    # All edge ids must start with the expected prefix.
    for eid in ids1:
        assert eid.startswith("edge-")


# --------------------------------------------------------------------------- #
# Test 10 — deterministic source/target ordering regardless of span order
# --------------------------------------------------------------------------- #
def test_contradiction_edge_source_target_deterministic():
    """source/target must be sorted alphabetically so the same pair always
    yields the same edge direction, regardless of which span comes first."""
    a1 = _artifact("art-aaa")
    a2 = _artifact("art-zzz")

    # Spans in reverse order (art-zzz first)
    f_forward = _finding("f-fwd", spans=[_span("art-aaa"), _span("art-zzz")])
    f_reverse = _finding("f-rev", spans=[_span("art-zzz"), _span("art-aaa")])

    def _edge_direction(finding):
        result = build_package_map(
            artifacts=[a1, a2],
            segments_by_artifact={},
            current_findings=[finding],
            prev_findings=None,
            run_id="run-1",
            prev_run_id=None,
        )
        edges = [e for e in result["edges"] if e["kind"] == "contradiction"]
        assert len(edges) == 1
        return edges[0]["source"], edges[0]["target"]

    src1, tgt1 = _edge_direction(f_forward)
    src2, tgt2 = _edge_direction(f_reverse)
    assert src1 == src2 == "art-aaa"
    assert tgt1 == tgt2 == "art-zzz"
