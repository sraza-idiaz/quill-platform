# DECISIONS.md — QUILL Architecture Decision Log

> Log **every** architecture-level decision here, in the format below. Resolve ambiguity by writing down the decision and the reasoning. One entry per decision, append-only (supersede with a new entry rather than editing history).

**Format:**

```markdown
## DECISION-NNN: <short title>
Date: YYYY-MM-DD
Decider: <agent / person>
Status: proposed | accepted | superseded by DECISION-MMM
Options considered:
  - Option A (chosen — why)
  - Option B (rejected — why)
Decision: <the decision in one or two sentences>
Reasoning:
  - <bullet>
Trade-offs accepted:
  - <bullet>
```

---

## DECISION-001: Local LLM choice for Tier 2 evidence scoring
Date: 2026-06-08
Decider: System Architect Agent
Status: accepted
Options considered:
  - Ollama + Mistral 24B (chosen — inherited from AXO, proven on the Alienware m18 R2)
  - Ollama + Llama 3.x (viable alternative; revisit if eval underperforms)
  - Cloud-only (rejected — violates the air-gap principle)
Decision: Ollama + Mistral 24B locally for Tier 2; Claude API as opt-in Tier 3 only, disabled in air-gap mode.
Reasoning:
  - Air-gap capability is non-negotiable for CUI artifacts.
  - Reuses AXO's proven local-inference setup.
  - Defers fine-tuning until attested-finding data exists.
Trade-offs accepted:
  - Local inference latency higher than cloud; acceptable for batch artifact analysis.

## DECISION-002: QUILL is a fully standalone product; AXO is reference only
Date: 2026-06-08
Decider: Product owner
Status: accepted — **supersedes the earlier framing that QUILL would extend/import AXO modules**
Decision: QUILL is fully standalone. AXO (a sibling product whose patterns inspired QUILL) is used as **reference architecture only** — its codebase may be read to study proven patterns (e.g., signed change-request flows, circuit breakers) but **nothing is imported, shared, or required at runtime**. QUILL builds its own auth, provenance, audit, change-request, GPG-signing, Slack bot, desktop shell, and brand.
Reasoning:
  - Product owner directive: AXO is inspiration, not obligation; "if unnecessary, don't use it."
  - Avoids coupling between two products.
  - Keeps QUILL deployable independently.
Trade-offs accepted:
  - Phase I scope grows: QUILL builds its own auth/provenance/audit/change-request/signing stack rather than reusing existing code. Still achievable in Phase I; the patterns are well-understood.
  - Supersedes earlier wording in CLAUDE.md / ARCHITECTURE.md / WP-4 that implied imports — corrected 2026-06-08.

## DECISION-003: Attestation gate is QUILL's own PR-style change-request flow
Date: 2026-06-08
Decider: System Architect
Status: accepted (revised under DECISION-002)
Decision: A finding's lifecycle (`unattested → approved | edited | rejected`) is implemented as a QUILL-native change-request over the finding, signed with GPG and recorded in QUILL's own provenance + audit ledger. An `attester` role gates the approve/edit/reject actions.
Reasoning:
  - PR-style change-request + signed provenance + tamper-proof audit is a well-known pattern (and the one the PRD designs for); QUILL implements its own.
  - Keeps "AI proposes → human signs → recorded immutably" intact without coupling to another product.
Trade-offs accepted:
  - Finding semantics must be mapped onto CR statuses; mapping documented in `docs/01_FUNCTIONAL_REQUIREMENTS.md`.

## DECISION-004: Circuit breaker is a native QUILL service, threshold = 3
Date: 2026-06-08
Decider: System Architect
Status: accepted (revised under DECISION-002)
Decision: QUILL ships its own circuit-breaker service (`backend/services/analysis/confidence.py`) with threshold `3` (the documented PRD value). It counts low-confidence/contradictory analyzer outputs per artifact and trips the artifact to full human review. The constructor refuses `threshold = 999` (the well-known "disabled" value the PRD warns against).
Reasoning:
  - Safety-critical component built and tested in QUILL; well-known pattern.
Trade-offs accepted:
  - None of note; tested at threshold=3 and explicit-rejects 999.

## DECISION-005: QUILL is a standalone FastAPI service (no shared packages)
Date: 2026-06-08
Decider: System Architect
Status: accepted (revised under DECISION-002)
Decision: QUILL ships as its own self-contained FastAPI service with no shared packages or runtime dependencies on any sibling product.
Reasoning:
  - Independently deployable; no cross-product coupling.
Trade-offs accepted:
  - QUILL owns implementations of auth, provenance, audit, change-request, signing.

## DECISION-006: Default control baseline = Moderate (proposed)
Date: 2026-06-08
Decider: PM Agent
Status: proposed — confirm with TPOC
Decision: Default `baseline: moderate` for FR-CAT-03 unless the TPOC specifies otherwise; configurable per `catalog.yaml`.
Reasoning:
  - Moderate is the common RMF default for R&D systems; Low/High selectable via config.
Trade-offs accepted:
  - May need per-program override; supported by config.

## DECISION-007: `missing` findings cite a catalog reference, not an artifact span
Date: 2026-06-08
Decider: Backend Developer Agent
Status: accepted
Decision: A `missing` finding (control required by baseline but absent from all artifacts) has no artifact text to quote, so its evidence span is a *catalog reference* (`artifact_id='catalog:<baseline>'`, `quoted_text=` the requirement) and records the set of artifacts searched. The citation validator validates catalog-reference spans against the catalog (not artifact text); artifact-derived findings still require a verbatim artifact span.
Reasoning:
  - Keeps "every finding carries a traceable basis" literally true (PRD §8 / traceability gate) while remaining honest — the basis for a missing control is the requirement + the proven absence, not a quote.
Trade-offs accepted:
  - The eval traceability metric (docs/04 §3) measures verbatim-presence for artifact spans; `missing` findings are traceable-by-construction and counted separately.

## DECISION-008: Normalizer uses section carry-forward for control keying
Date: 2026-06-08
Decider: Backend Developer Agent
Status: accepted
Decision: During normalization, the most recently seen control id (typically in a heading like `## AC-2`) is propagated to subsequent paragraphs until a new control id appears. Parser-supplied hints (OSCAL) reset it per block.
Reasoning:
  - Real SSPs put the control id in a heading and the narrative in following paragraphs; without carry-forward, Tier 0 coverage/required-field checks would see only the heading.
Trade-offs accepted:
  - Coarse attribution (acceptable for Tier 0's deterministic net; Tier 1 does semantic mapping). Revisit if documents interleave controls without headings.

## DECISION-009: Repository abstraction with in-memory dev/test impl
Date: 2026-06-08
Decider: Backend Developer Agent
Status: accepted
Decision: Data access goes through a `Repository` Protocol. `InMemoryRepository` backs dev/test (no live Postgres needed); a Postgres adapter (asyncpg, mirroring AXO `db/*_queries.py`) implements the same Protocol against migrations 001/002 for production.
Reasoning:
  - Lets the full pipeline + API run and be tested here without a database.
  - Keeps persistence swappable and tenant-scoped from day one.
Trade-offs accepted:
  - Two implementations to keep in sync; the Postgres adapter is wired before any near-real-data run.

## DECISION-010: Tier 1 ships a lexical retrieval baseline (embeddings later)
Date: 2026-06-08
Decider: ML/Eval + Backend
Status: accepted
Decision: Tier 1 uses deterministic lexical token-overlap scoring for the Phase I baseline; the `EvidenceIndexEntry` interface is stable so local embeddings can replace the scorer without downstream changes.
Reasoning:
  - No model download, fully air-gap-safe, deterministic and testable now.
  - Retrieval quality is tuned against the eval corpus (WP-6); upgrade to local embeddings if recall needs it.
Trade-offs accepted:
  - Lexical recall is weaker than embeddings on paraphrased text; revisit at T-6.2.

## DECISION-011: QUILL builds its own JWT auth; header dev-mode for local testing
Date: 2026-06-08
Decider: Backend
Status: accepted (revised under DECISION-002)
Decision: QUILL implements its own JWT-based auth + `require_role(...)` dependency in `backend/services/auth.py`. Roles: `admin / engineer / attester / viewer`. For local dev convenience, when QUILL is started in DEV_MODE the auth dependency falls back to reading role/user/tenant from `X-QUILL-*` headers (no signed token required); in any non-dev configuration a valid JWT is required. `attester` is first-class and gates approve/edit/reject; `admin` is not auto-granted attestation.
Reasoning:
  - QUILL is standalone (DECISION-002) — no external auth to import.
  - Dev-mode header fallback keeps local testing simple without compromising prod.
Trade-offs accepted:
  - Must keep `DEV_MODE` off by default and explicitly off in any deployed environment.

<!-- Append DECISION-012+ as the build progresses. -->

## DECISION-012: Signing is pluggable — GPG for production, HMAC for dev/test
Date: 2026-06-08
Decider: Security + Backend
Status: accepted
Decision: A `Signer` Protocol abstracts signing. `GpgSigner` (python-gnupg + a real GPG key) is used in production / near-real-data runs. `HmacSigner` (deterministic HMAC-SHA256) backs dev/tests so signing can be exercised end-to-end without a keyring. The HMAC signer's `scheme` field reads `"hmac-sha256-dev"` so any record's origin is unambiguous; production deployments MUST use GpgSigner and verify the field at export.
Reasoning:
  - Lets the attestation gate be tested in CI without keyring setup.
  - Keeps the data shape identical downstream (signature/key_id/scheme/signed_at).
Trade-offs accepted:
  - Operations must verify that production runs use `scheme=="gpg"` (added to export-time check at WP-5 / SECURITY_AUDIT §6).

## DECISION-013: Audit trail is a SHA-256 hash chain with content redaction
Date: 2026-06-08
Decider: Backend + Security
Status: accepted
Decision: The audit ledger appends events with `event_hash = SHA-256(prev_hash || canonical(payload))`. `verify_chain()` re-computes the full chain — any tampering breaks it (NFR-AUD-02). Forbidden keys (`quoted_text`, `artifact_text`, `narrative`, `content`) are redacted at append time (FR-RES-03 / NFR-OBS-01) so artifact content can never leak into audit storage.
Reasoning:
  - Standard hash-chain pattern; no external dependency beyond SHA-256.
Trade-offs accepted:
  - For Phase II at scale, consider Merkle-tree summarization for cheaper integrity queries.

## DECISION-014: Phase I `mock` Tier 2 analyzer for repeatable evaluation
Date: 2026-06-08
Decider: ML/Eval + Backend
Status: accepted
Decision: The Phase I eval harness uses a deterministic stand-in (`MockAnalyzer` in `tests/conftest.py`) that matches the `Analyzer` Protocol used by `OllamaAnalyzer`. Quality gates are computed against this stand-in until live Ollama is available in the sandbox. A re-measurement with live Ollama produces a separate report under `eval/reports/`; the regression test (`tests/integration/test_eval_gates.py`) re-runs against whichever analyzer is current.
Reasoning:
  - Lets Phase I gates be measured + locked deterministically in CI.
  - Same call surface as Ollama; swap is zero-code.
Trade-offs accepted:
  - Mock numbers are an LLM stand-in; live numbers will differ and must be re-published.

## DECISION-015: Cross-artifact analysis via `analyze_package`
Date: 2026-06-08
Decider: Backend
Status: accepted
Decision: A new orchestrator entrypoint `analyze_package(items)` aggregates all artifacts of an RMF package into one run so FR-T0-03 (cross-artifact consistency) actually fires across artifacts. The single-artifact `analyze()` is retained for the existing API.
Reasoning:
  - RMF packages are multi-artifact by nature; per-artifact analysis missed cross-artifact contradictions in eval (inconsistency recall = 0). After: 1.00.
Trade-offs accepted:
  - A package run is attributed to the first artifact for API compatibility; finalize multi-artifact `Run` shape in Phase II (or via a new `Package` model).

## DECISION-016: UI brand pivot — professional enterprise direction
Date: 2026-06-08
Decider: Product owner
Status: superseded by DECISION-017
Decision: The UI brand pivots from the PRD's original spec (light-green palette `#6fcf97`, 8-bit owl mascot) to a professional enterprise visual system. (Initial attempt used Inter + IBM Plex Mono + cool blue — rejected by owner; see DECISION-017.)

## DECISION-017: UI follows AXO V1 (Charcoal) visual system
Date: 2026-06-08
Decider: Product owner
Status: accepted — supersedes DECISION-016 and the PRD §2.10 brand language
Decision: The QUILL UI is a faithful port of **AXO V1's Charcoal theme** (reference at `/Users/muhammadshabbar/Downloads/axo/msp-platform/desktop` + `axo-assets/css/tokens.css`). Per DECISION-002, AXO is reference-only; nothing is imported, but the visual language is intentionally aligned.

Visual system:
  - **Theme:** Charcoal (dark). `--bg-base #1c1c1e`, `--bg-surface #252528`, `--bg-elevated #2c2c2e`, `--text-primary #f0ece4` (cream).
  - **Accent:** AXO terracotta `#c87840` with hover `#e09050` and subtle `#c8784018`.
  - **Severity:** `#cc4444 critical · #c87840 high · #a89040 medium · #6a6a70 low` — same accent family.
  - **Typography:** **Syne** (700/800) for display + nav labels; **DM Mono** as the **body font** (the AXO signature — body in mono); **Instrument Serif** italic for taglines + decorative accents. Same font set the PRD §2.10 originally called for.
  - **Iconography:** Unicode glyphs (`↥ ⊞ ⛓` etc.) matching AXO V1's nav style; no icon font dependency. Brand mark is a hand-built 4×4 pixel mark in QUILL's accent — homage to AXO's pixel logomark, not a copy.
  - **Spacing/radius:** AXO's 4px scale (`--space-1..16`) and small/medium radii.
Reasoning:
  - Owner directive: "follow the AXO V1 style." AXO V1 is the proven enterprise look QUILL should match — same suite-of-products voice.
  - The PRD originally specified Syne/DM Mono/Instrument Serif (§2.10) anyway; the rejected element was light-green + owl mascot, not the typography.
Trade-offs accepted:
  - Visual coupling to AXO's look. If AXO's design evolves, QUILL should re-port deliberately (write a new DECISION-018+).

## DECISION-018: Palette returns to the PRD light-green spec; layout tightened
Date: 2026-06-09
Decider: Product owner
Status: accepted — supersedes the accent portion of DECISION-017
Decision: The accent palette pivots from AXO's terracotta (`#c87840`) to the PRD §2.10 spec: `#6fcf97` primary, `#a8e6c1` accent-soft, `#ff7a6b` alarm, on a slightly green-shifted charcoal (`#0f1612 → #161e1a → #1c2620`). Typography (Syne / DM Mono / Instrument Serif) and the AXO V1 information architecture (4-view sidebar, 50/50-ish split-pane) carry over from DECISION-017 unchanged — PRD already calls for the same fonts. Inline source highlights are now severity-coded background fills (alarm/orange/amber/slate) rather than dashed underlines, per owner feedback that highlights were not prominent enough. Attestation footer enlarged (taller textarea, larger buttons, primary surface treatment). 8-bit owl mascot is intentionally not restored — owner rejected it as too gimmicky in earlier feedback.
Reasoning:
  - Owner directive: "follow what the PRD mentions" for color palette.
  - Owner directive: highlights too subtle, gate page too congested, footer too small.
  - PRD §2.10 typography spec aligns with what's already shipping under DECISION-017; only colors changed.
Trade-offs accepted:
  - Mascot still omitted (DECISION-017 rationale stands).
  - The "alarm" highlight for high-severity findings is visually loud — that's intentional, not noise.

## Known follow-ups (not blocking)
- **Finding dedup:** Tier 0 (field-level) and Tier 2 (objective-level) can both flag the same control; add a dedup/merge pass before attestation (candidate WP-3 tail or WP-5). Currently both surface (acceptable, traceable).
- **Postgres adapter for audit/provenance:** In-memory today (DECISION-009 covers the same pattern); add Postgres-backed implementations alongside `quill_artifacts`/`quill_findings` adapters.
