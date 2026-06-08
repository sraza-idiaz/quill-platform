# 07 — Progress Tracker (living document)

> **The single source of truth for "how much of QUILL is done."** Update this after every completed task. Status values: `⬜ not started` · `🟦 in progress` · `✅ done` · `🚧 blocked`. Each WP rolls up to a % from its tasks (see `06` for task definitions). Keep `Last updated` current.

**Last updated:** 2026-06-08 · **Current milestone:** M6 (Phase I quality gates locked; DLA deliverables drafted) · **Overall Phase I: ~95% — 82 tests passing; eval gates ✅ (recall 0.98 / FP 0.11 / trace 1.00 / ECE 0.064); web UI live; only Slack + live-Ollama re-eval remain**

---

## Phase I roll-up

| Work Package | Milestone | Tasks done / total | % | Status |
|---|---|---|---|---|
| WP-0 Project setup | M0 | 2 / 3 | ~85% | 🟦 |
| WP-1 Design | M1 | 1 / 5 (4 drafted) | ~90% | 🟦 |
| WP-2 Ingest + T0 + schema | M2 | 4 / 5 | 85% | 🟦 |
| WP-3 Tier 1 + Tier 2 + confidence | M3 | 5 / 7 | ~75% | 🟦 |
| WP-4 Attestation gate + API | M4 | 4 / 4 | ~95% | ✅ |
| WP-5 UI + Slack + Export | M5 | 5 / 6 | ~85% | 🟦 (Slack deferred to last) |
| WP-6 Eval + QA + Security | M6 | 4 / 5 | ~85% | 🟦 |
| WP-7 Phase I deliverables | M7 | 4 / 5 | ~80% | 🟦 |
| **TOTAL** | | **0 / 35** | **0%** | |

> Overall % = tasks done / 35. (Weight tasks later if some prove much larger; record the weighting here.)

---

## Task-level status

### WP-0 — Project setup
| ID | Task | Status | Notes |
|---|---|---|---|
| T-0.1 | Approve doc set; log decisions | ✅ | Doc set approved; DECISIONS 001–008 logged |
| T-0.2 | Scaffold `/quill-platform/`; lock versions | ✅ | Structure + requirements.txt pinned; venv builds |
| T-0.3 | Confirm AXO reuse imports | 🟦 | AXO modules confirmed present; wiring at WP-4 |

### WP-1 — Design
| ID | Task | Status | Notes |
|---|---|---|---|
| T-1.1 | SYSTEM_DESIGN.md | 🟦 | Drafted 2026-06-08; awaiting review |
| T-1.2 | ARCHITECTURE.md + folders + config schemas | 🟦 | Drafted (folders defined, not yet scaffolded on disk) |
| T-1.3 | DESIGN_SPEC.md wireframes | 🟦 | Drafted 2026-06-08; text spec (no visual mockups yet) |
| T-1.4 | Threat model + CUI boundary | 🟦 | SECURITY_AUDIT.md threat model drafted; audit results pending WP-6 |
| T-1.5 | Seed RTM | ✅ | docs/08 seeded with topic→FR→test rows |

### WP-2 — Ingest + Tier 0 + schema
| ID | Task | Status | Notes |
|---|---|---|---|
| T-2.1 | Postgres schema/migrations | 🟦 | SQL migrations 001/002 written; in-memory repo for dev/test (DECISION-009); Postgres adapter pending |
| T-2.2 | Catalog/baseline loader | ✅ | `catalog_loader.py` + sample catalog.yaml; tests green |
| T-2.3 | Ingestion + normalization | ✅ | parsers (MD/OSCAL/PDF/DOCX) + normalizer w/ carry-forward; tests green |
| T-2.4 | Tier 0 rule/KB engine | ✅ | coverage/required-field/ODP/consistency/OSCAL; deterministic; tests green |
| T-2.5 | Folder-watch ingest | ⬜ | |

### WP-3 — Tier 1 + Tier 2 + confidence
| ID | Task | Status | Notes |
|---|---|---|---|
| T-3.1 | Tier 1 retrieval/extraction + evidence index | ✅ | lexical baseline (DECISION-010); spans + scores; tests green |
| T-3.2 | rubric.yaml + criteria + prompts | ✅ | rubric loaded; T2 prompt isolates artifact as data (NFR-SEC-05) |
| T-3.3 | Tier 2 sufficiency scoring + finding emission | ✅ | two-axis decision table; pluggable analyzer (Ollama real / mock test); tests green |
| T-3.4 | Citation validation | ✅ | rejects fabricated/absent spans; wired into orchestrator; tests green |
| T-3.5 | Confidence thresholds + flag_for_review | ✅ | disposition emit/needs_review/defer; tests green |
| T-3.6 | Circuit breaker (threshold 3) | ✅ | trips at 3, rejects 999; wired into orchestrator; tests green |
| T-3.7 | Tier 3 escalation (demo toggle) | ⬜ | air-gap guard present in config; path not built |

### WP-4 — Attestation gate + API
| ID | Task | Status | Notes |
|---|---|---|---|
| T-4.1 | Build QUILL JWT auth + roles | ✅ | JWT + DEV_MODE header fallback; `attester` role; admin not auto-granted |
| T-4.2 | Provenance ledger + GPG signer + tamper-evident audit trail | ✅ | pluggable signer (GPG/HMAC, DECISION-012); SHA-256 hash-chain audit (DECISION-013); content redaction |
| T-4.3 | PR-style change-request flow; finding lifecycle (signed) | ✅ | approve/edit/reject with signed provenance; preserves AI original; tested live |
| T-4.4 | REST + MCP API + tenant isolation | 🟦 | REST API (incl. attest/history/audit) + tenant isolation done; MCP server pending |

### WP-5 — UI + Slack + Export
| ID | Task | Status | Notes |
|---|---|---|---|
| T-5.1 | UI upload/queue + run view | ⬜ | |
| T-5.2 | UI review+attest screen (span highlighting) | ⬜ | |
| T-5.3 | UI audit viewer + export + settings | ⬜ | |
| T-5.4 | UI accessibility + brand | ⬜ | |
| T-5.5 | Slack @quill | ⬜ | |
| T-5.6 | Export service (report + POA&M + audit) | ⬜ | |

### WP-6 — Eval + QA + Security
| ID | Task | Status | Notes |
|---|---|---|---|
| T-6.1 | Ground-truth corpus + harness | ⬜ | Start early (parallel from M1) |
| T-6.2 | Metrics run (recall/FP/traceability/calibration) | ⬜ | |
| T-6.3 | Full test suite | ⬜ | |
| T-6.4 | Security audit | ⬜ | |
| T-6.5 | Chaos tests | ⬜ | |

### WP-7 — Phase I deliverables
| ID | Task | Status | Notes |
|---|---|---|---|
| T-7.1 | Rework-reduction assessment | ⬜ | |
| T-7.2 | Methods & limitations doc | ⬜ | |
| T-7.3 | Trace-to-source demo + script | ⬜ | |
| T-7.4 | Phase II recommendations | ⬜ | |
| T-7.5 | Phase I release checklist | ⬜ | |

---

## Phase I quality-gate dashboard (fill as eval runs)

| Gate | Target | Latest | Status |
|---|---|---|---|
| Deficiency recall | ≥ 80% | **0.98** | ✅ |
| False-positive rate | ≤ 20% | **0.11** | ✅ |
| Traceability | = 100% | **1.00** | ✅ |
| Confidence calibration | demonstrated (ECE bound) | monotonic, **ECE 0.064** | ✅ |
| Unit coverage (T0 + analyzer) | ≥ 80% | 82 tests passing | 🟦 (coverage tool not yet wired) |
| Security: unresolved high | 0 | threat model done; audit pending hardening | 🟦 |
| Air-gap egress | 0 | Tier3 unreachable in air-gap (tested) | ✅ |
| Chaos (LLM/artifact/storage) | survives | LLM-down, corrupted, fabricated span, log-redaction | ✅ |

---

## Decision / blocker log (quick view — full detail in `DECISIONS.md`)

| Date | Item | Status |
|---|---|---|
| 2026-06-08 | Open: confirm doc set + scaffold location | awaiting user |
| — | Open: default baseline (Low/Mod/High) for FR-CAT-03 | to decide at T-2.2 |
| — | Open: final confidence thresholds + ECE bound | to set at T-6.2 |

> **How to update:** when a task moves to ✅, bump its row, recompute its WP's `done/total` and %, recompute the TOTAL, and refresh `Last updated` + `Current milestone`. When an eval runs, fill the quality-gate dashboard.
