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


# A block is treated as a "section anchor" only when it looks like a heading.
# Otherwise a paragraph like "Account events are logged per AU-2" — which sits
# under the AC-2 section but mentions AU-2 — would be re-keyed to AU-2 and the
# narrative would lose its real section context. Distinguishing headings from
# body text fixes that.
_HEADING_RE = re.compile(
    r"""^\s*(?:
            \#{1,6}\s+            |   # markdown heading: # / ## / ### …
            \*{1,2}[^*]{0,80}\*{1,2}\s*$  | # bold-only line: **AC-2 Account Management**
            [A-Z]{2}-\d{1,3}(?:\(\d+\))?  \s+[A-Z]    # bare 'AC-2 Account Mgmt …'
        )""",
    re.VERBOSE,
)


def _looks_like_heading(text: str) -> bool:
    """Heuristic: does this block start a section?

    True for `## AC-2 ...`, `**AC-2 Title**`, and short `AC-2 Account Mgmt …`
    headings. False for ordinary prose that merely mentions a control id.
    """
    head = text.lstrip()
    if not head:
        return False
    return bool(_HEADING_RE.match(head))


def normalize(artifact_id: str, path: Path) -> list[NormalizedSegment]:
    """Parse + segment + key by control. Raises ParseError on corrupt input.

    Section carry-forward: documents put the control id in a heading (e.g.
    '## AC-2') and the narrative in following paragraphs. The most recently
    seen control hint is propagated to subsequent segments until a NEW heading
    is encountered. Critically: control ids mentioned in *body text* are
    treated as references (not new section anchors) so a paragraph like
    "Account events are logged per AU-2" stays under its AC-2 section instead
    of getting re-keyed to AU-2.

    Parser-supplied hints (e.g. OSCAL's structured `control-id`) override
    the heuristic and reset the current control per block.
    """
    blocks = parse_artifact(path)
    segments: list[NormalizedSegment] = []
    current_control: str | None = None
    for b in blocks:
        hint = b.control_hint
        if hint is None:
            if _looks_like_heading(b.text):
                ids = detect_control_ids(b.text)
                if ids:
                    hint = ids[0]
                    current_control = hint
                else:
                    hint = current_control
            else:
                hint = current_control  # body text → carry forward
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
