"""Phase II FR-XA-03 — dependency graph builder (unit tests)."""
from pathlib import Path

import pytest

from backend.models.domain import NormalizedSegment
from backend.services.analysis.dependency_graph import build_graph
from backend.services.catalog_loader import load_catalog

ROOT = Path(__file__).resolve().parents[2]
CATALOG = load_catalog(ROOT / "config" / "catalog.yaml")


def _seg(art_id: str, control_hint: str, text: str, locator: str = "¶1") -> NormalizedSegment:
    return NormalizedSegment(
        artifact_id=art_id, control_hint=control_hint, text=text,
        locator=locator, char_start=0, char_end=len(text),
    )


def test_empty_input_yields_empty_graph():
    g = build_graph([], CATALOG)
    assert g.nodes == [] and g.edges == []


def test_segment_with_no_references_creates_only_its_own_node():
    g = build_graph([
        _seg("a1", "AC-2", "The organization manages accounts.")
    ], CATALOG)
    ids = {n.control_id for n in g.nodes}
    assert ids == {"AC-2"}
    assert g.edges == []
    n = next(n for n in g.nodes if n.control_id == "AC-2")
    assert n.found_in_artifacts == ["a1"]


def test_reference_creates_outbound_edge():
    g = build_graph([
        _seg("a1", "AC-2", "Account management is performed in accordance with AC-1.")
    ], CATALOG)
    # Even though AC-1 isn't in the sample catalog, it should be ignored,
    # not crash. Verify: catalog has no AC-1, so the edge is skipped.
    assert all(e.to_control != "AC-1" for e in g.edges)


def test_reference_to_known_control_creates_edge():
    # AC-2 references AU-2, which IS in our sample catalog.
    g = build_graph([
        _seg("a1", "AC-2", "Account events are logged per AU-2.")
    ], CATALOG)
    edges = [e for e in g.edges if e.from_control == "AC-2" and e.to_control == "AU-2"]
    assert len(edges) == 1
    e = edges[0]
    assert e.artifact_id == "a1"
    assert "AU-2" in e.quoted_text


def test_self_reference_is_ignored():
    g = build_graph([
        _seg("a1", "AC-2", "AC-2 covers account management.")
    ], CATALOG)
    assert not [e for e in g.edges if e.from_control == "AC-2" and e.to_control == "AC-2"]


def test_inbound_outbound_degrees_counted_correctly():
    g = build_graph([
        _seg("a1", "AC-2", "Account events are logged per AU-2 and IA-2 too."),
        _seg("a1", "AU-2", "Includes AC-2 events."),
    ], CATALOG)
    by_id = {n.control_id: n for n in g.nodes}
    assert by_id["AC-2"].outbound_degree == 2   # AU-2 and IA-2
    assert by_id["AC-2"].inbound_degree == 1    # from AU-2
    assert by_id["AU-2"].outbound_degree == 1   # to AC-2
    assert by_id["AU-2"].inbound_degree == 1    # from AC-2


def test_cross_artifact_edges_track_their_source():
    g = build_graph([
        _seg("ssp.md", "AC-2", "See AU-2 for audit logging."),
        _seg("arch.md", "AU-2", "Logs are reviewed for AC-2 anomalies."),
    ], CATALOG)
    ac2_to_au2 = [e for e in g.edges if e.from_control == "AC-2" and e.to_control == "AU-2"]
    au2_to_ac2 = [e for e in g.edges if e.from_control == "AU-2" and e.to_control == "AC-2"]
    assert len(ac2_to_au2) == 1 and ac2_to_au2[0].artifact_id == "ssp.md"
    assert len(au2_to_ac2) == 1 and au2_to_ac2[0].artifact_id == "arch.md"


def test_in_baseline_flag_reflects_active_baseline():
    g = build_graph([
        _seg("a1", "AC-2", "Account events are logged per AU-2."),
        _seg("a1", "CM-2", "Baseline configuration."),
    ], CATALOG, baseline="low")
    by_id = {n.control_id: n for n in g.nodes}
    # AC-2 and AU-2 are in low; CM-2 is moderate/high only.
    assert by_id["AC-2"].in_baseline is True
    assert by_id["AU-2"].in_baseline is True
    assert by_id["CM-2"].in_baseline is False


def test_neighbors_helper_buckets_edges():
    g = build_graph([
        _seg("a1", "AC-2", "Uses AU-2 and IA-2."),
        _seg("a1", "AU-2", "Records AC-2 events."),
    ], CATALOG)
    n = g.neighbors("AC-2")
    out = {e.to_control for e in n["references"]}
    inn = {e.from_control for e in n["referenced_by"]}
    assert out == {"AU-2", "IA-2"}
    assert inn == {"AU-2"}


def test_duplicate_mention_in_same_segment_dedups():
    g = build_graph([
        _seg("a1", "AC-2", "Reference to AU-2 and AU-2 and AU-2 again."),
    ], CATALOG)
    ac2_to_au2 = [e for e in g.edges if e.from_control == "AC-2" and e.to_control == "AU-2"]
    # Same (from, to, artifact, locator) — collapses to a single edge.
    assert len(ac2_to_au2) == 1


def test_unknown_control_id_does_not_create_phantom_node():
    g = build_graph([
        _seg("a1", "AC-2", "Refers to ZZ-99 which is not a real control."),
    ], CATALOG)
    ids = {n.control_id for n in g.nodes}
    assert "ZZ-99" not in ids
