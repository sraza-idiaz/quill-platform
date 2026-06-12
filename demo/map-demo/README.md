# Map Demo — purpose-built for the Cross-Document Map view

These four short documents are designed to make the **🗺 Map** feature
show its full vocabulary in one screen:

- **3 coral contradiction lines** (active disagreements)
- **6 grey shared-control lines** (every pair shares ≥1 control)
- **3 green dashed resolved lines** after you drop the v2 SSP in

The docs are short on purpose so analysis runs fast (4 files × short
narratives × ~6 min Tier 2 = manageable demo time).

---

## The three planted contradictions

Tier 0's cross-document consistency check is **frequency-based** — it
canonicalizes phrases like "quarterly" ↔ "every 90 days" and flags the
same control mentioned with **different normalized frequency values
across artifacts**. So the three planted conflicts are all frequency
mismatches:

| Control | Conflict | Document pair |
|---|---|---|
| **AC-2** | review cadence | SSP says monthly · Identity Policy says quarterly |
| **AU-11** | log retention | SSP says 90 days · Operations Runbook says 365 days |
| **AT-2** | training cadence | SSP says annually · Identity Policy says quarterly |

(Authentication-mode conflicts like password-vs-PIV won't fire from
Tier 0 alone — they need Tier 2's family-coherence judgment. The
documents are styled realistically but only frequency-style conflicts
are reliable demo material on this rule.)

## The four documents in v1/

| File | What it is | Contains... |
|---|---|---|
| `01_System_Security_Plan.md` | The SSP under review | The three "weak" sides of the planted conflicts |
| `02_Architecture_Document.md` | System architecture | Compatible narratives + shared controls (gives a 4th node) |
| `03_Identity_Access_Policy.md` | Account governance | Quarterly AC-2 review, quarterly AT-2 training (the conflicting side) |
| `04_Operations_Runbook.md` | Operations procedures | 365-day AU-11 retention (the conflicting side) |

What you should see on the Map after the first analysis:

```
                Architecture           Operations Runbook
                   │                          │
                   │  grey                    │  grey
                   │                          │  coral⚠ AU-11
                   ├──────── SSP ─────────────┤
                   │         │ │
                   │  grey   │ │  coral⚠ AC-2
                   │         │ │  coral⚠ AT-2
                   │     Identity Policy
```

- 4 nodes (one per document)
- 3 coral solid lines (verified to fire on Tier 0 alone, no LLM needed):
  - SSP ↔ Identity Policy on **AC-2** (monthly vs quarterly)
  - SSP ↔ Identity Policy on **AT-2** (annually vs quarterly) — yes, two
    coral edges between the same pair of docs; they visually stack
  - SSP ↔ Operations Runbook on **AU-11** (90 days vs annually)
- 6 grey thin lines (every pair shares at least one control)
- 0 green dashed yet (no prior version exists)

After dropping `v2/01_System_Security_Plan.md` over the v1 SSP and
re-analyzing, all 3 coral lines turn into **green dashed ✓ resolved**
edges. Verified end-to-end.

---

## The v2/ folder

`v2/01_System_Security_Plan.md` is the *fixed* SSP. It updates the IA-2,
AC-2, and AU-11 narratives so they agree with the supporting docs. When
you drop this over the v1 SSP and re-analyze:

- **All 3 coral lines turn into green dashed ✓** ("resolved since last run")
- 6 grey lines stay
- Diff chips on the package detail show those 3 as "resolved"

---

## 60-second setup (copy-paste)

**Step 1 — make an empty folder** (order matters: empty *first*, so the
watcher's first-poll fingerprint is empty, so the first file drop fires
an event):

```bash
rm -rf /tmp/map-demo && mkdir -p /tmp/map-demo
```

**Step 2 — in the UI**, set up the package and start watching:

1. **Packages** → **+ New package** → name it `Map Demo`
2. Click the new row → **👁 Watch folder** → paste `/tmp/map-demo`

**Step 3 — drop the v1 files into the watched folder**:

```bash
cp /Users/muhammadshabbar/Work/quill-platform/demo/map-demo/v1/*.md /tmp/map-demo/
```

Within ~5 seconds the watcher fires, ingests the 4 files, and kicks off
analysis. Wait ~5–6 minutes for Tier 2 to finish (good time for a coffee
or to walk through the architecture).

**Step 4 — open the Map**:

Click **🗺 Map** on the package detail. You should see:
- 4 cards (one per document)
- 3 coral solid lines (the planted contradictions)
- 6 grey thin lines (every pair shares ≥1 control)

**Step 5 — click any coral line.** The drawer shows both quoted passages
side by side. *That's the demo's punchline.*

---

## The "what got fixed" moment (the green dashed lines)

After step 5 above, run this in a terminal:

```bash
cp /Users/muhammadshabbar/Work/quill-platform/demo/map-demo/v2/01_System_Security_Plan.md /tmp/map-demo/
```

Within 5 seconds the watcher detects the change and re-analyzes. Wait
again, then re-open the Map.

- The 3 coral lines are now **green dashed ✓**
- Click any of them — the drawer shows "Resolved since version 1 — no
  longer present" with the *old* quotes

That's the cross-document equivalent of the per-finding diff badges in
the package detail panel.

---

## Resetting between demos

```bash
rm -rf /tmp/map-demo
# Then re-run the 60-second setup above
```

The in-Render version is even simpler: delete the package via the UI
and re-create it (the package detail's status menu has a Delete option
in `archived` state).

---

## Files in this folder

```
demo/map-demo/
├── README.md                                     ← you are here
├── v1/                                            ← initial state
│   ├── 01_System_Security_Plan.md
│   ├── 02_Architecture_Document.md
│   ├── 03_Identity_Access_Policy.md
│   └── 04_Operations_Runbook.md
└── v2/                                            ← drop-in over the SSP
    └── 01_System_Security_Plan.md
```
