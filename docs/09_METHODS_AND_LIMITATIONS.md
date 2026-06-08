# 09 — Methods & Limitations (DLA Phase I deliverable)

> Required by the DLA Phase I scope: *"Documentation of methods and limitations."*
> This document describes **what QUILL does, how it does it, and what it cannot
> do** — honestly and concretely. It pairs with the eval report
> (`eval/reports/latest.md`) and the rubric (`docs/03`).

---

## 1. What QUILL is and is not

**QUILL is** an artifact-centric, human-attested AI capability for **RMF
pre-adjudication**. It analyzes draft RMF artifacts (SSPs, control
implementation statements, architecture documents, OSCAL) against a configured
NIST SP 800-53 Rev.5 baseline and produces **confidence-scored, source-cited
findings** that a named human reviewer must approve, edit, or reject before
they are authoritative.

**QUILL is NOT** an authorization tool. It never recommends authorize/deny,
never represents that a control is "satisfied" as a system fact, and never
reduces governance rigor. Every finding is a *statement about documentation*,
subject to human attestation.

## 2. Method — tiered analysis (T0 → T1 → T2 → T3)

Each artifact (or package of artifacts) flows through a deterministic-first
pipeline. The PRD sequence is enforced: each tier must be proven before the
next is enabled.

### Tier 0 — Deterministic rule/KB engine
Implements **NIST SP 800-53A Rev.5 examine-only** signals that require no LLM:

- **Coverage vs baseline (FR-T0-01):** every control required by the configured
  baseline (default `moderate`) must be addressed by at least one segment;
  uncovered controls produce `missing` findings.
- **Required-field / ODP gaps (FR-T0-02):** per-family required elements
  (`config/rubric.yaml::family_rules`) checked deterministically. Unfilled
  organization-defined parameters (e.g., `[Assignment: organization-defined
  frequency]`, `TBD`) are flagged by regex against `odp_unfilled_patterns`.
- **Cross-artifact consistency (FR-T0-03):** the same control's frequency
  tokens (`annually|quarterly|monthly|…`) across artifacts in a package must
  agree; contradictions → `inconsistent` findings citing both spans.
- **OSCAL structural validation (FR-T0-04):** OSCAL JSON must contain a valid
  SSP/component shape (`uuid`, `metadata`, `control-implementation`,
  `implemented-requirements[*].control-id`).

T0 is **fully deterministic and reproducible** (FR-T0-05): identical input
yields identical findings in stable order.

### Tier 1 — Lexical retrieval + evidence index
Maps normalized segments to control IDs + 800-53A determination statements,
records every segment's locator (`page/section/char-offset`), and builds the
**evidence index** that downstream tiers consume. Phase I uses a lexical
baseline (logged as DECISION-010); the protocol is embedding-ready for a
Phase II upgrade.

### Tier 2 — Local-LLM evidence-sufficiency scoring
Tier 2 runs **on-box** via Ollama (default Mistral 24B per DECISION-001). It
scores each determination statement on two independent axes (docs/03 §1):

- **Axis A — Narrative Presence:** does the artifact address this statement?
- **Axis B — Evidence Sufficiency:** is the narrative *specific, complete, and
  verifiable from documentation*?

The output type is constrained: `missing | inconsistent | weak_narrative |
insufficient_evidence | narrative_present_evidence_unclear`. Tier 2 also emits
a **calibrated confidence** and a **severity** derived from the rubric's
config-driven model.

**Every Tier 2 finding must carry ≥1 verbatim source span** — fabricated
quotes are caught and dropped by the citation validator (see §5).

### Tier 3 — Cloud escalation (opt-in, air-gap-disabled)
A demo toggle in Phase I; never invoked in air-gap mode and never with data
marked restricted. Three explicit safety gates (`tier3_enabled` AND
`!air_gap` AND `!restricted`) — verified by negative tests.

## 3. Confidence + circuit breaker

- **Confidence disposition (`docs/03` §5.2):** `≥0.75` → emit finding;
  `0.50–0.75` → emit with `needs_review` flag; `<0.50` → emit a
  `flag_for_review` *deferral* (not an asserted finding).
- **Circuit breaker (FR-CONF-02):** repeated low-confidence or contradictory
  Tier 2 outputs on one artifact trip the breaker at threshold **3** (the
  documented value, explicitly **not** 999), routing the whole artifact to
  human review.

## 4. Human attestation gate (the hard rule)

A finding's lifecycle is `unattested → approved | edited | rejected`. The
`attester` role is required; **admin is not auto-granted attestation**
(security-critical separation). Every attestation:

1. validates state transitions,
2. preserves the AI-proposed original AND the edit (signed),
3. writes a **signed provenance record** to QUILL's ledger,
4. emits an event to the **tamper-evident SHA-256 hash-chained audit trail**.

Signing is pluggable: `GpgSigner` in production (`scheme=="gpg"`),
`HmacSigner` in dev/tests (`scheme=="hmac-sha256-dev"`). Production exports
are blocked unless the signature scheme is `gpg`.

## 5. Source traceability (mandatory)

Every artifact-derived finding must cite a **verbatim quote** from the source
artifact. The `citation_validator` enforces this and **rejects** any finding
whose quoted text is not present in the artifact. `missing` findings cite the
**catalog requirement** (artifact_id `catalog:<baseline>`) instead of a quote
— traceable to the baseline that demanded the control, not to artifact text
that does not exist.

## 6. What we measured (Phase I gates)

Eval harness in `eval/harness/`; synthetic ground-truth corpus in
`eval/artifacts/` + `eval/ground_truth/labels.yaml`. Method and equivalence
table per `docs/04 §3`. Current results (`eval/reports/latest.md`,
analyzer=`mock` — the deterministic Tier 2 stand-in):

| Gate | Target | Measured | Result |
|---|---|---|:---:|
| Deficiency-detection recall | ≥ 0.80 | **0.98** | ✅ |
| False-positive rate | ≤ 0.20 | **0.11** | ✅ |
| Traceability | = 1.00 | **1.00** | ✅ |
| Calibration | monotonic + ECE ≤ 0.20 | monotonic + **ECE 0.064** | ✅ |
| Coverage recall (`missing`) | informational | **1.00** | — |
| Inconsistency recall (cross-artifact) | informational | **1.00** | — |
| Severity agreement (±1 level) | informational | **1.00** | — |

A regression test (`tests/integration/test_eval_gates.py`) locks the gates so
they cannot silently regress.

## 7. Limitations (honestly)

- **Tier 2 in this report uses a deterministic mock**, not the live local LLM.
  The MockAnalyzer matches Ollama's interface and was tuned against the rubric;
  it captures generic-restatement / unfilled-ODP / partial-coverage patterns
  reliably but **does not yet detect every "requires interview/test" doc-boundary
  case** (e.g., the `pkg_doc_boundary` IA-2 label remains unmatched in mock).
  Real Ollama is expected to lift this; numbers must be re-measured at live-LLM
  cut-in and recorded as a separate report under `eval/reports/`.
- **Synthetic corpus.** The corpus is 14 artifacts × 12 analysis packages.
  Real RMF packages are larger and more heterogeneous; numbers will shift on
  realistic data. The corpus is designed to exercise the deficiency taxonomy,
  not to estimate absolute performance.
- **Document-only analysis.** A determination requiring *test* or *interview*
  cannot be satisfied by documentation alone; QUILL emits a
  `narrative_present_evidence_unclear` advisory in those cases (the
  documentation-boundary rule, docs/03 §3.3). Assessors still own the actual
  examination.
- **Cross-artifact consistency** in Phase I covers frequency tokens
  (annually/quarterly/etc.). Other ODP value classes (retention periods,
  authenticator types) are detected within an artifact but not yet contrasted
  across artifacts; planned for Phase II's dependency-graph work.
- **No fine-tuning in Phase I.** Calibration mapping only (post-hoc) is allowed;
  fine-tuning waits for sufficient attested findings (per PRD).
- **Lexical retrieval at T1.** Phase I uses lexical mapping; embeddings come
  later. Some semantic mappings will be missed today.
- **Storage is in-memory in the sandbox build.** Schema + Postgres adapter are
  defined; a hardened Postgres backend is a Phase I tail / Phase II item.
- **Slack bot deferred.** Slack `@quill` is planned but not yet shipped; the
  REST API and MCP tools provide equivalent access for now.
- **Numbers are batch-latency-acceptable.** QUILL is not interactive; runs are
  measured in seconds-to-minutes on the reference workstation.

## 8. What we did NOT do (out of scope by design)

- Recommend authorize/deny. Period.
- Auto-merge edits.
- Use artifact content in logs, metrics, or telemetry.
- Phone home with artifact data in air-gap mode (egress = 0 verified by
  configuration; an end-to-end egress monitor will run at hardening).
