# QUILL Eval Report

- **Generated:** 2026-06-08T13:47:48.893691+00:00
- **Analyzer:** `mock`
- **Packages:** 12
- **Findings emitted:** 83
- **Labels:** 13  ·  Expected missing: 43

## Gates

| Gate | Target | Result | Pass |
|---|---|---|:---:|
| Deficiency-detection recall | ≥ 0.80 | **0.98** | ✅ |
| False-positive rate         | ≤ 0.20 | **0.11** | ✅ |
| Traceability                | = 1.00 | **1.00** | ✅ |
| Confidence calibration      | monotonic + ECE ≤ 0.20 | **monotonic=True, ECE=0.0639** | ✅ |

**Overall:** ✅ ALL GATES PASSED

## Recall breakdown

- Narrative recall (per labelled deficiency): **0.92**
- Coverage recall (`missing` for baseline): **1.00**
- Inconsistency recall (cross-artifact contradictions): **1.00**

## Precision

- Precision: **0.89**  ·  Severity agreement (±1 level): **1.00**

## Confidence calibration

| Range | Findings | Empirical correct | Mean confidence |
|---|---:|---:|---:|
| 0.50–0.60 | 0 | 0.00 | 0.00 |
| 0.60–0.70 | 0 | 0.00 | 0.00 |
| 0.70–0.80 | 7 | 0.71 | 0.70 |
| 0.80–0.90 | 0 | 0.00 | 0.00 |
| 0.90–1.00 | 76 | 0.91 | 0.98 |

_Monotonic in confidence: True; ECE = 0.0639._

## Per-package detail

| Package | Artifacts | Labels | Matched | Findings | Expected missing |
|---|---|---:|---:|---:|---|
| `pkg_weak_ac2` | syn_01_weak_ac2.md | 2 | 2 | 10 | CM-2, IA-2, SC-7, SI-4 |
| `pkg_good_full` | syn_02_good_full.md | 0 | 0 | 4 | — |
| `pkg_arch_conflict` | syn_07_minimal_only_ac2.md, syn_11_arch_freq_conflict.md | 1 | 1 | 7 | AU-2, CM-2, IA-2, SC-7, SI-4 |
| `pkg_odp_placeholders` | syn_04_odp_placeholders.md | 2 | 2 | 9 | AC-2, IA-2, SC-7, SI-4 |
| `pkg_partial_au2` | syn_05_partial_au2.md | 1 | 1 | 7 | CM-2, IA-2, SC-7, SI-4 |
| `pkg_doc_boundary` | syn_06_doc_boundary.md | 1 | 0 | 5 | AC-2, AU-2, CM-2, SI-4 |
| `pkg_generic_ac2` | syn_08_generic_ac2.md | 2 | 2 | 9 | AU-2, CM-2, SC-7, SI-4 |
| `pkg_oscal_weak` | syn_10_oscal_weak.json | 2 | 2 | 10 | CM-2, IA-2, SC-7, SI-4 |
| `pkg_compat_arch` | syn_02_good_full.md, syn_09_arch_compat.md | 0 | 0 | 4 | — |
| `pkg_au2_weak` | syn_13_au2_weak.md | 1 | 1 | 7 | AC-2, CM-2, IA-2, SC-7, SI-4 |
| `pkg_cm2_minimal` | syn_14_cm2_minimal.md | 1 | 1 | 7 | AC-2, AU-2, IA-2, SC-7, SI-4 |
| `pkg_sc7_si4` | syn_12_sc7_si4_addressed.md | 0 | 0 | 4 | AC-2, AU-2, CM-2, IA-2 |