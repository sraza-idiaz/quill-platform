# QUILL — AI-Assisted RMF Pre-Adjudication Terminal

> Standalone FastAPI service + web UI for **DLA SBIR topic DLA26BZ02-NV006**.
> Ingests draft RMF artifacts, finds missing / inconsistent / weak control
> implementations against a NIST SP 800-53 Rev.5 baseline, and routes every
> finding through a mandatory **named-human attestation gate** with signed
> provenance and a tamper-evident audit chain.

QUILL **never** makes the authorization decision. It informs; humans decide.

## What's in this repo

```
quill-platform/
├── CLAUDE.md  QUILL_PRD.md  DECISIONS.md         ← context, vision, decision log
├── ARCHITECTURE.md  SYSTEM_DESIGN.md             ← design layer
├── DESIGN_SPEC.md   SECURITY_AUDIT.md            ← design + security
├── docs/01–12                                    ← FR/NFR, rubric, eval plan,
│                                                   data handling, project plan,
│                                                   progress tracker, RTM,
│                                                   methods/limitations, rework
│                                                   assessment, Phase II recs,
│                                                   Phase I release checklist
├── backend/                                      ← FastAPI app
│   ├── models/      domain entities
│   ├── routes/      REST endpoints
│   └── services/    auth · catalog · ingest · analysis (T0/T1/T2/T3) ·
│                    citation_validator · confidence · provenance · audit ·
│                    change_request · export · gpg_signer · mcp_server
├── config/          quill.config.yaml · catalog.yaml · rubric.yaml
├── desktop/web/     vanilla HTML/CSS/JS UI served by FastAPI at /ui/
├── eval/            synthetic corpus + harness + reports (Phase I gates)
└── tests/           82 tests (unit + integration + eval-gate regression)
```

## Quick start (local)

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --port 8000
```

Then open **http://localhost:8000/ui/**.

### Try Tier 2 (live LLM) locally

```bash
ollama serve &                  # if you don't already have it running
ollama pull mistral:7b          # or mistral-small:24b for the PRD's model
# Edit config/quill.config.yaml:
#   ollama.model: "mistral:7b"
#   enable_tier2_at_startup: true
uvicorn backend.main:app --port 8000
```

### Run the test suite

```bash
pytest -q
```

### Run the eval against the synthetic corpus

```bash
python -m eval.harness.run_eval
# reports land under eval/reports/
```

## Phase I quality gates (locked in CI)

Measured on the synthetic ground-truth corpus (`eval/artifacts/` + `eval/ground_truth/labels.yaml`):

| Gate | Target | Latest |
|---|---|---|
| Deficiency-detection recall | ≥ 0.80 | **0.98** ✅ |
| False-positive rate | ≤ 0.20 | **0.11** ✅ |
| Traceability | = 1.00 | **1.00** ✅ |
| Calibration (ECE) | ≤ 0.20 monotonic | **0.064** monotonic ✅ |

`tests/integration/test_eval_gates.py` fails the build if any gate regresses.

## Deployment

The repo ships a `render.yaml` blueprint:

- Web service on Render's Python runtime (3.12.7)
- Auto-deploys on push to `main`
- Tier 2 is disabled in cloud (no Ollama daemon); orchestrator falls back to
  Tier 0 + Tier 1 with graceful degradation (FR-RES-01)
- Header-based dev auth (`X-QUILL-Role`) so reviewers can switch roles
  without provisioning JWTs

## Hard rules (non-negotiable)

1. Artifact-centric, not chat.
2. Human attestation is a hard gate. Nothing authoritative until a named human signs.
3. Every finding has a valid in-document source span. The pipeline rejects fabricated quotes.
4. Confidence is explicit and calibrated; low-confidence outputs **defer**, never assert.
5. Local-first / air-gap. Production = zero outbound calls with artifact data.
6. **Never automate the authorization decision.**
7. Circuit breaker threshold = **3**, never 999.

See `CLAUDE.md` and `DECISIONS.md` for the operating context and architecture decisions.
