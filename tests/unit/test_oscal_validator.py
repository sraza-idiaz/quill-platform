"""OSCAL structural validation tests (FR-T0-04)."""
from backend.services.ingest.oscal_validator import validate_oscal_file, validate_oscal_structure


def test_valid_oscal_passes(fixtures_dir):
    assert validate_oscal_file(fixtures_dir / "ssp_sample.oscal.json") == []


def test_missing_root_flagged():
    assert validate_oscal_structure({"foo": "bar"})


def test_missing_control_id_flagged():
    data = {
        "system-security-plan": {
            "uuid": "u", "metadata": {"title": "t"},
            "control-implementation": {"implemented-requirements": [{"statements": []}]},
        }
    }
    violations = validate_oscal_structure(data)
    assert any("control-id" in v for v in violations)


def test_no_requirements_flagged():
    data = {"system-security-plan": {"uuid": "u", "metadata": {}, "control-implementation": {}}}
    assert any("implemented-requirements" in v for v in validate_oscal_structure(data))
