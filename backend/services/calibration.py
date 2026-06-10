"""Phase II FR-AI-02 — confidence calibration measurement & reliability curve.

A model says it's 0.80-confident on a finding. Is that actually right?
Calibration answers: of all findings the model claimed 0.80, what
fraction were ultimately attested as real (approved/edited)? If a
well-calibrated 0.80 bucket sees 80% approval — and a 0.50 bucket sees
50% — the confidence number is meaningful. If 0.80 confidence
correlates with 30% approval, the model is over-confident; if 0.50
with 90% approval, under-confident.

We measure this against the **attestation record** — the human signal
in the change-request ledger — because that is the only authoritative
truth in QUILL. Unattested findings don't contribute (we don't know if
they're real). Rejected findings count against confidence; approved /
edited count for.

Outputs:
  * 10 bins across [0, 1], each with (n, observed_rate, mean_confidence)
  * monotonicity score: 1.0 means observed_rate increases with bin
  * ECE (Expected Calibration Error): bin-weighted average gap between
    observed_rate and mean_confidence

The Phase II quality gate is **ECE ≤ 0.20** AND monotonic across all
populated bins (where "populated" = ≥ 3 attestations in the bin).

The /calibration/report endpoint returns this in JSON for the UI's
"AI Calibration" admin page (and for the published per-release
reliability curve mandated by P-AI-03).
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from backend.models.domain import Finding, FindingStatus

ATTESTED_REAL = {FindingStatus.approved, FindingStatus.edited}
ATTESTED_NOT_REAL = {FindingStatus.rejected}

DEFAULT_BIN_EDGES = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


@dataclasses.dataclass
class Bin:
    """One bin of the reliability histogram."""
    lo: float
    hi: float
    n: int                         # findings landed in this bin
    n_real: int                    # of those, attested approved/edited
    mean_confidence: float         # mean confidence among landed
    observed_rate: float           # n_real / n  (0 if n == 0)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class CalibrationReport:
    """The full calibration measurement for a program (or all tenants)."""
    n_total: int
    n_attested: int
    bins: list[Bin]
    ece: float                     # Expected Calibration Error
    monotonic: bool
    monotonic_violations: int
    sample_threshold: int = 3      # bins below this don't count

    def to_dict(self) -> dict:
        return {
            "n_total": self.n_total,
            "n_attested": self.n_attested,
            "ece": round(self.ece, 4),
            "monotonic": self.monotonic,
            "monotonic_violations": self.monotonic_violations,
            "sample_threshold": self.sample_threshold,
            "bins": [b.to_dict() for b in self.bins],
            "phase_ii_gate": {
                "ece_max":   0.20,
                "ece_pass":  self.ece <= 0.20,
                "monotonic_pass": self.monotonic,
                "overall_pass": (self.ece <= 0.20) and self.monotonic,
            },
        }


def _bin_for(conf: float, edges: list[float]) -> int:
    """Return the index of the bin containing `conf`. Right-edge inclusive
    on the top bin so confidence=1.0 lands in the last bin."""
    if conf < edges[0]:
        return 0
    for i in range(len(edges) - 1):
        if edges[i] <= conf < edges[i + 1]:
            return i
    return len(edges) - 2  # confidence == 1.0


def compute_calibration(
    findings: list[Finding],
    *,
    bin_edges: Optional[list[float]] = None,
    sample_threshold: int = 3,
) -> CalibrationReport:
    """Compute the reliability curve + ECE + monotonicity from attested findings.

    `findings` should be the COMPLETE finding set you want to measure —
    typically every finding in a program ever, possibly filtered by
    program/run/time. Unattested findings are silently dropped (no ground
    truth). Flagged-for-review are also dropped — they're explicit deferrals,
    not assertions.

    Bins with fewer than `sample_threshold` attestations are reported but
    not counted toward the monotonicity check (otherwise a single
    rejection in a sparse bin can fail the gate spuriously).
    """
    edges = bin_edges or DEFAULT_BIN_EDGES
    nbins = len(edges) - 1

    # Filter to ground-truth findings.
    judged = [f for f in findings if f.status in (ATTESTED_REAL | ATTESTED_NOT_REAL)]
    n_total = len(findings)
    n_attested = len(judged)

    # Per-bin accumulators.
    bin_conf_sum = [0.0] * nbins
    bin_n        = [0]   * nbins
    bin_real     = [0]   * nbins
    for f in judged:
        i = _bin_for(f.confidence, edges)
        bin_conf_sum[i] += f.confidence
        bin_n[i] += 1
        if f.status in ATTESTED_REAL:
            bin_real[i] += 1

    bins: list[Bin] = []
    for i in range(nbins):
        n = bin_n[i]
        bins.append(Bin(
            lo=edges[i],
            hi=edges[i + 1],
            n=n,
            n_real=bin_real[i],
            mean_confidence=(bin_conf_sum[i] / n) if n > 0 else (edges[i] + edges[i + 1]) / 2,
            observed_rate=(bin_real[i] / n) if n > 0 else 0.0,
        ))

    # ECE — bin-weighted gap between observed rate and mean confidence.
    if n_attested == 0:
        ece = 0.0
    else:
        ece = sum(
            (b.n / n_attested) * abs(b.observed_rate - b.mean_confidence)
            for b in bins if b.n > 0
        )

    # Monotonicity over POPULATED bins only.
    populated = [b for b in bins if b.n >= sample_threshold]
    violations = 0
    for a, b in zip(populated, populated[1:]):
        if b.observed_rate < a.observed_rate:
            violations += 1
    monotonic = (violations == 0)

    return CalibrationReport(
        n_total=n_total, n_attested=n_attested, bins=bins, ece=ece,
        monotonic=monotonic, monotonic_violations=violations,
        sample_threshold=sample_threshold,
    )


def reliability_curve_csv(report: CalibrationReport) -> str:
    """Render the reliability curve as CSV (one row per bin) for inclusion
    in a release note or external plot tool."""
    rows = ["bin_lo,bin_hi,n,n_real,mean_confidence,observed_rate"]
    for b in report.bins:
        rows.append(f"{b.lo:.2f},{b.hi:.2f},{b.n},{b.n_real},"
                    f"{b.mean_confidence:.4f},{b.observed_rate:.4f}")
    return "\n".join(rows) + "\n"
