# 03 — Evidence-Sufficiency Rubric (Core IP)

> This is the heart of QUILL. It defines **how the system distinguishes "a control narrative exists" from "the supporting evidence is sufficient and clear."** Tier 2 implements this rubric; Tier 0 implements its deterministic subset. **Read this before writing any analysis code.** The rubric is **config-driven** (`rubric.yaml`) — this document specifies the schema and the scoring logic, not hardcoded prompts.
>
> Grounded in **NIST SP 800-53A Rev.5**: assessment objectives, determination statements, the examine/interview/test methods, and the review→study→analyze depth gradient. QUILL does **document-only** pre-adjudication — it has access to the *artifact text*, not the live system — so it assesses what an assessor can determine **from the documentation alone**, and explicitly flags where a determination would require interview/test that documentation cannot satisfy.

---

## 1. The conceptual model

For each in-baseline control, SP 800-53A defines one or more **assessment objectives**, each decomposed into **determination statements** (the atomic things an assessor must determine to be true). QUILL grades the artifact against each determination statement on two **independent axes**:

- **Axis A — Narrative Presence:** Does the artifact contain text that *addresses* this determination statement at all?
- **Axis B — Evidence Sufficiency:** Is that text *specific, complete, and clear enough* that a reasonable assessor could determine the statement is satisfied **from the documentation**, without needing to ask follow-up questions or test the system?

The product's entire value is that **A and B are scored separately.** "Narrative present, evidence unclear" is the signature finding type the DLA topic asks for.

```
                         Axis B: Evidence Sufficiency  ───────────────▶
                    │  Insufficient        Partial            Sufficient
   Axis A   Present │  insufficient_       narrative_present_  (no finding —
   Narrative        │  evidence            evidence_unclear    evidence ok)
   Presence         │
            Absent  │  missing             missing             (impossible)
                    ▼
```

The cell determines the **finding type** (see §4). Cross-artifact contradictions are a separate, orthogonal check producing `inconsistent` (see §6).

---

## 2. Determination-statement scoring (per statement)

Each determination statement gets a record:

```yaml
determination_statement_id: AC-2_obj.1_det.a       # from 800-53A config
control_id: AC-2
narrative_presence:          # Axis A — deterministic where possible, LLM-assisted otherwise
  score: present | partial | absent
  evidence_spans: [ {artifact_id, locator, quoted_text} ]   # REQUIRED if present/partial
evidence_sufficiency:        # Axis B — Tier 2 (local LLM) graded against the criteria in §3
  score: sufficient | partial | insufficient | not_determinable_from_docs
  rationale: "<one or two sentences, grounded in the quoted span>"
  missing_elements: [ "specific actor/role", "frequency/period", "enforcement mechanism", ... ]
confidence: 0.0–1.0          # calibrated; see §5 and 04_EVALUATION
```

**Hard rule:** if `narrative_presence` is `present` or `partial`, there must be ≥1 `evidence_span` whose `quoted_text` is verbatim-present in the artifact. The pipeline rejects any record violating this (FR-T2-03).

---

## 3. Evidence-Sufficiency criteria (Axis B rubric)

A determination statement's narrative is scored **sufficient** only if it satisfies the applicable criteria below. The criteria are the configurable rubric; `rubric.yaml` maps control families / statement patterns to the criteria that apply.

### 3.1 Universal sufficiency criteria (apply to every statement)

| Code | Criterion | "Insufficient" trigger |
|---|---|---|
| C1 **Specificity** | Names the concrete actor, system, or mechanism — not a generic restatement of the control text. | Statement merely paraphrases the control ("The organization manages accounts.") |
| C2 **Completeness** | Addresses *all* parameters the determination statement requires (who, what, where, how). | One or more required parameters absent. |
| C3 **Assignment/selection values** | Where the control has ODP (organization-defined parameters: frequencies, roles, time periods), the artifact states the chosen value. | "…at an organization-defined frequency" left unfilled. |
| C4 **Mechanism/enforcement** | Describes *how* the control is implemented/enforced, not just that it is intended. | "We plan to…" / aspirational language with no mechanism. |
| C5 **Internal consistency** | Does not contradict itself or other statements for the same control. | Conflicting values across the narrative. |
| C6 **Verifiability from docs** | A reasonable assessor could confirm the statement from this text via the **examine** method. | Statement asserts a fact that could only be confirmed by **interview/test** (then score `not_determinable_from_docs`, not `insufficient` — see §3.3). |

### 3.2 Family-specific criteria (examples; full set in `rubric.yaml`)

- **AC (Access Control):** named roles, least-privilege rationale, account types enumerated, review frequency stated.
- **AU (Audit & Accountability):** event types listed, retention period stated, review/alerting mechanism named.
- **IA (Identification & Authentication):** authenticator types, MFA scope, lifecycle (issuance/revocation) addressed.
- **CM (Config Mgmt):** baseline reference, change-control process, deviation handling.
- (Extend per family in config; each family entry lists required `C*` codes + family-specific elements.)

### 3.3 The documentation-boundary rule (critical, prevents false negatives)

Some determination statements **cannot** be satisfied by documentation alone — they require the assessor to *test* the system or *interview* staff (e.g., "the mechanism actually enforces X"). For these:

- Do **not** score `insufficient` (the doc isn't deficient — it's the wrong evidence type).
- Score `not_determinable_from_docs` and emit a low-severity advisory finding noting **what method (interview/test) would be needed**.
- This keeps QUILL honest about the limits of document-only pre-adjudication and feeds the **methods & limitations** deliverable.

### 3.4 Inherited / common controls

If a statement is marked **inherited** or **common** (provider-implemented) in the artifact/OSCAL, QUILL checks that the inheritance is *declared and attributed* (C2/C3 on the inheritance claim) rather than grading the implementation itself. A control claiming inheritance with no provider/attribution → `insufficient_evidence` on the inheritance claim.

---

## 4. Finding-type derivation (the decision table)

Tier 0 produces the deterministic rows; Tier 2 produces the rows requiring judgment.

| Narrative (A) | Sufficiency (B) | Finding type | Tier | Severity baseline |
|---|---|---|---|---|
| absent | — | `missing` | T0 | high (if control in baseline) |
| present | sufficient | *(no finding)* | T2 | — |
| present | partial | `narrative_present_evidence_unclear` | T2 | medium |
| present | insufficient | `insufficient_evidence` | T2 | medium–high |
| partial | insufficient/partial | `weak_narrative` | T2 | medium |
| any | not_determinable_from_docs | advisory (`narrative_present_evidence_unclear` + method note) | T2 | low |
| present (≥2 artifacts) | conflicting | `inconsistent` | T0/T2 | high |
| required field absent | — | `insufficient_evidence` (field-level) | T0 | medium |

Below the confidence threshold (see §5), **do not emit a finding** — emit a `flag_for_review` deferral (FR-CONF-01).

---

## 5. Severity & confidence

### 5.1 Severity model (`severity.yaml`)

Severity = f(control importance, finding type, baseline). Default ranking: `critical > high > medium > low`. Factors:

- **Control importance:** higher for controls in the baseline core families (AC, AU, IA, SC, SI) and for controls flagged high-impact in config.
- **Finding type:** `missing` and `inconsistent` ≥ `insufficient_evidence` ≥ `narrative_present_evidence_unclear` ≥ advisory.
- **Baseline:** a gap on a control required by the selected baseline outranks one outside it.

Severity is **config-driven and explainable** — every severity carries the factors that produced it. Severity is **never** "authorization risk"; it is documentation-deficiency severity only.

### 5.2 Confidence (0–1, calibrated)

Confidence reflects QUILL's certainty in the *finding*, not the severity. Inputs:

- Tier 1 retrieval score (how cleanly the text mapped to the control/objective).
- Tier 2 model self-reported certainty (used as a signal, **not trusted raw** — see calibration).
- Span quality (exact, unambiguous quote vs. fuzzy match).
- Agreement across determination statements for the same control.

**Thresholds (initial; tune via `04_EVALUATION`, record final in `DECISIONS.md`):**

| Confidence | Behavior |
|---|---|
| ≥ 0.75 | Emit finding normally. |
| 0.50–0.75 | Emit finding marked **needs-review** (surfaced but flagged). |
| < 0.50 | **Do not assert** — emit `flag_for_review` deferral. |

Repeated < 0.50 / contradictory outputs on one artifact → **circuit breaker (threshold 3)** trips the artifact to full human review (FR-CONF-02).

Calibration is **demonstrated**, not assumed: the score must correlate with human agreement on the ground-truth set (FR-CONF-03 / `04_EVALUATION`). Until calibration is measured, treat raw model confidence as *uncalibrated* and lean conservative (defer more).

---

## 6. Cross-artifact consistency (orthogonal check)

Independent of A/B scoring, Tier 0 compares the same control's claims across all artifacts in a package:

- Same control, conflicting ODP values (e.g., review "annually" vs "quarterly") → `inconsistent`, high severity.
- Control referenced in SSP but absent in architecture doc (or vice-versa) → `inconsistent`.
- Each `inconsistent` finding cites **both** spans (one per artifact).

---

## 7. `rubric.yaml` schema (authoring contract)

```yaml
version: 1
catalog: nist-800-53-rev5
assessment_catalog: nist-800-53a-rev5
baseline: moderate            # low | moderate | high  (FR-CAT-03)

sufficiency_criteria:         # the C* codes from §3.1, with prompts/checks
  - code: C1
    name: Specificity
    applies_to: all
    check: llm                # llm | deterministic | hybrid
    guidance: "Reject generic restatements of the control text…"
  - code: C3
    name: ODP values present
    applies_to: all
    check: deterministic       # can be partly rule-based: detect unfilled '[Assignment: …]'
    guidance: "Flag any unfilled organization-defined parameter."
  # … C2, C4, C5, C6 …

family_rules:                 # §3.2
  AC:
    required_criteria: [C1, C2, C3, C4, C6]
    required_elements: [named_roles, account_types, review_frequency]
  AU:
    required_criteria: [C1, C2, C3, C4]
    required_elements: [event_types, retention_period, review_mechanism]
  # …

severity_model:               # §5.1
  factors: [control_importance, finding_type, baseline_membership]
  high_impact_families: [AC, AU, IA, SC, SI]

confidence_thresholds:        # §5.2
  emit: 0.75
  needs_review: 0.50
  defer_below: 0.50

documentation_boundary:       # §3.3
  not_determinable_methods: [interview, test]
```

The engine reads this file; changing the rubric must require **no code change** (NFR-MNT-01).

---

## 8. What QUILL must NOT do (guardrails baked into the rubric)

- Never output an authorize/deny recommendation or any "risk acceptance" judgment (FR-ATT-05).
- Never claim a control is "satisfied" as an authoritative fact — it produces *findings about documentation*, all subject to human attestation.
- Never emit a finding without a verifiable source span.
- Never treat the model's self-reported confidence as ground truth before calibration.
- Never penalize a document for evidence that legitimately requires interview/test (use `not_determinable_from_docs`).

---

## 9. Worked example (illustrative)

**Artifact text (SSP, AC-2):** *"The organization manages information system accounts."*

- Axis A: `present` (the topic is addressed). Span captured.
- Axis B: fails C1 (generic restatement), C2 (no account types, no roles), C3 (no review frequency) → `insufficient`.
- Finding: `insufficient_evidence`, severity high (AC family, in baseline), confidence ~0.9 (clearly generic), `missing_elements: [account_types, responsible_role, review_frequency, enforcement_mechanism]`.
- Recommendation: *"Specify account types managed, the responsible role, the review frequency, and the enforcement mechanism per AC-2 determination statements (a)–(j)."*
- Routed to an attester to approve/edit/reject — **never** auto-accepted.
