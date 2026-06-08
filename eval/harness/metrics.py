"""Metrics computation per docs/04 §3–4.

Reports:
  * deficiency-detection recall (target ≥ 0.80)
  * false-positive rate (target ≤ 0.20)
  * precision (informational)
  * traceability (must be 1.00)
  * severity-agreement (informational; target ≥ 0.70)
  * confidence calibration (reliability buckets + ECE; demonstrated)

The harness counts coverage-driven `missing` findings against `missing` labels
implied by the baseline (per package `expect_missing_for_baseline_moderate`).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

SEV_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class MetricBucket:
    matched: int = 0
    total: int = 0
    @property
    def rate(self) -> float:
        return (self.matched / self.total) if self.total else 0.0


@dataclass
class CalibrationBucket:
    lo: float
    hi: float
    findings: int = 0
    correct: int = 0
    confs: list[float] = field(default_factory=list)
    @property
    def empirical(self) -> float:
        return (self.correct / self.findings) if self.findings else 0.0
    @property
    def mean_conf(self) -> float:
        return statistics.fmean(self.confs) if self.confs else 0.0


def make_calibration_buckets() -> list[CalibrationBucket]:
    edges = [(0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 0.90), (0.90, 1.0001)]
    return [CalibrationBucket(lo=a, hi=b) for a, b in edges]


def bucket_for(conf: float, buckets: list[CalibrationBucket]) -> CalibrationBucket | None:
    for b in buckets:
        if b.lo <= conf < b.hi:
            return b
    return None


def severity_within_one(a: str, b: str) -> bool:
    return abs(SEV_RANK.get(a, 0) - SEV_RANK.get(b, 0)) <= 1


def expected_ce(buckets: list[CalibrationBucket]) -> float:
    """Expected Calibration Error (weighted mean over buckets)."""
    total = sum(b.findings for b in buckets) or 1
    return sum((b.findings / total) * abs(b.mean_conf - b.empirical) for b in buckets)


def monotonic_in_confidence(buckets: list[CalibrationBucket]) -> bool:
    rates = [b.empirical for b in buckets if b.findings > 0]
    return all(rates[i] <= rates[i + 1] + 0.05 for i in range(len(rates) - 1))
