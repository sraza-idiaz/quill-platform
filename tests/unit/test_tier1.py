"""Tier 1 retrieval / evidence-index tests (FR-T1-01..03)."""
from backend.services.ingest.normalizer import normalize
from backend.services.analysis.tier1_retrieval import build_evidence_index, best_evidence_per_objective


def test_evidence_index_has_spans_and_scores(fixtures_dir, catalog):
    segs = normalize("art0", fixtures_dir / "ssp_good_ac2.md")
    index = build_evidence_index(segs, catalog)
    assert index, "expected evidence index entries"
    for e in index:
        assert e.span.quoted_text          # FR-T1-02: every entry has a source span
        assert 0.0 <= e.score <= 1.0       # FR-T1-03: retrieval score recorded
        assert e.control_id


def test_maps_text_to_correct_control(fixtures_dir, catalog):
    segs = normalize("art0", fixtures_dir / "ssp_good_ac2.md")
    index = build_evidence_index(segs, catalog)
    ac2 = [e for e in index if e.control_id == "AC-2"]
    assert ac2 and max(e.score for e in ac2) >= 0.6  # hinted control scores strongly


def test_best_evidence_per_objective_dedupes(fixtures_dir, catalog):
    segs = normalize("art0", fixtures_dir / "ssp_good_ac2.md")
    index = build_evidence_index(segs, catalog)
    best = best_evidence_per_objective(index)
    # one entry per (control, objective)
    keys = list(best.keys())
    assert len(keys) == len(set(keys))
