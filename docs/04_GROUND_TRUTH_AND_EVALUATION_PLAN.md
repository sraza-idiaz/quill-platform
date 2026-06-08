# 04 — Ground-Truth Dataset & Evaluation Plan

> Phase I success is **defined** by measured metrics (recall ≥ 80%, false-positive rate ≤ 20%, traceability = 100%, calibration demonstrated). This document specifies **where the test artifacts come from**, **how they are labeled**, and **exactly how each metric is computed**. Without this, the Phase I deliverable "quantitative assessment of rework reduction" cannot be produced. **Build the dataset and harness from day one** (parallel with the engine), not at the end.

---

## 1. The data problem (and the solution)

Real DLA RMF packages are **CUI / ITAR-restricted** and cannot be freely used as a test corpus in a non-ATO sandbox. So QUILL's ground truth is built from three sources, in priority order:

| Source | Description | Use |
|---|---|---|
| **S1 — Synthetic seeded artifacts** (primary) | We author realistic SSP / control-implementation / architecture artifacts and **deliberately seed known deficiencies** (missing controls, generic narratives, unfilled ODPs, cross-artifact contradictions). Because we seed them, the ground-truth labels are exact. | Core recall / FP / calibration measurement. |
| **S2 — Public / sample RMF & OSCAL artifacts** | NIST OSCAL example SSPs, FedRAMP templates, public sample SSPs. Labeled by our reviewer. | Realism + generalization check. |
| **S3 — Sanitized historical artifacts** (if available, with TPOC approval) | De-identified draft artifacts the TPOC can share for the sandbox. | Highest realism; used only if cleared. |

**S1 is the backbone** — it gives precise, defensible labels and is fully shareable. S2 adds realism. S3 is opportunistic.

> Record in `DECISIONS.md`: the final corpus composition and counts. Target Phase I corpus: **≥ 30 artifacts** spanning ≥ 5 control families, with **≥ 100 seeded/labeled deficiencies** total.

## 2. Deficiency taxonomy for labeling

Every labeled deficiency uses the finding types from `03_…RUBRIC` §4:

`missing` · `inconsistent` · `weak_narrative` · `insufficient_evidence` · `narrative_present_evidence_unclear` · (advisory) `not_determinable_from_docs`

Each label record:

```yaml
label_id: GT-0001
artifact_id: synthetic_ssp_03
control_id: AC-2
determination_statement_id: AC-2_obj.1_det.a
deficiency_type: insufficient_evidence
severity_expected: high
source_span: { locator: "p4 §2.1", quoted_text: "The organization manages information system accounts." }
seeded: true                      # true for S1; false (reviewer-judged) for S2/S3
notes: "Generic restatement; no ODP, no roles."
```

Labels live in `eval/ground_truth/*.yaml`, versioned. A **second reviewer** double-labels a ≥ 20% sample to measure inter-rater agreement (report Cohen's κ; target ≥ 0.7). Disagreements are adjudicated and the rule recorded.

## 3. Metrics — exact definitions

A QUILL finding **matches** a ground-truth label when: same `control_id`, compatible `deficiency_type` (per the equivalence table below), **and** the finding's source span **overlaps** the label's span (any character overlap on the same artifact/locator). Span overlap is mandatory — a "right control, wrong location" hit does **not** count (this enforces traceability).

**Type-equivalence for matching:** `insufficient_evidence` ↔ `narrative_present_evidence_unclear` ↔ `weak_narrative` are treated as a single "evidence-deficiency" class for recall (they are gradations of the same human judgment); `missing` and `inconsistent` match only themselves.

| Metric | Definition | Target | Phase I gate |
|---|---|---|---|
| **Deficiency-detection recall** | `matched_labels / total_labels` | ≥ 80% | ✅ |
| **False-positive (low-value) rate** | `unmatched_findings / total_findings_emitted` (findings not corresponding to any label, after human review confirms they're not valid catches) | ≤ 20% | ✅ |
| **Precision** (reported alongside FP) | `matched_findings / total_findings_emitted` | report | — |
| **Traceability** | fraction of emitted findings whose source span is verbatim-present in the artifact | = 100% | ✅ |
| **Confidence calibration** | correlation between confidence buckets and empirical correctness (reliability curve / ECE) | demonstrated | ✅ |
| **Severity agreement** | fraction where QUILL severity matches expected within ±1 level | report (target ≥ 70%) | — |

> **On false positives:** an "unmatched finding" is reviewed by a human before counting against FP rate — a real deficiency we didn't seed but that is genuinely valid is **not** a false positive (it's a bonus catch). This prevents penalizing correct findings just because the label set is finite.

## 4. Confidence-calibration methodology

1. Bucket emitted findings by confidence (e.g., [0.5–0.6), [0.6–0.7), …, [0.9–1.0]).
2. For each bucket, compute empirical correctness = `matched / total in bucket` (using human-confirmed correctness).
3. Plot the **reliability curve** (mean predicted confidence vs. empirical correctness) and compute **Expected Calibration Error (ECE)**.
4. **Pass criterion:** monotonic relationship (higher confidence → higher correctness) and ECE below an agreed bound (record bound in `DECISIONS.md`).
5. If miscalibrated, apply a post-hoc calibration map (e.g., isotonic/Platt scaling) — **not** fine-tuning (deferred to Phase II per the PRD). Record the mapping.

This satisfies "confidence calibration demonstrated (score correlates with human agreement)."

## 5. The evaluation harness (`eval/`)

```
eval/
  ground_truth/         # labeled YAML (§2)
  artifacts/            # S1/S2/S3 source artifacts
  harness/
    run_eval.py         # runs the full pipeline over the corpus, collects findings
    match.py            # finding↔label matching (§3)
    metrics.py          # recall, FP, precision, traceability, calibration, severity
    report.py           # emits the eval report + reliability curve
  reports/              # timestamped eval runs (committed for the Phase I deliverable)
```

- The harness runs **deterministically** for T0; for T2, fix the model + seed and record `model+version` per run (provenance).
- Every eval run produces a dated report under `eval/reports/` — these reports **are** the Phase I "quantitative assessment" evidence.
- Harness runs in CI (on the synthetic corpus) so regressions in recall/FP are caught.

## 6. Rework-reduction assessment (Phase I deliverable)

The DLA topic requires a **quantitative + qualitative assessment of potential rework reduction**. Methodology:

- **Quantitative:** For the labeled corpus, compute deficiencies QUILL surfaces **before** formal review that would otherwise trigger a package rejection / rework cycle. Estimate rework reduction as `(deficiencies caught pre-review × avg rework cost per deficiency)`. Use a documented, conservative assumption set (record assumptions; do **not** overclaim). Report as a range, not a point estimate.
- **Qualitative:** Walk an RMF assessor (or the TPOC, if available) through the finding-review workflow; capture structured feedback on whether QUILL's findings are the kind that drive real rework. Record verbatim where permitted.
- **Honesty:** explicitly state the limits — document-only analysis, synthetic-corpus caveats, methods-vs-evidence boundary (`03` §3.3). This feeds the **methods & limitations** deliverable.

## 7. Acceptance gate mapping

| `08_RTM` gate | Met by |
|---|---|
| Recall ≥ 80% | §3 recall on ground-truth set |
| FP ≤ 20% | §3 FP rate (human-confirmed) |
| Traceability = 100% | §3 traceability metric |
| Calibration demonstrated | §4 reliability curve + ECE |
| Rework-reduction assessment | §6 |

## 8. Anti-overfitting discipline

- Keep a **held-out slice** (≥ 20% of the corpus) the engineers do not inspect while tuning prompts/rubric; report metrics on the held-out slice separately.
- Do not tune the rubric to pass a specific labeled item; tune to the **criteria** in `03`.
- No fine-tuning in Phase I (PRD). Calibration mapping only.
