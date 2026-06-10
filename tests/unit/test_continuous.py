"""Phase II FR-CONT-01..07 — diff engine + watcher unit tests.

We test these as pure functions / objects, separately from the
orchestrator integration. End-to-end ("file drops in folder → run
fires") is covered in tests/integration/test_continuous_api.py.
"""
import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from backend.models.domain import (
    EvidenceSpan, Finding, FindingStatus, FindingType, Severity, Tier,
)
from backend.services.continuous import (
    FolderWatcher,
    affected_controls,
    carryover_attestations,
    diff_findings,
    finding_signature,
    folder_fingerprint,
    version_diff,
)


def _f(*, id, control, ftype=FindingType.weak_narrative,
       quote="x", artifact="ssp.md", locator="¶1",
       status=FindingStatus.unattested) -> Finding:
    return Finding(
        id=id, run_id="r1", control_id=control, type=ftype,
        severity=Severity.medium, confidence=0.8,
        recommendation="r", rationale="why",
        evidence_spans=[EvidenceSpan(artifact_id=artifact, locator=locator,
                                      quoted_text=quote)],
        tier=Tier.t2, status=status,
    )


# ─── finding_signature ────────────────────────────────────────────── #

def test_signature_stable_across_whitespace_variants():
    a = _f(id="a", control="AC-2", quote="manages account types quarterly")
    b = _f(id="b", control="AC-2",
           quote="manages   account types\n\tquarterly")     # whitespace-different
    assert finding_signature(a) == finding_signature(b)


def test_signature_differs_for_different_controls():
    a = _f(id="a", control="AC-2")
    b = _f(id="b", control="AU-2")
    assert finding_signature(a) != finding_signature(b)


def test_signature_differs_for_different_finding_type():
    a = _f(id="a", control="AC-2", ftype=FindingType.weak_narrative)
    b = _f(id="b", control="AC-2", ftype=FindingType.insufficient_evidence)
    assert finding_signature(a) != finding_signature(b)


def test_signature_differs_for_different_paragraph():
    a = _f(id="a", control="AC-2", locator="¶1", quote="alpha")
    b = _f(id="b", control="AC-2", locator="¶2", quote="beta")
    assert finding_signature(a) != finding_signature(b)


# ─── diff_findings ────────────────────────────────────────────────── #

def test_diff_classifies_new_unchanged_resolved():
    prev = [
        _f(id="p1", control="AC-2", quote="old paragraph"),
        _f(id="p2", control="AU-2", quote="logging not enough"),
    ]
    new = [
        # AC-2 same signature → unchanged
        _f(id="n1", control="AC-2", quote="old paragraph"),
        # CM-2 brand-new finding
        _f(id="n2", control="CM-2", quote="config baseline missing"),
        # AU-2 is missing in new (no attestation → resolved, not stale)
    ]
    d = diff_findings(prev, new)
    assert {f.control_id for f in d.unchanged} == {"AC-2"}
    assert {f.control_id for f in d.new}       == {"CM-2"}
    assert {f.control_id for f in d.resolved}  == {"AU-2"}
    assert d.stale == []
    assert d.counts() == {"new": 1, "resolved": 1, "stale": 0, "unchanged": 1}


def test_attested_finding_that_disappears_is_stale_not_resolved():
    prev = [
        _f(id="p1", control="AC-2", quote="attested deficiency",
           status=FindingStatus.approved),
        _f(id="p2", control="AU-2", quote="never reviewed",
           status=FindingStatus.unattested),
    ]
    new = []   # nothing emitted this run
    d = diff_findings(prev, new, prev_attested={"p1"})
    assert {f.control_id for f in d.stale}    == {"AC-2"}
    assert {f.control_id for f in d.resolved} == {"AU-2"}
    assert d.counts()["stale"] == 1
    assert d.counts()["resolved"] == 1


def test_diff_is_deterministic():
    prev = [_f(id="a", control="AC-3"), _f(id="b", control="AC-2")]
    new  = [_f(id="x", control="AU-2"), _f(id="y", control="AC-2")]
    d1 = diff_findings(prev, new)
    d2 = diff_findings(prev, new)
    assert [f.control_id for f in d1.new]      == [f.control_id for f in d2.new]
    assert [f.control_id for f in d1.resolved] == [f.control_id for f in d2.resolved]


def test_to_dict_is_json_serializable():
    import json
    prev = [_f(id="p", control="AC-2")]
    new  = [_f(id="n", control="AU-2")]
    json.dumps(diff_findings(prev, new).to_dict())   # must not raise


# ─── carryover_attestations ───────────────────────────────────────── #

def test_carryover_preserves_approved_status():
    prev = [_f(id="p", control="AC-2", quote="same",
               status=FindingStatus.approved)]
    new  = [_f(id="n", control="AC-2", quote="same")]
    c = carryover_attestations(prev, new)
    assert "n" in c
    assert c["n"].status == FindingStatus.approved


def test_carryover_skips_unchanged_unattested():
    prev = [_f(id="p", control="AC-2", quote="same",
               status=FindingStatus.unattested)]
    new  = [_f(id="n", control="AC-2", quote="same")]
    assert carryover_attestations(prev, new) == {}


def test_carryover_skips_when_paragraph_changed():
    prev = [_f(id="p", control="AC-2", quote="alpha",
               status=FindingStatus.approved)]
    new  = [_f(id="n", control="AC-2", quote="beta")]   # different signature
    assert carryover_attestations(prev, new) == {}


# ─── affected_controls ────────────────────────────────────────────── #

def test_affected_controls_detects_change():
    prev = {"ssp.md": "AC-2 narrative", "arch.md": "boundary"}
    new  = {"ssp.md": "AC-2 narrative REVISED", "arch.md": "boundary"}
    affected = affected_controls(prev, new)
    assert affected == {"ssp.md"}


def test_affected_controls_returns_empty_when_unchanged():
    prev = {"a.md": "unchanged"}
    new  = {"a.md": "unchanged"}
    assert affected_controls(prev, new) == set()


def test_affected_controls_detects_added_and_removed():
    prev = {"a.md": "x"}
    new  = {"a.md": "x", "b.md": "y"}
    # b.md was added → affected
    assert "b.md" in affected_controls(prev, new)
    # a.md unchanged → not affected when same text on both sides
    assert "a.md" not in affected_controls(prev, new)
    # a.md removed (present in prev, absent in new) → affected
    assert "a.md" in affected_controls({"a.md": "x"}, {})


# ─── folder_fingerprint ───────────────────────────────────────────── #

def test_folder_fingerprint_is_stable(tmp_path: Path):
    (tmp_path / "a.md").write_text("hello")
    (tmp_path / "b.md").write_text("world")
    fp1 = folder_fingerprint(tmp_path)
    fp2 = folder_fingerprint(tmp_path)
    assert fp1 and fp1 == fp2


def test_folder_fingerprint_changes_on_content_edit(tmp_path: Path):
    f = tmp_path / "a.md"
    f.write_text("hello")
    before = folder_fingerprint(tmp_path)
    f.write_text("hello world")
    after = folder_fingerprint(tmp_path)
    assert before != after


def test_folder_fingerprint_changes_on_new_file(tmp_path: Path):
    (tmp_path / "a.md").write_text("hello")
    before = folder_fingerprint(tmp_path)
    (tmp_path / "b.md").write_text("world")
    after = folder_fingerprint(tmp_path)
    assert before != after


def test_folder_fingerprint_empty_for_missing_dir(tmp_path: Path):
    missing = tmp_path / "nope"
    assert folder_fingerprint(missing) == ""


# ─── FolderWatcher ────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_watcher_fires_on_content_change(tmp_path: Path):
    events = []

    async def on_ev(ev):
        events.append(ev)

    w = FolderWatcher(poll_interval_s=0.01)
    w.on_change(on_ev)
    w.add_watch("pkg-1", "default", tmp_path)
    # First poll on an unchanged seeded fingerprint -> no event.
    await w.poll_once()
    assert events == []
    # Now write a file → fingerprint changes → event fires.
    (tmp_path / "ssp.md").write_text("AC-2 narrative")
    await w.poll_once()
    assert len(events) == 1
    assert events[0].package_id == "pkg-1"


@pytest.mark.asyncio
async def test_watcher_dedupes_unchanged_fingerprint(tmp_path: Path):
    (tmp_path / "ssp.md").write_text("AC-2 narrative")
    fires = []
    w = FolderWatcher(poll_interval_s=0.01)
    w.on_change(lambda ev: fires.append(ev) or asyncio.sleep(0))  # noqa: ARG005
    w.add_watch("pkg-1", "default", tmp_path)
    # First poll: fingerprint already seeded by add_watch → no event.
    await w.poll_once()
    # Second poll: still nothing changed.
    await w.poll_once()
    assert fires == []


# ─── version_diff (signature-only quick diff) ─────────────────────── #

def test_signature_only_diff_counts():
    assert version_diff(["a", "b", "c"], ["b", "c", "d"]) == {
        "new": 1, "resolved": 1, "unchanged": 2,
    }
