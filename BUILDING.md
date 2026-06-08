# BUILDING.md — running QUILL locally

> Build status and how to run what exists. Updated as work lands. See
> `docs/07_PROGRESS_TRACKER.md` for the full task-level status.

## Current state (2026-06-08)

A **runnable FastAPI service** with the full pipeline + the human attestation gate.
**66 tests passing** (unit + integration), no live DB/LLM/keyring required.

- Domain models · config (catalog/rubric/runtime, generic-first) · catalog+rubric loader
- Ingestion: MD/TXT/OSCAL/PDF/DOCX parsers + normalizer (section carry-forward) — FR-ING
- **Tier 0** deterministic engine (coverage/required-field/ODP/consistency/OSCAL) — FR-T0
- **Tier 1** lexical retrieval + evidence index (spans + scores) — FR-T1
- **Tier 2** local-LLM sufficiency scoring, pluggable analyzer (Ollama real / mock test),
  two-axis rubric decision table, artifact-as-data prompt isolation — FR-T2
- Citation/traceability validator · confidence disposition · circuit breaker (=3) — FR-CONF/T2-03
- Run orchestrator with graceful degradation (no LLM → T0/T1 + flag) — FR-RES-01
- REST API + JWT auth (with DEV_MODE header fallback) + tenant isolation — FR-API
- **Attestation gate live** — approve/edit/reject with **signed provenance** and a
  **tamper-evident SHA-256 hash-chained audit trail** — FR-ATT-01..06, NFR-AUD-01..04
  - signer is pluggable: `GpgSigner` for production, `HmacSigner` for dev/tests (DECISION-012)
  - admin is **not** auto-granted attestation (security-critical separation)
- SQL migrations 001/002; in-memory repo for dev/test (Postgres adapter pending)

### Run the live service
```bash
. .venv/bin/activate
uvicorn backend.main:app --port 8731
curl localhost:8731/health
curl -X POST localhost:8731/artifacts -H "X-QUILL-Role: engineer" -F "file=@tests/fixtures/ssp_weak_ac2.md"
# then POST /artifacts/{id}/runs and GET /runs/{id}/findings
```
(Tier 2 activates when Ollama+Mistral is reachable; otherwise the service safely runs T0/T1.)

Not yet built (next): signed export (human report + OSCAL POA&M + audit artifact), MCP server,
desktop UI + Slack bot (WP-5), eval harness + ground-truth corpus + metrics (WP-6),
Postgres adapter (replaces in-memory repos).

## Setup

```bash
cd quill-platform
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt          # full stack
# (for the Tier 0 slice only: pip install pydantic pyyaml pytest pypdf python-docx)
```

## Run the tests

```bash
. .venv/bin/activate
python -m pytest tests/unit -v
```

## Try Tier 0 on a document (quick REPL)

```python
from backend.services.catalog_loader import load_catalog, load_rubric
from backend.services.ingest.normalizer import normalize
from backend.services.analysis.tier0_rules import run_tier0

catalog = load_catalog("config/catalog.yaml")
rubric  = load_rubric("config/rubric.yaml")
segs    = normalize("art0", __import__("pathlib").Path("tests/fixtures/ssp_weak_ac2.md"))
for f in run_tier0("run1", segs, catalog, rubric):
    print(f"{f.severity.value:8} {f.type.value:30} {f.control_id:6} {f.recommendation}")
```

## Conventions

- Match AXO style (`/Users/muhammadshabbar/Downloads/axo/msp-platform`): pydantic models, async FastAPI, numbered SQL migrations.
- Generic-first: no catalog/rubric data hardcoded — edit the YAML.
- Every finding carries a traceable span; deterministic checks have confidence 1.0.
- No artifact content in logs; no authorization decision anywhere.
