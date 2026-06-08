"""Ingestion + normalization tests (FR-ING-01..05)."""
import pytest

from backend.services.ingest.normalizer import compute_hash, detect_control_ids, normalize
from backend.services.ingest.parsers import ParseError, parse_artifact


def test_hash_is_deterministic(fixtures_dir):
    p = fixtures_dir / "ssp_good_ac2.md"
    assert compute_hash(p) == compute_hash(p)  # FR-ING-03
    assert len(compute_hash(p)) == 64


def test_detect_control_ids():
    ids = detect_control_ids("This addresses AC-2 and SC-7(3) and AU-12.")
    assert ids == ["AC-2", "SC-7", "AU-12"]


def test_normalize_markdown_keeps_locators(fixtures_dir):
    segs = normalize("art1", fixtures_dir / "ssp_good_ac2.md")
    assert segs, "expected segments"
    # AC-2 and AU-2 segments are keyed to their control (FR-ING-02).
    hints = {s.control_hint for s in segs if s.control_hint}
    assert "AC-2" in hints and "AU-2" in hints
    for s in segs:
        assert s.locator  # every segment carries a locator


def test_oscal_parse_maps_controls(fixtures_dir):
    blocks = parse_artifact(fixtures_dir / "ssp_sample.oscal.json")
    hints = {b.control_hint for b in blocks}
    assert "AC-2" in hints and "AU-2" in hints  # FR-ING-04


def test_corrupted_oscal_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json")
    with pytest.raises(ParseError):  # FR-ING-05 (no crash; clean error)
        parse_artifact(bad)


def test_unsupported_type_raises(tmp_path):
    f = tmp_path / "x.zip"
    f.write_text("x")
    with pytest.raises(ParseError):
        parse_artifact(f)
