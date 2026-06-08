# 02 — Non-Functional Requirements (NFRD)

> Quality attributes and constraints. Each NFR is measurable and verifiable. Where a target is an estimate for a Phase I prototype (not a contractual SLA), it is marked **[prototype target]** — tune against real hardware and record the final value in `DECISIONS.md`.

**Reference hardware:** AXO's proven local-inference box (Alienware m18 R2-class: high-core CPU, ≥32 GB RAM, NVIDIA GPU). Air-gap deployments assume a single workstation/server, not a cluster.

---

## 1. Performance & Throughput

| ID | Requirement | Target | Verification |
|---|---|---|---|
| NFR-PERF-01 | Tier 0 analysis of a typical SSP (≤200 pages) shall complete quickly. | ≤ 30 s **[prototype target]** | Timed run on reference hardware. |
| NFR-PERF-02 | Full pipeline (T0→T1→T2) on a typical SSP shall complete within a batch-acceptable window. | ≤ 10 min **[prototype target]** | Timed run; Tier 2 is the dominant cost. |
| NFR-PERF-03 | Ingestion + normalization of a single artifact shall complete promptly. | ≤ 60 s for ≤200 pages **[prototype target]** | Timed run. |
| NFR-PERF-04 | The UI finding-review screen shall render source-span highlights without perceptible lag. | ≤ 200 ms interaction response | UI profiling / Playwright timing. |
| NFR-PERF-05 | The system shall support batch analysis of multiple artifacts queued sequentially without memory exhaustion. | No OOM over a 10-artifact batch | Soak test. |

> Latency is explicitly a **batch** concern, not interactive. Local inference is accepted as slower than cloud (DECISION-001). Optimize correctness and traceability before speed.

## 2. Scalability

| ID | Requirement | Target | Verification |
|---|---|---|---|
| NFR-SCAL-01 | Phase I shall handle a single-program / single-tenant workload on one workstation. | 1 tenant, 100s of artifacts | Functional. |
| NFR-SCAL-02 | The architecture shall not preclude Phase II multi-tenant / multi-program scaling (tenant isolation present from day one; no global mutable singletons keyed without tenant). | Design review pass | Architecture review. |
| NFR-SCAL-03 | Catalog/rubric loading shall scale to the full 800-53 Rev.5 catalog (1000+ controls/objectives) without manual code edits. | Full catalog loads | Load test. |

## 3. Reliability & Availability

| ID | Requirement | Target | Verification |
|---|---|---|---|
| NFR-REL-01 | A failure in any single tier shall not crash the run; the pipeline degrades (see FR-RES-01). | Graceful degradation | Chaos test (LLM down). |
| NFR-REL-02 | The system shall recover from a storage outage without data loss or corruption. | Consistent state after outage | Chaos test (storage). |
| NFR-REL-03 | The circuit breaker shall prevent emission of unreliable findings under low-confidence storms. | Trips at threshold 3 | Circuit-breaker test. |
| NFR-REL-04 | Analysis runs shall be idempotent/restartable — re-running a failed run shall not duplicate findings. | No duplicate findings | Integration test. |
| NFR-REL-05 | Phase I availability target (sandbox, single node). | Best-effort; no HA required | N/A (documented). |

## 4. Security (cross-references `05_DATA_HANDLING` and the Security Audit)

| ID | Requirement | Target | Verification |
|---|---|---|---|
| NFR-SEC-01 | **Zero outbound network egress of artifact data** in air-gap/default mode. | 0 bytes egress | Egress monitor during full run. |
| NFR-SEC-02 | All inter-service auth uses JWT with role enforcement (reuse AXO `auth.py`). | Enforced on every endpoint | Auth tests; unauthenticated calls rejected. |
| NFR-SEC-03 | Tenant isolation enforced at the data layer. | No cross-tenant reads/writes | Isolation tests. |
| NFR-SEC-04 | Secrets (GPG keys, API keys, DB creds) shall never be committed or logged. | 0 secrets in repo/logs | Secret scan in CI. |
| NFR-SEC-05 | Prompt injection in an artifact shall **not** cause QUILL to assert authorization, suppress findings, or exfiltrate data. | Resists the prompt-injection test suite | Adversarial security test. |
| NFR-SEC-06 | Dependencies shall be scanned; zero unresolved high-severity vulnerabilities at Phase I gate. | 0 unresolved high | Dependency scan (e.g., pip-audit). |
| NFR-SEC-07 | Artifacts treated as CUI; handling per `05_DATA_HANDLING_CUI_ITAR_POLICY.md`. | Policy compliance | Security audit. |

## 5. Auditability & Integrity

| ID | Requirement | Target | Verification |
|---|---|---|---|
| NFR-AUD-01 | Every state-changing action (ingest, analyze, attest, export) shall produce an integrity-verifiable audit event. | 100% of actions audited | Audit-coverage test. |
| NFR-AUD-02 | Audit trail tampering shall be detectable. | Tamper detection passes | Integrity-verification test. |
| NFR-AUD-03 | Every finding shall be traceable to its source span (artifact + locator + quote). | Traceability = 100% | Traceability test (Phase I gate). |
| NFR-AUD-04 | Provenance shall record AI model + version + reasoning path for every finding. | Recorded per finding | Provenance inspection. |

## 6. Usability & Accessibility

| ID | Requirement | Target | Verification |
|---|---|---|---|
| NFR-USE-01 | An RMF assessor shall be able to review and attest a finding without reading documentation. | Task completion in usability check | Heuristic/usability review. |
| NFR-USE-02 | UI shall meet WCAG 2.1 AA contrast and support keyboard navigation. | AA pass | Axe / manual audit. |
| NFR-USE-03 | UI shall honor reduced-motion preferences. | Respected | Manual / automated check. |
| NFR-USE-04 | Source-span highlighting shall make the AI's evidence basis obvious at a glance. | Highlight ↔ finding link clear | Usability review. |

## 7. Maintainability & Portability

| ID | Requirement | Target | Verification |
|---|---|---|---|
| NFR-MNT-01 | Control catalogs, objectives, finding types, severity, and the rubric shall be defined in YAML/OSCAL config — never hardcoded (generic-first). | 0 hardcoded catalog data | Code review / grep test. |
| NFR-MNT-02 | Adding a new artifact parser shall require implementing a documented interface only, no core changes. | New parser via interface | Extension test + docs. |
| NFR-MNT-03 | Adding a new framework catalog shall require config only. | Toy catalog loads | Load test. |
| NFR-MNT-04 | Unit-test coverage ≥ 80% on Tier 0 + the analyzer. | ≥ 80% | Coverage report (Phase I gate). |
| NFR-MNT-05 | The system shall run via Docker and in an air-gapped install (no internet during install/run). | Offline install works | Air-gap install test. |
| NFR-MNT-06 | Code shall follow AXO platform conventions (structure, naming, migration numbering). | Consistent with AXO | Review. |

## 8. Compliance Constraints

| ID | Requirement | Target | Verification |
|---|---|---|---|
| NFR-CMP-01 | Projected CMMC Level 2 (Self) control handling for the sandbox boundary. | L2 self-assessment review | Security audit mapping. |
| NFR-CMP-02 | ITAR (22 CFR 120–130) / EAR (15 CFR 730–774): technical data controlled; any foreign-national involvement disclosed per topic §3.5. | FN disclosure documented | Compliance review. |
| NFR-CMP-03 | No ATO required for Phase I (runs in approved R&D sandbox). | Sandbox-only operation | Deployment review. |
| NFR-CMP-04 | The system shall never reduce governance rigor or automate the authorization decision. | 0 authorization logic | Negative test (FR-ATT-05). |

## 9. Observability (non-artifact-content)

| ID | Requirement | Target | Verification |
|---|---|---|---|
| NFR-OBS-01 | The system shall emit operational metrics (run durations, tier hit-rates, breaker trips) **without** artifact content. | Metrics present, content absent | Log/metric scan. |
| NFR-OBS-02 | Errors shall be logged with enough context to debug without exposing CUI. | Debuggable, CUI-free | Review. |
