# QUILL — Documentation Index

QUILL is the **AI-Assisted RMF Pre-Adjudication** product in the MERP suite, built for **DLA SBIR DLA26BZ02-NV006**. This `docs/` folder holds the buildable specifications that sit underneath the vision-level `QUILL_PRD.md`.

**Read order for a new contributor / agent:**

1. **`../CLAUDE.md`** — operating context, the 7 hard rules, the AXO reuse map. Read first.
2. **`../QUILL_PRD.md`** — the vision, agent roster, and phase orchestration.
3. **`01_FUNCTIONAL_REQUIREMENTS.md`** — enumerated, testable FR-IDs (what to build).
4. **`02_NON_FUNCTIONAL_REQUIREMENTS.md`** — quality targets and constraints.
5. **`03_EVIDENCE_SUFFICIENCY_RUBRIC.md`** — the core IP; read before any analysis code.
6. **`04_GROUND_TRUTH_AND_EVALUATION_PLAN.md`** — how Phase I success is measured.
7. **`05_DATA_HANDLING_CUI_ITAR_POLICY.md`** — CUI/ITAR/air-gap rules (compliance gate).
8. **`06_PROJECT_PLAN_AND_PHASES.md`** — WBS, milestones, dependencies, risks.
9. **`07_PROGRESS_TRACKER.md`** — living "% complete" tracker (update as work lands).
10. **`08_REQUIREMENTS_TRACEABILITY_MATRIX.md`** — topic req → FR → test → status.
11. **`../DECISIONS.md`** — architecture decision log.

## Document map

| Layer | Documents |
|---|---|
| **Vision / orchestration** | `QUILL_PRD.md`, `CLAUDE.md` |
| **Requirements** | `01_FUNCTIONAL_REQUIREMENTS`, `02_NON_FUNCTIONAL_REQUIREMENTS` |
| **Core IP / algorithm** | `03_EVIDENCE_SUFFICIENCY_RUBRIC` |
| **Data & evaluation** | `04_GROUND_TRUTH_AND_EVALUATION_PLAN` |
| **Compliance** | `05_DATA_HANDLING_CUI_ITAR_POLICY` |
| **Project management** | `06_PROJECT_PLAN_AND_PHASES`, `07_PROGRESS_TRACKER`, `08_REQUIREMENTS_TRACEABILITY_MATRIX` |
| **Decisions** | `DECISIONS.md` |

## Design-layer documents (drafted — at repo root, awaiting review)

- `../ARCHITECTURE.md` — locked stack, repo structure, file-level AXO reuse map, config schemas, OSCAL + migration strategy.
- `../SYSTEM_DESIGN.md` — components, data flows, API/MCP contract, roles, FMEA, calibration design.
- `../DESIGN_SPEC.md` — QUILL brand + screen-by-screen UX (the review+attest screen is the core).
- `../SECURITY_AUDIT.md` — threat model + boundary (drafted); audit *results* filled at WP-6.

## Still produced *during* the build (owned by their agents per the PRD)

- `methods_and_limitations.md` (Compliance/Tech Docs — DLA deliverable)
- `/docs/` end-user + operator guides (Tech Docs) · `eval/` harness + reports (ML/Eval)
- Visual UI mockups (FE Designer — `DESIGN_SPEC.md` is currently a text spec)
- `SECURITY_AUDIT.md` §4/§6 results (Security — at hardening)

## AXO reuse

AXO (the sibling product QUILL extends) lives at **`/Users/muhammadshabbar/Downloads/axo/msp-platform`**. See the reuse map in `../CLAUDE.md` for the exact modules to extend (auth, provenance, audit, Change-Request, GPG, Slack, desktop, policies, migrations).
