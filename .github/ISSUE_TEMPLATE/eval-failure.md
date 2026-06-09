---
name: "Eval Gate Failure"
about: "Report a Phase I eval gate failure or regression"
title: "[Eval]: "
labels: "type: eval, priority: high"
assignees: ''
---

## Eval Gate Affected

- [ ] Precision (>= 0.85)
- [ ] Recall (>= 0.75)
- [ ] F1 (>= 0.80)
- [ ] Citation accuracy
- [ ] Confidence calibration
- [ ] Rework reduction (vs. baseline)
- [ ] Other: ___

## Tier(s) Affected

- [ ] T0 (deterministic)
- [ ] T1 (rule-based)
- [ ] T2 (LLM-assisted)
- [ ] T3 (full LLM)

## Current vs. Required Metric

- **Current:** [e.g., precision = 0.78]
- **Required:** [e.g., >= 0.85]
- **Gap:** [e.g., -0.07]

## Eval Run Reference

- Run ID / commit hash:
- Report path:
- Synthetic corpus version:

## Hypothesis

What you think is causing the regression.

## Reproduction

```bash
# Commands to reproduce
```
