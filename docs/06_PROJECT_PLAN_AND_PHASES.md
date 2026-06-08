# 06 — Project Plan, WBS & Phase Breakdown

> The execution plan. Maps the PRD's three-phase vision to a task-level Work Breakdown Structure (WBS) with dependencies, owners (agent roles), exit gates, and milestones. The companion **`07_PROGRESS_TRACKER.md`** is the living "% complete" view you update as work lands. **Phase I is the focus** (DLA Phase I: ≤12 months, ≤$100K, sandbox, no ATO). Phases II/III are summarized for forward planning.

**Sequencing principle (from the PRD):** build one tier/layer at a time; **prove each before adding the next.** No over-engineering.

---

## Milestone map (Phase I)

| Milestone | Definition | Depends on |
|---|---|---|
| **M0 — Docs approved** | This document set reviewed & accepted; repo scaffolded; AXO reuse confirmed | — |
| **M1 — Design complete** | SYSTEM_DESIGN.md, ARCHITECTURE.md, DESIGN_SPEC.md, threat model, RTM seeded | M0 |
| **M2 — Ingest + T0 working** | Artifacts ingest/normalize; Tier 0 deterministic findings; schema live; eval corpus started | M1 |
| **M3 — T1 + T2 working** | Retrieval/extraction + local-LLM sufficiency scoring; spans + citation validation; circuit breaker | M2 |
| **M4 — Attestation gate live** | Findings flow through signed Change-Request + provenance + audit; `attester` role | M2 (parallel with M3) |
| **M5 — UI + Slack + Export** | Review/attest UI with span highlighting; `@quill` bot; signed report + OSCAL POA&M + audit artifact | M3, M4 |
| **M6 — Eval + hardening passed** | Recall/FP/traceability/calibration met; security audit clean; chaos passed | M3, M4, M5 |
| **M7 — Phase I deliverables** | Prototype demo, methods & limitations, trace-to-source demo, rework-reduction assessment, Phase II recs | M6 |

A milestone is reached only when its tasks are complete **and** the relevant exit-gate checks (see §Phase I gates) pass.

---

## Work Breakdown Structure — Phase I

> IDs are stable. `Owner` = agent role from the PRD roster. `Dep` = prerequisite task IDs. Each task's "Done when" is its definition of done.

### WP-0 — Project setup (→ M0)

| ID | Task | Owner | Dep | Done when |
|---|---|---|---|---|
| T-0.1 | Approve doc set; record open decisions in `DECISIONS.md` | PM | — | Docs accepted; decisions logged |
| T-0.2 | Scaffold `/quill-platform/` mirroring `/msp-platform/`; lock tech versions | Architect | T-0.1 | Repo skeleton builds; versions pinned |
| T-0.3 | Confirm AXO reuse points compile/import against QUILL | Integration | T-0.2 | AXO auth/provenance/audit/CR importable |

### WP-1 — Design (→ M1)

| ID | Task | Owner | Dep | Done when |
|---|---|---|---|---|
| T-1.1 | `SYSTEM_DESIGN.md` (components, data-flow, API draft, failure modes, calibration approach) | System Designer | T-0.2 | Reviewed by PM |
| T-1.2 | `ARCHITECTURE.md` + skeleton folders, config schemas, model-tier config, migration strategy | Architect | T-1.1 | Reviewed; folders exist |
| T-1.3 | `DESIGN_SPEC.md` wireframes (upload/queue, run view, **review+attest**, audit viewer, export, settings) | FE Designer | T-1.1 | Reviewed; covers FR-UI-01..05 |
| T-1.4 | Threat model + CMMC L2 / CUI boundary draft (`SECURITY_AUDIT.md` start) | Security | T-1.1 | Reviewed |
| T-1.5 | Seed RTM (`08`) — topic req → FR → test rows | Compliance | T-1.1 | RTM populated for P0 FRs |

### WP-2 — Backend core: Ingest + Tier 0 + Schema (→ M2)  *[Track A]*

| ID | Task | Owner | Dep | Done when |
|---|---|---|---|---|
| T-2.1 | Postgres schema/migrations: artifact, control, assessment_objective, run, finding, evidence_span, attestation (+ reuse provenance/audit/CR) | Backend | T-1.2 | Migrations apply; tables match `04`/domain model |
| T-2.2 | Catalog/baseline loader from OSCAL/YAML (800-53 Rev.5 + 800-53A) | Backend | T-2.1 | FR-CAT-01..03 pass |
| T-2.3 | Ingestion + normalization (PDF/DOCX/MD/OSCAL → control-keyed, locators preserved) | Backend | T-2.1 | FR-ING-01..06 pass |
| T-2.4 | Tier 0 rule/KB engine (coverage, required-field, cross-artifact consistency, OSCAL schema) | Backend | T-2.2, T-2.3 | FR-T0-01..05 pass, deterministic |
| T-2.5 | Folder-watch ingest | Backend | T-2.3 | FR-ING-07 |

### WP-3 — Analysis: Tier 1 + Tier 2 + Confidence (→ M3)  *[Track B]*

| ID | Task | Owner | Dep | Done when |
|---|---|---|---|---|
| T-3.1 | Tier 1 retrieval/extraction + evidence index with spans + retrieval scores | Backend + ML/Eval | T-2.4 | FR-T1-01..03 |
| T-3.2 | `rubric.yaml` + sufficiency criteria + prompt templates (per `03`) | ML/Eval | T-1.5 | Rubric authored; loads |
| T-3.3 | Tier 2 local-LLM sufficiency scoring; finding emission (type/severity/confidence/recommendation) | Backend + ML/Eval | T-3.1, T-3.2 | FR-T2-01..05 |
| T-3.4 | **Citation validation** — reject findings whose span isn't in the artifact | Backend | T-3.3 | FR-T2-03; traceability test |
| T-3.5 | Confidence thresholds + `flag_for_review` deferral | ML/Eval | T-3.3 | FR-CONF-01 |
| T-3.6 | **Circuit breaker (threshold 3)** | Backend | T-3.3 | FR-CONF-02; breaker test |
| T-3.7 | Tier 3 escalation path (opt-in, air-gap-disabled) — demo toggle | Backend | T-3.3 | FR-T3-01/02 |

### WP-4 — Attestation gate + Auth/Provenance/Audit + API (→ M4)  *[Track C, parallel with WP-3]*

Under DECISION-002 (QUILL standalone), this WP also builds QUILL's own auth, provenance ledger, audit trail, change-request flow, and GPG signing. AXO's design may be studied as a reference; no code is imported.

| ID | Task | Owner | Dep | Done when |
|---|---|---|---|---|
| T-4.1 | Build QUILL JWT auth + roles (`admin/engineer/attester/viewer`) + `require_role` | Backend | T-0.2 | FR-API-02; real JWT required outside DEV_MODE |
| T-4.2 | Build QUILL provenance ledger + GPG signer + tamper-evident audit trail | Backend | T-4.1 | NFR-AUD-01..04 |
| T-4.3 | PR-style change-request flow; finding lifecycle (unattested→approved/edited/rejected) signed; reused for export signing | Backend | T-4.2 | FR-ATT-01..06 |
| T-4.4 | REST + MCP API for all capabilities; tenant isolation | Backend | T-4.3 | FR-API-01/03 |

### WP-5 — UI + Slack + Export (→ M5)

| ID | Task | Owner | Dep | Done when |
|---|---|---|---|---|
| T-5.1 | UI: upload/queue + run view | FE Dev | T-1.3, T-4.4 | FR-UI-01 |
| T-5.2 | UI: **review + attest screen** with source-span highlighting | FE Dev | T-3.4, T-4.4 | FR-UI-02 |
| T-5.3 | UI: audit/provenance viewer + export + settings (air-gap/T3 toggles) | FE Dev | T-4.3 | FR-UI-03/04 |
| T-5.4 | UI: accessibility + reduced-motion + brand | FE Dev | T-5.2 | FR-UI-05 / NFR-USE |
| T-5.5 | Slack `@quill`: status/findings/attest/health + file upload | Slack | T-4.4 | FR-SLK-01..06 |
| T-5.6 | Export service: signed report + OSCAL POA&M + audit artifact | Backend | T-4.3 | FR-EXP-01..03 |

### WP-6 — Eval, QA, Security, Hardening (→ M6)

| ID | Task | Owner | Dep | Done when |
|---|---|---|---|---|
| T-6.1 | Ground-truth corpus (≥30 artifacts, ≥100 labels) + harness | ML/Eval | T-1.5 | Per `04`; runs in CI |
| T-6.2 | Run metrics: recall ≥80%, FP ≤20%, traceability 100%, calibration | ML/Eval | T-3.4, T-6.1 | Gates met; report in `eval/reports/` |
| T-6.3 | Full test suite (unit ≥80% on T0+analyzer, integration, traceability, breaker, security, chaos, UI/Playwright, Slack) | QA | T-5.* | All green |
| T-6.4 | Security audit: threat model, CMMC L2/CUI, egress=zero, prompt-injection, dep scan | Security | T-5.* | `SECURITY_AUDIT.md` complete; 0 unresolved high |
| T-6.5 | Chaos: LLM-down, corrupted artifact, storage outage | QA | T-5.* | FR-RES-01..03 / NFR-REL |

### WP-7 — Phase I deliverables (→ M7)

| ID | Task | Owner | Dep | Done when |
|---|---|---|---|---|
| T-7.1 | Rework-reduction assessment (quant + qual) | Compliance + ML/Eval | T-6.2 | Per `04` §6 |
| T-7.2 | Methods & limitations document | Compliance + Tech Docs | T-6.2 | DLA deliverable complete |
| T-7.3 | Trace-to-source demonstration + demo script | Compliance | T-5.2 | Demo rehearsed |
| T-7.4 | Phase II recommendations | Compliance + PM | T-6.* | Written |
| T-7.5 | Phase I release checklist (PRD §8) | Release Coord | T-6.*, T-7.* | All boxes checked; phase marked shippable |

---

## Critical path & parallelism

```
M0 ─ WP-0 ─▶ M1 ─ WP-1 ─▶ ┬─ WP-2 (Ingest+T0) ─▶ M2 ─┬─ WP-3 (T1+T2) ─▶ M3 ─┐
                          │                          │                       ├─ WP-5 (UI/Slack/Export) ─▶ M5 ─ WP-6 ─▶ M6 ─ WP-7 ─▶ M7
                          └──────────────────────────┴─ WP-4 (Attest+API) ─▶ M4 ┘
```

- **WP-3 and WP-4 run in parallel** after M2 (analysis vs. attestation gate).
- **WP-6 (eval/QA)** starts its corpus/harness work (T-6.1) in **parallel from M1** — do not leave eval to the end.
- Tier sequencing is strict: T-2.4 (T0) before T-3.1 (T1) before T-3.3 (T2).

## Phase I exit gates (the PM verifies all)

Pulled from PRD §8 and the FR/NFR docs — see `08_RTM` for the full traceable list. Summary:
**Functional** (ingest 4 formats, T0 deterministic, T2 narrative-vs-evidence, every finding has type/severity/confidence/recommendation/span, citation validation rejects bad spans, breaker=3, signed attestation gate, provenance+audit, review UI with highlighting, signed exports, Slack basics, sandbox/no-ATO/zero-egress) ·
**Quality** (recall ≥80%, FP ≤20%, traceability 100%, calibration demonstrated, security clean, chaos survived) ·
**DLA deliverables** (prototype, methods & limitations, trace-to-source, rework-reduction, Phase II recs).

---

## Phase II (summary — DLA Phase II: ≤24 mo, ≤$1M)

Multi-program/multi-tenant scale · eMASS-class integration (write findings/POA&M, never authorization) · cross-artifact dependency graph (optional Memgraph) · continuous re-analysis as configs evolve · cross-program rework analytics · hardened Tier 3 · begin local-model fine-tuning **only after** enough attested findings logged · CMMC L2 evidence + stronger air-gap packaging. Human-attestation gate preserved everywhere.

## Phase III (summary — DLA Phase III: dual-use, no PoP/funding limit)

Productized SaaS + on-prem + air-gap · multi-framework catalogs (FedRAMP/ISO 27001/CMMC) · enterprise SSO/RBAC · rubric/catalog marketplace · offline-validated licensing (no phoning home) · full MERP suite integration. Human authority/accountability preserved as the core differentiator.

---

## Risk register (top Phase I risks — keep current)

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-1 | Recall < 80% on ground truth | Med | High | Build corpus early (T-6.1); iterate rubric on criteria not items; held-out slice; conservative deferral |
| R-2 | No access to realistic artifacts (CUI) | High | Med | Synthetic seeded corpus (S1) is primary; S3 only if TPOC clears |
| R-3 | Local LLM too slow/weak for sufficiency judgment | Med | Med | Batch latency accepted; Tier 3 demo toggle as fallback signal; revisit model (DECISION-001) |
| R-4 | Confidence uncalibrated | Med | Med | Post-hoc calibration (Platt/isotonic), no fine-tuning; demonstrate via reliability curve |
| R-5 | (retired) Phase I scope growth from building auth/provenance/audit natively | Med | Med | DECISION-002: QUILL is standalone. Scope tracked under WP-4; patterns are well-known. |
| R-6 | Prompt injection via artifact | Med | High | Content-as-data isolation, citation validation, injection test suite (`05` §7) |
| R-7 | Scope creep beyond Phase I | Med | Med | Phase I scope-out list (PRD §6) enforced; Release Coord gates |
| R-8 | FN/ITAR access mishandled | Low | High | FN disclosure recorded (`05` §6); access controls before any restricted data |
