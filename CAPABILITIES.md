# QUILL / AXO — Capability Q&A

> Plain answers to common technical-diligence questions about the AXO platform and the QUILL (RMF pre-adjudication) product built on it. Each answer is labeled **Today** (shipping/specified), **Roadmap** (architecturally supported, not yet wired), or **Out of scope** (not pursued by design) so there's no ambiguity about what exists.
>
> **Quick frame:** **AXO** analyzes *operational state* (alerts/telemetry) and proposes remediation. **QUILL** reuses the same engine but analyzes *documents/evidence* (RMF artifacts) and emits findings. Same architecture, different input. QUILL never makes the authorization decision.

---

## 1. Current artifact analysis capability
- **AXO (Today):** analyzes **operational state and event data** — alerts/telemetry from ScienceLogic SL1, Zabbix, and Fleet, plus device/CMDB context. The reasoning engine consumes normalized state to *propose* remediation, gated by human approval before execution.
- **QUILL (Today):** analyzes **written artifacts** as the primary input — control implementation statements, SSPs, architecture documents (PDF/DOCX/Markdown/OSCAL). It reads documents, it does not act on systems.
- So: AXO = operational-state analysis; QUILL = document/evidence analysis.

## 2. NIST 800-53 & RMF framework knowledge
- **QUILL (Today):** ships a **NIST SP 800-53 Rev. 5 control catalog (OSCAL-based)** and a data model with exactly: control ID, control description, implementation intent, and an **evidence-sufficiency rubric derived from SP 800-53A determination statements**. It distinguishes "a control narrative exists" from "the evidence is sufficient and clear."
- **AXO:** was not built around 800-53; that control knowledge lives in QUILL.

## 3. General architecture & extensibility
- **Adapters (Today):** new data sources/alert types integrate via a normalized `BaseAdapter` interface (`fetch` → `normalize`). Current adapters: SL1, Fleet, ConnectWise (AXO); PDF/DOCX/MD/OSCAL (QUILL). Adding a source = one new adapter, no engine changes.
- **API surface (Today):** API-first. REST (FastAPI): `/ingest`, `/analysis`, `/findings`, `/attestation`, `/audit`, `/exports`, `/admin`; OpenAPI docs at `/docs`. MCP server exposes the same as tools. JWT auth, roles `admin/engineer/viewer/attester`.
- **Domain swap (Today, proven):** the reasoning engine is parameterized by **config + rubric**, not hardcoded. QUILL *is* the proof — we swapped "propose remediation" for "score evidence sufficiency / emit findings" by changing the catalog, rubric, and finding-types, not the engine.

## 4. External integrations — threat & compliance context
- **Roadmap:** the adapter + framework-agnostic catalog model is designed to ingest **threat-intel** (MITRE ATT&CK, vulnerability databases, Recorded Future) and **additional compliance frameworks** (NIST CSF, ISO 27001, SOC 2). These would be new adapters/catalogs — not a re-architecture.
- **Straight answer:** those specific feeds are **not wired up today**. Low-friction roadmap, not a current integration.

## 5. Evidence, audit trail & compliance export
- **Approval metadata (Today):** every attestation captures **who** (named JWT identity, role `attester`), **decision** (approve/edit/reject), **justification** (reasoning/change rationale), **timestamp**, the **original AI finding preserved verbatim**, and any **edited content** — as a **GPG-signed record** in a **SHA-256 hash-chained, tamper-evident ledger** (`/audit/verify-integrity` verifies the chain).
- **Exports (Today):** signed human-readable findings report; **OSCAL-style POA&M** of open findings; integrity-verifiable audit artifact.
- **Domain renderings:** RMF change summaries, compliance narratives, and IR timelines are **export templates** off the same signed records — the metadata is already captured; new formats don't require new data capture.

## 6. Policy engine & reasoning customization
- **Rule authoring (Today):** rules live in **config/YAML** (control baselines, severity thresholds, approval triggers). A domain author defines them without touching the engine — no engineering required.
- **Out-of-policy / high-risk handling (Today):** if the LLM proposes something out of policy, contradictory, low-confidence, or high-risk, it **does not act** — a **circuit breaker (trips at 3 strikes)** routes the item to human review, and every finding/action stays `unattested` until a named human signs off. Nothing AI-proposed is authoritative on its own.

## 7. Testing, validation & risk management
- **Sandbox (Today):** runs in an isolated sandbox against draft/historical/synthetic data — analysis happens **without executing** on production systems (for QUILL there is no execution at all; it only reads and scores).
- **Validation (Today):** labeled ground-truth set + evaluation harness measuring recall, false-positive rate, traceability, and confidence calibration (ECE).
- **Feedback loop (Today → ongoing):** human attest/edit/reject decisions are captured against the AI's original output; that labeled stream drives **rubric/threshold tuning** (versioned via GitOps). **Fine-tuning is deferred** until enough real attested decisions exist — no fine-tuning on synthetic-only data.

## 8. Penetration testing use case
- **Out of scope (by design):** QUILL/AXO do **not** orchestrate offensive tooling (Nmap, Metasploit, Burp, Qualys) and do **not** simulate attack chains (recon → exploitation → lateral movement). That is outside both AXO's (self-healing remediation) and QUILL's (compliance documentation analysis) intent and design. We'd rather be precise than imply a capability we don't have.

---

*Suggested next step: a live walkthrough of the audit trail, the attestation gate, and the 800-53 evidence-sufficiency analysis on a sanitized package — the fastest way to make these concrete. References: NIST SP 800-37 Rev.2, SP 800-53 Rev.5, SP 800-53A Rev.5, NIST OSCAL.*
