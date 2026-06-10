"""Phase II FR-CAT-01..04 — full NIST 800-53 Rev. 5 catalog loading.

Verifies the converted YAML is shape-compatible with the existing
catalog_loader (no code change needed to use it), and that the counts +
baseline assignments match what NIST publishes.
"""
from pathlib import Path

import pytest

from backend.services.catalog_loader import load_catalog

ROOT = Path(__file__).resolve().parents[2]
FULL_CATALOG = ROOT / "config" / "catalog-nist-800-53-rev5.yaml"

# Skip if the generated file isn't present (e.g. a fresh checkout that
# hasn't run scripts/convert_oscal_catalog.py yet).
pytestmark = pytest.mark.skipif(
    not FULL_CATALOG.exists(),
    reason="Run `python -m scripts.convert_oscal_catalog` to generate this file.",
)


@pytest.fixture(scope="module")
def full():
    return load_catalog(FULL_CATALOG)


def test_loads_with_no_code_change(full):
    assert full.source_catalog == "nist-800-53-rev5"
    assert full.assessment_catalog == "nist-800-53a-rev5"
    assert full.baseline == "moderate"


def test_control_count_in_expected_range(full):
    # Rev. 5 published baselines: low ~149, mod ~287, high ~370.
    # We allow modest variance (the OSCAL release may add/remove a handful).
    assert 360 <= len(full.controls) <= 400, f"expected ~370 controls, got {len(full.controls)}"


def test_all_required_families_present(full):
    """The 18 mainline families (excluding PT/PM which aren't in L/M/H baselines)."""
    families = {c.family for c in full.controls.values()}
    expected = {"AC", "AT", "AU", "CA", "CM", "CP", "IA", "IR", "MA", "MP",
                "PE", "PL", "PS", "RA", "SA", "SC", "SI", "SR"}
    missing = expected - families
    assert not missing, f"missing families: {missing}"


def test_baseline_counts_match_NIST_published_figures(full):
    low  = full.baseline_controls("low")
    mod  = full.baseline_controls("moderate")
    high = full.baseline_controls("high")
    # Published Rev. 5 counts. Tolerate ±5 for OSCAL release variance.
    assert 145 <= len(low)  <= 155, len(low)
    assert 280 <= len(mod)  <= 295, len(mod)
    assert 360 <= len(high) <= 380, len(high)


def test_low_subset_of_moderate_subset_of_high(full):
    low  = {c.control_id for c in full.baseline_controls("low")}
    mod  = {c.control_id for c in full.baseline_controls("moderate")}
    high = {c.control_id for c in full.baseline_controls("high")}
    assert low.issubset(mod),  f"low ⊄ moderate: {low - mod}"
    assert mod.issubset(high), f"moderate ⊄ high: {mod - high}"


def test_canonical_AC_2_present_with_objectives(full):
    ac2 = full.get_control("AC-2")
    assert ac2 is not None
    assert ac2.family == "AC"
    assert "low" in ac2.baselines
    objs = full.objectives_for("AC-2")
    assert objs, "AC-2 should have at least one assessment objective"


def test_AC_2_enhancement_recognized(full):
    # AC-2(1) — Automated System Account Management; in moderate + high.
    enh = full.get_control("AC-2(1)")
    assert enh is not None
    assert enh.family == "AC"
    assert "moderate" in enh.baselines
    assert "low" not in enh.baselines    # enhancements typically start at moderate


def test_required_fields_carry_over_for_known_controls(full):
    # AC-2's required_fields was set in the converter from the original sample
    # catalog so existing Tier 0 rules keep firing on the full catalog.
    assert "account_types" in full.required_fields("AC-2")
    assert "responsible_role" in full.required_fields("AC-2")


def test_unknown_control_returns_none(full):
    assert full.get_control("ZZ-99") is None
