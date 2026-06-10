"""Phase II FR-XA-04 — document-level family-coherence flow.

End-to-end proof that when a control narrative is split across paragraphs
(or across artifacts in a package), Tier 2 receives the FULL family scope
as `family_context`, not just the single best-evidence paragraph.

We can't fully prove the LLM judgment changed (that's the live-Ollama
property), but we can prove the data plumbing reaches the analyzer.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models.domain import NormalizedSegment, EvidenceSpan        # noqa: E402
from backend.services.analysis.tier1_retrieval import build_evidence_index  # noqa: E402
from backend.services.analysis.tier2_sufficiency import (                 # noqa: E402
    SufficiencyResult,
    run_tier2,
)
from backend.services.catalog_loader import load_catalog, load_rubric     # noqa: E402

CATALOG = load_catalog(ROOT / "config" / "catalog.yaml")
RUBRIC = load_rubric(ROOT / "config" / "rubric.yaml")


class CapturingAnalyzer:
    """Analyzer that records every kwarg it received. Accepts family_context."""
    name = "capture"; version = "test"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def score(self, *, control_id, objective_text, evidence_text,
              required_elements, required_methods, family_context="") -> SufficiencyResult:
        self.calls.append({
            "control_id": control_id,
            "evidence_text": evidence_text,
            "family_context": family_context,
        })
        return SufficiencyResult("present", "sufficient", "", [], 0.9)


def _seg(art_id: str, cid: str, loc: str, text: str) -> NormalizedSegment:
    return NormalizedSegment(
        artifact_id=art_id, control_hint=cid, text=text, locator=loc,
        char_start=0, char_end=len(text),
    )


def test_family_context_includes_all_AC_paragraphs_across_artifacts():
    """AC-2 in SSP + AC-3 in architecture + more AC-2 in supplemental.
    When scoring any of them, Tier 2 must see ALL three in family_context.
    Texts are realistic length so the lexical tokenizer creates index entries."""
    segments = [
        _seg("ssp.md",   "AC-2", "¶3",
             "Account types are managed by the Information System Security Officer "
             "with quarterly reviews of compliance and enforcement."),
        _seg("arch.md",  "AC-3", "¶7",
             "Access enforcement is performed by the central directory service "
             "across all managed account types."),
        _seg("supp.md",  "AC-2", "¶11",
             "Supplemental account management: PIV authenticators are required for all "
             "privileged accounts at the directory level."),
        _seg("supp.md",  "AU-2", "¶13",
             "Audit event logging captures authentication and authorization events "
             "with a retention period of 365 days."),  # different family
    ]
    index = build_evidence_index(segments, CATALOG)
    analyzer = CapturingAnalyzer()
    run_tier2("r1", index, CATALOG, RUBRIC, analyzer)
    assert analyzer.calls, "expected at least one Tier 2 score() call"

    # Any call on an AC-* control should have family_context containing all
    # three AC paragraphs (regardless of which one is the focal evidence).
    ac_calls = [c for c in analyzer.calls if c["control_id"].startswith("AC-")]
    assert ac_calls, "expected calls on AC-family controls"
    for c in ac_calls:
        fc = c["family_context"]
        assert "Account types are managed" in fc            # AC-2 in ssp.md
        assert "Access enforcement is performed" in fc      # AC-3 in arch.md
        assert "Supplemental account management" in fc      # AC-2 in supp.md
        # AU paragraphs MUST NOT leak into AC family context
        assert "Audit event logging" not in fc


def test_family_context_uses_locator_headers():
    """Each chunk in family_context is prefixed with [CTRL · artifact · locator]
    so the LLM can attribute any contradiction or coherence claim to source."""
    segments = [_seg("ssp.md", "AC-2", "¶3", "managed by ISSO")]
    index = build_evidence_index(segments, CATALOG)
    analyzer = CapturingAnalyzer()
    run_tier2("r2", index, CATALOG, RUBRIC, analyzer)

    ac_calls = [c for c in analyzer.calls if c["control_id"].startswith("AC-")]
    assert any("[AC-2 · ssp.md · ¶3]" in c["family_context"] for c in ac_calls)


def test_single_family_run_has_no_cross_family_leak():
    """Two control families. AC and AU. Each family's context must contain
    only its own paragraphs."""
    segments = [
        _seg("a.md", "AC-2", "¶1",
             "Account management is performed by the directory service quarterly."),
        _seg("a.md", "AU-2", "¶2",
             "Audit logging captures all authentication and configuration events."),
    ]
    index = build_evidence_index(segments, CATALOG)
    analyzer = CapturingAnalyzer()
    run_tier2("r3", index, CATALOG, RUBRIC, analyzer)

    for c in analyzer.calls:
        fam = c["control_id"].split("-")[0]
        if fam == "AC":
            assert "Account management is performed" in c["family_context"]
            assert "Audit logging captures" not in c["family_context"]
        if fam == "AU":
            assert "Audit logging captures" in c["family_context"]
            assert "Account management is performed" not in c["family_context"]


def test_strict_analyzer_still_works_via_safe_dispatch():
    """An older analyzer that doesn't accept family_context must continue
    to work — _safe_score filters kwargs to the analyzer's signature."""
    class StrictAnalyzer:
        name = "strict"; version = "old"
        def __init__(self): self.calls = []
        def score(self, *, control_id, objective_text, evidence_text,
                  required_elements, required_methods) -> SufficiencyResult:
            self.calls.append(control_id)
            return SufficiencyResult("present", "sufficient", "", [], 0.9)

    segments = [_seg("a.md", "AC-2", "¶1",
                     "The organization manages account types and reviews accounts quarterly.")]
    index = build_evidence_index(segments, CATALOG)
    analyzer = StrictAnalyzer()
    run_tier2("r4", index, CATALOG, RUBRIC, analyzer)  # must not raise
    assert "AC-2" in analyzer.calls
