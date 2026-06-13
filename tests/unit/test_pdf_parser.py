"""PdfParser must split a page into per-control blocks (not one block/page),
so the normalizer can attach a distinct control_hint to each control's
narrative. Without this, cross-artifact consistency collapses every page's
frequency tokens onto the first control id on the page.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.ingest.parsers import _pdf_page_blocks, _pdf_is_heading, parse_artifact  # noqa: E402
from backend.services.ingest.normalizer import normalize  # noqa: E402

fpdf = pytest.importorskip("fpdf")


def _make_pdf(path: Path, sections: list[tuple[str, str]]):
    """sections = [(heading, body), ...]"""
    pdf = fpdf.FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Test Security Document", ln=True)
    pdf.ln(4)
    for heading, body in sections:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, heading, ln=True)
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 6, body)
        pdf.ln(3)
    pdf.output(str(path))


# ── unit: _pdf_is_heading ─────────────────────────────────────────── #

def test_heading_detects_control_id():
    assert _pdf_is_heading("AC-2 Account Management")
    assert _pdf_is_heading("AU-11 Audit Record Retention")
    assert _pdf_is_heading("AC-2(1) Automated System Account Management")

def test_heading_detects_numbered_section():
    assert _pdf_is_heading("3.2 Account Review")
    assert _pdf_is_heading("1. System Identification")

def test_heading_detects_allcaps_title():
    assert _pdf_is_heading("ACCESS CONTROL")

def test_heading_rejects_body_text():
    assert not _pdf_is_heading("Accounts are reviewed monthly by the ISSO.")
    assert not _pdf_is_heading("The organization implements AC-2 across all systems and reviews them.")


# ── unit: _pdf_page_blocks ────────────────────────────────────────── #

def test_page_blocks_split_at_control_headings():
    text = ("AC-2 Account Management\n"
            "Accounts are reviewed monthly by the ISSO.\n"
            "AU-11 Audit Record Retention\n"
            "Audit logs are retained annually.\n")
    blocks = _pdf_page_blocks(text)
    assert len(blocks) == 2
    assert blocks[0][0].startswith("AC-2")
    assert "monthly" in blocks[0][0]
    assert blocks[1][0].startswith("AU-11")
    assert "annually" in blocks[1][0]


# ── integration: real PDF → per-control hints ────────────────────── #

def test_pdf_parse_attaches_distinct_control_hints(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf(pdf_path, [
        ("AC-2 Account Management", "Accounts are reviewed monthly by the ISSO. "
                                    "The enforcement mechanism is the corporate directory."),
        ("AU-11 Audit Record Retention", "Audit logs are retained annually in the audit bucket."),
        ("AT-2 Literacy Training", "Security awareness training is delivered quarterly."),
    ])
    blocks = parse_artifact(pdf_path)
    # More than one block (not collapsed to a single page block).
    assert len(blocks) >= 3, [b.text[:40] for b in blocks]

    segments = normalize("art-pdf", pdf_path)
    hints = {}
    for s in segments:
        if s.control_hint:
            hints.setdefault(s.control_hint, []).append(s.text)
    # Each control's narrative is attributed to its OWN control id.
    assert "AC-2" in hints
    assert "AU-11" in hints
    assert "AT-2" in hints
    # And the frequency token lives under the right control.
    assert any("monthly" in t for t in hints["AC-2"])
    assert any("annually" in t for t in hints["AU-11"])
    assert any("quarterly" in t for t in hints["AT-2"])
