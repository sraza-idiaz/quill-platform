"""Normalization (FR-ING-02/03): parse an artifact into control-keyed segments
with preserved locators, and compute the content hash.

Control detection here is *deterministic* only (regex on control IDs like 'AC-2').
Semantic mapping of free text -> control is Tier 1's job (FR-T1-01); the normalizer
just captures explicit references so Tier 0 can do coverage checks without an LLM.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from backend.models.domain import NormalizedSegment
from backend.services.ingest.parsers import parse_artifact

# Control id pattern, e.g. AC-2, AU-12, SC-7(3)
CONTROL_RE = re.compile(r"\b([A-Z]{2})-(\d{1,3})(?:\(\d+\))?\b")


def compute_hash(path: Path) -> str:
    """SHA-256 of raw bytes (FR-ING-03)."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def detect_control_ids(text: str) -> list[str]:
    """Return normalized control ids explicitly referenced in text."""
    out: list[str] = []
    for fam, num in CONTROL_RE.findall(text):
        cid = f"{fam}-{int(num)}"
        if cid not in out:
            out.append(cid)
    return out


def normalize(artifact_id: str, path: Path) -> list[NormalizedSegment]:
    """Parse + segment + key by control. Raises ParseError on corrupt input.

    Section carry-forward: documents put the control id in a heading (e.g.
    '## AC-2') and the narrative in following paragraphs. We propagate the most
    recently seen control hint to subsequent segments until a new control id
    appears, so the body text is keyed to its control for Tier 0 coverage and
    required-field checks. Parser-supplied hints (e.g. OSCAL) reset it per block.
    """
    blocks = parse_artifact(path)
    segments: list[NormalizedSegment] = []
    current_control: str | None = None
    for b in blocks:
        hint = b.control_hint
        if hint is None:
            ids = detect_control_ids(b.text)
            if ids:
                hint = ids[0]
                current_control = hint
            else:
                hint = current_control  # carry forward from the last heading
        else:
            current_control = hint
        segments.append(
            NormalizedSegment(
                artifact_id=artifact_id,
                text=b.text,
                locator=b.locator,
                char_start=b.char_start,
                char_end=b.char_end,
                control_hint=hint,
            )
        )
    return segments
