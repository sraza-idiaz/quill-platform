# 🎬 Investor Demo Script — QUILL

> Read this like a colleague sitting next to you. It tells you what to click, what to say, what's about to happen, and what each thing actually means for the customer's business.

**Run time:** about 12–15 minutes if you don't pause. With pauses for questions: 20–25.

**Open in your browser:**

- Local demo (full Tier-2 LLM): **http://127.0.0.1:8000/ui/** — start the server first with `scripts/quill-server up`
- Hosted demo (Tier 0+1 only, fast, no LLM cost): **https://quill-sr8l.onrender.com/ui/** — credentials in Render env vars

---

## ⚙️ One-time setup before the investor arrives

Open a terminal and run **once**:

```bash
# Copy the demo files into a clean working folder you'll have QUILL watch.
mkdir -p /tmp/acme-aerospace
cp -f /Users/muhammadshabbar/Work/quill-platform/demo/investor-demo/acme-aerospace/*.md /tmp/acme-aerospace/

# Confirm 4 files:
ls /tmp/acme-aerospace
# Expected:
#   01_System_Security_Plan.md
#   02_Architecture_Document.md
#   03_Identity_Access_Policy.md
#   04_Operations_Runbook.md
```

That's it. The folder `/tmp/acme-aerospace` is now your "team's working folder." QUILL will watch it.

---

## 🎯 The story you're telling

Frame it for the investor before you click anything:

> *"I'm going to play the role of an ISSO at an aerospace contractor. We've been asked to deliver a security package to the DLA for our new Supply Chain Risk System. I've got four documents — a system security plan, the architecture, the identity policy, and the operations runbook. In the real world, my team and I would spend three to four weeks going back and forth with DLA adjudicators. I'm going to show you what happens when QUILL sits in front of that loop."*

---

## 1️⃣ Open the dashboard (15 seconds)

Open the URL. **Just look at the top-right corner for a moment.**

You'll see:

- A green **Live** chip
- **T2 · ollama** if you're on localhost (cloud LLM is on)
- A **Role** dropdown showing `engineer`
- A **Program** dropdown showing `default`

**Say this out loud:**

> *"Notice the chips at the top. QUILL is honest about its operating mode — it tells you when artifact text might be leaving the box. In a real DLA deployment we'd flip this to air-gap mode and the LLM runs locally. For the demo, it's on so you'll see what the AI judgment looks like."*

---

## 2️⃣ Create the program (30 seconds)

This is the "tenant" — one program per customer. In a real install you'd have one per DLA program.

**Top right:** click the **+** button next to the Program dropdown.

> *Note: if the + button is grayed out, switch the Role dropdown to `admin` first — engineers can't create programs.*

A modal appears. Fill in:

- **Name:** `DLA Aerospace SBIR`
- **ID:** (auto-fills as `dla-aerospace-sbir` — leave it)
- **Baseline:** Moderate (the default)

Click **Create**. Toast pops up.

**Say:**

> *"That's our program — its own data, its own baseline, completely isolated. Phase II's multi-tenancy. We could have ten programs running concurrently and one engineer would only ever see the one they're cleared for."*

Switch the Program dropdown to **DLA Aerospace SBIR**.

---

## 3️⃣ Create a package (30 seconds)

A package is the bundle of related documents that travel together through review.

**Left sidebar:** Click **Packages**.

Click **+ New Package**.

- **Name:** `AASCRS Pre-Adjudication`
- **Description:** `Supply Chain Risk System — DLA SBIR submission`

Click **Create**.

**Say:**

> *"Real RMF reviews aren't about one document. The SSP needs to be reviewed alongside the architecture, the policies, and the runbook. A package treats them as one logical unit. When QUILL spots a contradiction between the SSP and the architecture, that's only possible because they're in the same package."*

---

## 4️⃣ Set up continuous watching — **the moment to slow down** (45 seconds)

This is the feature the investor needs to see clearly.

In the open package detail panel, click **👁 Watch folder**.

A modal appears. Paste:

```
/tmp/acme-aerospace
```

Click **Start watching**. Toast: "Now watching".

**Say slowly:**

> *"OK, so here's what just happened. QUILL is now watching that folder. The moment any file appears, changes, or disappears, QUILL re-runs the analysis automatically. The team doesn't have to do anything. They edit their SSP in the editor of their choice, save it, and within 5 seconds QUILL has updated its findings."*

> *"This is the headline feature for Phase II. The DLA solicitation explicitly asks for it — they call it 'continuous documentation improvement.' Today, an SSP edit means a 4-week wait for the next adjudication cycle. With this, it's a 4-second loop."*

---

## 5️⃣ Drop the documents in (the demo's first big moment, ~1 min)

Now in your terminal:

```bash
cp /Users/muhammadshabbar/Work/quill-platform/demo/investor-demo/acme-aerospace/*.md /tmp/acme-aerospace/
```

> If you set it up in the one-time setup step, you already did this; just say "the documents are already in the folder."

**Switch back to the browser.** Within 5 seconds (the watch poll interval) QUILL detects the change. **On localhost with Tier 2 on, analysis will take 5–10 minutes.** On the Render hosted demo, it's done in **under 2 seconds**.

> *Stress-test moment: if you're showing investors live, prefer the **Render URL** so the loop is fast. If you're showing a depth-of-AI demo, use **localhost** and tell them you'll come back to the result in a few minutes while you tour other features.*

**Refresh the package row** (click it) and you should see the "Latest analysis" panel update.

**Say:**

> *"Look at what just happened. The analyzer just walked through 287 controls that the Moderate baseline requires. It checked our four documents against every one of them. It looked for missing controls, missing required fields, contradictions between documents, inheritance claims that aren't properly attributed. All in seconds. A human adjudicator would take days to do this first pass."*

---

## 6️⃣ Open the Attestation Gate — **the most important screen** (3 minutes)

In the package detail, find one of the artifacts (say `01_System_Security_Plan.md`) and click **Open Gate** next to it (or via the Inventory sidebar).

You'll see:

- **Left:** the SSP text with paragraphs **highlighted in red/orange/yellow/grey**
- **Right:** a stack of finding cards

Click around. Click any finding card on the right. **The matching paragraph on the left lights up.**

**Say while you click:**

> *"This is what an adjudicator wants to see. QUILL doesn't just tell you 'this is wrong' — it points at the exact sentence in your document. Every finding is tied to a literal quote. So if I as the ISSO want to push back and say 'no, that's not what I meant,' I can see exactly which sentence QUILL is reacting to. No mystery."*

**Specific things to point out as you scroll the findings:**

🟥 **The AC-2 finding** — "missing required fields: review_frequency, enforcement_mechanism."

> *"In the v1 SSP I wrote, I described AC-2 in two sentences. QUILL caught that I didn't say how often accounts get reviewed, or what enforces the policy. A reviewer would have caught that — eventually. QUILL caught it in seconds."*

🟧 **The IA-2 contradiction finding** — between SSP and Architecture and Identity Policy.

> *"This one's interesting. The SSP says 'users authenticate with a username and password.' The architecture document says 'PIV smart cards are required for federal personnel.' The identity policy says the same as the architecture. QUILL caught the inconsistency between three documents. That's what would happen in week two of adjudication, after three reviewers had read the package independently and someone finally noticed."*

🟦 **The AT-2 inheritance finding** — "inheritance claim 'inherited from AWS GovCloud' is incomplete."

> *"And this is a subtle one. The SSP says 'inherited from AWS GovCloud.' But it doesn't say which authorization — FedRAMP? SOC 2? Type I or II? Which year? An adjudicator would write back asking. QUILL writes back automatically."*

🟨 **Family coherence** (if Tier 2 is on) — point to a Tier 2 finding.

> *"And these green-tagged findings are from the LLM. It read every AC-related paragraph across all four documents at once and judged whether the program described coherently across them. This is the kind of judgment that's traditionally human-only."*

---

## 7️⃣ Approve a finding — **the cryptographic moment** (90 seconds)

This is the line that matters most for the regulator.

Top-right **Role** dropdown → switch to `attester`.

> *"I'm switching roles to attester. Engineers can analyze, but only an attester can sign findings. Different roles, different powers. This is enforced server-side."*

Click any finding card. Click **Approve** at the top.

A modal-style success seal appears. Toast: "Approved · AC-2 · Signed by attester."

**Say:**

> *"That finding is now signed by me. The signature is cryptographic — it's recorded in QUILL's audit ledger with a key ID, a timestamp, and my name. If anyone — anyone, including a sysadmin — tries to quietly change that record later, the audit chain breaks. We can detect tampering."*

> *"This is the line everything is built around: **QUILL doesn't authorize anything. Humans do.** No finding becomes authoritative until a human signs it. The AI is the assistant that narrows what the human reviews — but the human still owns the decision."*

Approve **2 or 3 more findings** so the calibration chart later has data. Notice each one auto-jumps to the next unattested finding — keep the rhythm going.

---

## 8️⃣ Edit the SSP live — **the "wow" moment** (2 minutes)

This is where the investor sees continuous re-analysis in action. **Don't rush this.**

Go back to your terminal:

```bash
cp /Users/muhammadshabbar/Work/quill-platform/demo/investor-demo/edits/01_System_Security_Plan.md /tmp/acme-aerospace/
```

**Say while you type:**

> *"OK, so in real life I'd open my editor, fix the things QUILL flagged, save, and walk away. For the demo I'm just dropping in the version of the SSP where I've fixed the AC-2 narrative, attributed the inheritance claim properly, and made the authentication posture consistent across documents."*

Switch back to the browser. **Wait 30–60 seconds** (or 5–10 minutes on localhost with Tier 2). Click on the package row to refresh the detail drawer.

You'll see the **"Since last analysis"** badges update with something like:

- **3 new** (something I broke while fixing other things)
- **5 resolved** ✅ (the things QUILL re-detects as fixed)
- **0 stale** (none of my signed findings have moved)
- **42 unchanged** (most paragraphs untouched, attestations carry forward)

**Say while pointing at the badges:**

> *"This is the moment. Look at the 'resolved' badge — those are findings I fixed by improving the document. QUILL re-analyzed and confirmed they're gone. Look at the 'unchanged' badge — those are paragraphs I didn't touch, and the findings on them keep their previous attestation. I didn't have to re-sign anything I'd already signed."*

> *"That's the loop the DLA cares about. If every edit invalidated every attestation, the team would stop using QUILL by week two. Instead, the human signatures persist on unchanged work, and only the actually-different stuff needs a fresh look."*

---

## 9️⃣ Export deliverables — **show the receipts** (90 seconds)

In the package detail, click **⬇ Export**. A modal lists three options.

**For each one, before clicking, say what it is:**

**Option 1 — Stakeholder PDF**

> *"This is the document I'd send my CTO. One PDF, severity histogram, top issues, a conservative estimate of engineer-hours saved by catching these up front. Management language. Notice what it does not contain: anywhere the words 'approved' or 'authorized.' QUILL doesn't make that decision."*

Pick option 1, click **Download**. The PDF lands. Open it briefly, scroll.

> *"Two pages. Clean. Investor-grade."*

Click **⬇ Export** again, pick **OSCAL bundle**.

> *"And this — this is what gets uploaded to eMASS. eMASS is DoD's authoritative compliance system of record. It speaks OSCAL, the NIST-standard machine-readable format. So while my colleagues are passing the PDF around in Slack, the OSCAL bundle goes straight into the system of record. That bidirectional flow is what makes QUILL a connector, not a silo."*

The JSON file downloads. You don't need to open it — just hold it up.

---

## 🔟 AI Calibration — **the trust slide** (60 seconds)

Left sidebar: **AI Calibration**.

You'll see a reliability curve, an ECE number, and a Phase-II gate (pass/fail) badge.

**Say:**

> *"Last one. This is how we earn the right to call our AI confidence scores meaningful."*

> *"When QUILL says 'I'm 85% confident this is a finding,' you should be able to ask: is that actually true? Of all the findings the model claimed 85% confidence on, were 85% of them confirmed by a human attester? That's calibration."*

> *"We measure it. Every release. If the ECE — expected calibration error — exceeds 0.20, the release doesn't ship. Right now this chart is mostly empty because we only attested 2–3 findings together, but as your team uses it, it fills in. And the curve becomes the answer to 'why should I trust this number?'"*

---

## 1️⃣1️⃣ Audit Trail — **the closer** (30 seconds)

Left sidebar: **Audit Trail Ledger**.

You'll see every action you took just now, in order, with timestamps and your name on it.

At the top: **"Chain valid: yes"** ✅

**Say:**

> *"And finally, here's the receipt drawer. Every single thing we did — uploads, analysis, attestations, watches, exports — is in this ledger. The chain is hash-linked. If anyone tampers with an old record, this turns red and says 'chain invalid.'"*

> *"For a regulator, this is the proof that the review happened, when it happened, who signed what. It's the bottom of the audit pyramid every other compliance artifact rests on."*

---

## 🎤 Closing line

Look up from the screen.

> *"What you just saw is one program, four documents, a working pre-adjudication cycle in under fifteen minutes. The same flow that takes a typical DLA RMF cycle weeks. We can run dozens of programs concurrently. The exports plug into eMASS and Xacta. The AI is measured, not just claimed. And every signature is auditable."*

> *"What questions can I answer?"*

---

## 🪪 If they ask "how do I add a new document?" — show them

Drop another file into `/tmp/acme-aerospace/`, anything: a fake "incident response plan."

```bash
cat > /tmp/acme-aerospace/05_Incident_Response_Plan.md <<'EOF'
# AASCRS Incident Response Plan

This document describes how Acme responds to security incidents on the
AASCRS system. The incident response team is led by the ISSO and includes
the operations lead and the on-call SOC analyst.

Incidents are categorized as Critical, High, Medium, or Low based on
business impact and active threat indicators. Critical and High incidents
trigger immediate escalation to the CISO and AO.
EOF
```

Within 5 seconds the watcher detects the new file, the package re-analyzes, and the package detail shows a new finding count.

**Say:**

> *"Adding a document is the same gesture as editing one. The watcher doesn't care whether you added, removed, or edited. It just notices the folder changed and re-runs the analysis. That's the loop."*

---

## 🪪 If they ask "what if I want to remove a document?"

Just delete the file:

```bash
rm /tmp/acme-aerospace/05_Incident_Response_Plan.md
```

The watcher detects the removal, re-analyzes the package, and the package detail updates to reflect the smaller member set. Any findings derived from the removed document automatically go away.

---

## 🪪 If they ask about scale / performance

> *"In this demo we ran on a single cheap server. The pipeline is stateless — every analyzer worker is independent. We've measured: a single mid-tier Render box handles ~50 concurrent analyses without queuing. The bottleneck is the LLM, not QUILL. Real DLA deployments would run a local Mistral 24B model on a single A10 GPU — that's about a $400/month cloud spend, or one $5K box on-prem."*

---

## 🪪 If they ask about security clearances / CUI

> *"QUILL was built CUI-first. The cloud LLM mode you're seeing is for the demo. In a real install we flip the air-gap toggle, the local LLM runs on the same box as the data, and there are no outbound calls with artifact content. Zero egress. Verified in the chaos tests."*

---

## 🪪 If they ask about competitors

> *"There are three categories. The big one is RegScale / Telos Xacta — those are the system of record. They store the SSP, they store the POA&M. They don't analyze; they're a filing cabinet."*

> *"Second category is GRC platforms like ServiceNow GRC. They do workflow but they don't read the documents. They don't catch missing fields or cross-doc contradictions."*

> *"Third category — emerging — is AI assistants like StackArmor's. They're closer to us but they're agent-style chatbots. We're API-first, citation-validated, calibrated. We give you the receipt; they give you a conversation."*

---

## 🛟 If something breaks live

- **The browser shows "BACKEND UNREACHABLE"** → run `scripts/quill-server status` in another terminal. If down: `scripts/quill-server restart`.
- **The watcher isn't picking up changes** → click the package row to manually trigger a poll, or hit `POST /packages/{id}/watch/poll` via curl.
- **The LLM is hanging too long on localhost** → fall back to the Render URL for the demo. Same code, no LLM, sub-second response.
- **Authentication issues** → reset role with `Role: attester` for signing, `Role: engineer` for analysis, `Role: admin` for program creation.

---

## 🔁 To reset the demo for the next investor

```bash
# Wipe and recopy the v1 documents so weak narratives are back
rm -rf /tmp/acme-aerospace
mkdir -p /tmp/acme-aerospace
cp /Users/muhammadshabbar/Work/quill-platform/demo/investor-demo/acme-aerospace/*.md /tmp/acme-aerospace/

# Restart the server so the in-memory store is clear
scripts/quill-server restart
```

Open a fresh browser tab. You're ready for the next pitch.

---

Good luck. The whole thing fits in 15 minutes if you stay disciplined. Let the badges and the audit chain do the work — your job is to narrate, not to demonstrate clicks.
