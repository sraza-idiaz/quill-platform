# 11 — Phase II Recommendations (DLA Phase I deliverable)

> Required by the DLA Phase I scope: *"recommendations for Phase II."* This is
> the prioritized plan for scaling QUILL's validated Phase I capabilities into
> broader RMF workflows, preserving the human attestation gate at every step.

Phase II per the DLA topic: **≤24 months, ≤$1M**. The goal: expand validated
capabilities for broader adoption, integrate with enterprise RMF workflows
while preserving cybersecurity authority, correlate documentation analysis
with evolving system configurations, and support continuous documentation
improvement.

---

## 1. Recommendations — ranked by value × risk

### R1 (highest) — Run live Tier 2 (Ollama) and publish a real-LLM eval report
**Why first:** Phase I numbers were measured with a deterministic Tier-2
stand-in. Switching to live Ollama is the single most informative thing for
DLA stakeholders.
**Effort:** small (1–2 engineer-weeks). The analyzer interface is already
plug-in compatible.
**Deliverable:** `eval/reports/eval-ollama-<date>.md` measured on the same
synthetic corpus + at least one cleared real artifact.

### R2 — Realistic corpus + held-out slice
**Why:** synthetic numbers don't generalize until measured on real packages.
**Effort:** medium. Requires TPOC-cleared draft artifacts (per FN/CUI rules),
or a partner program's sanitized historical packages.
**Deliverable:** ≥ 50 artifacts, ≥ 200 labeled deficiencies, with a held-out
slice (≥ 20%) untouched during tuning. Metrics reported separately on
held-out.

### R3 — eMASS-class integration (read-only first, then write findings)
**Why:** the topic specifically calls for "integrating with enterprise RMF
workflows while preserving cybersecurity authority." The path is incremental:
1. **Phase IIa:** read draft packages from eMASS-class systems.
2. **Phase IIb:** push findings as POA&M items + comments (never authorization).
3. **Phase IIc:** continuous re-analysis on package updates.
**Effort:** large (4–6 engineer-months including security review).
**Guardrail:** writes are confined to finding/POA&M shapes; the engine has no
code path that produces an authorization output (already enforced by
FR-ATT-05 + tests).

### R4 — Cross-artifact dependency graph (optionally Memgraph)
**Why:** Phase I cross-artifact consistency covers frequency tokens only.
Phase II should consistency-check identifiers, role names, system boundaries,
component lists, and ODP value classes across the whole package via a graph
the orchestrator queries.
**Effort:** medium (PRD already mentions Memgraph as an optional Phase II
backend; the design slot is reserved).

### R5 — Continuous re-analysis as configurations evolve
**Why:** the topic explicitly asks QUILL to "correlate documentation analysis
with evolving system configurations." A folder/repo watcher plus a diff-aware
runner that re-evaluates only impacted controls would let teams keep packages
fresh without re-running the full analysis.
**Effort:** medium. Folder-watch is already in (FR-ING-07); the diff-aware
runner is new.

### R6 — Post-hoc calibration mapping + fine-tuning gate
**Why:** Phase I demonstrates calibration; Phase II should *correct* it via
isotonic/Platt mapping recomputed periodically from attested findings.
Fine-tuning a local model becomes feasible once attested-finding data
accumulates (PRD constraint: *only* after enough attested data).
**Effort:** small-to-medium. No fine-tuning without an explicit, written
decision (`DECISIONS.md`) and a fresh eval.

### R7 — Multi-program / multi-tenant hardening
**Why:** Phase I's in-memory storage suffices for one sandbox; Phase II needs
the Postgres adapter (already scaffolded) and per-tenant key isolation, plus
operational metrics (run durations, breaker trips, finding mix) — never
artifact content (NFR-OBS-01).
**Effort:** medium.

### R8 — Embedding-based Tier 1 retrieval
**Why:** Phase I uses a lexical baseline (`DECISION-010`). Local embeddings
(e.g., a small CPU-friendly model) will lift semantic mapping and raise
narrative recall.
**Effort:** small. The retrieval surface is already designed for pluggability.

### R9 — Stronger air-gap packaging + CMMC L2 evidence
**Why:** stand-alone offline-install validation, signed image bundles, and
the L2 control-handling evidence mapping promised in the PRD's Phase II scope.
**Effort:** medium. The hardening checklist (`SECURITY_AUDIT.md` §6) becomes
a tested install gate.

### R10 — Slack `@quill` bot in QUILL's own workspace
**Why:** first-class per PRD; deferred to last in Phase I per project owner.
Best-fit work for early Phase II: command parser is already designed (status,
findings, attest, health, upload).
**Effort:** small once a workspace + bot tokens are issued.

### R11 — Hardened Tier 3 (cloud) for *non-restricted* artifacts
**Why:** Phase I keeps T3 as a demo toggle. Phase II hardens it with explicit
classification gates (no restricted data ever), an outbound allow-list, and
operator audit trails.
**Effort:** small once a Claude API endpoint and policy are agreed.

### R12 — Methods & limitations doc refresh after each milestone
**Why:** honesty is a feature. Every major change re-runs the eval and
updates `docs/09`.
**Effort:** trivial (it's a discipline, not an artifact).

## 2. Sequencing (the next 24 months at a glance)

```
Q1  ─ R1 live Tier 2 ─ R8 embeddings ─ R7 Postgres + tenancy hardening
Q2  ─ R2 realistic corpus ─ R6 calibration mapping ─ R10 Slack
Q3  ─ R4 dependency graph ─ R3a eMASS read-only ─ R11 hardened T3
Q4  ─ R3b/c eMASS write findings + continuous re-analysis ─ R9 air-gap CMMC pkg
Q5–Q8 ─ broaden program coverage; refresh R12; Phase III prep
```

## 3. Non-negotiables carried forward into Phase II

- **Never automate the authorization decision.** Every Phase II feature is
  audited against FR-ATT-05.
- **Human attestation remains the hard gate.** No exception, no auto-merge.
- **Source-span traceability = 100%.**
- **No artifact content in egress in air-gap mode.**
- **Circuit-breaker threshold remains 3.**
- **Generic-first / schema-driven.** New catalogs (FedRAMP, ISO 27001, CMMC)
  are config additions, not code.

## 4. Risk register update (delta from Phase I)

| ID | Risk | Likelihood | Impact | Mitigation in Phase II |
|---|---|---|---|---|
| RII-1 | Real-package numbers fall short of Phase I gates | Med | High | R2 + held-out slice; R1 live-LLM tuning |
| RII-2 | eMASS-class integration introduces a path that could imply authorization | Low | Critical | R3 gated by audit; FR-ATT-05 regression tests retained |
| RII-3 | Tier 3 escalation leaks sensitive technical data | Low | Critical | R11 explicit classification gate + egress allow-list + FN/ITAR review |
| RII-4 | Calibration drifts as the corpus grows | Med | Med | R6 periodic recomputation + monitoring |
| RII-5 | Multi-tenant key/storage isolation gap | Low | High | R7 hardening + tenant-isolation tests on every PR |

## 5. Exit criteria for Phase II → Phase III

- Live Tier 2 numbers on realistic + held-out corpora hit Phase I gates with
  margin (recall ≥ 0.85, FP ≤ 0.15, traceability = 1.00, calibration ECE ≤ 0.10).
- One production deployment in an approved sandbox + one mirrored air-gap
  install validated.
- eMASS-class write findings + continuous re-analysis demonstrated end-to-end.
- Independent security review (third-party or DLA-led) of the attestation
  chain + air-gap egress.
- Signed offline-validated licensing model demonstrated (no phoning home).

If these are met, Phase III (production / dual-use) is justified: multi-
framework catalogs, enterprise SSO/RBAC, SaaS + on-prem + air-gap, marketplace
of rubrics — with the same human-authority guarantee at the core.
