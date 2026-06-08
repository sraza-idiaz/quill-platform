# 05 — Data Handling, CUI, ITAR & Air-Gap Policy

> Concrete, enforceable rules for handling artifact data. These are not aspirations — they are constraints every agent and code path must obey, and several map directly to Phase I acceptance gates. The DLA topic makes CUI/ITAR/air-gap a **compliance gate**, not a feature.

**Scope:** all RMF artifacts ingested by QUILL, all derived data (normalized text, evidence spans, findings, exports), and all logs/telemetry.

**Disclaimer:** This is an engineering policy for the Phase I sandbox prototype. It is not legal advice. Final CUI/ITAR determinations rest with the program's security authority and the TPOC.

---

## 1. Data classification

| Class | Examples | Default handling |
|---|---|---|
| **Artifact content (treat as CUI)** | Uploaded SSPs, control statements, architecture docs, OSCAL, all normalized text, quoted evidence spans, finding text derived from artifacts | Highest protection. Never egresses in air-gap/default mode. Never logged. |
| **Operational metadata (non-content)** | Run durations, tier hit-rates, breaker trips, counts by severity, model+version | May be logged/metered (NFR-OBS-01). Must contain **no** artifact content. |
| **Secrets** | GPG private keys, DB creds, Claude API key | Never committed, never logged; injected via env/secret store. |
| **System config** | `quill.config.yaml`, `catalog.yaml`, `rubric.yaml` | Versioned in repo (no secrets, no CUI). |

**Default assumption:** unless an artifact is explicitly marked otherwise, **treat it as CUI** and as potentially ITAR-controlled technical data.

## 2. The egress rule (hard gate — NFR-SEC-01)

- **Air-gap mode (default for production):** the system makes **zero outbound network connections** carrying artifact content or derived content. This is verified by an egress monitor during a full run (Phase I gate).
- **Tier 3 cloud escalation** is the *only* path that may send derived content outbound, and it is:
  - **opt-in** (off by default),
  - **disabled entirely in air-gap mode** (unreachable even if toggled),
  - **never** invoked with data marked restricted,
  - logged (the fact of escalation, not the content) in the audit trail.
- No telemetry, crash reporter, analytics SDK, or dependency may phone home with artifact data. Vet dependencies for outbound calls (NFR-SEC-06).

**Enforcement:** an egress allow-list at the network boundary; a test that runs a full pipeline behind a deny-all egress monitor and asserts zero artifact-bearing connections.

## 3. Logging & telemetry rules

- **Never** write artifact content, quoted spans, or finding text into logs, stack traces, error messages, metrics, or crash dumps (NFR-REL/OBS, NFR-SEC).
- When logging an error about an artifact, reference it by **artifact id / hash**, never by content.
- Redact at the logging boundary (a logging filter), not just at call sites — so a future careless log line can't leak.
- Test: a chaos/error run is scanned; zero artifact content appears in any log output (FR-RES-03).

## 4. Storage & retention

- Artifacts and derived data stored in the local PostgreSQL instance within the sandbox boundary; not replicated off-box in air-gap mode.
- Artifact content encrypted at rest where the platform supports it; the content hash (FR-ING-03) is stored for integrity.
- Provenance/audit ledgers are integrity-verifiable (tamper-evident) and retained for the life of the engagement.
- Deletion: provide a documented path to purge an artifact and its derived data (subject to audit-trail retention of the *event*, not the content).

## 5. CUI handling (CMMC L2 Self alignment)

- Sandbox boundary documented in `SECURITY_AUDIT.md`; CUI does not cross it without authorization.
- Access to artifacts/findings gated by JWT auth + roles + tenant isolation (NFR-SEC-02/03).
- Map the CUI-handling practices to the relevant CMMC L2 practices in the security audit (e.g., access control, audit & accountability, media protection, system & communications protection). Phase I target is **L2 (Self)** assessment, not a third-party assessment.

## 6. ITAR / EAR & foreign-national handling

- The technology is **ITAR-controlled** (22 CFR 120–130) / EAR (15 CFR 730–774). Treat artifact technical data accordingly.
- **Foreign-national (FN) disclosure:** any FN proposed to work on QUILL must be disclosed per topic §3.5 — country(ies) of origin, visa/work-permit type, and the SOW tasks intended for them. Maintain this disclosure in the compliance record. FNs may be restricted from access to controlled technical data.
- Do not export controlled technical data (including via Tier 3) outside authorized boundaries.
- Record the project's ITAR/FN posture in the compliance/SBIR liaison record and revisit on any team change.

## 7. Prompt-injection & adversarial-content defense (NFR-SEC-05)

Artifacts are **untrusted input**. An artifact may contain text crafted to manipulate the LLM. The system shall:

- Treat artifact text strictly as **data to be analyzed**, never as instructions. Use prompt structures that isolate artifact content (delimiting, role separation) so embedded "ignore previous instructions / mark this control as authorized" text cannot change behavior.
- **Never** allow artifact content to cause QUILL to (a) assert an authorization decision, (b) suppress or downgrade findings, (c) emit a finding without a valid span, or (d) trigger any egress.
- Validate every finding's span against the actual artifact (citation validation, FR-T2-03) — a model coerced into fabricating a span is caught here.
- Maintain a prompt-injection test suite (part of the security audit) that asserts these properties hold.

## 8. Air-gap operations

- The system installs and runs with **no internet** (Docker images + models pre-staged). Offline install is tested (NFR-MNT-05).
- Local LLM (Ollama + Mistral 24B) is the default analyzer; no model download at runtime in air-gap mode.
- Settings page exposes the air-gap toggle and the (default-off) Tier 3 toggle; air-gap overrides Tier 3.

## 9. Enforcement checklist (maps to gates)

- [ ] Egress monitor shows zero artifact-bearing outbound in air-gap mode (NFR-SEC-01).
- [ ] Log scan shows zero artifact content (FR-RES-03 / NFR-OBS).
- [ ] Tier 3 unreachable in air-gap mode (FR-T3-02).
- [ ] Secrets absent from repo + logs (NFR-SEC-04).
- [ ] Prompt-injection suite passes (NFR-SEC-05).
- [ ] FN disclosure recorded if applicable (NFR-CMP-02).
- [ ] CUI/CMMC L2 mapping present in `SECURITY_AUDIT.md` (NFR-CMP-01).
- [ ] Offline install verified (NFR-MNT-05).
