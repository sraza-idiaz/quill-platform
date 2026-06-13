"""Artifact parsers (FR-ING-01). Pluggable: adding a format = implementing
the Parser interface, no core change (NFR-MNT-02).

Each parser returns plain text plus a list of (text, locator, char_start, char_end)
blocks so the normalizer can preserve source locators (FR-ING-02). MD/text and
OSCAL JSON are pure-Python; PDF/DOCX use optional libs and degrade with a clear
error if the lib is absent (FR-ING-05).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class TextBlock:
    text: str
    locator: str
    char_start: int
    char_end: int
    control_hint: str | None = None


class ParseError(Exception):
    """Raised for corrupted/unparseable artifacts (FR-ING-05)."""


class Parser(Protocol):
    suffixes: tuple[str, ...]

    def parse(self, path: Path) -> list[TextBlock]: ...


import re as _re

# A line that starts a markdown heading. Used as an implicit block boundary
# so authors who write headings without a preceding blank line (very common
# in RMF drafts: `... text.\n## AU-2 Event Logging\n...`) still get separate
# blocks per section.
_HEADING_LINE_RE = _re.compile(r"\n(?=#{1,6}\s)")

# Heading detection for PDF-extracted text (no markdown markers survive PDF
# extraction). A line is treated as a section boundary when it looks like a
# control heading ("AC-2 Account Management"), a numbered section ("3.2
# Account Review"), or a short ALL-CAPS title ("ACCESS CONTROL").
_PDF_CTRL_HEAD_RE = _re.compile(r"^[A-Z]{2}-\d{1,3}(?:\(\d+\))?(?:\s|$)")
_PDF_NUM_HEAD_RE  = _re.compile(r"^\d+(?:\.\d+)*\.?\s+[A-Z]")


def _pdf_is_heading(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 80:
        return False
    if _PDF_CTRL_HEAD_RE.match(s):
        return True
    if _PDF_NUM_HEAD_RE.match(s):
        return True
    # Short ALL-CAPS title (letters mostly uppercase, no sentence punctuation).
    letters = [c for c in s if c.isalpha()]
    if letters and len(s) <= 60 and sum(c.isupper() for c in letters) / len(letters) > 0.85 \
       and not s.endswith((".", ":", ";")):
        return True
    return False


def _pdf_page_blocks(text: str) -> list[tuple[str, int]]:
    """Split one PDF page's extracted text into (block_text, rel_start) pairs.

    A new block starts at every heading-like line (so each control section is
    its own block) and after blank lines. rel_start is the character offset of
    the block within `text` (best-effort, for source locators)."""
    lines = text.split("\n")
    out: list[tuple[str, int]] = []
    cur: list[str] = []
    cur_start = 0
    pos = 0

    def flush():
        nonlocal cur
        if cur:
            chunk = "\n".join(cur).strip()
            if chunk:
                out.append((chunk, cur_start))
        cur = []

    for ln in lines:
        line_len = len(ln) + 1  # + newline
        stripped = ln.strip()
        if not stripped:
            flush()
            pos += line_len
            continue
        if _pdf_is_heading(ln) and cur:
            flush()
            cur_start = pos
        if not cur:
            cur_start = pos
        cur.append(ln)
        pos += line_len
    flush()
    return out if out else [(text.strip(), 0)]


# --------------------------------------------------------------------------- #
def _blocks_from_lines(text: str, label: str) -> list[TextBlock]:
    """Split into paragraph blocks, tracking char offsets for locators.

    Block boundaries are blank lines OR markdown heading lines — so a
    section that wasn't separated by a blank line still becomes its own
    block. This matters for downstream control-keying: without it, a whole
    document with only single-newline separators collapses into one mega-
    block and every paragraph gets attributed to the first section's id.
    """
    # Insert an explicit blank line before any heading that doesn't have
    # one. This preserves the source text's character offsets in the
    # transformed string (we only ADD characters; existing ones stay put,
    # which is what `text.find(para, offset)` relies on).
    text = _HEADING_LINE_RE.sub("\n\n", text)

    blocks: list[TextBlock] = []
    offset = 0
    para_no = 0
    for para in text.split("\n\n"):
        start = text.find(para, offset)
        if start < 0:
            start = offset
        end = start + len(para)
        offset = end
        stripped = para.strip()
        if stripped:
            para_no += 1
            blocks.append(
                TextBlock(text=stripped, locator=f"{label}¶{para_no}", char_start=start, char_end=end)
            )
    return blocks


class MarkdownParser:
    suffixes = (".md", ".markdown", ".txt")

    def parse(self, path: Path) -> list[TextBlock]:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            raise ParseError(f"Cannot read {path.name}: {e}") from e
        return _blocks_from_lines(text, label=path.name)


class OscalParser:
    """Parses OSCAL SSP/component JSON, extracting control-implementation
    statements keyed by control id (FR-ING-04)."""

    suffixes = (".json",)

    def parse(self, path: Path) -> list[TextBlock]:
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as e:  # noqa: BLE001
            raise ParseError(f"Invalid OSCAL JSON {path.name}: {e}") from e

        blocks: list[TextBlock] = []
        # Walk OSCAL implemented-requirements (SSP) or control-implementations.
        ssp = data.get("system-security-plan", data)
        impl = ssp.get("control-implementation", {})
        reqs = impl.get("implemented-requirements", [])
        for req in reqs:
            control_id = (req.get("control-id") or "").upper()
            # statements -> by-components -> description (simplified mapping)
            chunks: list[str] = []
            for stmt in req.get("statements", []):
                for comp in stmt.get("by-components", []):
                    desc = comp.get("description")
                    if desc:
                        chunks.append(desc)
            if not chunks and req.get("remarks"):
                chunks.append(req["remarks"])
            text = "\n".join(chunks).strip()
            if text:
                start = raw.find(text)
                blocks.append(
                    TextBlock(
                        text=text,
                        locator=f"oscal:{control_id}",
                        char_start=max(start, 0),
                        char_end=max(start, 0) + len(text),
                        control_hint=control_id or None,
                    )
                )
        if not blocks:
            raise ParseError(f"No implemented-requirements found in {path.name}")
        return blocks


class PdfParser:
    suffixes = (".pdf",)

    def parse(self, path: Path) -> list[TextBlock]:
        try:
            from pypdf import PdfReader
        except ImportError as e:  # pragma: no cover
            raise ParseError("pypdf not installed; cannot parse PDF") from e
        try:
            reader = PdfReader(str(path))
        except Exception as e:  # noqa: BLE001
            raise ParseError(f"Corrupted PDF {path.name}: {e}") from e
        blocks: list[TextBlock] = []
        offset = 0
        for page_no, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            # CRITICAL: do NOT emit one block per page. The cross-artifact
            # consistency check keys every segment by control_hint, which the
            # normalizer derives from the START of each block. A whole-page
            # block would tag the entire page with the first control id it
            # sees, collapsing per-control attribution. Split each page into
            # per-section blocks at heading boundaries (control-id lines,
            # numbered/ALL-CAPS section titles) so each control's narrative
            # is its own block and gets its own hint.
            for sub_text, rel_start in _pdf_page_blocks(text):
                start = offset + rel_start
                blocks.append(
                    TextBlock(text=sub_text, locator=f"p{page_no}",
                              char_start=start, char_end=start + len(sub_text)))
            offset += len(text)
        if not blocks:
            raise ParseError(f"No extractable text in {path.name}")
        return blocks


class DocxParser:
    suffixes = (".docx",)

    def parse(self, path: Path) -> list[TextBlock]:
        try:
            import docx  # python-docx
        except ImportError as e:  # pragma: no cover
            raise ParseError("python-docx not installed; cannot parse DOCX") from e
        try:
            document = docx.Document(str(path))
        except Exception as e:  # noqa: BLE001
            raise ParseError(f"Corrupted DOCX {path.name}: {e}") from e
        blocks: list[TextBlock] = []
        offset = 0
        for i, para in enumerate(document.paragraphs, start=1):
            text = para.text.strip()
            if text:
                blocks.append(
                    TextBlock(text=text, locator=f"§{i}", char_start=offset, char_end=offset + len(text))
                )
                offset += len(text)
        if not blocks:
            raise ParseError(f"No text in {path.name}")
        return blocks


_PARSERS: list[Parser] = [MarkdownParser(), OscalParser(), PdfParser(), DocxParser()]


def get_parser(path: Path) -> Parser:
    suffix = path.suffix.lower()
    for p in _PARSERS:
        if suffix in p.suffixes:
            return p
    raise ParseError(f"Unsupported artifact type: {suffix}")


def parse_artifact(path: Path) -> list[TextBlock]:
    return get_parser(path).parse(path)
