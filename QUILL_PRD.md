# BUILD SPEC / PRD — QUILL

### AI-Assisted RMF Pre-Adjudication · MERP Suite · DLA SBIR DLA26BZ02-NV006

> This document is the complete product requirements + build specification for **QUILL**, the RMF pre-adjudication product in the MERP suite.
> You are the **Project Manager Agent**. You will coordinate all other agents listed below to deliver this product across three phases that map directly to the DLA SBIR Phase I / II / III scope. Read this entire document before dispatching any work.
> Every agent reports back to you. You do not write code yourself — you plan, dispatch, verify, and log decisions.
>
> **Heritage:** QUILL reuses AXO's proven methodology and codebase patterns (FastAPI backend, tiered classification, KB+local-LLM analysis, cryptographic provenance chain, tamper-proof audit trail, PR-like Change Requests, React/Tauri desktop UI, Slack bot). Where AXO *heals infrastructure*, QUILL *reviews documentation*. Reuse, don't reinvent.

---

## 0. Document Control

| Field | Value |
|---|---|
| Product | QUILL — AI-Assisted RMF Pre-Adjudication |
| Suite | MERP (Managed Enterprise Resilience Platform) |
| Solicitation | DLA SBIR DLA26BZ02-NV006 |
| Projected CMMC | Level 2 (Self) |
| Export control | ITAR (22 CFR 120–130) / EAR (15 CFR 730–774) |
| TPOC | Barry Humphrey · Barry.Humphrey@dla.mil · 571-789-6978 |
| Primary references | NIST SP 800-37 Rev. 2 (RMF), NIST SP 800-53 Rev. 5 (controls), NIST SP 800-53A Rev. 5 (assessment), NIST OSCAL |
| Decision log | `DECISIONS.md` (repo root) — log every architecture-level decision |

---

## 1. Mission

Build **QUILL** — an **artifact-centric**, human-attested AI capability that ingests draft RMF artifacts (control implementation statements, System Security Plans, system architecture documents), identifies missing / inconsistent / weak controls, distinguishes *"a control narrative exists"* from *"the supporting evidence is sufficient and clear,"* and produces **confidence-scored, structured findings traceable to the exact source text** — then routes every finding through a mandatory **human attestation gate**.

QUILL must:
1. Operate on **submitted artifacts as primary inputs** — not a conversational chatbot UI.
2. Detect missing, inconsistent, and weak control implementation statements against a loaded NIST SP 800-53 control baseline.
3. Separate **narrative presence** from **evidence sufficiency**, using a rubric derived from SP 800-53A assessment objectives and determination statements.
4. Emit **structured, confidence-scored findings**, each with a **source-span citation** (file + location + quoted text).
5. Enforce an explicit **human attestation mechanism** — no finding is treated as authoritative until a named human reviews and signs it; every action is cryptographically recorded.
6. **Never** automate the authorization decision or reduce governance rigor. QUILL informs; humans decide.
7. Run in a **government-approved R&D sandbox** with **no ATO required** (Phase I), and be **local-first / air-gap capable** (no client artifact data leaves the local environment in production — inherited as a hard constraint from AXO).

---

## 2. Non-Negotiable Design Principles

Enforce these at every level. Any agent that violates these sends their work back for revision.

### 2.1 Artifact-centric, not conversational
The primary input is a **document** (or a set of documents), not a chat prompt. The core unit of work is an *artifact analysis run*, not a conversation turn. A chat affordance may exist as a secondary aid, but the system of record is artifact → findings → attestation.

### 2.2 Human attestation is a hard gate
No finding is "accepted," exported, or treated as authoritative until a named, qualified human reviewer **approves, edits, or rejects** it. This reuses AXO's **provenance chain + Change Request + signed audit trail** pattern verbatim. The authorization decision itself is **out of scope** — QUILL never recommends "authorize / don't authorize."

### 2.3 Everything is traceable to source
Every finding carries a **source span**: artifact ID, location (page/section/line or character offset), and the exact quoted text it is based on. A finding with no source span is invalid and must be rejected by the pipeline. This is the documentation analog of AXO's provenance ("AI reasoning → approval → execution").

### 2.4 Confidence is explicit and calibrated
Every finding has a **confidence score** and a **severity**. The pipeline uses confidence-aware logic: high-confidence/clear → finding; low-confidence/ambiguous → defer to human ("flag for review") rather than assert. Borrow the confidence-aware RAG pattern: retrieval scoring → citation validation → abstention.

### 2.5 Local-first, air-gap capable, no phoning home
Production deployments make **zero outbound calls** with customer artifact data. Tiered model strategy (see 2.6) keeps analysis local by default; any cloud escalation is **opt-in, configurable, and disabled in air-gapped mode**. No telemetry on artifact content. (Inherited from AXO's core architectural identity.)

### 2.6 Tiered analysis engine (reuse AXO's tiering)
Mirror AXO's healing-engine tiering, repurposed for *classification + evidence analysis* instead of remediation:

| Tier | AXO (healing) | QUILL (pre-adjudication) |
|---|---|---|
| **Tier 0** | Graph-first lookup (Memgraph/Cypher) | **Rule/KB-first**: deterministic checks — control coverage vs. baseline, required-field presence, cross-artifact consistency, OSCAL schema validation. No LLM. Fast, explainable, free. |
| **Tier 1** | (n/a) | **Retrieval + structured extraction**: map artifact text to control IDs and SP 800-53A assessment objectives; build the evidence index with source spans. |
| **Tier 2** | Local LLM (Ollama / Mistral 24B) | **Local LLM evidence-sufficiency scoring**: judge narrative-vs-evidence per determination statement, generate finding text + confidence, all on-box. Default analyzer. |
| **Tier 3** | Claude API escalation (fallback) | **Cloud LLM escalation (optional, opt-in)**: only for low-confidence/complex artifacts, only when not air-gapped, never with restricted data. |

Tier 0 never invokes an LLM. Build one tier at a time; prove each before adding the next (AXO sequencing principle).

### 2.7 Circuit breaker is real
Reuse AXO's circuit-breaker pattern with the **documented threshold (3)**, not the disabled value (999). If the analyzer produces repeated low-confidence or contradictory outputs on an artifact, trip the breaker and route the whole artifact to human review rather than emitting unreliable findings. **This must be correctly configured before any near-real-data run.**

### 2.8 Generic-first, schema-driven
Control catalogs, assessment objectives, finding types, and severity rubrics are defined in **YAML/OSCAL config**, not hardcoded. QUILL ships with NIST SP 800-53 Rev. 5 + 800-53A preloaded, but the engine is catalog-agnostic so it can later support other frameworks (FedRAMP, ISO 27001, CMMC). Mirrors the Healing Graph's generic-first principle.

### 2.9 API-first
Every capability is exposed through the API (REST/FastAPI + optional GraphQL + MCP server). The desktop UI, Slack bot, and any external integration use the same API. If it's not in the API, it doesn't exist.

### 2.10 Reuse AXO, don't fork blindly
Where AXO already solves a problem (auth/JWT roles, provenance service, audit service, Change Request workflow, GPG signing, settings/integration cards, design system), **extend or reuse** it. QUILL is a sibling product in the same platform, not a greenfield rewrite.

---

## 3. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         ARTIFACT SOURCES                               │
│  Upload (PDF/DOCX/MD/OSCAL JSON) ── Folder watch ── eMASS-class export  │
└───────────────┬────────────────────────────────────────┬──────────────┘
                ▼                                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        QUILL BACKEND (FastAPI)                         │
│                                                                        │
│  ┌────────────┐  ┌──────────────────────┐  ┌───────────────────────┐  │
│  │ Ingest &   │  │  Analysis Engine      │  │ Attestation Layer     │  │
│  │ Normalize  │→ │  T0 rules/KB          │→ │ (Provenance chain,    │  │
│  │ (parsers,  │  │  T1 retrieval/extract │  │  Change-Request gate, │  │
│  │  OSCAL map)│  │  T2 local LLM score   │  │  signed Audit Trail)  │  │
│  │            │  │  T3 cloud escalate*   │  │                       │  │
│  └─────┬──────┘  └──────────┬───────────┘  └───────────┬───────────┘  │
│        │                    │                          │              │
│        ▼                    ▼                          ▼              │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │              PostgreSQL (Supabase/local)                          │ │
│  │  artifacts, controls, findings, evidence_spans, attestations,     │ │
│  │  provenance_records, audit_events, change_requests, runs          │ │
│  └──────────────────────────────────────────────────────────────────┘ │
└───────────────┬───────────────────────┬──────────────────┬────────────┘
                ▼                        ▼                  ▼
       ┌──────────────┐        ┌──────────────┐   ┌──────────────────┐
       │ React/Tauri  │        │ Slack Bot    │   │ Exports          │
       │ Desktop UI   │        │ (@quill)     │   │ (signed report,  │
       │ (review &    │        │ findings &   │   │  OSCAL POA&M,    │
       │  attest)     │        │ attest)      │   │  audit artifact) │
       └──────────────┘        └──────────────┘   └──────────────────┘
  *T3 cloud escalation is opt-in and disabled in air-gapped mode.
```

**Stack (locked, inherited from AXO):** Python 3.12+, FastAPI, PostgreSQL (Supabase or local), Ollama (local LLM), optional Claude API (T3), GPG signing, JWT auth (roles: admin/engineer/viewer + new: attester), React + Vite/Tauri desktop, Slack bot. Optional: Memgraph if cross-artifact dependency graphs are needed (defer to Phase II).

---

## 4. Domain Model (data)

Core tables (extend AXO's schema; reuse provenance/audit/change_request tables as-is):

- **artifact** — id, type (control_impl_stmt | ssp | architecture | oscal), filename, hash, source, uploaded_by, status (ingested|analyzing|reviewed|attested), created_at.
- **control** — control_id (e.g., `AC-2`), family, baseline, source_catalog (OSCAL). Loaded from SP 800-53 Rev.5.
- **assessment_objective** — derived from SP 800-53A; the determination statements per control used to grade sufficiency.
- **run** — id, artifact_id, tier_path (which tiers fired), model+version, started/finished, status, circuit_breaker_tripped (bool).
- **finding** — id, run_id, control_id, type (`missing` | `inconsistent` | `weak_narrative` | `insufficient_evidence` | `narrative_present_evidence_unclear`), severity, confidence (0–1), recommendation, status (`unattested` | `approved` | `edited` | `rejected`).
- **evidence_span** — id, finding_id, artifact_id, locator (page/section/char-offset), quoted_text. **Required** — a finding must have ≥1.
- **attestation** — id, finding_id, attester (user), decision, note, signed_at, signature (GPG). Reuses provenance chain.
- **provenance_record / audit_event** — reuse AXO's tamper-proof, integrity-verifiable ledger verbatim.

---

## 5. Agent Roster & Responsibilities

Dispatch in sequence and in parallel where possible. Each agent stays in its lane.

### 5.1 System Designer Agent
Produces `SYSTEM_DESIGN.md` before any code: component diagram; data-flow diagrams (ingest, analyze, finding emission, attestation, export); API contract draft (REST + MCP); auth/roles incl. the new **attester** role; failure-mode analysis (LLM down, low-confidence storm, corrupted artifact, storage unreachable); how confidence calibration is measured.

### 5.2 System Architect Agent
Produces `ARCHITECTURE.md` + skeleton folders. Locks tech versions; defines repo structure under `/quill-platform/` mirroring AXO's `/msp-platform/`; storage/parsers interface; OSCAL ingestion strategy; config schemas (`quill.config.yaml`, `catalog.yaml`, `rubric.yaml`); model-tier config (Ollama model, T3 toggle); migration strategy. Reuses AXO auth, provenance, audit, Change-Request modules.

### 5.3 Backend Developer Agent(s)
Builds:
- **Ingestion & normalization** — parsers for PDF/DOCX/MD + OSCAL JSON/SSP import; normalize to control-keyed internal representation.
- **Tier 0 rule/KB engine** — control-coverage vs baseline, required-field presence, cross-artifact consistency, OSCAL schema validation. Deterministic, explainable, no LLM.
- **Tier 1 retrieval/extraction** — map text → control IDs + 800-53A objectives; build evidence index with source spans.
- **Tier 2 local-LLM analyzer** — Ollama-backed evidence-sufficiency scoring per determination statement; emits finding text + calibrated confidence + severity; **mandatory source-span attachment + citation validation** (reject findings whose cited span isn't in the artifact).
- **Tier 3 escalation (optional)** — Claude API path, opt-in, disabled in air-gap mode, never with restricted data.
- **Circuit breaker** — threshold **3**; trips to human review on repeated low-confidence/contradiction.
- **Findings + attestation service** — reuse provenance + Change-Request + signed audit; expose finding lifecycle (`unattested → approved/edited/rejected`).
- **Export service** — signed human-readable report, OSCAL-style POA&M of open findings, integrity-verifiable audit artifact.
- **REST + MCP API**, auth + roles, tenant isolation.

### 5.4 ML/Eval Engineer Agent
Owns analysis quality. Builds the **rubric** (800-53A determination-statement → sufficiency scoring), prompt templates, confidence calibration, and the **evaluation harness**: labeled ground-truth set of known deficiencies; metrics (recall, false-positive rate, traceability 100%, confidence calibration). Defines success thresholds (see §8). Reuses the "log real decisions, defer fine-tuning until data exists" principle — no fine-tuning until attested-finding data accumulates.

### 5.5 Frontend Designer Agent
Produces `DESIGN_SPEC.md` using the **QUILL brand guide** (light-green palette `#6fcf97`, Syne/DM Mono/Instrument Serif, 8-bit owl mascot + status states, dark-mode-first). Wireframes for: artifact upload/queue, analysis run view, **finding review + attestation** screen (the heart of the product — source text on one side, finding+confidence on the other, approve/edit/reject), audit/provenance viewer, export screen, settings/integrations. Accessibility + reduced-motion required.

### 5.6 Frontend Developer Agent
Builds the UI in AXO's React/Tauri app as a new QUILL section (or standalone, architect's call). Source-span highlighting that maps a finding to the exact quoted text; confidence/severity chips using the semantic color system; attestation actions wired to the signed Change-Request flow; provenance/audit timeline reuse from AXO components.

### 5.7 Integration / Reuse Engineer Agent
Wires QUILL into the platform without breaking AXO: shared auth/JWT, shared provenance/audit services, settings page integration card, MERP suite nav. Ensures graceful degradation if the LLM tier is down (fall back to Tier 0 + flag for human). Adds the **attester** role to the existing role model.

### 5.8 Slack Bot Agent (@quill)
First-class, not an afterthought. Commands: `/quill status <artifact>` (run status + finding counts by severity), `/quill findings <artifact>` (top findings with control ID, confidence, source link), `/quill attest <finding-id>` (interactive approve/edit/reject with signed record), `/quill health`. File upload: drop an artifact in Slack → QUILL ingests + analyzes → returns finding summary. Respects tenant isolation + the attester role. Graceful errors if backend unreachable.

### 5.9 QA Tester Agent
Unit tests (80%+ on Tier 0 + analyzer), integration (upload → analyze → finding → attest → export), traceability tests (**every finding has a valid in-document span**), confidence-calibration tests, circuit-breaker tests, security (tenant isolation, no artifact leakage in logs, no prompt-injection-driven authorization claims), chaos (LLM down, corrupted artifact, storage outage), UI (Playwright) and Slack tests.

### 5.10 Security Engineer Agent
`SECURITY_AUDIT.md`: threat model (incl. prompt-injection trying to make QUILL claim authorization or suppress findings), CMMC L2 (Self) control-handling review, CUI handling in the sandbox boundary, secret handling, dependency scan, air-gap egress verification (zero artifact data leaves in air-gap mode). ITAR/FN handling note.

### 5.11 Technical Documentation Agent
`/docs/`: internal (architecture, how to add a parser, how to evolve the rubric/catalog, debugging), external (install Docker + air-gap, config reference, catalog/rubric authoring, API reference, security/air-gap guide), end-user (what QUILL is, how to review & attest findings, Slack usage). Plus **methods & limitations** doc required by the DLA Phase I deliverable.

### 5.12 Compliance / SBIR Liaison Agent
Keeps the build aligned to the solicitation: maps each capability to the DLA topic's required capabilities and Phase I deliverables; maintains the traceability matrix (topic requirement → feature → test); flags scope/timeline/criteria changes (paired with the daily solicitation watch). Prepares Phase I demo script + the rework-reduction assessment.

### 5.13 Release Coordinator Agent
Final per-phase validation. Runs the checklist (§8), confirms all tests green, docs complete, demo rehearsed, rollback documented. Only this agent marks a phase shippable.

---

## 6. Three-Phase Build Sequence (mapped to DLA Phase I / II / III)

> Sequencing principle: **build one tier/layer at a time; prove each before adding the next.** No over-engineering.

### PHASE I — Feasibility Prototype (DLA Phase I · ≤12 months · ≤$100K · sandbox, no ATO)
**Goal:** a functional prototype that ingests draft/historical RMF artifacts, runs Tier 0 + Tier 1 + Tier 2 analysis, emits confidence-scored findings traceable to source text, enforces the human attestation gate, and quantifies potential rework reduction.

```
STEP 1 — Design (System Designer, System Architect, Frontend Designer, Security Engineer, Compliance Liaison)
  → SYSTEM_DESIGN.md, ARCHITECTURE.md, DESIGN_SPEC.md, threat model, requirement→feature matrix. PM reviews before code.

STEP 2 — Core build (parallel)
  Track A [Backend]: ingestion+normalization; Tier 0 rule/KB engine; OSCAL import; Postgres schema
  Track B [Backend + ML/Eval]: Tier 1 retrieval/extraction; Tier 2 local-LLM sufficiency scoring; source-span + citation validation; circuit breaker (threshold 3)
  Track C [Integration/Reuse]: reuse AXO auth + provenance + audit + Change-Request as the attestation gate; add attester role
  [QA] writes tests from day one. [ML/Eval] stands up the labeled ground-truth set + eval harness.

STEP 3 — UI + attestation + Slack (parallel)
  Track A [Frontend]: upload/queue, run view, finding-review+attestation screen with source highlighting, audit viewer, export
  Track B [Slack Bot]: status/findings/attest/health + file upload
  Track C [Backend]: signed export (report + OSCAL POA&M + audit artifact)

STEP 4 — Hardening + evaluation
  [QA] full suite; [Security] audit + air-gap egress check; [ML/Eval] run metrics vs ground truth (recall, FP rate, traceability, calibration)
  [Compliance Liaison] rework-reduction assessment + methods/limitations doc + demo script
  [Release Coordinator] Phase I checklist

STEP 5 — Phase I deliverables (the DLA-required set)
  ✓ Functional prototype in approved R&D sandbox
  ✓ Documentation of methods and limitations
  ✓ Demonstration that findings trace to source text
  ✓ Quantitative + qualitative assessment of potential rework reduction
  ✓ Recommendations for Phase II
```

**Phase I scope (in):** PDF/DOCX/MD + OSCAL ingest; SP 800-53 Rev.5 baseline + 800-53A objectives; Tier 0–2; confidence-scored findings with spans; human attestation gate (signed); desktop review UI; signed export; Slack basics; full test + eval; docs.
**Phase I scope (out):** Tier 3 cloud escalation beyond a demo toggle; multi-program scaling; enterprise eMASS integration; fine-tuning; cross-artifact dependency graph (design interface only).

### PHASE II — Validated Scale (DLA Phase II · ≤24 months · ≤$1M)
**Goal:** expand validated capabilities for broader adoption, integrate with enterprise RMF workflows while preserving cybersecurity authority, correlate documentation analysis with evolving system configurations, support continuous documentation improvement.

In scope: multi-program/multi-tenant pre-adjudication at scale; **eMASS-class integration** (read draft packages, write findings back as comments/POA&M — never authorization); cross-artifact dependency graph (optionally Memgraph) for consistency at scale; continuous re-analysis as configurations evolve; analytics on rework reduction across programs; optional Tier 3 escalation hardened; begin fine-tuning a local model (e.g., Gemma) **only once enough attested findings are logged**; CMMC L2 evidence and stronger air-gap packaging. Preserve the human-attestation gate everywhere.

### PHASE III — Production / Dual-Use (DLA Phase III · no funding/PoP limit; proposals to SBIR2@dla.mil)
**Goal:** transition a production-grade product into enterprise RMF workflows for DoW labs, acquisition programs, civilian RMF agencies, and regulated commercial sectors (finance, healthcare, critical infrastructure) under SP 800-53 / FedRAMP / ISO 27001.

In scope: productized deployment (SaaS + on-prem + air-gap); multi-framework catalogs; enterprise SSO/RBAC; marketplace of rubrics/catalogs; managed + self-hosted licensing (offline-validated, no phoning home); full MERP suite integration. Human authority + accountability preserved as the core differentiator.

---

## 7. Cross-Cutting Requirements — Every Agent Respects These

- **Brand:** QUILL brand guide — light-green palette (`#6fcf97` primary, `#a8e6c1` accent, `#ff7a6b` alarm), Syne/DM Mono/Instrument Serif, 8-bit owl mascot + four status states (Idle/Reading/Alarm/Attested), dark-mode-first, semantic finding-status colors.
- **Reuse AXO platform:** shared `/quill-platform/` structure mirroring `/msp-platform/`, shared JWT auth + roles, shared provenance/audit/Change-Request services, settings integration card, MERP nav.
- **Never automate authorization:** no agent builds logic that recommends or implements an authorize/deny decision. QUILL informs.
- **Traceability is mandatory:** any finding without a valid in-document source span is a bug.
- **Local-first / air-gap:** zero artifact data egress in air-gap mode; T3 cloud path opt-in and disabled in air-gap.
- **CMMC L2 (Self) + ITAR:** treat sandbox artifacts as CUI; document handling; disclose any foreign nationals per topic §3.5.
- **Slack bot is first-class.**

---

## 8. Final Validation Checklist (PM marks each phase "Done")

### Phase I — Functional
- [ ] Ingests PDF, DOCX, MD, and OSCAL artifacts and normalizes to control-keyed form
- [ ] Loads SP 800-53 Rev.5 baseline + 800-53A objectives from config
- [ ] Tier 0 deterministically flags missing/inconsistent/required-field gaps with no LLM
- [ ] Tier 2 local-LLM distinguishes narrative-present vs evidence-sufficient per determination statement
- [ ] Every finding has type, severity, calibrated confidence, recommendation, and a valid source span
- [ ] Citation validation rejects any finding whose cited span isn't in the artifact
- [ ] Circuit breaker set to **3** (not 999); trips to human review on low-confidence/contradiction storms
- [ ] No finding is authoritative until a named human approves/edits/rejects it (signed)
- [ ] Provenance chain + tamper-proof audit trail record every action; integrity verifiable
- [ ] Desktop UI shows source text ↔ finding with highlighting; approve/edit/reject works
- [ ] Signed export produces human report + OSCAL POA&M + audit artifact
- [ ] Slack: status / findings / attest / health + file upload
- [ ] Runs fully in the approved R&D sandbox with **no ATO** and **no outbound artifact data** in air-gap mode

### Phase I — Quality / Eval
- [ ] Deficiency-detection recall ≥ 80% on the labeled ground-truth set
- [ ] Low-value/false-positive finding rate ≤ 20%
- [ ] Traceability = 100% (every finding maps to a source span)
- [ ] Confidence calibration demonstrated (score correlates with human agreement)
- [ ] Security audit: zero unresolved high-severity findings; air-gap egress = zero; prompt-injection cannot make QUILL assert authorization or suppress findings
- [ ] Chaos: survives LLM-down (degrades to Tier 0 + human), corrupted artifact, storage outage

### Phase I — DLA Deliverables
- [ ] Functional prototype demonstrated
- [ ] Methods & limitations documented
- [ ] Findings-trace-to-source demonstrated
- [ ] Quantitative + qualitative rework-reduction assessment delivered
- [ ] Phase II recommendations delivered

### Phase II / III gates (summary)
- [ ] Multi-program scale + eMASS-class integration that writes findings, never authorizations
- [ ] Continuous re-analysis as configs evolve; cross-program rework analytics
- [ ] Fine-tuning only after sufficient attested-finding data; human gate preserved
- [ ] Production deployment (SaaS/on-prem/air-gap), multi-framework, offline-validated licensing

---

## 9. Instructions for the Project Manager Agent

1. **Read this document twice.** Track the AXO-reuse mapping carefully — do not rebuild what AXO already provides.
2. **Dispatch Phase I Step 1 agents in parallel.** Wait for all design deliverables; review before any code.
3. **Dispatch Step 2 parallel tracks.** Prove Tier 0 before Tier 1, Tier 1 before Tier 2. Do not skip the sequencing.
4. **Enforce the non-negotiables**, especially: human attestation gate, mandatory source spans, circuit-breaker = 3, no authorization automation, air-gap egress = zero.
5. **At Hardening, personally verify the Phase I checklist (§8).** Anything failing goes back with specific feedback.
6. **Only the Release Coordinator marks a phase shippable.**
7. **Log every architecture decision in `DECISIONS.md`** (template below). Resolve ambiguity by writing down the decision and why.
8. **Keep the Compliance Liaison's requirement→feature→test matrix current** so the prototype always maps to the DLA topic.
9. **Ship a tool that works for an RMF assessor's real workflow**, not one that merely passes tests.

Begin by dispatching Phase I Step 1. Good luck.

---

## 10. Appendix — Decision Log Template (`DECISIONS.md`)

```markdown
## DECISION-001: Local LLM choice for Tier 2 evidence scoring
Date: 2026-MM-DD
Decider: System Architect Agent
Options considered:
  - Ollama + Mistral 24B (chosen — inherited from AXO, proven on the Alienware m18 R2)
  - Ollama + Llama 3.x
  - Cloud-only (rejected — violates air-gap principle)
Decision: Ollama + Mistral 24B locally; Claude API as opt-in Tier 3 only
Reasoning:
  - Air-gap capability is non-negotiable for CUI artifacts
  - Reuses AXO's proven local-inference setup
  - Defers fine-tuning until attested-finding data exists
Trade-offs accepted:
  - Local inference latency higher than cloud; acceptable for batch artifact analysis
```

Log every significant decision in this format. Future engineers will thank you.

---

*References: NIST SP 800-37 Rev.2; NIST SP 800-53 Rev.5; NIST SP 800-53A Rev.5 (determination statements; examine/interview/test; review→study→analyze depth); NIST OSCAL (machine-readable catalogs, profiles, SSP/POA&M); confidence-aware RAG (retrieval scoring → citation validation → abstention). Heritage: AXO backend (FastAPI, tiered healing engine, provenance chain, tamper-proof audit trail, PR-like Change Requests, GPG signing, React/Tauri UI, Slack bot) and BUILD_HEALING_GRAPH.md (PM-agent orchestration, generic-first, API-first, no phoning home).*

*End of QUILL build specification.*
