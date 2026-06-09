# 13 — Phase II Plan (End-to-End Implementation Specification)

> The complete plan for QUILL Phase II — what we build, what every piece must
> do, what rules it must obey, how we measure success. This is the executable
> spec, not a sales narrative.
>
> Scope is **deliberately bounded** per product-owner directive: no local
> on-box LLM yet, no desktop app, no audit-trail enhancements, **no real
> authentication (login/JWT/SSO) — identity stays header-declared as in
> Phase I**. The Phase I architectural guarantees (the seven hard rules)
> carry over unchanged.
>
> Cloud LLM is locked to **`kimi-k2.5:cloud`** as the primary Tier 2
> analyzer (Moonshot K2.5 via Ollama Cloud), with the other already-pulled
> cloud models — `qwen3.5:cloud`, `gemma4:31b-cloud`, `glm-5.1:cloud` — as
> fallbacks if K2.5 fails our calibration gate on benchmark.

---

## 1 — Context & Objectives

### 1.1 Why Phase II exists

Phase I proved feasibility: a single-program, single-machine prototype that
distinguishes narrative presence from evidence sufficiency, traces every
finding to source, and routes findings through a human attestation gate.
Numbers met every Phase I gate (recall 0.98, FP 0.11, traceability 1.00,
ECE 0.064 monotonic, on a 13-label synthetic corpus).

Phase II takes that capability from prototype to **deployable product**. The
question Phase II answers for the evaluator is: *"if you ran this in real
DLA R&D programs concurrently, would it hold up?"*

### 1.2 What Phase II adds, at altitude

1. **Multi-program operation** — many concurrent programs through one engine, isolated.
2. **Multi-framework support** — NIST 800-53 Rev. 5 fully loaded; FedRAMP, CMMC, ISO 27001 swap-in.
3. **Package-aware analysis** — bundles of related artifacts treated as one unit, with diff-aware continuous re-analysis.
4. **Better cross-artifact reasoning** — synonyms, inherited controls, dependency graph, document-level coherence.
5. **Calibrated AI** — Tier 2 confidence values are provably meaningful (reliability curve published).
6. **Multi-program identity model** — Phase I's header-declared identity continues, but extended with a program/tenant selector. Real authentication (login, JWT, SSO) is deferred.
7. **First-class Slack bot** — daily-driver attestation surface for distributed teams.
8. **Larger eval corpus + published metrics** — 300+ labeled deficiencies, fresh recall/FP/calibration numbers.
9. **Three new export formats** — stakeholder PDF, version-diff report, OSCAL package.
10. **eMASS-shaped connector code** — built and tested against the API spec, ready to flip on when access is granted.

### 1.3 What Phase II is NOT (deferred to later)

| Deferred item | Why | Future trigger |
|---|---|---|
| **Local on-box LLM** (Mistral 24B) | Cloud LLM is faster to iterate against; on-box deferred to when air-gap deployment is a near-term sale | Customer requests true air-gap install |
| **Desktop app (Tauri)** | Web UI + Slack covers the team daily-driver case; native app is a Phase III investment | Field validation says reviewers need offline-first signing |
| **Audit-trail enhancements** | Phase I audit functionality (signed, hash-chained, integrity-verifiable) remains; org-wide dashboards + third-party verifiable bundles are deferred | After core Phase II ships |
| **Real authentication (login + JWT + SSO + identity provider)** | Phase I's header-declared identity (`X-QUILL-Role`, `X-QUILL-User`, `X-QUILL-Tenant`) is sufficient for SBIR Phase II evaluation. Production deployments will require real auth, which becomes a Phase III hardening item | First production deployment outside the SBIR sandbox |

### 1.4 What Phase II is NOT (never changes)

The Phase I non-negotiables carry through verbatim:

1. QUILL never makes the authorization decision.
2. Human attestation is a hard gate — nothing authoritative until a named human signs.
3. Every finding has a verifiable, verbatim source span.
4. Confidence is calibrated; below-threshold outputs defer, never assert.
5. Circuit breaker threshold = 3. Not adjustable, not disable-able.
6. The pipeline is artifact-centric, not chat.
7. The engine does not author upstream RMF artifacts.

These show up below as Policies, not Features — they're invariants the
system must enforce on every change.

---

## 2 — Scope Boundaries

### 2.1 IN scope

The 10 capability blocks listed in §1.2, decomposed into FRs in §4.

### 2.2 OUT of scope (deferred)

| Item | Status |
|---|---|
| Local LLM on-box (Mistral 24B, GPU-backed) | Deferred |
| Tauri desktop app (Windows + macOS) | Deferred |
| Audit-trail enhancements (org-wide dashboard, third-party verifiable export bundles, attestation analytics) | Deferred (Phase I audit stays as-is) |
| Real authentication (login, JWT, SSO, identity provider integration) | Deferred — Phase I header-declared identity continues |
| Multi-agent framework (LangGraph / CrewAI / AutoGen) | Considered + rejected; see DECISIONS-021 |
| Authoring of upstream RMF artifacts (SSP, FIPS-199, PIA, control narratives) | Permanently out of scope — design boundary |
| Authorization decisions of any kind | Permanently out of scope — design boundary |
| Third-party CMMC L2 certification | Phase II ships L2 *Self* evidence; third-party audit waits for Phase III |
| eMASS production write-back integration | Connector code ready; the live connection requires DLA access (paperwork, not code) |

### 2.3 External dependencies (not coding tasks)

These are listed for completeness but explicitly **not** required by the
plan in this document. They are paperwork/relationships tracks running in
parallel:

- eMASS API access for live integration
- Pilot program agreement (real DLA program willing to be measured)
- Independent security review (Phase III gate)
- Foreign-national disclosure / ITAR clearance (only if team composition triggers it)

---

## 3 — Policies (Invariants the System MUST Enforce)

Policies are not features. They are rules every feature must obey. Every
new feature in §4 is audited against these on every change.

### 3.1 P-CORE — Architectural Non-Negotiables

| Policy | Statement | Enforcement |
|---|---|---|
| P-CORE-01 | No code path produces or recommends an authorize/deny decision. | Static analysis + negative test that scans the codebase for `approved_system`, `authorize`, `ato_granted`, etc. as fields or endpoints. |
| P-CORE-02 | No finding is treated as authoritative until cryptographically signed by a named human in the `attester` role. | Export pipeline filters by `status in {approved, edited}`. Test: attempt to export an unattested finding → 409. |
| P-CORE-03 | Every artifact-derived finding carries a verbatim source-span quote. Catalog-reference findings cite the baseline requirement. | Citation validator rejects any finding whose quote is not literally present in the source. Test gate: traceability == 1.00 on every eval run. |
| P-CORE-04 | LLM confidence below 0.50 produces a `flag_for_review` deferral, not an asserted finding. | Confidence disposition logic; tested per tier. |
| P-CORE-05 | Circuit breaker threshold is exactly 3. Configurable down (1, 2) for stricter programs; constructor rejects 999 (the "disabled" sentinel). | Constructor validation + unit test. |
| P-CORE-06 | `admin` role is NOT auto-granted attestation. Attester must be listed explicitly. | `require_role("attester")` enforced server-side. Negative test. |
| P-CORE-07 | Artifact text never appears in logs, metrics, or telemetry. | Logging filter at the boundary. Log-scan test on every chaos run. |

### 3.2 P-DATA — Data Handling

| Policy | Statement | Enforcement |
|---|---|---|
| P-DATA-01 | All artifacts treated as CUI by default. | Documented in `docs/05`. UI labels reflect this. |
| P-DATA-02 | Cross-tenant reads/writes are impossible. Every query is tenant-scoped at the data layer. | Repository layer takes `tenant` as a required parameter. Cross-tenant integration test. |
| P-DATA-03 | The Phase II cloud LLM (Ollama Cloud / Claude API) IS an egress path. Operators MUST be informed. | `/health` reports `air_gap: false` when cloud LLM is active. UI shows "Live" indicator. Banner shown for any program whose policy demands air-gap. |
| P-DATA-04 | Artifact content sent to a cloud LLM is treated as transmitted off-machine. Programs requiring strict CUI handling must disable Tier 2 (orchestrator falls back to Tier 0+1 with graceful degradation). | Per-program toggle in admin UI. Documented in user guide. |
| P-DATA-05 | Secrets (JWT keys, GPG keys, API tokens, DB creds) never committed; loaded from env / secret store at boot. | `.gitignore` + secret scan in CI. |

### 3.3 P-IDENTITY — Identity & Accountability (header-declared in Phase II)

| Policy | Statement | Enforcement |
|---|---|---|
| P-IDENTITY-01 | Every user action is attributed to a declared identity (user + program + role from request headers). Anonymous requests see only `/health` and `/ui/`. | Header parsing; missing identity → 401. Real authentication is deferred (see §1.3). |
| P-IDENTITY-02 | The declared identity is recorded with every attestation as the cryptographic signer. | Provenance record carries `attester` field; signature payload includes it. |
| P-IDENTITY-03 | Roles are scoped per program. A user can be `attester` in Program A and `viewer` in Program B. | Per-program role declared via header; admin UI tracks the canonical role table. |
| P-IDENTITY-04 | `admin` is not auto-granted `attester`. | Carryover from Phase I. |
| P-IDENTITY-05 | Header-declared identity is documented as a Phase II tradeoff. UI surfaces the operator's current identity prominently so accidental misattribution is obvious. | Identity chip in topbar; documented in user guide. |

### 3.4 P-AI — AI Behavior

| Policy | Statement | Enforcement |
|---|---|---|
| P-AI-01 | LLM outputs are validated against a constrained schema (5 finding types, severity enum, confidence 0–1, ≥1 source span). | JSON schema validation. Malformed outputs rejected. |
| P-AI-02 | Fabricated citations are silently dropped before any human sees them. | Citation validator (carryover from Phase I). |
| P-AI-03 | Calibration is *measured*, not assumed. A reliability curve is published as a deliverable. | Eval harness computes ECE per release; gates monotonic + ECE ≤ 0.20. |
| P-AI-04 | The model + version + prompt-hash for every Tier 2 call is recorded in the provenance ledger. | Orchestrator emits structured trace events. |
| P-AI-05 | Tier 3 cloud escalation is opt-in per program and never invoked on artifacts marked `restricted`. | Tier 3 guard checks before any outbound call. |

### 3.5 P-CONFIG — Generic-First / Schema-Driven

| Policy | Statement | Enforcement |
|---|---|---|
| P-CONFIG-01 | Catalogs (controls, objectives), rubrics (criteria, severity, thresholds), and frameworks are loaded from YAML/OSCAL config. No catalog data hardcoded. | Grep test: no control IDs in source. |
| P-CONFIG-02 | Adding a new framework requires zero code changes. | Demonstration test: load FedRAMP catalog, verify it works. |
| P-CONFIG-03 | Per-program rubric overrides are supported (e.g. one program tightens AC-2 required elements). | Rubric layering: base rubric + program overlay. |

---

## 4 — Functional Requirements

Every FR has a stable ID, priority (P0 = Phase II gate, P1 = should-have,
P2 = nice-to-have), and explicit acceptance criteria. Acceptance is what
makes the FR testable.

### 4.A — Identity & Tenancy (header-declared in Phase II; real auth deferred)

Phase II keeps Phase I's header-declared identity (`X-QUILL-User`,
`X-QUILL-Role`, `X-QUILL-Tenant`) and extends it with multi-program support.
Real authentication (login, JWT, SSO) is deferred to Phase III (§2.2).

| ID | Requirement | Pri | Acceptance |
|---|---|---|---|
| FR-ID-01 | Identity is declared per request via `X-QUILL-User`, `X-QUILL-Role`, `X-QUILL-Tenant` headers. Missing headers → 401 on any non-`/health`, non-`/ui/` endpoint. | P0 | Header-stripped request → 401. |
| FR-ID-02 | Roles are constrained to the enum `admin`, `engineer`, `attester`, `viewer`. Unknown role → 400. | P0 | Bad-role request rejected. |
| FR-ID-03 | `admin` is NOT auto-granted attestation. The `attester` role must be selected explicitly. | P0 | Negative test: admin attests → 403 (Phase I carryover). |
| FR-ID-04 | The web UI surfaces "Acting as `<user>` · `<role>` · `<program>`" prominently in the topbar so misattribution is visually obvious. | P0 | Identity chip visible on every view. |
| FR-ID-05 | Slack-bot identity is bound by Slack OAuth handshake on first attest; subsequent requests carry that linkage. | P0 | Linking flow works. |
| FR-MT-01 | Program (tenant) is a first-class entity: id, name, baseline, framework, created_at, owner_user (declared name). | P0 | Admin UI: create/edit/disable programs. |
| FR-MT-02 | Every artifact, run, finding, attestation is tenant-scoped via foreign key. | P0 | DB integrity test. |
| FR-MT-03 | A request whose `X-QUILL-Tenant` does not match the target resource's tenant gets 404. | P0 | Cross-tenant test. |
| FR-MT-04 | The UI has a program switcher; switching changes `X-QUILL-Tenant` on subsequent requests. | P0 | UI test. |
| FR-MT-05 | Admin can rename a program; IDs are stable. | P1 | Rename does not break existing references. |
| FR-MT-06 | A "disabled" program is read-only — its data is preserved but no new actions are accepted. | P1 | Disabled-program test. |

### 4.B — Catalog & Frameworks

| ID | Requirement | Pri | Acceptance |
|---|---|---|---|
| FR-CAT-01 | Load the full NIST SP 800-53 Rev. 5 catalog (~1,000 controls) from OSCAL JSON. | P0 | All controls + assessment objectives queryable. |
| FR-CAT-02 | Load 800-53A determination statements (Rev. 5) with method tags (examine/interview/test). | P0 | For any control, full set of determination statements is loaded. |
| FR-CAT-03 | Baseline selector (Low / Moderate / High) per program — admin UI dropdown. | P0 | Changing the baseline changes the "required controls" set. |
| FR-CAT-04 | Framework swap via config: FedRAMP, CMMC L2, ISO 27001 supported via separate catalog files. | P0 | Loading a FedRAMP catalog produces correct findings on a sample artifact. |
| FR-CAT-05 | Per-program catalog override (a program can pin to a specific catalog version). | P0 | Two programs running different catalogs concurrently. |
| FR-CAT-06 | Catalog versioning — every analysis run records which catalog version was active. | P0 | Provenance event includes catalog version. |
| FR-CAT-07 | "Active baseline" displayed in UI on every relevant view (Inventory, Gate). | P0 | Visible chip. |

### 4.C — Packages

A **package** is the new unit of analysis. Instead of one artifact at a
time, a package is the bundle of documents that travel together through
RMF review.

| ID | Requirement | Pri | Acceptance |
|---|---|---|---|
| FR-PKG-01 | Package entity: id, name, baseline, owner, member artifacts, created_at. | P0 | CRUD via UI + API. |
| FR-PKG-02 | An artifact belongs to exactly one package. (Phase II — multi-package membership deferred.) | P0 | DB FK + integrity test. |
| FR-PKG-03 | Package types: `SSP`, `architecture`, `network_diagram`, `oscal`, `policy_doc`, `supplemental`. | P0 | Artifact-type metadata. |
| FR-PKG-04 | Package-level Analyze: runs the full pipeline across every artifact in the package as one logical run (carries cross-artifact reasoning forward from Phase I's `analyze_package`). | P0 | One run id, findings linked to specific artifact + package. |
| FR-PKG-05 | Package status: `draft`, `under-review`, `submitted`, `archived`. | P0 | UI shows status; transitions logged. |
| FR-PKG-06 | A package has a Package Target ID (PKG-YYYY-XXXX from Phase I) — deterministic from package hash. | P0 | Stable across re-ingest. |

### 4.D — Continuous Re-Analysis (Diff-Aware)

| ID | Requirement | Pri | Acceptance |
|---|---|---|---|
| FR-CONT-01 | Watcher monitors a configured source per package (folder, Git repo, Slack channel). | P0 | Drop a file → ingest event fires within ≤ 5s. |
| FR-CONT-02 | On artifact change, the system computes which controls are affected (via the evidence index from Phase I), and re-runs only those controls' analysis. | P0 | Diff-aware re-run takes < 25% of full-package time when only one paragraph changed. |
| FR-CONT-03 | Finding states across versions: `new`, `stale` (no longer matches), `resolved` (deficiency fixed in new version), `unchanged`. | P0 | Test fixture: edit one paragraph, verify states. |
| FR-CONT-04 | UI surfaces the diff: "since last analysis, 3 new findings, 2 resolved, 5 unchanged." | P0 | Visible on package detail. |
| FR-CONT-05 | Severity-threshold pings: when a new finding lands above a configured threshold, notify Slack channel / email recipients. | P1 | Notification fires; idempotent (no duplicate on retry). |
| FR-CONT-06 | A new version of an artifact does NOT invalidate prior attestations on findings that survived unchanged. | P0 | Attested findings carry through if their cited span is still present and unchanged. |
| FR-CONT-07 | When a previously-attested finding becomes `stale`, the system asks an attester to re-confirm or rescind. | P0 | UI flow. |

### 4.E — Cross-Artifact Reasoning

| ID | Requirement | Pri | Acceptance |
|---|---|---|---|
| FR-XA-01 | Synonym resolution table (configurable). "Every 90 days" ≡ "quarterly," "ISSO" ≡ "Information System Security Officer," etc. | P0 | Synonym table in `config/synonyms.yaml`. Round-trip test on contradiction detection. |
| FR-XA-02 | Inheritance pattern detection: when a control narrative says "inherited from [provider]," QUILL classifies it as inherited and checks evidence of inheritance separately from implementation. | P0 | Test fixture with SOC 2 inheritance claim. |
| FR-XA-03 | Cross-artifact dependency graph: which controls reference which other controls within the package. | P0 | Graph endpoint returns nodes + edges. Finding card shows "related controls" panel. |
| FR-XA-04 | Document-level coherence check: does the SSP as a whole present a coherent program for a given control family? (Tier 2 prompt receives all family-relevant paragraphs, not just one.) | P0 | Test: AC-2 narrative split across 3 paragraphs analyzes as a whole. |
| FR-XA-05 | Role-name resolution: detect that "the ISSO" in §3 and "Information System Security Officer" in §7 refer to the same role. | P1 | Same as FR-XA-01 with role-name flavor. |
| FR-XA-06 | ODP value-family consistency: same ODP across artifacts (e.g. retention period) must match after normalization. | P0 | Cross-doc retention contradiction test. |

### 4.F — AI Pipeline (Cloud LLM Only in Phase II)

| ID | Requirement | Pri | Acceptance |
|---|---|---|---|
| FR-AI-01 | Tier 2 backed by **Ollama Cloud, primary model `kimi-k2.5:cloud`** (Moonshot K2.5). Configurable fallbacks among already-pulled cloud models (`qwen3.5:cloud`, `gemma4:31b-cloud`, `glm-5.1:cloud`). Claude API stays as a Tier 3 escalation option, opt-in. | P0 | Switching the active model is a single config line. |
| FR-AI-02 | Confidence values are calibrated. Reliability curve (ECE + monotonic check) is published per release. | P0 | Eval gate: monotonic + ECE ≤ 0.20. Curve visible in UI Settings → "AI Calibration." |
| FR-AI-03 | Confidence threshold per program (default 0.50 for defer, 0.75 for emit). Admin can tune within bounds. | P0 | Per-program config. |
| FR-AI-04 | The model + version + prompt-hash for every Tier 2 call is recorded with the finding. | P0 | Provenance event includes `model`, `version`, `prompt_sha256`. |
| FR-AI-05 | Tier 2 supports the synonym + inheritance + doc-level extensions from §4.E. The prompt template is updated; rubric stays the six criteria. | P0 | Prompt template versioned. |
| FR-AI-06 | Tier 3 cloud-escalation guard: opt-in per program; off in air-gap-only programs; never with `restricted` artifacts. | P0 | Negative test: Tier 3 unreachable when restricted. |
| FR-AI-07 | LLM call timeout (default 60s); on timeout, the orchestrator falls back to Tier 0+1 for that finding with `flag_for_review`. | P0 | Chaos test: artificially-slow LLM → graceful degradation. |
| FR-AI-08 | LLM call cost telemetry recorded (per-program token counts, no artifact content). | P1 | Admin can see "tokens this month" per program. |
| FR-AI-09 | Prompt-injection defense: artifact text passed to the LLM is delimited and the system prompt instructs the model to ignore embedded instructions. | P0 | Adversarial prompt test suite. |

### 4.G — Findings & Attestation (Phase I carryover + extensions)

| ID | Requirement | Pri | Acceptance |
|---|---|---|---|
| FR-FIND-01 | Five finding types: `missing`, `inconsistent`, `weak_narrative`, `insufficient_evidence`, `narrative_present_evidence_unclear`. (Phase I carryover.) | P0 | Schema-locked enum. |
| FR-FIND-02 | Severity levels: `critical`, `high`, `medium`, `low`. Severity computed from control family + finding type. (Phase I carryover.) | P0 | |
| FR-FIND-03 | Attestation states: `unattested → approved | edited | rejected`. Re-attestation rejected on terminal states. (Phase I carryover.) | P0 | |
| FR-FIND-04 | Edit-and-approve preserves the AI-proposed original alongside the edited finding, both signed. (Phase I carryover.) | P0 | |
| FR-FIND-05 | Bulk attestation: admin/attester can approve N findings at once with one signature ceremony (each finding still individually signed, just sequenced). | P1 | Bulk-approve test for 50 findings completes in < 10s. |
| FR-FIND-06 | A finding shows its "related controls" panel (FR-XA-03) inline during attestation. | P0 | UI test. |
| FR-FIND-07 | A finding can be tagged with reviewer comments (free-text, attached to the signed record). | P1 | Comment field on attestation. |
| FR-FIND-08 | "Flag for human" sub-state — the AI explicitly defers (below threshold). Surfaced in the queue distinct from `unattested`. | P0 | Carryover from Phase I (`flag_for_review`). |
| FR-FIND-09 | Per-program severity threshold for export filtering (e.g. "only export critical + high"). | P1 | Export config. |

### 4.H — Exports (Three New Formats Added)

| ID | Requirement | Pri | Acceptance |
|---|---|---|---|
| FR-EXP-01 | Signed Markdown findings report. (Phase I carryover.) | P0 | |
| FR-EXP-02 | OSCAL POA&M JSON. (Phase I carryover.) | P0 | |
| FR-EXP-03 | Signed audit-chain JSON. (Phase I carryover.) | P0 | |
| FR-EXP-04 | **NEW** — Stakeholder Summary PDF: non-technical readout, counts by severity, top 10 findings, rework-reduction estimate. Branded. | P0 | Generated PDF < 1 MB. |
| FR-EXP-05 | **NEW** — Version-Diff Report: side-by-side between two analysis runs of the same package. New / resolved / changed findings highlighted. | P0 | Diff between v1 and v2 of a package is correct. |
| FR-EXP-06 | **NEW** — OSCAL Package Export: full OSCAL bundle (SSP + POA&M + assessment results) in the shape an eMASS-class system expects. | P0 | Validates against OSCAL 1.1.x schema. |
| FR-EXP-07 | All exports include the model + version that produced underlying findings (provenance). | P0 | Exported header includes provenance. |
| FR-EXP-08 | Exports of unattested findings are blocked. Attempts return 409 with a clear message. | P0 | Negative test. |
| FR-EXP-09 | Export jobs are tracked; status reflected in the UI. | P1 | Background-job pattern for slow exports (large packages). |

### 4.I — Slack Bot (`@quill`)

The Slack bot is a first-class surface — not just notifications, but a
fully-featured attestation channel.

| ID | Requirement | Pri | Acceptance |
|---|---|---|---|
| FR-SLK-01 | `@quill help` — list available commands and per-user permissions. | P0 | Command works in any channel `@quill` is invited to. |
| FR-SLK-02 | `@quill status <package>` — open findings count by severity. | P0 | |
| FR-SLK-03 | `@quill findings <package> [severity]` — list top 10 findings. | P0 | Severity filter. |
| FR-SLK-04 | `@quill attest <finding-id> <approved|edited|rejected> "note"` — sign right from chat. Requires the user's Slack identity to be linked to a QUILL `attester` account. | P0 | Signing succeeds; cryptographic record created. |
| FR-SLK-05 | `@quill summary <package>` — daily digest (sent automatically at configured time per program). | P1 | Cron job. |
| FR-SLK-06 | `@quill ingest` (with attached file in a DM) — upload an artifact via Slack. | P1 | File appears in Inventory. |
| FR-SLK-07 | Severity-threshold pings: new critical/high findings auto-post to the program's designated channel. | P0 | |
| FR-SLK-08 | Identity linking: a Slack user must be linked to a QUILL user via OAuth before they can attest. Unlinked users get a "link your account" message. | P0 | Linking flow works; unlinked-user test. |
| FR-SLK-09 | Bot respects QUILL's role model. A Slack user with `viewer` role cannot attest from Slack. | P0 | Negative test. |
| FR-SLK-10 | Slack messages never contain artifact content — they show counts, IDs, recommendations, and source-locator references only. | P0 | Log-scan test on bot output. |
| FR-SLK-11 | Tenant isolation: a Slack workspace is bound to a tenant. Cross-tenant Slack queries fail. | P0 | |

### 4.J — eMASS Connector (Code-Only)

Even though the live integration requires access, Phase II builds and tests
the connector so the last mile is paperwork, not engineering.

| ID | Requirement | Pri | Acceptance |
|---|---|---|---|
| FR-EMS-01 | OSCAL Package Export (FR-EXP-06) is shaped against the eMASS-published OSCAL ingestion spec. | P0 | Spec-conformance test. |
| FR-EMS-02 | A connector module abstracts eMASS as a remote target. Implementation can be mocked for testing. | P0 | Mock test exercises full export → upload sequence. |
| FR-EMS-03 | Bidirectional field-mapping table: QUILL finding fields ↔ eMASS POA&M fields. | P0 | Round-trip preserves semantics. |
| FR-EMS-04 | When access is granted, switching from mock to live is a config flip + credential injection. | P0 | Config switch in admin UI. |
| FR-EMS-05 | Dry-run mode: simulate the upload and show what would be sent without sending. | P0 | UI button. |

### 4.K — Admin & Observability

| ID | Requirement | Pri | Acceptance |
|---|---|---|---|
| FR-ADM-01 | Admin UI for program creation, role assignment, baseline selection, framework selection, thresholds. | P0 | |
| FR-ADM-02 | Per-program settings: confidence thresholds, severity export filter, Tier 3 toggle, notification channels. | P0 | |
| FR-ADM-03 | Operational metrics endpoint (no artifact content): run durations, breaker trips, finding mix per program, LLM call latency, token usage. | P0 | Metrics exported in Prometheus-compatible format. |
| FR-ADM-04 | Error metrics: 5xx rate, LLM-call failure rate, parse-error rate. | P0 | |
| FR-ADM-05 | Per-program "AI Calibration" page: reliability curve, ECE history, threshold tuning controls. | P0 | Visible in admin UI. |
| FR-ADM-06 | Admin can disable a program (read-only mode). All data preserved; no new actions. | P1 | |

---

## 5 — Non-Functional Requirements

### 5.1 NFR-PERF — Performance

| ID | Requirement | Target |
|---|---|---|
| NFR-PERF-01 | Tier 0 + Tier 1 analysis of a 50-page artifact | ≤ 30s |
| NFR-PERF-02 | Tier 2 single LLM call (cloud) | ≤ 8s p95 |
| NFR-PERF-03 | Full package analysis (10 artifacts, ~500 controls) — first run | ≤ 12 min |
| NFR-PERF-04 | Diff-aware re-analysis (single paragraph change in same package) | ≤ 60s |
| NFR-PERF-05 | UI initial load | ≤ 2s on the standard reviewer laptop |
| NFR-PERF-06 | Slack `@quill` response | ≤ 3s p95 |
| NFR-PERF-07 | Export generation: report/POA&M/audit | ≤ 5s |
| NFR-PERF-08 | Stakeholder PDF export (typical package) | ≤ 15s |

### 5.2 NFR-SCALE — Scalability

| ID | Requirement | Target |
|---|---|---|
| NFR-SCALE-01 | Concurrent programs | ≥ 25 active programs per instance |
| NFR-SCALE-02 | Concurrent users | ≥ 100 active users per instance |
| NFR-SCALE-03 | Artifacts per package | ≤ 50 (warning above) |
| NFR-SCALE-04 | Findings per package | ≤ 5,000 (paginated UI) |
| NFR-SCALE-05 | DB rows (findings table) | ≥ 5M without query-perf degradation |

### 5.3 NFR-SEC — Security

| ID | Requirement |
|---|---|
| NFR-SEC-01 | Identity is header-declared in Phase II (deliberate Phase II scope). Real auth (JWT/SSO) is a Phase III hardening item and is NOT a Phase II security claim. |
| NFR-SEC-02 | TLS 1.3 enforced for all external connections (server-side; clients vary). |
| NFR-SEC-03 | Database connection uses TLS; credentials from secret store, never committed. |
| NFR-SEC-04 | Tenant isolation enforced at the repository layer (every query takes tenant); tested on every PR via integration suite. |
| NFR-SEC-06 | OWASP Top 10 controls: injection, broken auth, sensitive data exposure, XXE (OSCAL parse), broken access control, security misconfiguration, XSS (UI render), insecure deserialization, vulnerable dependencies, insufficient logging. Each addressed; tests for each. |
| NFR-SEC-07 | Dependency scan in CI: zero unresolved high/critical CVEs at release gate. |
| NFR-SEC-08 | Prompt-injection adversarial test suite passes on every release. |
| NFR-SEC-09 | All CUI-tagged data encrypted at rest (DB-level encryption). |
| NFR-SEC-10 | Cloud LLM mode explicit; UI reflects egress posture (FR-AI banner). |

### 5.4 NFR-REL — Reliability

| ID | Requirement |
|---|---|
| NFR-REL-01 | Uptime target 99.5% (excludes planned maintenance). |
| NFR-REL-02 | Graceful LLM-tier degradation: Tier 2 unavailable → Tier 0+1 + `flag_for_review`. |
| NFR-REL-03 | Idempotent run creation: re-submitting the same artifact does not create a duplicate. |
| NFR-REL-04 | DB-write atomicity: a finding + its provenance record + its audit event commit in one transaction or none. |
| NFR-REL-05 | Background job retry with exponential backoff (LLM calls, exports). Max 3 retries. |
| NFR-REL-06 | Storage outage during a run leaves a consistent state (run marked `failed`, no partial findings). |

### 5.5 NFR-MAINT — Maintainability

| ID | Requirement |
|---|---|
| NFR-MAINT-01 | Test coverage ≥ 80% on backend services. |
| NFR-MAINT-02 | All FRs in §4 are covered by at least one automated test. |
| NFR-MAINT-03 | Catalog/rubric edits do not require code changes (P-CONFIG-01). |
| NFR-MAINT-04 | New framework (e.g. CMMC) loadable via config only. |
| NFR-MAINT-05 | All deployments via single Docker Compose / Helm chart; rollback documented. |

### 5.6 NFR-COMPLIANCE

| ID | Requirement |
|---|---|
| NFR-COMP-01 | CMMC L2 (Self) evidence package complete: every L2 practice mapped to QUILL behavior. |
| NFR-COMP-02 | ITAR / EAR handling documented; FN disclosure mechanism in place per topic §3.5 (if applicable). |
| NFR-COMP-03 | NIST 800-53 Rev. 5 + 800-53A loaded as the canonical catalog. |
| NFR-COMP-04 | OSCAL 1.1.x format compliance for SSP, POA&M, assessment results. |

---

## 6 — Feature Deep-Dives

Each major feature gets a behavior spec, the rules it enforces, edge cases,
and what "done" looks like.

### 6.1 Multi-Program Operation

**Behavior:** An organization has many programs. Each program has its own
artifacts, runs, findings, attestations, settings, and audit slice. A user
in one program cannot see another program's data unless explicitly granted
access. The engine runs concurrently for all programs; the queue is
fair-share.

**Rules enforced:**
- Every DB query takes a `tenant` filter; integration tests prove cross-tenant queries return empty.
- Background jobs are tagged with `tenant`; never operate on cross-tenant data.
- LLM calls record their `tenant`; tokens are accounted per program.
- Slack workspace bindings are one-to-one with programs (FR-SLK-11).
- A user with `admin` in Program A is *not* admin in Program B unless granted.

**Edge cases:**
- User has roles in 3 programs — UI shows program selector at the top.
- A program is disabled mid-analysis — in-flight run finishes; new runs blocked.
- A program is renamed — IDs remain stable; only the display name changes.

**Acceptance:** 25 programs running simultaneously, zero cross-tenant leaks
verified by automated test, fair-share queueing demonstrated.

### 6.2 Continuous Re-Analysis

**Behavior:** A package is "watched." When any source artifact changes, the
system computes which controls are affected by the change (via the
evidence index) and re-runs just those controls. Finding states update in
place: new findings appear, resolved findings move to a "resolved"
sub-section, unchanged findings retain their attestation status, stale
findings prompt re-attestation.

**Rules enforced:**
- A re-analysis never invalidates an attestation if the cited source span is unchanged.
- A re-analysis MUST flag any attested finding whose cited source span has changed (`stale`), so the attester can re-confirm.
- Severity-threshold pings fire only on transitions (new finding above threshold, not "still exists").
- Re-analysis is queued, not synchronous; UI shows "re-analysis pending" until complete.

**Edge cases:**
- A new artifact is added to the package mid-run — gets queued for the next cycle.
- An artifact is removed from the package — its findings move to an archive state, still queryable for the audit trail.
- A change touches every control in the catalog — the system re-runs everything, but reports "wide change" to the user.
- A change is purely cosmetic (whitespace) — the diff engine skips it; no re-analysis triggered.

**Acceptance:** Single-paragraph change re-analyzes in < 60s; finding states correctly transition; attestation persistence demonstrated.

### 6.3 Cross-Artifact Reasoning

**Behavior:** When the engine analyzes a control, it considers ALL artifacts
in the package, not one in isolation. Contradictions, inheritance claims,
and dependencies are surfaced as findings or as context.

**Rules enforced:**
- Synonym resolution table is the SAME for all packages (org-level); program-level overlays allowed but not removals.
- Inheritance claims must cite their provider. A claim without provider attribution is `insufficient_evidence`.
- The dependency graph is rebuilt on every package analysis (cheap; the controls list is fixed).
- Cross-doc ODP conflicts (e.g. retention period: 30 days vs 60 days) MUST emit `inconsistent`.

**Edge cases:**
- A control references itself in a circular dependency — graph builder detects and warns.
- An inherited control is later contradicted in an architecture doc — both findings emit (the inheritance claim AND the contradiction).
- Synonym table doesn't recognize a domain-specific role name — system shows it as a potential contradiction with confidence < 0.50 (defers to human).

**Acceptance:** A test package with seeded contradictions, inherited controls, and dependent control chains produces the correct findings; the dependency graph for a package of 50 artifacts builds in < 5s.

### 6.4 Calibrated AI

**Behavior:** Every finding the LLM emits carries a confidence score. Those
scores are *calibrated* — meaning when the system says "0.85," about 85% of
those findings end up approved by humans. The calibration is measured each
release and re-applied as a post-hoc isotonic mapping; the underlying LLM
is not fine-tuned in Phase II.

**Primary model:** `kimi-k2.5:cloud` (Moonshot K2.5 on Ollama Cloud). Chosen
because K2.5 is in the trillion-parameter MoE class with strong long-context
reasoning and reliable structured-output behavior — both of which matter for
the six-criterion rubric. If K2.5 fails the calibration gate on the Phase II
corpus, the bench falls back to `qwen3.5:cloud` (very strong structured
output) → `gemma4:31b-cloud` (already validated in Phase I) → `glm-5.1:cloud`.

**Rules enforced:**
- The reliability curve is published per release as a deliverable.
- Confidence values are stored as both raw (model output) and calibrated (post-mapping).
- Severity disposition uses calibrated values, not raw.
- Below 0.50 (calibrated): no assertion, only `flag_for_review`.
- Between 0.50 and 0.75: emit finding with `needs_review` marker.
- Above 0.75: emit finding normally.

**Edge cases:**
- A new LLM model is plugged in — calibration must be redone before that model's outputs are trusted (gated in admin UI).
- Calibration mapping drifts after a corpus expansion — automatic re-fit on the held-out slice.
- A program demands stricter thresholds — admin tunes within bounds (defer ≤ 0.60, emit ≥ 0.85).

**Acceptance:** Reliability curve in the UI; ECE ≤ 0.20; monotonic across confidence buckets; published in Phase II eval report.

### 6.5 Stakeholder Summary PDF

**Behavior:** A management-facing readout of a package's pre-adjudication
state. Generated on demand. Non-technical. Brand-styled (Quill Green or
Skyline, matching the active theme).

**Sections:**
1. Cover page: package name, baseline, generated-at, generated-by.
2. Executive summary: counts by severity, percentage of controls clean.
3. Top 10 critical/high findings, plain-English summaries (no jargon).
4. Rework reduction estimate: "By catching N findings pre-review, you've avoided ~M reviewer cycles."
5. Outstanding items: what still needs attention.
6. Footer: "QUILL does not make the authorization decision. Findings require named human attestation."

**Rules enforced:**
- Only attested findings appear.
- The PDF carries a tamper-evident signature footer (signed export, FR-EXP-07).
- File size ≤ 1 MB even for large packages (we summarize, we don't dump).

**Acceptance:** Generated in < 15s for typical packages; opens correctly in Acrobat, Preview, Chrome PDF viewer.

### 6.6 Version-Diff Report

**Behavior:** Compare two analysis runs of the same package (e.g. last
Tuesday vs. today). Show what changed.

**Sections:**
- New findings (with diff against source)
- Resolved findings (and which edit fixed them)
- Changed findings (severity went up or down)
- Unchanged findings (count only; not listed)

**Acceptance:** Diff between v1 and v2 of a test package matches a known
ground-truth diff.

### 6.7 OSCAL Package Export

**Behavior:** One bundle containing the SSP (passed through), the POA&M
generated from findings, and the assessment results. Conforms to OSCAL
1.1.x. Ready to drop into eMASS or any other OSCAL-aware system.

**Rules enforced:**
- Schema validates on every export.
- No authorization decisions in the bundle (re-tested per FR-EXP, P-CORE-01).
- Provenance metadata embedded.

**Acceptance:** OSCAL 1.1.x validator passes; mock eMASS ingest succeeds.

### 6.8 Slack Bot

**Behavior:** First-class attestation surface. A user with an `attester`
role on a program can do their entire review day from Slack.

**Identity linking:** OAuth flow that ties a Slack user_id to a QUILL user.
Unlinked Slack users get a friendly "click here to link" reply.

**Rate limits:** 60 requests/min per linked user.

**Acceptance:** End-to-end test: ingest from Slack → analyze → attest from
Slack → verify in web UI. Tenant isolation verified.

---

## 7 — Calibration & Tuning Plan

This is the "fine-tuning" part — the deliberate, measurable work to make
the AI's outputs trustworthy in a real workflow. Phase II does NOT fine-
tune the underlying LLM (per Phase I design: fine-tuning waits until
sufficient attested data exists). It DOES tune everything around it.

### 7.1 Confidence Calibration

**Method:** Post-hoc isotonic regression on (raw_confidence, attested
result) pairs. The mapping is updated each release.

**Process:**
1. Run the full eval corpus through the production LLM.
2. Collect (raw_conf, was_approved_by_human) pairs.
3. Fit isotonic mapping from raw → calibrated.
4. Compute ECE; gate at ≤ 0.20.
5. Verify monotonic across 5 buckets ([0.5, 0.6), [0.6, 0.7), [0.7, 0.8), [0.8, 0.9), [0.9, 1.0]).
6. Publish reliability curve as a release artifact.
7. Apply mapping in production.

### 7.2 Threshold Tuning

**Per-program tunable thresholds:**
- `defer_below` (default 0.50) — admin can raise to 0.60 for stricter programs.
- `emit_above` (default 0.75) — admin can raise to 0.85 for stricter programs.
- Severity threshold for Slack pings (default `high`).
- Circuit breaker count (default 3, range [1, 5]).

Tuning is logged; every change emits an admin-audit event.

### 7.3 Rubric Tuning

**Per-program rubric overlays.** A program can:
- Add required elements to a control family (e.g. require "encryption-at-rest mention" in CM-family controls).
- Tighten which determination statements are checked.
- Add domain-specific synonyms.

**What programs CANNOT do:**
- Remove the six universal criteria (specificity, completeness, ODP-filled, mechanism, internal consistency, doc-verifiability).
- Loosen citation validation.
- Disable the human attestation gate.

### 7.4 Corpus Expansion Methodology

**Phase II target: 300+ labeled deficiencies** across at least 30
synthetic packages. Built deliberately, not opportunistically.

| Source | Target count | Method |
|---|---|---|
| Phase I synthetic carryover | 13 | Already labeled |
| New synthetic SSPs (engineered strong) | 30 packages × 4 labels avg = 120 | Hire a contractor RMF specialist to write 30 well-formed SSPs at varying baseline levels |
| New synthetic SSPs (engineered weak) | 30 packages × 5 labels avg = 150 | Same contractor, weak versions with seeded deficiencies |
| Public NIST OSCAL samples | ~10 packages, ~30 labels | Repackage public-domain NIST OSCAL examples |
| Cross-doc contradiction fixtures | ~20 | Custom: write A & B with seeded mismatches |

**Total ≥ 333 labels.** Held-out slice: 20% of corpus untouched during
prompt/rubric tuning; metrics published on held-out separately.

**Labeling protocol:**
- Each deficiency labeled with: control_id, finding_type, severity_expected, quoted_text (the verbatim span).
- 20% double-labeled by a second reviewer; Cohen's κ target ≥ 0.7.
- Disagreements adjudicated and the rule recorded.

### 7.5 What's NOT Tuned in Phase II

- The LLM model weights (no fine-tuning).
- The seven hard rules (P-CORE).
- The five finding-type enum.
- The circuit breaker constant of 3.
- The citation validation behavior.

---

## 8 — Success Criteria & Acceptance Gates

### 8.1 Quality Gates (must hit ALL to ship)

| Gate | Target | Measured how |
|---|---|---|
| Deficiency recall (corpus) | ≥ 0.85 | Eval harness on full corpus |
| Deficiency recall (held-out slice) | ≥ 0.80 | Eval harness on held-out only |
| False-positive rate | ≤ 0.15 | Eval harness |
| Traceability | = 1.00 | Eval harness (citation validation) |
| Calibration | monotonic + ECE ≤ 0.20 | Reliability curve |
| Tenant isolation | 0 leaks | Cross-tenant integration tests |
| Cross-artifact contradiction recall | ≥ 0.85 | Specific test fixture set |
| Inheritance pattern detection | ≥ 0.80 recall | Specific test fixture set |
| Unit-test coverage | ≥ 80% | Coverage report |
| OWASP Top 10 coverage | each addressed + tested | Security audit |
| Zero unresolved high-severity dep CVEs | 0 | Dep scan in CI |
| OSCAL 1.1.x conformance | passes validator | OSCAL CLI |

### 8.2 Functional Acceptance (each FR has a binding test)

Every FR in §4 has at least one automated test that passes. The test ID is
the FR ID prefixed with `test_`. Coverage is enforced via a meta-test that
walks `docs/01_FUNCTIONAL_REQUIREMENTS.md` + this document and verifies
each P0 FR has a corresponding test.

### 8.3 Demo Acceptance (the SBIR-review demo flow)

End-to-end demo flow that must succeed without intervention:

1. Open the live URL.
2. Sign in (real identity).
3. Create a new program "Demo R&D."
4. Upload an SSP + an architecture doc + a network diagram as one package.
5. Wait for analysis (≤ 12 min).
6. Open the package — see ~40 findings across the three artifacts, including a cross-artifact contradiction.
7. Click a finding — see the source span highlighted, the "related controls" panel populated.
8. Switch role to attester. Approve 5, edit 3, reject 2.
9. Switch role to engineer. Edit the SSP locally; replace the contradictory paragraph. Re-upload.
10. Watch the diff-aware re-analysis fire. See "1 finding resolved, 2 unchanged."
11. Export the OSCAL package; verify OSCAL CLI accepts it.
12. Export the Stakeholder Summary PDF; show to a non-technical reviewer.
13. From Slack: `@quill summary Demo R&D` — see daily roundup.
14. Approve one more finding via Slack.
15. Confirm in web UI that the Slack-signed finding has the same signed provenance as the web-signed ones.

### 8.4 What Doesn't Need to Pass for Phase II (deferred to later)

- Live eMASS upload (paperwork)
- Real-program rework number (pilot)
- Third-party CMMC L2 audit (Phase III)
- Local LLM operation (deferred)
- Desktop app (deferred)
- Audit-trail dashboards (deferred)

---

## 9 — Evaluation Methodology

### 9.1 Eval Cadence

- **Pre-release:** full eval on every release candidate; gates must pass.
- **Continuous:** eval harness runs in CI on every PR against a tier-0-only smoke set (fast; gates the merge).
- **Quarterly:** held-out slice metrics published.
- **Per release:** reliability curve and calibration mapping refit.

### 9.2 Eval Report Format

Each release produces an eval report (Markdown + JSON) under
`eval/reports/eval-<release>.md` with:
- Run date, model + version, prompt version, catalog version.
- Per-gate metric (recall, FP, precision, traceability, severity agreement, ECE).
- Reliability curve.
- Held-out vs. tuned comparison.
- Anti-overfitting verification.

### 9.3 Anti-Overfitting Discipline

- Held-out slice ≥ 20% of corpus, untouched during tuning.
- Held-out metrics published separately from tuned metrics.
- A drop of > 0.05 between tuned and held-out triggers a rubric review.

---

## 10 — Risk Register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-PII-01 | A program operator inadvertently uploads true CUI to the cloud-LLM mode. | Med | High | Banner; per-program toggle off-by-default for "treats this as CUI"; degraded mode (Tier 0+1 only) clearly available; admin documentation. |
| R-PII-02 | Cloud LLM provider has an outage. | Med | Med | Graceful degradation (FR-AI-07); secondary provider as fallback (configurable). |
| R-CAL-01 | Calibration mapping drifts as corpus grows. | High (by design) | Low | Quarterly refit; held-out monitoring. |
| R-COR-01 | Corpus contractor produces unrealistic synthetic SSPs. | Med | Med | Spot-check by an RMF-experienced reviewer before labeling; throw out unrealistic packages. |
| R-COR-02 | Held-out slice leak (engineer eyeballs it during tuning). | Low | High | Process discipline; held-out hashing + commit gate. |
| R-TENANT-01 | Cross-tenant leak via a poorly-scoped query. | Low (with tests) | Critical | Mandatory tenant-scope integration tests on every PR. |
| R-INJECTION-01 | An adversarial artifact triggers QUILL into asserting authorization. | Low | Critical | Prompt-injection adversarial suite; P-CORE-01 negative tests. |
| R-OSCAL-01 | eMASS-published spec drifts between connector build and live access. | Med | Low | Connector module abstracted; mock + spec-conformance tests. |
| R-SLACK-01 | A Slack workspace is misbound (admin links wrong workspace). | Low | High | Two-step confirmation for workspace binding; only org admins can bind. |

---

## 11 — Sequencing (24 Months)

A four-quarter plan. Each quarter has a ship-or-show gate.

### Quarter 1 — Foundations

- Multi-tenant data model: programs, declared-identity per-program roles.
- Postgres migration from in-memory.
- Full NIST 800-53 Rev. 5 catalog + 800-53A loaded.
- Per-program baseline selector + framework swap.
- Topbar program-switcher + identity chip.
- Corpus expansion begins; first 10 synthetic packages internally authored.

**Gate:** Two programs running concurrently with separate data; topbar identity model working; corpus expansion in flight.

### Quarter 2 — Package Awareness + Slack

- Package entity + bundle analysis.
- Continuous re-analysis (folder watch + diff-aware).
- Slack `@quill` bot: status, findings, attest, summary, pings, Slack-OAuth identity linking.
- Three new export formats: Stakeholder PDF, Version-Diff, OSCAL Package.
- Corpus to ≥ 150 labels.

**Gate:** Package analysis works end-to-end; Slack-signing produces same provenance as web; new exports validate.

### Quarter 3 — Cross-Artifact Reasoning + Calibration

- Synonym resolution.
- Inheritance pattern detection.
- Dependency graph.
- Document-level coherence.
- Confidence calibration (reliability curve, isotonic mapping).
- Per-program threshold tuning.
- Corpus to ≥ 300 labels; first held-out slice frozen.

**Gate:** Cross-artifact recall ≥ 0.85; reliability curve monotonic + ECE ≤ 0.20.

### Quarter 4 — Hardening + eMASS Connector + CMMC L2

- eMASS-shaped OSCAL package export.
- eMASS connector module with mock + spec-conformance tests.
- CMMC L2 (Self) evidence package complete.
- Security audit pass: OWASP, dependency scan, prompt-injection suite, tenant-isolation suite.
- Phase II eval report published.
- Demo flow rehearsed.

**Gate:** All Phase II quality gates green; demo flow runs without intervention; eval report and CMMC L2 evidence package finalized.

---

## 12 — Open Decisions

The four paperwork-shaped items from earlier drafts (corpus contractor,
Slack workspace strategy, RMF-assessor sign-off, eMASS access) were
removed — they belong to external tracks, not the code-only Phase II we're
planning. The two decisions that were genuinely "open" (SSO provider,
cloud LLM choice) are now closed by directive:

- **Authentication:** Phase II keeps the header-declared identity model
  from Phase I. Real auth (login / JWT / SSO) is deferred. No SSO provider
  decision is needed.
- **Cloud LLM:** Primary = `kimi-k2.5:cloud`. Fallback chain = `qwen3.5:cloud`
  → `gemma4:31b-cloud` → `glm-5.1:cloud`. Locked.

That leaves **one** real internal decision:

1. **Per-program LLM cost cap** — should each program have a hard monthly
   token budget that, when exceeded, halts further Tier 2 calls until reset
   (or shifts the program to Tier 0+1 only)? Default recommendation: yes,
   with a generous starting cap that admin can raise. Affects FR-AI-08
   (cost telemetry) and FR-ADM-02 (per-program settings).

---

## 13 — Phase III Bridge

Phase II prepares Phase III without committing to it. By end of Phase II,
the following are ready to graduate:

- **Real authentication** (deferred from Phase II) — header-declared identity
  is replaced by JWT + SSO via OIDC (Google Workspace / Microsoft Entra /
  Okta — chosen at Phase III kickoff). The identity model already has the
  fields it needs; the gap is the auth challenge + session management.
- **Local LLM port** (deferred from Phase II) — architecture is LLM-provider
  agnostic; switching to on-box Mistral 24B is a configuration + ops task.
- **Desktop app** (deferred from Phase II) — same web app wrapped in Tauri.
- **Audit-trail enhancements** (deferred from Phase II) — Phase I audit
  functionality remains; Phase III adds org-wide dashboards + third-party
  verifiable bundles.
- **eMASS live integration** — connector is built; needs access only.
- **CMMC L2 third-party audit** — evidence package ready.
- **Pilot program rework number** — eval framework ready; needs real-program
  participation.

Each one is teed up. Phase III turns these from "ready" to "shipped."
