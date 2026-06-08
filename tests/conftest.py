"""Shared test fixtures."""
import sys
from pathlib import Path

import pytest

# Make the repo root importable (so `backend...` resolves) regardless of CWD.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.catalog_loader import load_catalog, load_rubric  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def catalog():
    return load_catalog(ROOT / "config" / "catalog.yaml")


@pytest.fixture(scope="session")
def rubric():
    return load_rubric(ROOT / "config" / "rubric.yaml")


@pytest.fixture
def fixtures_dir():
    return FIXTURES


# --------------------------------------------------------------------------- #
# Deterministic Tier 2 analyzer double (stands in for the local LLM in tests).
# --------------------------------------------------------------------------- #
from backend.services.analysis.tier2_sufficiency import SufficiencyResult  # noqa: E402

_WEAK_MARKERS = [
    "organization-defined",
    "in accordance with policy",
    "manages information system accounts",
]


class MockAnalyzer:
    name = "mock"
    version = "test-1"

    def score(self, *, control_id, objective_text, evidence_text,
              required_elements, required_methods) -> SufficiencyResult:
        text = evidence_text.lower()
        if not text.strip():
            return SufficiencyResult("absent", "insufficient", "no narrative", required_elements, 0.95)

        # Doc-boundary: needs interview/test AND evidence is thin -> not determinable.
        weak = any(m in text for m in _WEAK_MARKERS) or len(evidence_text) < 80
        if weak and ({"interview", "test"} & set(required_methods)):
            return SufficiencyResult(
                "present", "not_determinable_from_docs",
                "requires interview/test to confirm", [], 0.7)
        if weak:
            missing = [e for e in required_elements
                       if not any(w in text for w in e.split("_"))]
            return SufficiencyResult("present", "insufficient",
                                     "generic restatement; lacks specifics", missing, 0.9)

        missing = [e for e in required_elements
                   if not any(w in text for w in e.split("_"))]
        if missing:
            return SufficiencyResult("present", "partial",
                                     "addresses topic but incomplete", missing, 0.6)
        return SufficiencyResult("present", "sufficient", "evidence is clear and complete", [], 0.85)


@pytest.fixture
def mock_analyzer():
    return MockAnalyzer()
