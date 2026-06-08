"""Confidence disposition + circuit breaker tests (FR-CONF-01/02)."""
import pytest

from backend.models.domain import EvidenceSpan, Finding, FindingStatus, FindingType, Severity, Tier
from backend.services.analysis.confidence import CircuitBreaker, Disposition, apply_disposition, classify


def test_classify_thresholds(rubric):
    assert classify(0.9, rubric) == Disposition.emit
    assert classify(0.6, rubric) == Disposition.needs_review
    assert classify(0.4, rubric) == Disposition.defer


def _f(conf):
    return Finding(id="x", run_id="r", control_id="AC-2", type=FindingType.insufficient_evidence,
                   severity=Severity.medium, confidence=conf, recommendation="r",
                   evidence_spans=[EvidenceSpan(artifact_id="a", locator="l", quoted_text="q")],
                   tier=Tier.t2)


def test_low_confidence_defers_not_asserts(rubric):
    f = apply_disposition(_f(0.3), rubric)
    assert f.status == FindingStatus.flag_for_review  # FR-CONF-01: defer, don't assert


def test_mid_confidence_flags_needs_review(rubric):
    f = apply_disposition(_f(0.6), rubric)
    assert f.needs_review and f.status == FindingStatus.unattested


def test_circuit_breaker_trips_at_three():
    cb = CircuitBreaker(3)
    assert not cb.observe(low_confidence=True)   # 1
    assert not cb.observe(low_confidence=True)   # 2
    assert cb.observe(low_confidence=True)        # 3 -> trip
    assert cb.tripped


def test_circuit_breaker_resets_on_good_output():
    cb = CircuitBreaker(3)
    cb.observe(low_confidence=True)
    cb.observe(low_confidence=False)             # reset
    cb.observe(low_confidence=True)
    cb.observe(low_confidence=True)
    assert not cb.tripped                         # only 2 consecutive


def test_breaker_rejects_disabled_999():
    with pytest.raises(AssertionError):           # PRD non-negotiable
        CircuitBreaker(999)
