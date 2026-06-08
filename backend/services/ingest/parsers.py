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


# --------------------------------------------------------------------------- #
def _blocks_from_lines(text: str, label: str) -> list[TextBlock]:
    """Split into paragraph blocks, tracking char offsets for locators."""
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
            if text:
                blocks.append(
                    TextBlock(text=text, locator=f"p{page_no}", char_start=offset, char_end=offset + len(text))
                )
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
