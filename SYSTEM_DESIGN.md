# SYSTEM_DESIGN.md — QUILL

> Owner: System Designer. Describes *behavior*: components, data flows, the API contract, roles, failure-mode analysis, and how confidence calibration is measured. Pairs with `ARCHITECTURE.md` (structure) and the FR/NFR specs (requirements).

---

## 1. Component overview

```
            ┌───────────────── ARTIFACT SOURCES ─────────────────┐
            │  Upload (PDF/DOCX/MD/OSCAL)  ·  Folder watch  ·  Slack drop │
            └───────────────────────┬─────────────────────────────┘
                                     ▼
   ┌──────────────────────── INGEST & NORMALIZE ────────────────────────┐
   │  parser(pdf/docx/md/oscal) → normalizer → control-keyed segments     │
   │  + locators (page/§/char-offset) + content hash → artifact row       │
   └───────────────────────────┬─────────────────────────────────────────┘
                                ▼
   ┌──────────────────────── ANALYSIS ENGINE (run) ─────────────────────┐
   │  T0 rules/KB (deterministic)  →  T1 retrieval+evidence index         │
   │  →  T2 local-LLM sufficiency  →  citation_validator  →  confidence   │
   │       │                                                   │           │
   │       └──► circuit_breaker (threshold 3) ──► route to human review    │
   │  T3 escalation* (opt-in, air-gap-disabled)                           │
   └───────────────────────────┬─────────────────────────────────────────┘
                                ▼  findings (type/severity/confidence/span/recommendation)
   ┌──────────────────────── ATTESTATION LAYER ─────────────────────────┐
   │  finding_service → Change-Request → provenance(GPG sign) → audit     │
   │  status: unattested → approved | edited | rejected (by `attester`)   │
   └───────────────────────────┬─────────────────────────────────────────┘
                                ▼
   ┌──────────┬──────────────────────────┬────────────────────────────────┐
   │ Desktop  │ Slack @quill             │ Export (signed report,         │
   │ review&  │ status/findings/attest   │  OSCAL POA&M, audit artifact)  │
   │ attest   │ /health + upload         │                                │
   └──────────┴──────────────────────────┴────────────────────────────────┘
   * disabled in air-gap mode
```

All components are reachable only through the API (API-first). The UI, Slack bot, and MCP server are clients of the same endpoints.

## 2. Data-flow diagrams

### 2.1 Ingest
`source → parser → normalizer (control-keyed segments + locators) → hash → persist artifact(status=ingested) → audit_event(ingest)`. Corrupt/unparseable → `run(status=failed, reason)`, no crash (FR-ING-05).

### 2.2 Analyze (a `run`)
```
create run(status=analyzing, tier_path=[])
  T0: coverage vs baseline · required-field · cross-artifact consistency · OSCAL schema
      → deterministic findings (missing/inconsistent/field-level)            [append T0]
  T1: map segments→control_id + 800-53A objective; build evidence_index(spans, scores) [append T1]
  T2: per determination statement → sufficiency score (rubric) → candidate finding
        → citation_validator: span must be verbatim in artifact, else DROP+log
        → confidence: ≥emit→finding ; needs_review→finding(flagged) ; <defer→flag_for_review
        → circuit_breaker.observe(): 3rd low-conf/contradiction → trip → route artifact to human
  (T3 only if tier3_enabled && !air_gap && !restricted)
finish run(status, circuit_breaker_tripped)
```
Idempotent: re-running a run replaces its findings, never duplicates (NFR-REL-04).

### 2.3 Finding emission → attestation
`finding(unattested) → attester opens review → approve|edit|reject → change_request → git_signer(GPG) → provenance_record → audit_event`. Edit preserves original + edited, both signed (FR-ATT-06). Nothing exportable while `unattested` (FR-ATT-02).

### 2.4 Export
`select attested findings → render {signed report | OSCAL POA&M | audit artifact} → GPG sign → verify`. POA&M contains no authorization field (FR-EXP-02).

## 3. API contract (draft — REST; MCP mirrors 1:1)

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/artifacts` | engineer+ | Upload + ingest (multipart) |
| GET | `/artifacts/{id}` | viewer+ | Artifact + status |
| POST | `/artifacts/{id}/runs` | engineer+ | Start analysis run |
| GET | `/runs/{id}` | viewer+ | Run status + tier_path + breaker flag |
| GET | `/runs/{id}/findings` | viewer+ | Findings (filter by type/severity/status) |
| GET | `/findings/{id}` | viewer+ | Finding + evidence spans + provenance |
| POST | `/findings/{id}/attest` | **attester** | `{decision: approve|edit|reject, note, edited_fields?}` → signed |
| GET | `/findings/{id}/audit` | viewer+ | Audit/provenance trail |
| GET | `/catalog` / `/catalog/{control_id}` | viewer+ | Loaded controls + objectives |
| POST | `/runs/{id}/export` | engineer+ | `{format: report|poam|audit}` → signed artifact |
| GET | `/health` | any | Tier + backend health |

**MCP tools:** `quill.upload`, `quill.analyze`, `quill.run_status`, `quill.findings`, `quill.attest`, `quill.export`, `quill.health` — same auth/role rules.

**Auth/roles:** reuse AXO JWT + `require_role`. Roles: `admin` (all), `engineer` (ingest/analyze/export), `attester` (attest — the new role), `viewer` (read). Tenant isolation on every query.

## 4. Failure-mode analysis (FMEA)

| Failure | Detection | Behavior | Req |
|---|---|---|---|
| Ollama / LLM down | health check / call error | Degrade to T0 + `flag_for_review`; run completes | FR-RES-01 |
| Low-confidence storm / contradictions | confidence + breaker counter | Breaker (3) trips → whole artifact to human review | FR-CONF-02 |
| Corrupted / unparseable artifact | parser error | `run=failed` + reason; no crash; quarantine | FR-ING-05 |
| Storage outage mid-run | DB error | Consistent state; run resumable/fails clean; no corruption | NFR-REL-02 |
| Cited span not in artifact | citation_validator | Finding dropped + logged; never surfaced | FR-T2-03 |
| Prompt injection in artifact | content-as-data isolation + span validation | No authorization claim, no suppression, no egress | NFR-SEC-05 |
| T3 toggled on in air-gap | config guard | T3 path unreachable | FR-T3-02 |
| Backend unreachable (Slack/UI) | client error handling | Clean error, no stack trace, no cross-tenant data | FR-SLK-06 |

## 5. Confidence-calibration design

- Confidence inputs: T1 retrieval score, T2 model self-certainty (untrusted raw), span quality, cross-statement agreement (`docs/03` §5.2).
- **Measurement:** bucket findings by confidence; compute empirical correctness per bucket from human-confirmed labels; plot reliability curve; compute ECE (`docs/04` §4).
- **Correction:** if miscalibrated, apply post-hoc isotonic/Platt mapping (no fine-tuning in Phase I). Store the mapping in config; re-measure.
- **Until calibrated:** treat raw confidence as uncalibrated and lean conservative (defer more, assert less).

## 6. Security boundaries (summary; full in `SECURITY_AUDIT.md` + `docs/05`)

- Sandbox boundary = trust boundary; CUI does not cross without authorization.
- Artifact content never logged; egress = zero in air-gap.
- Every state change audited and integrity-verifiable.
- No code path produces an authorize/deny output (tested negatively).

## 7. Observability

Operational metrics only (run durations, tier hit-rates, breaker trips, finding counts by severity) — **never** artifact content (NFR-OBS-01). Health endpoint reports tier availability.

## 8. Open design questions (resolve in `DECISIONS.md`)

1. Standalone QUILL service vs. embedded router-set in AXO (recommend standalone importing AXO shared pkgs).
2. Default baseline (recommend Moderate) — `FR-CAT-03`.
3. Embedding/retrieval approach for T1 (local embeddings model) — pick at T-3.1.
4. Final confidence thresholds + ECE bound — set at eval (T-6.2).
