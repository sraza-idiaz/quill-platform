"""Unit tests for backend/services/analysis/visual_grounding.py.

Phase II FR-XA extension — visual grounding builder.

Tests are pure (no I/O, no FastAPI): they build Finding / Artifact /
EvidenceSpan objects directly, construct lightweight in-memory Catalog
instances, and assert on the dict returned by build_grounding().
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models.domain import (
    Artifact, ArtifactStatus, ArtifactType,
    EvidenceSpan, Finding, FindingStatus, FindingType, Severity, Tier,
)
from backend.services.analysis.visual_grounding import build_grounding
from backend.services.catalog_loader import Catalog


# --------------------------------------------------------------------------- #
# Lightweight in-memory catalog builder (no YAML loading in unit tests)
# --------------------------------------------------------------------------- #

def _make_catalog(controls: list[dict] = None) -> Catalog:
    """Build a minimal Catalog from a plain dict — no YAML required."""
    return Catalog({
        "version": 1,
        "source_catalog": "nist-800-53-rev5",
        "assessment_catalog": "nist-800-53a-rev5",
        "baseline": "moderate",
        "controls": controls or [],
    })


def _ac2_catalog() -> Catalog:
    return _make_catalog([
        {
            "control_id": "AC-2",
            "family": "AC",
            "title": "Account Management",
            "baselines": ["moderate"],
            "required_fields": ["account_types"],
            "objectives": [
                {
                    "objective_id": "AC-2_obj.a",
                    "text": "Account types to be managed are defined.",
                    "required_methods": ["examine"],
                },
                {
                    "objective_id": "AC-2_obj.j",
                    "text": "Accounts are reviewed for compliance at the organization-defined frequency.",
                    "required_methods": ["examine", "interview"],
                },
            ],
        }
    ])


# --------------------------------------------------------------------------- #
# Domain helpers
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


def _span(
    artifact_id: str,
    locator: str = "¶1",
    quote: str = "some text",
    char_start: int | None = None,
    char_end: int | None = None,
) -> EvidenceSpan:
    return EvidenceSpan(
        artifact_id=artifact_id,
        locator=locator,
        quoted_text=quote,
        char_start=char_start,
        char_end=char_end,
    )


def _finding(
    fid: str,
    run_id: str = "run-1",
    control_id: str = "AC-2",
    ftype: FindingType = FindingType.inconsistent,
    severity: Severity = Severity.high,
    spans: list[EvidenceSpan] | None = None,
    status: FindingStatus = FindingStatus.unattested,
    recommendation: str = "Fix it.",
    rationale: str = "Evidence conflicts across documents.",
    tier: Tier = Tier.t0,
) -> Finding:
    return Finding(
        id=fid,
        run_id=run_id,
        control_id=control_id,
        type=ftype,
        severity=severity,
        confidence=0.9,
        recommendation=recommendation,
        rationale=rationale,
        evidence_spans=spans or [],
        tier=tier,
        status=status,
    )


# --------------------------------------------------------------------------- #
# Test 1 — catalog-only finding is excluded
# --------------------------------------------------------------------------- #

def test_catalog_only_finding_is_excluded():
    """A finding whose every span is a catalog ref has no document location
    and must be excluded from the groundings list."""
    a1 = _artifact("art-1", "01_SSP.md")
    catalog_span = _span("catalog:nist-800-53-rev5/AC-2", "obj.1", "control text")
    f = _finding("f-cat", ftype=FindingType.missing, spans=[catalog_span])

    result = build_grounding(
        artifacts=[a1],
        artifact_texts={"art-1": "some text"},
        findings=[f],
        catalog=_ac2_catalog(),
        run_id="run-1",
    )
    assert result["groundings"] == []


# --------------------------------------------------------------------------- #
# Test 2 — single-artifact weak_narrative finding
# --------------------------------------------------------------------------- #

def test_single_artifact_weak_narrative_has_empty_conflicts():
    """A finding with a single non-catalog span must produce primary set and
    conflicts_with == []."""
    a1 = _artifact("art-1", "01_SSP.md")
    span = _span("art-1", "¶3", "Accounts are managed per policy.", 100, 135)
    f = _finding(
        "f-weak",
        ftype=FindingType.weak_narrative,
        severity=Severity.medium,
        spans=[span],
    )

    result = build_grounding(
        artifacts=[a1],
        artifact_texts={"art-1": "...Accounts are managed per policy...."},
        findings=[f],
        catalog=_ac2_catalog(),
        run_id="run-1",
    )

    assert len(result["groundings"]) == 1
    g = result["groundings"][0]
    assert g["type"] == "weak_narrative"
    assert g["primary"]["artifact_id"] == "art-1"
    assert g["primary"]["filename"] == "01_SSP.md"
    assert g["primary"]["locator"] == "¶3"
    assert g["primary"]["quote"] == "Accounts are managed per policy."
    assert g["primary"]["char_start"] == 100
    assert g["primary"]["char_end"] == 135
    assert g["conflicts_with"] == []


# --------------------------------------------------------------------------- #
# Test 3 — multi-artifact inconsistent finding
# --------------------------------------------------------------------------- #

def test_multi_artifact_inconsistent_finding_conflicts_with():
    """An inconsistent finding with spans across two artifacts:
    primary = first non-catalog span, conflicts_with = the other, deduped."""
    a1 = _artifact("art-1", "01_SSP.md")
    a2 = _artifact("art-2", "02_Arch.md", ArtifactType.architecture)

    span1 = _span("art-1", "¶4", "Accounts are reviewed quarterly", 102, 134)
    span2 = _span("art-2", "¶3", "Accounts are reviewed annually", 80, 112)

    f = _finding("f-incon", spans=[span1, span2])

    result = build_grounding(
        artifacts=[a1, a2],
        artifact_texts={"art-1": "...Accounts are reviewed quarterly...",
                        "art-2": "...Accounts are reviewed annually..."},
        findings=[f],
        catalog=_ac2_catalog(),
        run_id="run-1",
    )

    assert len(result["groundings"]) == 1
    g = result["groundings"][0]
    assert g["type"] == "inconsistent"
    assert g["primary"]["artifact_id"] == "art-1"
    assert g["primary"]["filename"] == "01_SSP.md"
    assert g["primary"]["quote"] == "Accounts are reviewed quarterly"
    assert len(g["conflicts_with"]) == 1
    cw = g["conflicts_with"][0]
    assert cw["artifact_id"] == "art-2"
    assert cw["filename"] == "02_Arch.md"
    assert cw["locator"] == "¶3"
    assert cw["quote"] == "Accounts are reviewed annually"


# --------------------------------------------------------------------------- #
# Test 4 — conflicts_with deduplication by (artifact_id, locator)
# --------------------------------------------------------------------------- #

def test_conflicts_with_deduped_by_artifact_and_locator():
    """Duplicate spans with the same (artifact_id, locator) must appear only once
    in conflicts_with."""
    a1 = _artifact("art-1", "01_SSP.md")
    a2 = _artifact("art-2", "02_Arch.md")

    primary = _span("art-1", "¶1", "primary text")
    dup1    = _span("art-2", "¶2", "conflict text A")
    dup2    = _span("art-2", "¶2", "conflict text B — same locator")  # duplicate key

    f = _finding("f-dup", spans=[primary, dup1, dup2])

    result = build_grounding(
        artifacts=[a1, a2],
        artifact_texts={},
        findings=[f],
        catalog=_ac2_catalog(),
        run_id="run-1",
    )
    g = result["groundings"][0]
    # dup2 should be deduplicated away; only dup1's key survives.
    assert len(g["conflicts_with"]) == 1
    assert g["conflicts_with"][0]["locator"] == "¶2"


# --------------------------------------------------------------------------- #
# Test 5 — regulatory.objective_summary joins first 3 objectives with ' · '
# --------------------------------------------------------------------------- #

def test_regulatory_objective_summary_uses_up_to_3_objectives():
    """objective_summary must join the first 1-3 objectives' text with ' · '."""
    catalog = _make_catalog([
        {
            "control_id": "AC-2",
            "family": "AC",
            "title": "Account Management",
            "baselines": ["moderate"],
            "required_fields": [],
            "objectives": [
                {"objective_id": "AC-2_obj.a", "text": "Objective A text.", "required_methods": []},
                {"objective_id": "AC-2_obj.b", "text": "Objective B text.", "required_methods": []},
                {"objective_id": "AC-2_obj.c", "text": "Objective C text.", "required_methods": []},
                {"objective_id": "AC-2_obj.d", "text": "Objective D text.", "required_methods": []},
            ],
        }
    ])

    a1 = _artifact("art-1")
    f = _finding("f-obj", spans=[_span("art-1", "¶1", "text")])

    result = build_grounding(
        artifacts=[a1],
        artifact_texts={},
        findings=[f],
        catalog=catalog,
        run_id="run-1",
    )

    summary = result["groundings"][0]["regulatory"]["objective_summary"]
    # Must contain exactly 3 objectives (the 4th is dropped).
    assert "Objective A text." in summary
    assert "Objective B text." in summary
    assert "Objective C text." in summary
    assert "Objective D text." not in summary
    assert " · " in summary


# --------------------------------------------------------------------------- #
# Test 6 — regulatory.objective_summary truncated at 280 chars with ellipsis
# --------------------------------------------------------------------------- #

def test_regulatory_objective_summary_truncated_at_280():
    """If the joined objectives exceed 280 chars the summary must be capped
    with a trailing '...'."""
    long_text = "A" * 200
    catalog = _make_catalog([
        {
            "control_id": "AC-2",
            "family": "AC",
            "title": "Account Management",
            "baselines": ["moderate"],
            "required_fields": [],
            "objectives": [
                {"objective_id": "AC-2_obj.1", "text": long_text, "required_methods": []},
                {"objective_id": "AC-2_obj.2", "text": long_text, "required_methods": []},
            ],
        }
    ])

    a1 = _artifact("art-1")
    f = _finding("f-trunc", spans=[_span("art-1")])

    result = build_grounding(
        artifacts=[a1],
        artifact_texts={},
        findings=[f],
        catalog=catalog,
        run_id="run-1",
    )

    summary = result["groundings"][0]["regulatory"]["objective_summary"]
    assert len(summary) <= 280
    assert summary.endswith("...")


# --------------------------------------------------------------------------- #
# Test 7 — fallback to control title when catalog has no objectives
# --------------------------------------------------------------------------- #

def test_regulatory_falls_back_to_title_when_no_objectives():
    """When a control has no objectives the objective_summary must be the
    control title."""
    catalog = _make_catalog([
        {
            "control_id": "AC-2",
            "family": "AC",
            "title": "Account Management",
            "baselines": ["moderate"],
            "required_fields": [],
            "objectives": [],  # intentionally empty
        }
    ])

    a1 = _artifact("art-1")
    f = _finding("f-no-obj", spans=[_span("art-1")])

    result = build_grounding(
        artifacts=[a1],
        artifact_texts={},
        findings=[f],
        catalog=catalog,
        run_id="run-1",
    )

    g = result["groundings"][0]
    assert g["control_title"] == "Account Management"
    assert g["regulatory"]["objective_summary"] == "Account Management"


# --------------------------------------------------------------------------- #
# Test 8 — unknown control: control_title '' and objective_summary '' — no crash
# --------------------------------------------------------------------------- #

def test_unknown_control_does_not_crash():
    """A finding whose control_id is not present in the catalog must produce
    control_title='' and objective_summary='' without raising an exception."""
    catalog = _make_catalog([])  # empty catalog
    a1 = _artifact("art-1")
    f = _finding("f-unknown-ctrl", control_id="ZZ-99", spans=[_span("art-1")])

    result = build_grounding(
        artifacts=[a1],
        artifact_texts={},
        findings=[f],
        catalog=catalog,
        run_id="run-1",
    )

    assert len(result["groundings"]) == 1
    g = result["groundings"][0]
    assert g["control_title"] == ""
    assert g["regulatory"]["objective_summary"] == ""
    assert g["control_id"] == "ZZ-99"


# --------------------------------------------------------------------------- #
# Test 9 — output sorted by (severity, type, control_id, finding_id)
# --------------------------------------------------------------------------- #

def test_output_sorted_by_severity_type_control_finding():
    """Groundings must be ordered: severity priority → type priority →
    control_id ASC → finding_id ASC."""
    catalog = _make_catalog([
        {"control_id": "AC-2", "family": "AC", "title": "Account Management",
         "baselines": ["moderate"], "required_fields": [], "objectives": []},
        {"control_id": "AU-2", "family": "AU", "title": "Event Logging",
         "baselines": ["moderate"], "required_fields": [], "objectives": []},
    ])

    a1 = _artifact("art-1", "01.md")

    findings = [
        # low/missing → last in severity (3) + type (4)
        _finding("f-low-miss", control_id="AC-2", ftype=FindingType.missing,
                 severity=Severity.low, spans=[_span("art-1")]),
        # high/inconsistent → earlier (severity 1, type 0)
        _finding("f-high-inc", control_id="AU-2", ftype=FindingType.inconsistent,
                 severity=Severity.high, spans=[_span("art-1")]),
        # high/weak → severity 1, type 1 — after inconsistent, before missing
        _finding("f-high-weak", control_id="AC-2", ftype=FindingType.weak_narrative,
                 severity=Severity.high, spans=[_span("art-1")]),
        # critical/inconsistent → comes first
        _finding("f-crit-inc", control_id="AU-2", ftype=FindingType.inconsistent,
                 severity=Severity.critical, spans=[_span("art-1")]),
    ]

    result = build_grounding(
        artifacts=[a1],
        artifact_texts={},
        findings=findings,
        catalog=catalog,
        run_id="run-1",
    )

    ids = [g["finding_id"] for g in result["groundings"]]
    assert ids == ["f-crit-inc", "f-high-inc", "f-high-weak", "f-low-miss"]


# --------------------------------------------------------------------------- #
# Test 10 — empty findings → groundings == [], artifacts pass-through
# --------------------------------------------------------------------------- #

def test_empty_findings_produces_empty_groundings():
    """With no findings the groundings list must be empty and artifacts must
    pass through verbatim (sorted by filename)."""
    a1 = _artifact("art-1", "01_SSP.md")
    a2 = _artifact("art-2", "02_Arch.md")

    result = build_grounding(
        artifacts=[a2, a1],  # intentionally reversed to test sorting
        artifact_texts={"art-1": "text1", "art-2": "text2"},
        findings=[],
        catalog=_ac2_catalog(),
        run_id=None,
    )

    assert result["groundings"] == []
    assert result["run_id"] is None
    assert result["package_id"] is None
    # Artifacts sorted by filename ASC: 01 before 02.
    assert result["artifacts"][0]["id"] == "art-1"
    assert result["artifacts"][1]["id"] == "art-2"
    assert result["artifacts"][0]["text"] == "text1"
    assert result["artifacts"][1]["text"] == "text2"


# --------------------------------------------------------------------------- #
# Test 11 — artifacts list passed through with normalized text
# --------------------------------------------------------------------------- #

def test_artifacts_include_text_from_artifact_texts():
    """Each artifact in the output must carry the text from artifact_texts."""
    a1 = _artifact("art-1", "doc.md")
    text = "The normalized content of the document."

    result = build_grounding(
        artifacts=[a1],
        artifact_texts={"art-1": text},
        findings=[],
        catalog=_ac2_catalog(),
        run_id="run-x",
    )

    assert len(result["artifacts"]) == 1
    assert result["artifacts"][0]["text"] == text


# --------------------------------------------------------------------------- #
# Test 12 — function never mutates its inputs
# --------------------------------------------------------------------------- #

def test_build_grounding_does_not_mutate_inputs():
    """build_grounding must be side-effect-free; inputs must be unchanged."""
    a1 = _artifact("art-1", "01_SSP.md")
    a2 = _artifact("art-2", "02_Arch.md")

    span1 = _span("art-1", "¶4", "quarterly")
    span2 = _span("art-2", "¶3", "annually")
    f = _finding("f-m", spans=[span1, span2])

    artifacts_before  = copy.deepcopy([a1, a2])
    findings_before   = copy.deepcopy([f])
    texts_before      = {"art-1": "q", "art-2": "a"}

    build_grounding(
        artifacts=[a1, a2],
        artifact_texts={"art-1": "q", "art-2": "a"},
        findings=[f],
        catalog=_ac2_catalog(),
        run_id="run-1",
    )

    # Deep-compare artifacts
    for orig, after in zip(artifacts_before, [a1, a2]):
        assert orig.model_dump() == after.model_dump()
    # Deep-compare findings
    assert findings_before[0].model_dump() == f.model_dump()
    # artifact_texts dict unchanged
    assert texts_before == {"art-1": "q", "art-2": "a"}
