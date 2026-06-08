"""Tier 0 deterministic engine tests (FR-T0-01..05)."""
from backend.models.domain import FindingType
from backend.services.ingest.normalizer import normalize
from backend.services.analysis.tier0_rules import run_tier0


def _segs(fixtures_dir, *names):
    segs = []
    for i, name in enumerate(names):
        segs += normalize(f"art{i}", fixtures_dir / name)
    return segs


def test_coverage_flags_missing_baseline_controls(fixtures_dir, catalog, rubric):
    # good SSP only covers AC-2 + AU-2; moderate baseline also needs IA-2, CM-2, SC-7, SI-4.
    segs = _segs(fixtures_dir, "ssp_good_ac2.md")
    findings = run_tier0("run1", segs, catalog, rubric)
    missing = {f.control_id for f in findings if f.type == FindingType.missing}
    assert {"IA-2", "CM-2", "SC-7", "SI-4"}.issubset(missing)  # FR-T0-01
    assert "AC-2" not in missing


def test_required_field_gaps_on_weak_ssp(fixtures_dir, catalog, rubric):
    segs = _segs(fixtures_dir, "ssp_weak_ac2.md")
    findings = run_tier0("run1", segs, catalog, rubric)
    ac2 = [f for f in findings if f.control_id == "AC-2"
           and f.type == FindingType.insufficient_evidence]
    assert ac2, "weak AC-2 should produce insufficient_evidence finding(s)"
    # The weak SSP uses 'organization-defined frequency' -> ODP placeholder (C3).
    assert any("organization_defined_parameter" in f.missing_elements for f in ac2)


def test_cross_artifact_inconsistency(fixtures_dir, catalog, rubric):
    # good SSP says 'quarterly' for AC-2; arch doc says 'annually' -> inconsistent (FR-T0-03).
    segs = _segs(fixtures_dir, "ssp_good_ac2.md", "arch_ac2_conflict.md")
    findings = run_tier0("run1", segs, catalog, rubric)
    inconsistent = [f for f in findings if f.type == FindingType.inconsistent]
    assert any(f.control_id == "AC-2" for f in inconsistent)
    f = next(f for f in inconsistent if f.control_id == "AC-2")
    assert len(f.evidence_spans) >= 2  # cites both artifacts


def test_tier0_is_deterministic(fixtures_dir, catalog, rubric):
    segs = _segs(fixtures_dir, "ssp_weak_ac2.md", "arch_ac2_conflict.md")
    a = run_tier0("run1", segs, catalog, rubric)
    b = run_tier0("run1", segs, catalog, rubric)
    assert [f.id for f in a] == [f.id for f in b]  # FR-T0-05
    assert [f.model_dump() for f in a] == [f.model_dump() for f in b]


def test_no_llm_used_in_tier0(fixtures_dir, catalog, rubric):
    # Confidence is exactly 1.0 for deterministic findings; no model field set.
    segs = _segs(fixtures_dir, "ssp_weak_ac2.md")
    findings = run_tier0("run1", segs, catalog, rubric)
    assert findings
    assert all(f.confidence == 1.0 and f.tier.value == "T0" for f in findings)
