# ARCHITECTURE.md — QUILL

> Owner: System Architect. Locks the tech stack, repo structure, config schemas, OSCAL strategy, and migration approach. **QUILL is fully standalone** (DECISION-002) — no shared packages with any sibling product. Read alongside `SYSTEM_DESIGN.md` (behavior) and `CLAUDE.md` (rules).

---

## 1. Locked tech stack

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.12+ | |
| API framework | FastAPI (async) | |
| DB | PostgreSQL via `asyncpg` | |
| Config | `pydantic-settings` `BaseSettings` + `.env`; secrets via env/secret manager | Never hardcode secrets |
| Local LLM | Ollama + Mistral 24B (Tier 2) | DECISION-001 |
| Cloud LLM | Claude API (Tier 3, opt-in, air-gap-disabled) | DECISION-001 |
| Signing | GPG via `python-gnupg` (built in QUILL) | Signs attestations + exports |
| Auth | JWT (built in QUILL); roles via `require_role()` | `admin / engineer / attester / viewer` |
| Desktop | React + Vite + Tauri (QUILL's own shell) | |
| Slack | QUILL-owned bot in its own workspace | |
| Migrations | Numbered SQL (`backend/db/migrations/NNN_*.sql`) | Forward-only |
| Container | Docker + docker-compose | |
| Graph (optional) | Memgraph | **Deferred to Phase II** |

Pin exact versions in `requirements.txt` and record deviations in `DECISIONS.md`.

## 2. Repo structure — `/quill-platform/` (standalone)

```
quill-platform/
├── CLAUDE.md  QUILL_PRD.md  DECISIONS.md  BUILDING.md
├── ARCHITECTURE.md  SYSTEM_DESIGN.md  DESIGN_SPEC.md  SECURITY_AUDIT.md
├── docs/                         # 01–08 specs + build-time guides
├── config/
│   ├── quill.config.yaml         # runtime config (air-gap, tier toggles, model)
│   ├── catalog.yaml              # 800-53 Rev.5 catalog ref (OSCAL) + baseline
│   └── rubric.yaml               # evidence-sufficiency rubric (see docs/03)
├── backend/
│   ├── config.py                 # Settings: ollama, tier3 toggle, air_gap, jwt
│   ├── main.py                   # FastAPI app
│   ├── db/
│   │   ├── connection.py
│   │   ├── migrations/           # NNN_quill_*.sql (forward-only)
│   │   ├── repository.py         # Repository protocol + InMemory + Postgres impls
│   │   └── *_queries.py          # Postgres adapter modules
│   ├── models/                   # pydantic: artifact, control, assessment_objective,
│   │                             #   run, finding, evidence_span, attestation, user
│   ├── routes/                   # artifacts, runs, findings, attestation, catalog,
│   │                             #   export, auth, change_requests, audit, mcp
│   ├── services/
│   │   ├── auth.py               # JWT + require_role (QUILL-owned)
│   │   ├── provenance_service.py # signed provenance ledger (QUILL-owned)
│   │   ├── audit_service.py      # tamper-evident audit trail (QUILL-owned)
│   │   ├── change_request_service.py  # PR-style attestation flow (QUILL-owned)
│   │   ├── gpg_signer.py         # GPG sign/verify
│   │   ├── slack_bot.py          # @quill bot (QUILL workspace)
│   │   ├── ingest/               # parsers + normalizer
│   │   ├── analysis/
│   │   │   ├── tier0_rules.py
│   │   │   ├── tier1_retrieval.py
│   │   │   ├── tier2_sufficiency.py
│   │   │   ├── tier3_escalation.py     # opt-in; air-gap-disabled
│   │   │   ├── rubric_engine.py
│   │   │   ├── citation_validator.py
│   │   │   └── confidence.py           # disposition + circuit breaker (=3)
│   │   ├── finding_service.py
│   │   ├── export_service.py     # signed report + OSCAL POA&M + audit artifact
│   │   └── mcp_server.py
│   └── integrations/             # eMASS-class (Phase II; interface only in Phase I)
├── desktop/                      # React + Vite + Tauri (QUILL UI)
├── eval/                         # ground-truth + harness (see docs/04)
└── tests/                        # unit / integration / traceability / chaos / security
```

## 3. QUILL component map (self-contained — no external dependencies)

| Capability | Module | Status |
|---|---|---|
| JWT auth + roles + `require_role` | `backend/services/auth.py` | dev-mode header fallback today (DECISION-011); real JWT next |
| Provenance ledger (signed records) | `backend/services/provenance_service.py` | to build (WP-4) |
| Tamper-evident audit trail | `backend/services/audit_service.py` | to build (WP-4) |
| PR-style change-request (attestation flow) | `backend/services/change_request_service.py` | to build (WP-4) |
| GPG signing | `backend/services/gpg_signer.py` | to build (WP-4) |
| Circuit breaker | `backend/services/analysis/confidence.py` | built, threshold=3, rejects 999 |
| Catalog + rubric loader | `backend/services/catalog_loader.py` | built |
| Ingestion + normalization | `backend/services/ingest/` | built |
| Tier 0 deterministic engine | `backend/services/analysis/tier0_rules.py` | built |
| Tier 1 retrieval / evidence index | `backend/services/analysis/tier1_retrieval.py` | built (lexical baseline, DECISION-010) |
| Tier 2 local-LLM analyzer | `backend/services/analysis/tier2_sufficiency.py` | built (Ollama adapter + mock for tests) |
| Citation/traceability validator | `backend/services/analysis/citation_validator.py` | built |
| Run orchestrator | `backend/services/orchestrator.py` | built |
| REST API | `backend/routes/api.py` | built |
| MCP server | `backend/services/mcp_server.py` | pending |
| Signed export (report + POA&M + audit) | `backend/services/export_service.py` | pending (WP-5) |
| Slack `@quill` bot | `backend/services/slack_bot.py` | pending (WP-5) |
| Desktop UI | `desktop/` | pending (WP-5) |

**Note on AXO references in older docs.** Earlier drafts of the design layer used AXO's codebase as an explicit reuse target. Under DECISION-002, AXO is **reference architecture only** — its files may be read to study proven patterns, but no code, packages, or services are shared. Any remaining "AXO" mentions in docs should be read as *"the pattern AXO demonstrates,"* not *"import AXO."*

## 4. Config schemas

- **`quill.config.yaml`** — `air_gap: true|false`, `tier3_enabled: false`, `ollama: {model, host}`, `confidence: {emit, needs_review, defer_below}`, `circuit_breaker: {threshold: 3}`, `watch_folder`, `tenant`, `dev_mode: bool`.
- **`catalog.yaml`** — points at the OSCAL 800-53 Rev.5 catalog + 800-53A objectives; sets `baseline: low|moderate|high`.
- **`rubric.yaml`** — full schema in `docs/03` §7.

All three are read at runtime; changing them must require no code change (NFR-MNT-01/03).

## 5. OSCAL ingestion strategy

- Use NIST OSCAL models (catalog, profile, SSP, component-definition, POA&M).
- Ingest: OSCAL JSON → validate against OSCAL schema (FR-T0-04) → map `control-implementation` statements to internal `control` keys + `evidence_span` locators.
- Export: open findings → OSCAL **POA&M** model (FR-EXP-02). Never an authorization artifact.
- Keep an OSCAL adapter module so catalog/profile versions can change via config.

## 6. Migration strategy

- Numbered SQL migrations (`backend/db/migrations/NNN_quill_*.sql`); forward-only.
- New tables: `quill_artifacts, quill_runs, quill_findings, quill_evidence_spans, quill_attestations`, plus `quill_users, quill_provenance_records, quill_audit_events, quill_change_requests` for QUILL's own auth/provenance/audit/CR stack (added in WP-4 migrations).

## 7. Deployment topologies

| Mode | Description |
|---|---|
| **Sandbox (Phase I default)** | Single workstation, Docker, local Postgres + Ollama, air-gap on, Tier 3 off |
| **Air-gap install** | Pre-staged images + model; offline install verified (NFR-MNT-05) |
| **Connected demo** | Tier 3 toggle available for demonstration only; never with restricted data |

## 8. Cross-cutting

- **API-first:** every capability has a REST endpoint and an MCP tool.
- **Tenant isolation:** every query is tenant-scoped; no global mutable state keyed without tenant.
- **No artifact content in logs** (`docs/05`).
- **Generic-first:** catalogs/objectives/rubric/severity all in config.
