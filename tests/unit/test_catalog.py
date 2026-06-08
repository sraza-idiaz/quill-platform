"""Catalog + rubric loader tests (FR-CAT-01..03)."""


def test_catalog_loads_controls(catalog):
    assert catalog.source_catalog == "nist-800-53-rev5"
    assert catalog.get_control("AC-2") is not None
    assert catalog.get_control("AC-2").family == "AC"


def test_baseline_selection(catalog):
    mod_ids = {c.control_id for c in catalog.baseline_controls("moderate")}
    low_ids = {c.control_id for c in catalog.baseline_controls("low")}
    # CM-2 and SI-4 are moderate/high only, not low (FR-CAT-03).
    assert "CM-2" in mod_ids and "SI-4" in mod_ids
    assert "CM-2" not in low_ids and "SI-4" not in low_ids
    assert "AC-2" in low_ids


def test_required_fields_and_objectives(catalog):
    assert "review_frequency" in catalog.required_fields("AC-2")
    objs = catalog.objectives_for("AC-2")
    assert any(o.objective_id == "AC-2_obj.j" for o in objs)


def test_rubric_threshold_is_three_not_999(rubric):
    # PRD non-negotiable / DECISION-004.
    assert rubric.circuit_breaker_threshold == 3
    assert rubric.confidence_thresholds["emit"] == 0.75
