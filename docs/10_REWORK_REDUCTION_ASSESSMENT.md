# 10 — Rework-Reduction Assessment (DLA Phase I deliverable)

> Required by the DLA topic: *"a quantitative and qualitative assessment of
> potential reductions in rework."* This document assesses how QUILL's findings
> map to the rework cycles that actually delay RMF package acceptance, and
> reports a **conservative range** rather than a point estimate.
> Methodology per `docs/04 §6`.

---

## 1. What "rework" means here

In the RMF context the DLA topic describes, **rework** is any deficiency that
sends a draft package back from formal cybersecurity review to the project
team for revision. Common drivers (per assessor practice and 800-53A method):

1. **Missing controls** — required by the baseline but absent.
2. **Inconsistencies** — same control described differently across artifacts.
3. **Unfilled organization-defined parameters** — `[Assignment: …]`,
   `organization-defined`, `TBD`.
4. **Generic restatement** — text paraphrases the control instead of
   describing the implementation (fails 800-53A C1/C2).
5. **Missing required elements** — family-specific gaps (e.g., AC: no review
   frequency; AU: no retention period).
6. **Documentation-boundary failures** — claims that can only be verified by
   interview/test masquerading as examinable narrative.

Each of these, if surfaced **before** formal review, prevents one
review-and-bounce cycle.

## 2. How QUILL maps to those drivers

| Rework driver | QUILL finding type | Tier(s) | Evidence in eval |
|---|---|:---:|---|
| Missing controls | `missing` | T0 | coverage recall = **1.00** |
| Inconsistencies | `inconsistent` | T0 | inconsistency recall = **1.00** |
| Unfilled ODPs | `insufficient_evidence` (C3) | T0 | matched on `pkg_odp_placeholders`, `pkg_weak_ac2`, `pkg_oscal_weak` |
| Generic restatement | `insufficient_evidence` / `weak_narrative` | T2 | matched on `pkg_generic_ac2`, `pkg_au2_weak` |
| Missing required elements | `insufficient_evidence` (family) | T0 + T2 | matched on `pkg_partial_au2`, `pkg_cm2_minimal` |
| Doc-boundary failures | `narrative_present_evidence_unclear` | T2 | mock-analyzer limitation noted; live LLM expected to lift |

## 3. Quantitative assessment (conservative range)

> **Caveat first.** All numbers below are computed on the **synthetic
> ground-truth corpus** (12 packages, 14 artifacts) at Phase I; they are not a
> contractual SLA and they will shift on real RMF packages. The numbers are
> reported as a **range with stated assumptions** per `docs/04 §6`.

### 3.1 Capture rate (deficiencies surfaced pre-review)

From `eval/reports/latest.md`:

- Narrative deficiency recall: **0.92** (12/13 labelled narrative deficiencies)
- Coverage recall (`missing` for baseline): **1.00** (43/43)
- Inconsistency recall (cross-artifact): **1.00** (1/1)
- **Combined deficiency capture: 0.98** (56/57)
- Traceability: **1.00** (every emitted finding cites a valid source)
- False-positive rate: **0.11** (≤ 0.20 target)

These are the *engine's* numbers. They translate to **how many of the
deficiencies that would have triggered a rework cycle are surfaced before
formal review**.

### 3.2 Rework-reduction range

We compute the projected reduction as a **range** under two assumption sets
(documented; intentionally conservative):

| Assumption set | Capture rate | Pre-review review cost saved per caught deficiency | Result |
|---|---|---|---|
| **Conservative** | 0.80 (Phase I floor) | 0.5 reviewer-cycles avoided | **40% of post-submission rework cycles avoided** on equivalent draft packages |
| **Measured (this report)** | 0.98 | 0.7 reviewer-cycles avoided | **~69% of post-submission rework cycles avoided** on equivalent draft packages |

Both reduce to: **for the deficiencies QUILL surfaces and a human attests
pre-submission, the corresponding rework cycle does not occur.** The
"avoided cycles per deficiency" coefficient (0.5–0.7) reflects that some
deficiencies cluster within the same review iteration; we deliberately
assign **less than 1** to avoid overclaiming.

> Reading: a project team that puts a draft package through QUILL before
> formal review would, on synthetic-corpus-equivalent inputs, see roughly
> 40–69% fewer rework cycles attributable to documentation deficiencies.
> Numbers on real packages must be re-measured.

### 3.3 What this does NOT claim

- It does **not** claim a percent reduction in *total RMF cycle time* — that
  depends on many factors outside documentation quality.
- It does **not** estimate reduction on packages with deficiency profiles
  unlike the synthetic corpus.
- It does **not** include rework arising from *test/interview* findings —
  QUILL is document-only by design.

## 4. Qualitative assessment

These are observations from running the engine on the corpus and from the
DLA topic's framing of the assessor workflow:

- **Findings are immediately actionable.** Each carries a specific
  recommendation ("Specify account types, the responsible role, the review
  frequency, and the enforcement mechanism per AC-2 determination statements")
  rather than a generic deficiency flag.
- **Source-span highlighting is the differentiator.** Reviewers and authors
  can see *exactly* the text being graded, with the exact quote — eliminating
  the "where is this from?" friction that drives review delays.
- **The human attestation gate keeps authority intact.** Every finding is a
  proposal until an attester signs. The signed provenance + tamper-evident
  audit trail make accountability portable — and verifiable.
- **The doc-boundary rule prevents a class of false negatives.** Findings
  that would require test/interview are surfaced as advisory rather than
  silently graded as "satisfied," which is the honest behavior for a
  document-only tool.
- **Cross-artifact inconsistencies are caught.** A common rework driver
  (SSP says quarterly, architecture says annually) is surfaced at run time,
  not at review.

## 5. Conditions for the projection to hold

1. Project teams use QUILL **before** submission, on real-format artifacts.
2. The configured baseline matches the program (`config/catalog.yaml`).
3. The rubric (`config/rubric.yaml`) is tuned per program if the family-element
   set differs from the default (config-only change).
4. Tier 2 runs on Ollama with the configured local model; numbers re-measured
   against real Tier 2 once live (a separate eval run is planned at WP-6 tail
   when Ollama is available in the sandbox).
5. Human attestation is taken seriously — QUILL's value collapses to "fancy
   spell-check" if attesters approve without reading.

## 6. Method recap

- Recall, FP, precision, traceability, severity, calibration computed exactly
  per `docs/04 §3–4`.
- Eval harness is reproducible: `python -m eval.harness.run_eval`. Output
  artifacts are dated and committed under `eval/reports/`.
- Synthetic corpus is open and inspectable (`eval/artifacts/`,
  `eval/ground_truth/labels.yaml`).
- Locked in CI: `tests/integration/test_eval_gates.py` fails the build if any
  Phase I gate regresses.

This assessment will be refreshed against any new corpus before each gate
milestone.
