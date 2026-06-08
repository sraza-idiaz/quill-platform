# 01 — Functional Requirements (FRD)

> Enumerated, testable requirements for QUILL. Each FR has a stable ID, a priority, the phase it lands in, and acceptance criteria. The Requirements Traceability Matrix (`08_…`) maps every FR to a DLA topic requirement and a test. **An FR is "done" only when its acceptance criteria are demonstrably met by an automated test.**

**Priority:** P0 = Phase I blocking · P1 = Phase I should-have · P2 = Phase II+
**Convention:** "The system shall…" statements are binding. IDs are stable; never renumber.

---

## A. Ingestion & Normalization (`FR-ING`)

| ID | Requirement | Pri | Phase | Acceptance criteria |
|---|---|---|---|---|
| FR-ING-01 | The system shall ingest artifacts in PDF, DOCX, Markdown, and OSCAL JSON formats. | P0 | I | Each format uploads, parses, and produces a stored `artifact` row with a content hash. |
| FR-ING-02 | The system shall normalize every ingested artifact to a **control-keyed internal representation** that preserves source locators (page/section/char-offset). | P0 | I | For a known artifact, normalized text segments map back to exact source locations. |
| FR-ING-03 | The system shall compute and store a cryptographic hash of each ingested artifact at ingest time. | P0 | I | Re-ingesting an identical file yields an identical hash; a 1-byte change yields a different hash. |
| FR-ING-04 | The system shall import OSCAL SSP/component artifacts and map them to internal control keys. | P0 | I | A sample OSCAL SSP imports and its control implementations are addressable by control ID. |
| FR-ING-05 | The system shall reject or quarantine corrupted/unparseable artifacts without crashing, recording the failure in the run. | P0 | I | A deliberately corrupted file produces a `failed`-status run with a reason, not an exception. |
| FR-ING-06 | The system shall set artifact status across `ingested → analyzing → reviewed → attested`. | P0 | I | Status transitions are observable via API and never skip illegally. |
| FR-ING-07 | The system shall support folder-watch ingestion (drop a file → auto-ingest). | P1 | I | A file placed in the watched folder is ingested within the configured poll interval. |
| FR-ING-08 | The system shall support eMASS-class package export ingestion. | P2 | II | Deferred — interface designed in Phase I. |

## B. Catalog & Baseline (`FR-CAT`)

| ID | Requirement | Pri | Phase | Acceptance criteria |
|---|---|---|---|---|
| FR-CAT-01 | The system shall load the NIST SP 800-53 Rev.5 control catalog from OSCAL/YAML config (not hardcoded). | P0 | I | Controls are queryable by ID/family; swapping the config file changes the loaded catalog. |
| FR-CAT-02 | The system shall load SP 800-53A Rev.5 assessment objectives / determination statements per control from config. | P0 | I | For a control (e.g., `AC-2`), its determination statements are retrievable. |
| FR-CAT-03 | The system shall select a control **baseline** (Low/Moderate/High) via config and scope coverage checks to that baseline. | P0 | I | Changing the configured baseline changes which controls are "required." (Default baseline recorded in `DECISIONS.md`.) |
| FR-CAT-04 | The system shall be catalog-agnostic so additional frameworks (FedRAMP, ISO 27001, CMMC) can be loaded later. | P1 | I/II | A second (toy) catalog loads without code changes. |

## C. Tier 0 — Deterministic Rule/KB Engine (`FR-T0`)

| ID | Requirement | Pri | Phase | Acceptance criteria |
|---|---|---|---|---|
| FR-T0-01 | The system shall, with **no LLM**, detect controls in the baseline that have **no implementation statement** in the artifact set (missing-control coverage). | P0 | I | Removing a control's narrative from a fixture produces a `missing` finding deterministically. |
| FR-T0-02 | The system shall detect **required-field absence** within a control implementation statement per the configured rubric. | P0 | I | A statement missing a required field yields a finding citing the gap. |
| FR-T0-03 | The system shall detect **cross-artifact inconsistency** (same control described differently across artifacts). | P0 | I | Two artifacts contradicting on a control produce an `inconsistent` finding. |
| FR-T0-04 | The system shall validate OSCAL artifacts against the OSCAL schema and flag violations. | P0 | I | An OSCAL file with a schema violation is flagged with the offending path. |
| FR-T0-05 | Tier 0 shall be fully deterministic and reproducible — identical input yields identical findings. | P0 | I | Running T0 twice on the same input produces byte-identical findings. |

## D. Tier 1 — Retrieval & Extraction (`FR-T1`)

| ID | Requirement | Pri | Phase | Acceptance criteria |
|---|---|---|---|---|
| FR-T1-01 | The system shall map artifact text to candidate control IDs and 800-53A assessment objectives. | P0 | I | For a fixture, known statements resolve to the correct control IDs above a confidence threshold. |
| FR-T1-02 | The system shall build an **evidence index** linking text segments to controls/objectives with **source spans** (artifact id + locator + quoted text). | P0 | I | Each indexed segment carries a verifiable locator and exact quote. |
| FR-T1-03 | Retrieval scoring shall be recorded so downstream tiers can apply confidence-aware logic. | P0 | I | Retrieval scores are persisted on the evidence index entries. |

## E. Tier 2 — Local-LLM Evidence-Sufficiency Scoring (`FR-T2`)

| ID | Requirement | Pri | Phase | Acceptance criteria |
|---|---|---|---|---|
| FR-T2-01 | The system shall, using a **local** LLM (Ollama), judge **evidence sufficiency** per determination statement, distinguishing *narrative present* from *evidence sufficient*. | P0 | I | For labeled fixtures, "narrative-present-but-insufficient" cases are graded distinctly from "sufficient" cases (per `03_…RUBRIC`). |
| FR-T2-02 | Each Tier 2 finding shall include a **type**, **severity**, **calibrated confidence (0–1)**, and a **recommendation**. | P0 | I | Every emitted finding carries all four fields populated. |
| FR-T2-03 | Each Tier 2 finding shall carry **≥1 source span**, and the pipeline shall **reject** any finding whose cited text is not present in the artifact (citation validation). | P0 | I | A finding citing absent text is dropped and logged; never surfaced. |
| FR-T2-04 | Tier 2 shall run **on-box** with no outbound network calls in default/air-gap mode. | P0 | I | Network egress monitor shows zero outbound during a T2 run. |
| FR-T2-05 | Finding `type` shall be one of: `missing`, `inconsistent`, `weak_narrative`, `insufficient_evidence`, `narrative_present_evidence_unclear`. | P0 | I | Emitted types are constrained to this enum. |

## F. Tier 3 — Cloud Escalation (`FR-T3`)

| ID | Requirement | Pri | Phase | Acceptance criteria |
|---|---|---|---|---|
| FR-T3-01 | The system shall provide an **opt-in** Tier 3 escalation path (Claude API) for low-confidence/complex artifacts only. | P1 | I (demo toggle) | Toggle off by default; when off, no cloud path is reachable. |
| FR-T3-02 | Tier 3 shall be **disabled in air-gap mode** and shall **never** be invoked with data classified restricted. | P0 | I | In air-gap mode the T3 path is unreachable even if toggled. |

## G. Confidence & Circuit Breaker (`FR-CONF`)

| ID | Requirement | Pri | Phase | Acceptance criteria |
|---|---|---|---|---|
| FR-CONF-01 | The system shall apply confidence-aware logic: high-confidence/clear → emit finding; low-confidence/ambiguous → emit a `flag_for_review` deferral rather than an assertion. | P0 | I | Below-threshold cases produce a deferral, not a confident claim. |
| FR-CONF-02 | The system shall implement a **circuit breaker with threshold = 3** that trips an artifact to full human review on repeated low-confidence/contradictory outputs. | P0 | I | The 3rd consecutive low-confidence/contradiction trips the breaker and routes to human review; configured value is 3, not 999. |
| FR-CONF-03 | Confidence scores shall be **calibrated** such that the score correlates with human agreement (see `04_…EVALUATION`). | P0 | I | Calibration curve / reliability metric demonstrated on the ground-truth set. |

## H. Findings & Attestation (`FR-ATT`) — the hard gate

| ID | Requirement | Pri | Phase | Acceptance criteria |
|---|---|---|---|---|
| FR-ATT-01 | A finding shall have lifecycle status `unattested → approved | edited | rejected`. | P0 | I | Illegal transitions are rejected; status observable via API. |
| FR-ATT-02 | No finding shall be exported or treated as authoritative while `unattested`. | P0 | I | Export excludes unattested findings; attempting to mark one authoritative fails. |
| FR-ATT-03 | Attestation shall be performed by a named user holding the **`attester`** role and recorded with a **GPG signature** in the provenance chain. | P0 | I | Approve/edit/reject by an attester produces a signed provenance record; a non-attester is denied. |
| FR-ATT-04 | Every attestation action shall be written to the **tamper-proof audit trail** and be integrity-verifiable. | P0 | I | Audit ledger integrity check passes; tampering is detectable. |
| FR-ATT-05 | The system shall **never** emit, store, or expose any field that recommends or implements an authorize/deny decision. | P0 | I | No code path produces an authorization recommendation; tested negatively. |
| FR-ATT-06 | An attester editing a finding shall preserve the original AI-proposed finding and the edit, both signed. | P0 | I | Original + edited versions and signatures are retrievable. |

## I. Export (`FR-EXP`)

| ID | Requirement | Pri | Phase | Acceptance criteria |
|---|---|---|---|---|
| FR-EXP-01 | The system shall produce a **GPG-signed human-readable report** of attested findings. | P0 | I | Report exports, signature verifies, includes source spans. |
| FR-EXP-02 | The system shall produce an **OSCAL-style POA&M** of open findings (never an authorization). | P0 | I | POA&M validates against OSCAL POA&M model; contains no authorization field. |
| FR-EXP-03 | The system shall produce an **integrity-verifiable audit artifact** for a run. | P0 | I | Exported audit artifact verifies against the ledger. |

## J. API & Roles (`FR-API`)

| ID | Requirement | Pri | Phase | Acceptance criteria |
|---|---|---|---|---|
| FR-API-01 | Every capability shall be exposed via REST (FastAPI) and via an MCP server. | P0 | I | Each user-facing action has a corresponding API endpoint + MCP tool. |
| FR-API-02 | The system shall add an **`attester`** role to AXO's existing `admin/engineer/viewer` model, gating attestation actions. | P0 | I | `attester` can attest; `viewer` cannot; enforced via `require_role`. |
| FR-API-03 | The system shall enforce **tenant isolation** — no artifact, finding, or audit data leaks across tenants. | P0 | I | Cross-tenant access attempts are denied; tested. |

## K. Desktop UI (`FR-UI`)

| ID | Requirement | Pri | Phase | Acceptance criteria |
|---|---|---|---|---|
| FR-UI-01 | The UI shall provide artifact upload + a run queue with status. | P0 | I | Upload works; queue reflects live run status. |
| FR-UI-02 | The UI shall provide the **finding-review + attestation screen** — source text on one side, finding+confidence+severity on the other, with **source-span highlighting** that maps a finding to the exact quoted text. | P0 | I | Selecting a finding highlights its exact source span; approve/edit/reject works and triggers the signed flow. |
| FR-UI-03 | The UI shall provide an audit/provenance timeline viewer. | P0 | I | Attestation history renders from the audit ledger. |
| FR-UI-04 | The UI shall provide an export screen and a settings/integrations page. | P0 | I | Exports trigger from UI; settings expose air-gap + T3 toggles. |
| FR-UI-05 | The UI shall meet accessibility + reduced-motion requirements and be dark-mode-first per the QUILL brand guide. | P1 | I | Axe/contrast checks pass; reduced-motion respected. |

## L. Slack Bot `@quill` (`FR-SLK`) — first-class

| ID | Requirement | Pri | Phase | Acceptance criteria |
|---|---|---|---|---|
| FR-SLK-01 | `/quill status <artifact>` shall return run status + finding counts by severity. | P0 | I | Command returns correct counts for a known artifact. |
| FR-SLK-02 | `/quill findings <artifact>` shall return top findings with control ID, confidence, and a source link. | P0 | I | Returns ranked findings with working source references. |
| FR-SLK-03 | `/quill attest <finding-id>` shall provide interactive approve/edit/reject producing a signed record. | P0 | I | Attestation via Slack writes a signed provenance + audit entry; respects `attester` role. |
| FR-SLK-04 | `/quill health` shall report backend/tier health. | P0 | I | Returns tier + backend status. |
| FR-SLK-05 | Dropping an artifact file in Slack shall ingest + analyze it and return a finding summary. | P1 | I | File upload triggers a run and returns a summary. |
| FR-SLK-06 | The bot shall respect tenant isolation and degrade gracefully when the backend is unreachable. | P0 | I | Backend-down yields a clean error, not a stack trace; no cross-tenant data. |

## M. Resilience / Degradation (`FR-RES`)

| ID | Requirement | Pri | Phase | Acceptance criteria |
|---|---|---|---|---|
| FR-RES-01 | If the LLM tier is unavailable, the system shall degrade to Tier 0 + `flag_for_review` rather than fail. | P0 | I | With Ollama down, runs complete using T0 and defer the rest. |
| FR-RES-02 | The system shall survive a storage outage without data corruption and recover on reconnect. | P0 | I | Storage outage during a run leaves consistent state; run resumes/fails cleanly. |
| FR-RES-03 | The system shall never write artifact content into logs or telemetry. | P0 | I | Log scan shows no artifact content; tested. |

---

## Finding lifecycle (state machine)

```
                 ┌─────────────┐
   T0/T1/T2  ──▶ │ unattested  │
                 └─────┬───────┘
        attester action │  (signed, audited)
        ┌───────────────┼────────────────┐
        ▼               ▼                 ▼
   ┌─────────┐   ┌─────────────┐   ┌──────────┐
   │ approved│   │   edited     │   │ rejected │
   └─────────┘   └─────────────┘   └──────────┘
   (exportable / authoritative)     (excluded from export)
```

Low-confidence outputs never enter as `unattested` findings — they enter as `flag_for_review` deferrals (FR-CONF-01). The circuit breaker (FR-CONF-02) can route an entire artifact to human review.
