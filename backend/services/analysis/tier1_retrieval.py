"""Tier 1 — retrieval + extraction (FR-T1-01..03). Local, no cloud.

Maps normalized segments to candidate control IDs and 800-53A objectives, and
builds an evidence index where each entry carries a source span and a retrieval
score. The Phase I baseline is deterministic lexical scoring (no model download,
fully air-gap-safe, testable); the EvidenceIndexEntry interface is unchanged when
local embeddings replace the scorer (DECISION-010 / T-3.1 follow-up).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.models.domain import EvidenceSpan, NormalizedSegment
from backend.services.catalog_loader import Catalog

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "is", "are", "be",
    "by", "on", "at", "as", "that", "this", "with", "which", "organization",
    "defined", "system", "information", "control",
}


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2}


@dataclass
class EvidenceIndexEntry:
    control_id: str
    objective_id: str | None
    span: EvidenceSpan
    score: float                     # retrieval score 0-1 (FR-T1-03)
    segment_text: str = field(repr=False, default="")


def _span(seg: NormalizedSegment) -> EvidenceSpan:
    return EvidenceSpan(
        artifact_id=seg.artifact_id, locator=seg.locator,
        quoted_text=seg.text[:500], char_start=seg.char_start, char_end=seg.char_end,
    )


def build_evidence_index(
    segments: list[NormalizedSegment], catalog: Catalog, min_score: float = 0.0
) -> list[EvidenceIndexEntry]:
    """Build the evidence index (FR-T1-02). Each segment maps to control/objective
    candidates with a score and a source span."""
    entries: list[EvidenceIndexEntry] = []
    for seg in segments:
        seg_tokens = _tokens(seg.text)
        if not seg_tokens:
            continue

        # Explicit control hint (from heading/OSCAL) is a strong signal.
        candidate_ids = []
        if seg.control_hint and catalog.get_control(seg.control_hint):
            candidate_ids = [seg.control_hint]
        else:
            candidate_ids = list(catalog.controls.keys())

        for cid in candidate_ids:
            control = catalog.get_control(cid)
            if not control:
                continue
            objectives = catalog.objectives_for(cid)
            base = 0.6 if seg.control_hint == cid else 0.0
            # Score against each objective; keep the best per objective.
            for obj in objectives:
                obj_tokens = _tokens(obj.text) | _tokens(control.title)
                if not obj_tokens:
                    overlap = 0.0
                else:
                    overlap = len(seg_tokens & obj_tokens) / len(obj_tokens)
                score = min(1.0, base + overlap)
                if score > min_score:
                    entries.append(
                        EvidenceIndexEntry(
                            control_id=cid, objective_id=obj.objective_id,
                            span=_span(seg), score=round(score, 3), segment_text=seg.text,
                        )
                    )
    entries.sort(key=lambda e: (-e.score, e.control_id, e.objective_id or ""))
    return entries


def best_evidence_per_objective(
    entries: list[EvidenceIndexEntry],
) -> dict[tuple[str, str], EvidenceIndexEntry]:
    """Reduce the index to the strongest evidence per (control, objective)."""
    best: dict[tuple[str, str], EvidenceIndexEntry] = {}
    for e in entries:
        key = (e.control_id, e.objective_id or "")
        if key not in best or e.score > best[key].score:
            best[key] = e
    return best
