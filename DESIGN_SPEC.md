# DESIGN_SPEC.md — QUILL UI/UX (revised, per DECISION-016)

> Owner: Frontend Designer. Updated 2026-06-08 to reflect the professional
> enterprise direction (DECISION-016). The previous brand spec (light-green
> palette, 8-bit owl mascot) is archived as `DESIGN_SPEC_ORIGINAL.md` for
> traceability to the PRD's original §2.10. **The information architecture
> (source-span highlighting, two-pane review, attestation drawer) is
> unchanged** — only the visual language.

---

## 1. Brand system (new)

| Token | Value | Use |
|---|---|---|
| Background gradient | radial `#0e1832 → #0a1224 → #060912` (top → bottom) | Page surface |
| Surface | `#0f1a2e` · `#142340` · `#1a2c4f` | Cards, panels, drawers |
| Border | `#1c2c4a` · `#243a60` | Dividers, card borders |
| Text | `#e6edf7` primary · `#b5c1d4` secondary · `#7a8aa3` muted · `#4f5e7a` dim | Reading order |
| Primary accent | `#4f8cff` (cool professional blue) · `#6ea3ff` hover · `#2864e0` active | CTAs, focus, highlights |
| Severity | `#ef4444` critical · `#f59e0b` high · `#eab308` medium · `#64748b` low | Finding chips |
| Status semantics | `#34d399` ok · `#fbbf24` warn · `#ef4444` error | Health chip, receipts |
| UI font | **Inter** (variable, with feature settings cv11/ss03/ss01) | All prose |
| Mono font | **IBM Plex Mono** | IDs, locators, code, data |

**No mascot.** The QUILL wordmark is paired with a minimal gradient logomark
(rounded square + corner accent). Dark-mode-only by design; reduced-motion
honored.

## 2. Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  ▢ QUILL                                          [chip] Acting as ▼ │  ← Top bar (56px)
├──────────────┬──────────────────────────────────────────────────────┤
│              │                                                      │
│  Upload      │  Source narrative          │  Findings                │
│  Artifacts   │  ┌──────────────────────┐  │  ┌─ AC-2 · HIGH ─────┐  │
│  Current run │  │                      │  │  │ insufficient_…    │  │
│              │  │ ...highlighted span  │  │  │ recommendation    │  │
│              │  │                      │  │  └───────────────────┘  │
│              │  │                      │  │                          │
│              │  └──────────────────────┘  │  ┌─ Attestation drawer ┐ │
│              │                            │  │ approve / edit / …  │ │
│              │                            │  └─────────────────────┘ │
└──────────────┴──────────────────────────────────────────────────────┘
│  QUILL does not make the authorization decision.       env meta      │
└─────────────────────────────────────────────────────────────────────┘
```

Sidebar is 280px, fixed; workspace is a 1.3 : 1 split (source slightly wider).
The attestation drawer lives at the bottom of the findings pane — only visible
when a finding is selected.

## 3. Screens

### 3.1 Top bar
- **Brand:** gradient mark + "QUILL" wordmark + tagline "RMF pre-adjudication — humans decide."
- **Health chip:** `air-gap · breaker 3 · Tier 0/1` (turns green when /health succeeds; red banner appears if unreachable).
- **Role picker:** "Acting as Engineer/Attester/Viewer/Admin." (Production swaps in real JWT identity.)

### 3.2 Sidebar
- **Upload:** click-to-pick file drop with dashed border; filename shows once selected; primary "Ingest artifact" button.
- **Artifacts:** mono-font list with type + status. Active item gets a primary-border highlight.
- **Current run:** appears after analyze. Shows run id, status, tier path, breaker chip if tripped, and three export buttons (Report · POA&M · Audit).

### 3.3 Source narrative pane (FR-UI-02 — the critical screen)
- Renders the full normalized artifact text in mono font with proper line height.
- Selecting a finding **highlights the exact quoted span** in primary-blue with a slight underline. Active spans get a stronger highlight and scroll into view.
- Empty state: explanatory placeholder.

### 3.4 Findings pane
- Each finding is a self-contained card with:
  - **Control id** (mono, bold)
  - **Severity chip** (critical/high/medium/low)
  - **Status pill** (unattested/approved/edited/rejected/flag_for_review)
  - **Finding type** (muted)
  - **Confidence bar** + numeric percent
  - **Recommendation** (primary text)
  - **Source pointer** (mono, dim)
- Empty state: "No deficiencies detected."

### 3.5 Attestation drawer (FR-ATT-01..06)
- Slides up from the bottom of the findings pane when a finding is selected.
- Shows the finding's rationale + a multi-line note field.
- Three buttons: **Approve** (primary) · **Edit & approve** (ghost) · **Reject** (danger).
- After signing: a mono receipt — `provenance · pr-…  scheme · …  key id · …  signed at · …`.
- Already-terminal findings show "This finding is already approved/edited/rejected. Re-attestation is not allowed."

### 3.6 Exports
- Three downloads from the run card: signed Markdown report, OSCAL POA&M JSON, integrity-verifiable audit artifact JSON.
- The signature scheme is shown on the export response so production can verify `scheme="gpg"` before distribution.

## 4. Component vocabulary
- `chip` — small pill for status. `.ok` `.warn` `.error` variants.
- `sev` — uppercase mono severity badge with colored border. `.critical` `.high` `.medium` `.low`.
- `status-pill` — uppercase mono lifecycle badge. `.approved` `.edited` `.rejected` `.flag_for_review`.
- `conf-bar` + `conf-num` — visual + numeric confidence pair.
- `pane` / `pane-header` / `pane-body` — workspace primitives.
- `attest-drawer` — bottom-anchored panel.
- `attest-receipt` — mono signing receipt; `.ok` (green border) / `.err` (red).

## 5. Microcopy principles (unchanged)
- QUILL **finds and explains**; humans **decide**.
- Never use "authorize," "approve system," "pass/fail ATO."
- Use "approve finding," "evidence insufficient," "flagged for review."

## 6. Accessibility (unchanged)
- WCAG 2.1 AA contrast (the new palette passes; verified with the
  enterprise blue on the dark gradient).
- Full keyboard navigation; visible focus rings on every actionable element.
- Honors `prefers-reduced-motion`.
- Screen-reader labels on findings and spans.

## 7. Not in scope here
- Logo refinement (the current mark is a placeholder geometry; a designed
  logomark can drop into the same slot).
- Tauri desktop shell (the same HTML/JS will load inside Tauri later;
  WP-5 final).
