"""Phase II FR-AI-02 — confidence calibration measurement."""
from backend.models.domain import (
    EvidenceSpan, Finding, FindingStatus, FindingType, Severity, Tier,
)
from backend.services.calibration import compute_calibration, reliability_curve_csv


def _f(*, conf: float, status: FindingStatus = FindingStatus.approved,
       cid="AC-2") -> Finding:
    return Finding(
        id=f"f-{conf:.2f}-{status.value}",
        run_id="r1", control_id=cid, type=FindingType.weak_narrative,
        severity=Severity.medium, confidence=conf,
        recommendation="r", rationale="why",
        evidence_spans=[EvidenceSpan(artifact_id="ssp.md", locator="¶1",
                                      quoted_text="x")],
        tier=Tier.t2, status=status,
    )


# ─── empty / unattested cases ─────────────────────────────────────── #

def test_empty_findings_returns_zero_ece():
    r = compute_calibration([])
    assert r.n_total == 0
    assert r.n_attested == 0
    assert r.ece == 0.0
    assert r.monotonic   # vacuously true
    assert len(r.bins) == 10


def test_unattested_findings_are_ignored():
    findings = [
        _f(conf=0.5, status=FindingStatus.unattested),
        _f(conf=0.8, status=FindingStatus.flag_for_review),
    ]
    r = compute_calibration(findings)
    assert r.n_total == 2
    assert r.n_attested == 0    # neither contributes to truth set


# ─── well-calibrated case ─────────────────────────────────────────── #

def test_perfectly_calibrated_model_has_low_ece():
    """Build a synthetic distribution where each bin's approve-rate equals
    its mean confidence."""
    findings = []
    # 0.95 bin → 19 approved, 1 rejected (95% real)
    for i in range(19):
        findings.append(_f(conf=0.95, status=FindingStatus.approved))
    findings.append(_f(conf=0.95, status=FindingStatus.rejected))
    # 0.55 bin → ~55%
    for i in range(11):
        findings.append(_f(conf=0.55, status=FindingStatus.approved))
    for i in range(9):
        findings.append(_f(conf=0.55, status=FindingStatus.rejected))
    # 0.15 bin → ~15%
    for i in range(3):
        findings.append(_f(conf=0.15, status=FindingStatus.approved))
    for i in range(17):
        findings.append(_f(conf=0.15, status=FindingStatus.rejected))

    r = compute_calibration(findings)
    assert r.ece <= 0.20, f"expected low ECE on well-calibrated data, got {r.ece}"
    # Bin 0.9-1.0 should have observed_rate ≈ 0.95
    top = r.bins[-1]
    assert 0.85 <= top.observed_rate <= 1.0


def test_overconfident_model_has_high_ece():
    """Confidence=0.95 but only 30% really approved → ECE is large."""
    findings = []
    for i in range(3):
        findings.append(_f(conf=0.95, status=FindingStatus.approved))
    for i in range(7):
        findings.append(_f(conf=0.95, status=FindingStatus.rejected))
    r = compute_calibration(findings)
    assert r.ece > 0.5, f"expected high ECE for overconfident data, got {r.ece}"
    assert not r.to_dict()["phase_ii_gate"]["overall_pass"]


# ─── monotonicity ─────────────────────────────────────────────────── #

def test_monotonic_when_higher_bins_have_higher_approve_rate():
    findings = []
    # 0.15 bin → 30%
    for i in range(3):
        findings.append(_f(conf=0.15, status=FindingStatus.approved))
    for i in range(7):
        findings.append(_f(conf=0.15, status=FindingStatus.rejected))
    # 0.55 bin → 60%
    for i in range(6):
        findings.append(_f(conf=0.55, status=FindingStatus.approved))
    for i in range(4):
        findings.append(_f(conf=0.55, status=FindingStatus.rejected))
    # 0.95 bin → 90%
    for i in range(9):
        findings.append(_f(conf=0.95, status=FindingStatus.approved))
    findings.append(_f(conf=0.95, status=FindingStatus.rejected))
    r = compute_calibration(findings)
    assert r.monotonic, f"expected monotonic, violations={r.monotonic_violations}"


def test_monotonicity_violation_when_higher_bin_does_worse():
    findings = []
    # Low bin: 90% real
    for i in range(9):
        findings.append(_f(conf=0.15, status=FindingStatus.approved))
    findings.append(_f(conf=0.15, status=FindingStatus.rejected))
    # High bin: 20% real (the model is inverted)
    for i in range(2):
        findings.append(_f(conf=0.95, status=FindingStatus.approved))
    for i in range(8):
        findings.append(_f(conf=0.95, status=FindingStatus.rejected))
    r = compute_calibration(findings)
    assert not r.monotonic
    assert r.monotonic_violations >= 1


# ─── sparse bins ──────────────────────────────────────────────────── #

def test_sparse_bins_do_not_trigger_monotonic_violation():
    """A bin with fewer than `sample_threshold` attestations is reported
    but doesn't count toward monotonicity (otherwise rare events fail us
    spuriously)."""
    findings = [
        # 0.15 bin — 5 approvals, no rejections
        *[_f(conf=0.15, status=FindingStatus.approved) for _ in range(5)],
        # 0.95 bin — 1 rejection, nothing else (sparse!)
        _f(conf=0.95, status=FindingStatus.rejected),
    ]
    r = compute_calibration(findings)
    # The 0.95 bin shouldn't count toward monotonicity
    assert r.monotonic


# ─── CSV output ───────────────────────────────────────────────────── #

def test_reliability_curve_csv_has_header_and_one_row_per_bin():
    r = compute_calibration([])
    csv = reliability_curve_csv(r)
    lines = csv.strip().splitlines()
    assert lines[0] == "bin_lo,bin_hi,n,n_real,mean_confidence,observed_rate"
    assert len(lines) == 11    # header + 10 bins


# ─── to_dict shape ────────────────────────────────────────────────── #

def test_report_to_dict_is_complete():
    r = compute_calibration([_f(conf=0.8, status=FindingStatus.approved)])
    d = r.to_dict()
    assert "ece" in d
    assert "monotonic" in d
    assert "bins" in d
    assert "phase_ii_gate" in d
    gate = d["phase_ii_gate"]
    assert "overall_pass" in gate
    assert gate["ece_max"] == 0.20
