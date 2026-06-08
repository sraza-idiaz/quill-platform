# 08 — Requirements Traceability Matrix (RTM)

> The spine that proves QUILL satisfies the DLA solicitation. Each row traces a **DLA topic requirement** → the **FR(s)** that implement it → the **test/evidence** that verifies it → **status**. The Compliance/SBIR Liaison keeps this current; the PM uses it at the Phase I gate. Status: `⬜` not started · `🟦` in progress · `✅` verified.

**Solicitation:** DLA26BZ02-NV006 — AI-Assisted RMF Pre-Adjudication. **Phase I deliverables** and the **four required capabilities** are the anchor rows.

---

## A. Topic-required capabilities → features → tests

| Topic requirement (from solicitation) | FR(s) | Verification / evidence | WP task | Status |
|---|---|---|---|---|
| Operate on **submitted artifacts** as primary input (not conversational UI) | FR-ING-01..06, FR-UI-01 | Upload→run flow; no chatbot is the system of record | T-2.3, T-5.1 | ⬜ |
| **Identify missing, inconsistent, or weak** control implementation statements | FR-T0-01..05, FR-T2-01/05 | Fixtures produce `missing`/`inconsistent`/`weak_narrative` correctly | T-2.4, T-3.3 | ⬜ |
| **Distinguish narrative presence from evidence sufficiency** | FR-T2-01, Rubric `03` §1–4 | Labeled cases graded on both axes; `narrative_present_evidence_unclear` emitted | T-3.2, T-3.3 | ⬜ |
| Generate **structured, confidence-scored** analytical feedback | FR-T2-02, FR-CONF-01/03 | Every finding has type/severity/confidence/recommendation | T-3.3, T-3.5 | ⬜ |
| **Source-traceable** findings (trace to source text) | FR-T1-02, FR-T2-03, NFR-AUD-03 | Traceability test = 100%; citation validation rejects bad spans | T-3.4 | ⬜ |
| **Explicit human attestation** mechanism (no reliance on unreviewed AI) | FR-ATT-01..06 | Signed approve/edit/reject; nothing authoritative while unattested | T-4.2 | ⬜ |
| **Never automate authorization / reduce governance rigor** | FR-ATT-05, NFR-CMP-04 | Negative test: no authorize/deny path exists | T-4.2 | ⬜ |
| Familiarity with **RMF assessment practices** (sufficiency, inherited controls, architectural maturity) | Rubric `03` §3.3–3.4 | Rubric encodes 800-53A methods + inheritance + doc-boundary | T-3.2 | ⬜ |
| Run in **approved R&D sandbox, no ATO** | NFR-CMP-03 | Deployment review; sandbox-only | T-6.4 | ⬜ |
| **Reduce package rejection / rework** without altering RMF authority | Rework assessment `04` §6 | Quant+qual rework-reduction report | T-7.1 | ⬜ |

## B. Phase I deliverables → evidence

| DLA Phase I deliverable | FR/Plan ref | Evidence artifact | WP task | Status |
|---|---|---|---|---|
| **Functional prototype** in approved R&D sandbox | All P0 FRs | Running demo build | T-7.3 | ⬜ |
| **Documentation of methods and limitations** | `03` §3.3, `04` §6 | `methods_and_limitations.md` | T-7.2 | ⬜ |
| **Demonstration findings trace to source text** | FR-T2-03, FR-UI-02 | Trace-to-source demo + recording | T-7.3 | ⬜ |
| **Quantitative + qualitative rework-reduction assessment** | `04` §6 | Rework assessment report | T-7.1 | ⬜ |
| **Recommendations for Phase II** | `06` Phase II | Phase II recs doc | T-7.4 | ⬜ |

## C. Compliance constraints → controls

| Constraint | FR/NFR | Verification | Status |
|---|---|---|---|
| Projected **CMMC Level 2 (Self)** | NFR-CMP-01 | CMMC L2 mapping in `SECURITY_AUDIT.md` | ⬜ |
| **ITAR / EAR**; FN disclosure per §3.5 | NFR-CMP-02, `05` §6 | FN disclosure record; export-control note | ⬜ |
| **Air-gap, zero egress** of artifact data | NFR-SEC-01, FR-T3-02 | Egress monitor = 0; T3 unreachable in air-gap | ⬜ |
| **No artifact content in logs** | FR-RES-03, NFR-OBS | Log scan clean | ⬜ |
| **Prompt-injection resistance** | NFR-SEC-05, `05` §7 | Injection test suite passes | ⬜ |

## D. Phase I acceptance gates → metric source

| Gate (PRD §8) | Source | Status |
|---|---|---|
| Ingests PDF/DOCX/MD/OSCAL → control-keyed | FR-ING-01/02 test | ⬜ |
| Loads 800-53 Rev.5 + 800-53A from config | FR-CAT-01/02 test | ⬜ |
| Tier 0 deterministic gaps, no LLM | FR-T0-05 test | ⬜ |
| Tier 2 narrative-vs-evidence per determination statement | FR-T2-01 test | ⬜ |
| Every finding: type/severity/confidence/recommendation/span | FR-T2-02/03 test | ⬜ |
| Citation validation rejects absent-span findings | FR-T2-03 test | ⬜ |
| Circuit breaker = 3 (not 999) | FR-CONF-02 test | ⬜ |
| No finding authoritative until signed human attestation | FR-ATT-02/03 test | ⬜ |
| Provenance + tamper-proof audit; integrity verifiable | NFR-AUD-01/02 test | ⬜ |
| UI source↔finding highlighting; approve/edit/reject | FR-UI-02 test | ⬜ |
| Signed export: report + OSCAL POA&M + audit artifact | FR-EXP-01..03 test | ⬜ |
| Slack: status/findings/attest/health + upload | FR-SLK-01..06 test | ⬜ |
| Sandbox, no ATO, zero egress in air-gap | NFR-CMP-03, NFR-SEC-01 | ⬜ |
| Recall ≥ 80% | `04` §3 | ⬜ |
| FP ≤ 20% | `04` §3 | ⬜ |
| Traceability = 100% | `04` §3 | ⬜ |
| Calibration demonstrated | `04` §4 | ⬜ |
| Security: 0 unresolved high; injection-safe | T-6.4 | ⬜ |
| Chaos: LLM-down / corrupted / storage-outage | FR-RES-01..03 | ⬜ |

---

## Coverage check

- Every **P0 FR** in `01` must appear in at least one row above. (Audit this when the RTM is seeded at T-1.5.)
- Every **DLA topic bullet** and **Phase I deliverable** has a row (sections A & B). ✅ structurally complete; statuses fill as build progresses.
- Orphan check: any FR with no test, or any test with no FR, is a gap to resolve.
