"""Confidence-aware logic (FR-CONF-01) + circuit breaker (FR-CONF-02).

Thresholds come from the rubric (docs/03 §5.2). High-confidence -> emit;
mid -> emit but flagged needs_review; low -> defer (flag_for_review), never assert.
Calibration mapping is applied at WP-6; until then confidence is treated as
uncalibrated and we lean conservative.
"""

from __future__ import annotations

from enum import Enum

from backend.models.domain import Finding, FindingStatus
from backend.services.catalog_loader import Rubric


class Disposition(str, Enum):
    emit = "emit"
    needs_review = "needs_review"
    defer = "defer"


def classify(confidence: float, rubric: Rubric) -> Disposition:
    th = rubric.confidence_thresholds
    if confidence >= th.get("emit", 0.75):
        return Disposition.emit
    if confidence >= th.get("needs_review", 0.50):
        return Disposition.needs_review
    return Disposition.defer


def apply_disposition(finding: Finding, rubric: Rubric) -> Finding:
    """Mutate finding per its confidence disposition. Deterministic (T0) findings
    have confidence 1.0 and always emit."""
    d = classify(finding.confidence, rubric)
    if d is Disposition.needs_review:
        finding.needs_review = True
    elif d is Disposition.defer:
        finding.status = FindingStatus.flag_for_review
    return finding


class CircuitBreaker:
    """Trips an artifact to full human review after `threshold` consecutive
    low-confidence/contradictory analyzer outputs (FR-CONF-02 / DECISION-004).
    Mirrors AXO's circuit_breaker (default 3). NEVER set to 999.
    """

    def __init__(self, threshold: int = 3):
        assert threshold and threshold != 999, "circuit breaker must be the real threshold, not disabled (999)"
        self.threshold = threshold
        self._consecutive = 0
        self.tripped = False

    def observe(self, *, low_confidence: bool) -> bool:
        """Record one analyzer output. Returns True if the breaker is now tripped."""
        if low_confidence:
            self._consecutive += 1
        else:
            self._consecutive = 0
        if self._consecutive >= self.threshold:
            self.tripped = True
        return self.tripped

    def reset(self) -> None:
        self._consecutive = 0
        self.tripped = False
