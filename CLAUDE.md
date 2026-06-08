# CLAUDE.md — QUILL Build Context

> **Read this before any work in this repo.** It is the operating context for every Claude Code session and every sub-agent. It is the short, load-bearing summary; the full specs live in `docs/`.

---

## What QUILL is

QUILL is an **artifact-centric, human-attested AI capability** for **RMF pre-adjudication**. It ingests draft RMF artifacts (control implementation statements, System Security Plans, architecture docs, OSCAL), finds **missing / inconsistent / weak / insufficiently-evidenced** controls against a NIST SP 800-53 Rev.5 baseline, and emits **confidence-scored, source-cited findings** that a named human must **approve / edit / reject** before they are authoritative.

It is built for **DLA SBIR topic DLA26BZ02-NV006**. Phase I = feasibility prototype, ≤12 months, ≤$100K, runs in an approved R&D sandbox with **no ATO**.

**The product never makes or recommends an authorization decision.** QUILL informs; humans decide.

QUILL is a **fully standalone product** — its own brand, its own Slack bot, its own auth, its own data, its own everything.

---

## The 7 hard rules (a violation is a bug, not a style choice)

1. **Artifact-centric, not a chatbot.** The unit of work is an *artifact analysis run*, not a chat turn.
2. **Human attestation is a hard gate.** No finding is exported or treated as authoritative until a named human signs it. Findings flow `unattested → approved | edited | rejected` via a PR-style change-request with a GPG signature recorded in QUILL's provenance + audit ledger.
3. **Every finding has a valid source span** (artifact id + locator + exact quoted text). A finding whose cited text is **not present** in the artifact must be **rejected by the pipeline**. No span → invalid finding.
4. **Confidence is explicit and calibrated.** High-confidence/clear → finding; low-confidence/ambiguous → defer to human ("flag for review"), never assert.
5. **Local-first / air-gap.** Production makes **zero outbound calls** with artifact data. Tier 3 cloud escalation is opt-in and **disabled in air-gap mode**. No telemetry on artifact content.
6. **Never automate authorization.** Do not build any logic that recommends or implements authorize/deny.
7. **Circuit breaker threshold = 3** (the documented value). Repeated low-confidence/contradiction on an artifact → route the whole artifact to human review.

If any change would break one of these, stop and flag it.

---

## The tiered analysis engine (build in order; prove each before the next)

| Tier | What it does | LLM? |
|---|---|---|
| **T0** | Rule/KB-first deterministic checks: control-coverage vs baseline, required-field presence, cross-artifact consistency, OSCAL schema validation | No |
| **T1** | Retrieval + structured extraction: map artifact text → control IDs + 800-53A assessment objectives; build evidence index with source spans | No (lexical baseline → embeddings later) |
| **T2** | Local-LLM evidence-sufficiency scoring per determination statement; emits finding text + calibrated confidence + severity; **mandatory source-span + citation validation** | Yes (Ollama, on-box) — default analyzer |
| **T3** | Cloud LLM escalation — **opt-in, disabled in air-gap, never with restricted data** | Yes (Claude API) — optional |

**Do not skip the sequence.** T0 must work and be tested before T1; T1 before T2. T3 is a demo toggle only in Phase I.

---

## About "AXO" references in this repo

The PRD repeatedly references AXO, another product whose architectural patterns inspired QUILL. **AXO is reference architecture only — not a runtime dependency, not imported, never required.** When a doc mentions AXO it means *"the same pattern AXO uses (which is proven)"*, not *"import code from AXO."*

You may look at AXO's codebase at `/Users/muhammadshabbar/Downloads/axo/msp-platform` **only if** you want to study a proven pattern (e.g., how a circuit breaker or signed change-request flow is structured). Then write QUILL's own implementation. **No imports, no shared packages, no shared services, no shared brand, no shared Slack.**

If AXO inspiration is unnecessary for the task at hand, skip it.

---

## Stack (locked)

Python 3.12+ · FastAPI · PostgreSQL (local) · Ollama (local LLM, default Mistral 24B) · optional Claude API (T3) · GPG signing (built in QUILL) · JWT auth (built in QUILL) · React + Vite/Tauri desktop (QUILL's own) · Slack bot (QUILL's own, separate workspace from any sibling product). Optional Memgraph deferred to Phase II.

Repo root: `/quill-platform/`.

---

## Where things are

- **The vision / orchestration spec:** the original `QUILL_PRD.md`.
- **Design layer:** `ARCHITECTURE.md`, `SYSTEM_DESIGN.md`, `DESIGN_SPEC.md`, `SECURITY_AUDIT.md` at the repo root.
- **Buildable specs:** `docs/01–08` — see `docs/README.md` for the index.
- **The core IP:** `docs/03_EVIDENCE_SUFFICIENCY_RUBRIC.md` — read this before touching T2.
- **Decision log:** `DECISIONS.md` — log every architecture-level decision here.
- **Progress:** `docs/07_PROGRESS_TRACKER.md` — update after every completed task.
- **How to run what exists today:** `BUILDING.md`.

---

## Working agreements

- **API-first:** every capability is exposed via the API (REST/FastAPI + MCP). UI, Slack, integrations call the same API. If it's not in the API, it doesn't exist.
- **Generic-first / schema-driven:** catalogs, objectives, finding types, severity, rubric live in YAML/OSCAL config — never hardcoded.
- **Tests from day one.** Traceability test (every finding has a valid in-document span) and circuit-breaker test are mandatory.
- **Log decisions in `DECISIONS.md`** when you resolve any ambiguity.
- **Treat sandbox artifacts as CUI.** See `docs/05_DATA_HANDLING_CUI_ITAR_POLICY.md`. Never log artifact content. Verify zero egress in air-gap mode.
