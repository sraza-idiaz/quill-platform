# 📇 Demo Cheat Sheet — pin on second monitor

## Before the demo

```bash
mkdir -p /tmp/acme-aerospace
cp -f /Users/muhammadshabbar/Work/quill-platform/demo/investor-demo/acme-aerospace/*.md /tmp/acme-aerospace/
scripts/quill-server up        # for full localhost demo with Tier 2
```

URL: `http://127.0.0.1:8000/ui/` (local) or `https://quill-sr8l.onrender.com/ui/` (Render)

---

## The 11 beats — keep this rhythm

| # | Beat | What you click | Time |
|---|---|---|---|
| 1 | Read the chips | Just look at top right | 15s |
| 2 | Create program | + button → "DLA Aerospace SBIR" | 30s |
| 3 | Create package | Packages → + New → "AASCRS Pre-Adjudication" | 30s |
| 4 | Start watching | 👁 Watch folder → `/tmp/acme-aerospace` | 45s |
| 5 | Drop docs in | (already in folder from setup) | 1 min |
| 6 | Open Gate | Click "Open Gate" on SSP row | 3 min |
| 7 | Approve a finding | Role→attester, click Approve on 2–3 | 90s |
| 8 | Edit the SSP | `cp demo/investor-demo/edits/01_*.md /tmp/acme-aerospace/` | 2 min |
| 9 | Export deliverables | ⬇ Export → try all 3 | 90s |
| 10 | AI Calibration | Sidebar → AI Calibration | 60s |
| 11 | Audit Trail | Sidebar → Audit Trail Ledger | 30s |

**Total:** ~15 minutes

---

## The 3 one-liners that sell it

After step 4 (watcher):
> "4-week loop → 4-second loop."

After step 7 (attest):
> "QUILL doesn't authorize. Humans do. Nothing is real until a human signs it."

After step 8 (edit):
> "Findings I already signed stay signed. Only the changed paragraphs need a fresh look."

---

## When to switch role

| Action | Required role |
|---|---|
| Create program | admin |
| Upload + Analyze | engineer |
| Attest findings | attester |
| Export | engineer / admin |

---

## Live edit commands (paste during demo)

**Add a new document:**
```bash
cp /Users/muhammadshabbar/Work/quill-platform/demo/investor-demo/edits/01_System_Security_Plan.md /tmp/acme-aerospace/
```

**Add a brand-new document for "what if I want to add one":**
```bash
echo "# New incident response plan" > /tmp/acme-aerospace/05_Incident_Response_Plan.md
```

**Remove a document:**
```bash
rm /tmp/acme-aerospace/05_Incident_Response_Plan.md
```

---

## Reset between investors

```bash
rm -rf /tmp/acme-aerospace
mkdir -p /tmp/acme-aerospace
cp /Users/muhammadshabbar/Work/quill-platform/demo/investor-demo/acme-aerospace/*.md /tmp/acme-aerospace/
scripts/quill-server restart
```

---

## If something breaks

- "Backend unreachable" → `scripts/quill-server restart`
- Watcher not firing → click the package row to refresh
- LLM hanging → switch to Render URL (Tier 0+1 only, sub-second)
