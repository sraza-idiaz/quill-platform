# DESIGN_SPEC.md — QUILL UI/UX

> Owner: Frontend Designer. Defines the QUILL brand application and screen-by-screen UX. The **finding-review + attestation screen is the heart of the product**. Built in AXO's React/Vite/Tauri shell (`desktop-v2/`), re-skinned from `axo-assets/` to the QUILL brand.

---

## 1. Brand system

| Token | Value | Use |
|---|---|---|
| Primary | `#6fcf97` (light green) | Primary actions, brand, "reading" state |
| Accent | `#a8e6c1` | Secondary surfaces, highlights |
| Alarm | `#ff7a6b` | Findings/alarms, destructive actions |
| Mode | **Dark-mode-first** | Default; light mode supported |
| Display font | Syne | Headings |
| Mono font | DM Mono | Control IDs, locators, code, quoted spans |
| Serif | Instrument Serif | Editorial accents |
| Mascot | 8-bit owl, 4 states | **Idle / Reading / Alarm / Attested** — reflects run + review state |

**Semantic finding-status colors:** `unattested` (neutral) · `approved` (green) · `edited` (amber) · `rejected` (muted/strikethrough). **Severity chips:** critical/high (alarm tones) → medium (amber) → low (neutral). **Confidence:** a 0–1 chip/bar; `needs-review` (0.5–0.75) visually distinct; deferrals shown as "flagged for review," not as assertions.

**Accessibility (NFR-USE):** WCAG 2.1 AA contrast, full keyboard nav, visible focus, honors reduced-motion (owl/transitions freeze), screen-reader labels on findings + spans.

## 2. Screens

### 2.1 Artifact Upload & Queue (FR-UI-01)
- Drag-drop / file picker (PDF/DOCX/MD/OSCAL); shows hash on ingest.
- Queue table: artifact, type, status (`ingested→analyzing→reviewed→attested`), finding counts by severity, run progress.
- Folder-watch indicator. Owl = Idle when no active run.

### 2.2 Analysis Run View
- Live tier progress (T0→T1→T2[→T3]); which tiers fired (`tier_path`).
- Breaker banner if tripped ("Routed to human review — low-confidence/contradiction").
- Summary: findings by type + severity; link into review. Owl = Reading during analysis, Alarm if findings/breaker.

### 2.3 ★ Finding Review & Attestation (FR-UI-02) — the core screen
**Two-pane layout:**
- **Left — Source:** the artifact rendered with the finding's **exact source span highlighted**; clicking a finding scrolls+highlights its span; multiple spans navigable. Locator shown in DM Mono (`p4 §2.1`).
- **Right — Finding:** control ID + family, finding type, **severity chip**, **confidence chip**, the rationale, `missing_elements`, and the recommendation. Determination-statement context shown.
- **Actions (attester only):** **Approve · Edit · Reject**, each requiring a note; triggers the signed Change-Request flow. Edit opens an inline editor preserving the AI original. Non-attesters see read-only + "requires attester."
- Keyboard-driven (j/k to move, a/e/r to act). Owl = Attested after sign.
- **Guardrail:** no "authorize/accept system" control exists anywhere — only finding-level approve/edit/reject of *documentation findings*.

### 2.4 Audit / Provenance Viewer (FR-UI-03)
- Timeline per finding/artifact: AI proposal → attester action → signature (signer + GPG key id) → audit hash. Integrity badge (verifiable). Reuses AXO trust-center/provenance components.

### 2.5 Export (FR-UI-04)
- Choose format: signed human report · OSCAL POA&M · audit artifact. Only attested findings included. Shows signature verification result.

### 2.6 Settings / Integrations (FR-UI-04)
- **Air-gap toggle** (default on) · **Tier 3 toggle** (default off, disabled when air-gap on) · Ollama model · confidence thresholds (read-only display of active values) · Slack integration card · catalog/baseline display.

## 3. Component reuse from `axo-assets/` + `desktop-v2/`
- Reuse layout shell, nav, cards, tables, timeline, chips, modals; re-skin to QUILL palette/fonts.
- New components: `SourceSpanHighlighter`, `FindingCard`, `ConfidenceChip`, `SeverityChip`, `AttestActions`, `OwlStatus`.
- Add QUILL section to MERP suite nav.

## 4. States & empty/error UX
- Empty queue, analyzing, no-findings ("no deficiencies detected"), breaker-tripped, LLM-down (degraded-to-T0 notice), backend-unreachable (clean message). Every error human-readable, never a stack trace, never artifact content.

## 5. Microcopy principles
- QUILL **finds and explains**; humans **decide**. Never use "authorize," "approve system," "pass/fail ATO." Use "approve finding," "evidence insufficient," "flagged for review."
