# SECURITY_AUDIT.md — QUILL (Threat Model + Audit Scaffold)

> Owner: Security Engineer. This file is started in WP-1 (threat model + boundaries) and **completed in WP-6** (the actual audit results: dep scan, egress check, prompt-injection suite, CMMC mapping). Sections marked *(WP-6)* are filled when the audit runs. Pairs with `docs/05_DATA_HANDLING_CUI_ITAR_POLICY.md`.

---

## 1. Scope & trust boundary

- **In scope:** QUILL backend (ingest, analysis tiers, finding/attestation, export, API/MCP), desktop UI, Slack bot, local LLM (Ollama), optional Tier 3, data stores (Postgres, provenance/audit ledgers).
- **Trust boundary:** the approved R&D **sandbox**. CUI artifacts and derived content do not cross it without authorization. Tier 3 (when enabled, non-air-gap) is the only sanctioned egress, content-restricted.
- **Assets to protect:** artifact content (CUI), evidence spans, findings, attestations/signatures, GPG keys, audit-trail integrity, tenant separation.

## 2. Threat model (STRIDE-style)

| Threat | Vector | Mitigation | Req |
|---|---|---|---|
| **Spoofing** | Forged attestation / impersonation | JWT auth; `attester` role; GPG-signed provenance ties action to identity | FR-ATT-03, NFR-SEC-02 |
| **Tampering** | Alter findings/audit after the fact | Tamper-proof, integrity-verifiable audit ledger; signed provenance | NFR-AUD-02 |
| **Repudiation** | "I didn't attest that" | Signed, audited attestation (signer + GPG key id) | FR-ATT-04 |
| **Information disclosure** | Artifact/CUI leak via logs, egress, cross-tenant | No content in logs; air-gap zero egress; tenant isolation | NFR-SEC-01/03, FR-RES-03 |
| **Denial of service** | Low-confidence storm; malformed artifact | Circuit breaker (3); corrupt-artifact quarantine; graceful degradation | FR-CONF-02, FR-ING-05 |
| **Elevation of privilege** | Viewer performs attestation | `require_role("attester")` enforced server-side | FR-API-02 |
| **★ Prompt injection** | Artifact text instructs the LLM to assert authorization, suppress findings, or exfiltrate | Treat artifact as **data not instructions** (delimited/role-isolated prompts); citation validation; no authorization code path; egress guard | NFR-SEC-05, `docs/05` §7 |
| **Model manipulation** | Coerced fabricated citation | `citation_validator` rejects spans not verbatim in artifact | FR-T2-03 |
| **Supply chain** | Malicious dependency phones home | Dependency scan; egress allow-list; vet for outbound calls | NFR-SEC-06 |

### 2.1 The signature threat: authorization claim
QUILL's gravest misuse is being made to **assert or imply an authorization decision**. Defenses are layered: (1) no data field or endpoint represents authorize/deny (FR-ATT-05); (2) prompts forbid it and isolate artifact content; (3) a negative test asserts no authorization output exists for any input, including adversarial artifacts; (4) human attestation is finding-level only.

## 3. Data protection
Per `docs/05`: artifacts = CUI; encrypted at rest where supported; content never logged (redaction at the logging boundary); air-gap zero egress; secrets via env/Vault, never committed/logged.

## 4. CMMC L2 (Self) mapping *(WP-6)*
Map sandbox practices to relevant CMMC L2 / 800-171 domains: Access Control, Audit & Accountability, Identification & Authentication, System & Communications Protection, System & Information Integrity, Media Protection. Target: **Level 2 (Self)** assessment. *(Fill the practice-by-practice table during the audit.)*

## 5. ITAR / EAR & foreign nationals
Technical data is ITAR-controlled (22 CFR 120–130) / EAR (15 CFR 730–774). Any FN involvement disclosed per topic §3.5 (country, visa/permit, SOW tasks); FNs may be access-restricted. Disclosure recorded in the compliance file. No controlled data egress (incl. via Tier 3) outside authorized boundaries.

## 6. Audit results *(WP-6 — fill at hardening)*
- [ ] Dependency scan: 0 unresolved high-severity
- [ ] Air-gap egress check: 0 artifact-bearing outbound
- [ ] Log scan: 0 artifact content
- [ ] Prompt-injection suite: all properties hold (no auth claim, no suppression, no egress, no fabricated span)
- [ ] Tenant-isolation tests: pass
- [ ] Secret scan: 0 secrets in repo/logs
- [ ] Tier 3 unreachable in air-gap: confirmed
- [ ] CMMC L2 mapping complete
- [ ] FN disclosure recorded (if applicable)

**Gate:** zero unresolved high-severity findings before Phase I ships.
