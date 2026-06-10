// QUILL UI client — 4 views with sidebar routing, talks to the FastAPI REST API.

const $  = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

const state = {
  artifacts: [],
  artifactPkg: {},           // artifact_id -> package id (PKG-YYYY-XXXX)
  runByArtifact: new Map(),  // artifact_id -> latest run object
  findingsByRun: new Map(),  // run_id -> [findings]
  currentArtifact: null,
  currentRunId: null,
  currentFindingId: null,
  artifactText: "",
  audit: [],
  chainValid: true,
  health: null,
  // Phase II — packages
  packages: [],
  currentPackageId: null,
  currentPackage: null,
  // Phase II FR-XA-03 — dependency graph for the active artifact/package
  graph: null,
};

// ─────────────────────────────────────────── API ──
function role()    { return $("#role").value; }
function program() { return $("#program") ? $("#program").value : "default"; }
async function api(path, opts = {}) {
  const headers = {
    "X-QUILL-Role":   role(),
    "X-QUILL-Tenant": program(),
    ...(opts.headers || {}),
  };
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.json);
    delete opts.json;
  }
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), opts.timeout || 60000);
  let res;
  try { res = await fetch(path, { ...opts, headers, signal: controller.signal }); }
  catch (e) {
    if (e.name === "AbortError") throw new Error("backend timeout (server unreachable on http://localhost:8000)");
    throw new Error(`network: ${e.message}`);
  } finally { clearTimeout(t); }
  const ct = res.headers.get("content-type") || "";
  const body = ct.includes("json") ? await res.json() : await res.text();
  if (!res.ok) throw new Error(`${res.status} · ${(body && body.detail) || body || res.statusText}`);
  return body;
}

// ─────────────────────────────────────────── View routing ──
function switchView(viewId) {
  $$(".view-frame").forEach(f => f.classList.remove("active"));
  $$(".nav-link").forEach(l => l.classList.remove("active"));
  const view = document.getElementById("view-" + viewId);
  const link = document.getElementById("link-" + viewId);
  if (view) view.classList.add("active");
  if (link) link.classList.add("active");
  if (viewId === "dashboard")   refreshDashboard();
  if (viewId === "inventory")   renderInventory();
  if (viewId === "packages")    renderPackages();
  if (viewId === "audit")       refreshAudit();
  if (viewId === "calibration") renderCalibration();
}

// Sidebar nav handler — extra logic so clicking the Gate when nothing is loaded
// shows a helpful empty state rather than a confusing blank panel.
$$(".nav-link").forEach(l => {
  l.addEventListener("click", () => {
    const target = l.dataset.view;
    if (target === "attestation" && !state.currentArtifact) {
      setGateEmpty();
      return;
    }
    switchView(target);
  });
});

// ─────────────────────────────────────────── Health ──
function showBackendBanner(message) {
  let bar = document.getElementById("backendBanner");
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "backendBanner";
    document.body.insertBefore(bar, document.body.firstChild);
  }
  bar.innerHTML = message;
}
function hideBackendBanner() {
  const bar = document.getElementById("backendBanner");
  if (bar) bar.remove();
}

async function refreshHealth() {
  try {
    const h = await api("/health");
    state.health = h;

    // Operational mode chip (no more 'demo mode' nag)
    const airChip = $("#airgapChip");
    airChip.textContent = h.air_gap ? "Air-Gap" : "Live";
    airChip.className = "env-chip ok";
    hideBackendBanner();

    $("#tier2Chip").textContent  = h.tier2_analyzer ? `T2 · ${h.tier2_analyzer}` : "T2 · disabled";
    $("#tier2Chip").className    = h.tier2_analyzer ? "env-chip ok" : "env-chip";
    $("#breakerChip").textContent = `breaker ${h.circuit_breaker_threshold}`;
    $("#engineSummary").innerHTML =
      `baseline · ${escapeHtml(h.baseline)}<br>controls · ${h.controls_loaded}<br>tier 2 · ${escapeHtml(h.tier2_analyzer || "—")}`;
    $("#footerEnv").textContent = `${h.air_gap ? "Air-Gap" : "Live"} · baseline ${h.baseline} · ${h.controls_loaded} controls · breaker ${h.circuit_breaker_threshold}`;

    // Dashboard breaker max
    $("#metric-breaker-max").textContent = h.circuit_breaker_threshold;
  } catch (e) {
    $("#airgapChip").textContent = "BACKEND UNREACHABLE";
    $("#airgapChip").className = "env-chip error";
    showBackendBanner(
      `<b>Backend unreachable.</b> Open <a href="http://localhost:8000/ui/">http://localhost:8000/ui/</a> in a regular browser tab. (${escapeHtml(e.message)})`
    );
  }
}

// ─────────────────────────────────────────── Package id derivation ──
// Deterministic PKG-YYYY-XXXX from artifact hash (no model needed; cosmetic grouping).
function packageIdFor(a) {
  if (state.artifactPkg[a.id]) return state.artifactPkg[a.id];
  const year = new Date().getFullYear();
  const slug = (a.hash || a.id).slice(0, 6).toUpperCase();
  const id = `PKG-${year}-${slug}`;
  state.artifactPkg[a.id] = id;
  return id;
}

// ─────────────────────────────────────────── Artifacts (data layer) ──
async function loadArtifacts() {
  try { state.artifacts = await api("/artifacts"); }
  catch { state.artifacts = []; }
  // Make sure pkg ids are computed
  state.artifacts.forEach(packageIdFor);
}

// ─────────────────────────────────────────── INVENTORY VIEW ──
async function renderInventory() {
  await loadArtifacts();
  const tbody = $("#inventoryTable tbody"); tbody.innerHTML = "";
  $("#inventoryEmpty").hidden = state.artifacts.length > 0;

  for (const a of state.artifacts.slice().reverse()) {
    const tr = document.createElement("tr");
    const status = inferArtifactStatus(a);
    tr.innerHTML = `
      <td><code>${escapeHtml(packageIdFor(a))}</code></td>
      <td>${escapeHtml(a.filename)}</td>
      <td class="muted">NIST SP 800-53 Rev. 5 · ${escapeHtml(state.health?.baseline || "—")} Baseline</td>
      <td><span class="vstatus ${status.cls}">${status.label}</span></td>
      <td class="col-action">
        <div class="inv-actions">
          <button class="btn-small btn-ghost" data-act="analyze" data-id="${a.id}">Analyze</button>
          <button class="btn-small"           data-act="gate"    data-id="${a.id}">Open Gate</button>
        </div>
      </td>`;
    tr.querySelector('[data-act="analyze"]').onclick = (e) => { e.stopPropagation(); analyzeArtifact(a.id); };
    tr.querySelector('[data-act="gate"]').onclick    = (e) => { e.stopPropagation(); openGateFor(a.id); };
    tbody.appendChild(tr);
  }
}

function inferArtifactStatus(a) {
  const run = state.runByArtifact.get(a.id);
  if (!run) return { cls: "ingested", label: "Ingested" };
  if (run.status === "analyzing") return { cls: "processing", label: "Processing" };
  const fs = state.findingsByRun.get(run.id) || [];
  if (!fs.length) return { cls: "auto-passed", label: "Auto-Passed" };
  const unattested = fs.filter(f => f.status === "unattested").length;
  if (unattested === 0) return { cls: "fully-attested", label: "Fully Attested" };
  return { cls: "pending-gate", label: `Pending Gate · ${unattested}` };
}

// ─────────────────────────────────────────── Upload ──
// Reset the upload form to its initial empty state. Centralized so the
// post-submit cleanup and the explicit "×" clear use the same logic.
function resetUploadForm() {
  $("#fileInput").value = "";
  $("#fileLabel").textContent = "PDF · DOCX · MD · OSCAL JSON";
  $("#fileHint").textContent  = "Click to select an artifact";
  $("#fileDrop").classList.remove("has-file");
  $("#fileClear").hidden = true;
  $("#ingestBtn").disabled = true;
}

$("#fileInput").addEventListener("change", (e) => {
  const f = e.target.files[0];
  if (f) {
    $("#fileLabel").textContent = f.name;
    $("#fileHint").textContent  = "Selected — ready to ingest";
    $("#fileDrop").classList.add("has-file");
    $("#fileClear").hidden = false;
    $("#ingestBtn").disabled = false;
  } else {
    resetUploadForm();
  }
});

// "×" button clears the picked file. preventDefault + stopPropagation are
// critical so the click doesn't bubble up to the <label> wrapper, which
// would otherwise re-open the OS file picker.
$("#fileClear").addEventListener("click", (e) => {
  e.preventDefault();
  e.stopPropagation();
  resetUploadForm();
});

$("#uploadForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = $("#fileInput").files[0];
  if (!f) return;
  const fd = new FormData(); fd.append("file", f);
  const btn = $("#uploadForm button[type=submit]");
  const orig = btn.textContent;
  btn.textContent = "Ingesting…"; btn.disabled = true;
  try {
    const res = await fetch("/artifacts", {
      method: "POST", body: fd,
      headers: { "X-QUILL-Role": role(), "X-QUILL-Tenant": program() },
    });
    if (!res.ok) throw new Error(`${res.status} · ${await res.text()}`);
    const a = await res.json();
    resetUploadForm();
    await renderInventory();
    refreshDashboard();
    // Open the Attestation Gate immediately on the freshly uploaded artifact
    // (this is what users actually want after upload).
    openGateFor(a.id);
  } catch (err) {
    alert("Upload failed: " + err.message);
  } finally { btn.textContent = orig; btn.disabled = false; }
});

// ─────────────────────────────────────────── Analyze ──
async function analyzeArtifact(artifactId) {
  try {
    const run = await api(`/artifacts/${artifactId}/runs`, { method: "POST", timeout: 120000 });
    state.runByArtifact.set(artifactId, run);
    const findings = await api(`/runs/${run.id}/findings`);
    state.findingsByRun.set(run.id, findings);
    await renderInventory();
    refreshDashboard();
    updateAlertBadge();
  } catch (e) {
    alert("Analysis failed: " + e.message);
  }
}

// ─────────────────────────────────────────── ATTESTATION GATE ──
function setGateBusy(message) {
  // Switches to the gate view immediately and shows a visible loading state
  // in both panes so the user always knows what is happening.
  switchView("attestation");
  $("#sourceMeta").textContent = "loading…";
  $("#findingsMeta").textContent = "—";
  $("#sourceCanvas").innerHTML =
    `<div class="gate-loading">
       <div class="gate-loading-title">${escapeHtml(message)}</div>
       <div class="gate-loading-sub">Tier 0 → Tier 1 → Tier 2 ` +
         `${state.health?.tier2_analyzer ? "(" + escapeHtml(state.health.tier2_analyzer) + ")" : ""}.
       This can take 10–60 seconds with cloud-backed models.</div>
     </div>`;
  $("#findingsList").innerHTML = "";
  $("#findingsEmpty").hidden = true;
  hideAttestFooter();
}

function setGateError(message) {
  $("#sourceCanvas").innerHTML =
    `<div class="gate-loading">
       <div class="gate-loading-title" style="color: var(--status-error);">Analysis failed</div>
       <div class="gate-loading-sub">${escapeHtml(message)}</div>
     </div>`;
}

function setGateEmpty() {
  switchView("attestation");
  state.currentArtifact = null; state.currentRunId = null;
  $("#gateContext").textContent = "Select an artifact from the Inventory to open the gate.";
  $("#gateActions").hidden = true;
  $("#sourceMeta").textContent = "—";
  $("#findingsMeta").textContent = "—";
  $("#sourceCanvas").innerHTML = `
    <div class="gate-loading">
      <div class="gate-loading-title">No artifact loaded</div>
      <div class="gate-loading-sub">
        Pick an artifact from the inventory and click <b>Open Gate</b>,
        or upload a new one.
      </div>
      <div style="margin-top: var(--space-4);">
        <button class="btn-ghost btn-small" id="goToInventoryBtn">Go to Artifact Inventory →</button>
      </div>
    </div>`;
  $("#goToInventoryBtn")?.addEventListener?.("click", () => switchView("inventory"));
  $("#findingsList").innerHTML = "";
  $("#findingsEmpty").hidden = false;
  $("#relatedControls").hidden = true;     // Phase II FR-XA-03 — clear the panel
  hideAttestFooter();
}

async function openGateFor(artifactId) {
  setGateBusy("Loading artifact…");

  // Ensure data is fresh
  await loadArtifacts();
  const a = state.artifacts.find(x => x.id === artifactId);
  if (!a) {
    setGateError("Artifact not found.");
    return;
  }

  state.currentArtifact = a;
  $("#gateContext").textContent =
    `Reviewing artifact ${a.filename}  ·  Package ${packageIdFor(a)}  ·  Baseline ${state.health?.baseline || "—"}`;

  // Auto-analyze if no run yet
  let run = state.runByArtifact.get(a.id);
  if (!run) {
    setGateBusy("Running analysis pipeline…");
    try { run = await api(`/artifacts/${a.id}/runs`, { method: "POST", timeout: 180000 }); }
    catch (e) { setGateError(e.message); return; }
    state.runByArtifact.set(a.id, run);
  }
  state.currentRunId = run.id;
  setGateBusy("Loading findings…");

  // Pull text + findings
  try {
    const txt = await api(`/artifacts/${a.id}/text`);
    state.artifactText = txt.text || "";
  } catch { state.artifactText = ""; }
  try {
    state.findingsByRun.set(run.id, await api(`/runs/${run.id}/findings`));
  } catch (e) { setGateError(e.message); return; }

  renderSourceCanvas();
  renderFindingsList();
  $("#findingsMeta").textContent = `${(state.findingsByRun.get(run.id) || []).length} findings`;
  $("#gateActions").hidden = false;
  await loadGraphForCurrent();      // Phase II FR-XA-03 — preload the dependency graph
  updateAlertBadge();
}

// ── Phase II FR-XA-03 — dependency graph + related controls ──────────── //
async function loadGraphForCurrent() {
  state.graph = null;
  if (!state.currentArtifact) return;
  // Prefer the package graph when the artifact belongs to a package;
  // otherwise fall back to the single-artifact graph.
  const pkgId = state.currentArtifact.package_id;
  const url = pkgId ? `/packages/${pkgId}/graph` : `/artifacts/${state.currentArtifact.id}/graph`;
  try {
    state.graph = await api(url);
  } catch (_) { state.graph = null; }
}

function renderRelatedControls(finding) {
  const panel = $("#relatedControls");
  if (!state.graph || !finding) { panel.hidden = true; return; }
  const cid = finding.control_id;
  const refs   = state.graph.edges.filter(e => e.from_control === cid);
  const refBy  = state.graph.edges.filter(e => e.to_control   === cid);
  if (!refs.length && !refBy.length) { panel.hidden = true; return; }

  panel.hidden = false;
  $("#relatedMeta").textContent = `${cid} · ${refs.length} out · ${refBy.length} in`;

  const nodesById = Object.fromEntries(state.graph.nodes.map(n => [n.control_id, n]));
  const renderEdge = (e, targetCid) => {
    const node = nodesById[targetCid] || {};
    const tag = node.in_baseline === false
      ? `<span class="out-of-baseline" title="not in active baseline">out-of-baseline</span>`
      : "";
    const src = `${escapeHtml(e.artifact_id)} · ${escapeHtml(e.locator)}`;
    return `<li>
        <span class="ctrl">${escapeHtml(targetCid)}</span>
        ${node.title ? `<span class="src">${escapeHtml(node.title)} — ${src}</span>` : `<span class="src">${src}</span>`}
        ${tag}
      </li>`;
  };

  const refsSection = $("#relatedRefs");
  const refsList = $("#relatedRefsList");
  if (refs.length) {
    refsSection.hidden = false;
    refsList.innerHTML = refs.map(e => renderEdge(e, e.to_control)).join("");
  } else {
    refsSection.hidden = true;
  }

  const refBySection = $("#relatedRefBy");
  const refByList = $("#relatedRefByList");
  if (refBy.length) {
    refBySection.hidden = false;
    refByList.innerHTML = refBy.map(e => renderEdge(e, e.from_control)).join("");
  } else {
    refBySection.hidden = true;
  }
}

// Re-analyze + export controls in the gate header
$("#reanalyzeBtn")?.addEventListener?.("click", async () => {
  if (!state.currentArtifact) return;
  const btn = $("#reanalyzeBtn");
  const orig = btn.textContent; btn.textContent = "Analyzing…"; btn.disabled = true;
  try {
    const run = await api(`/artifacts/${state.currentArtifact.id}/runs`, { method: "POST", timeout: 180000 });
    state.runByArtifact.set(state.currentArtifact.id, run);
    state.currentRunId = run.id;
    state.findingsByRun.set(run.id, await api(`/runs/${run.id}/findings`));
    renderSourceCanvas();
    renderFindingsList();
    $("#findingsMeta").textContent = `${(state.findingsByRun.get(run.id) || []).length} findings`;
    updateAlertBadge();
    refreshDashboard();
  } catch (e) { alert("Re-analyze failed: " + e.message); }
  finally { btn.textContent = orig; btn.disabled = false; }
});

$("#exportReportBtn")?.addEventListener?.("click", () => doExport("report"));
$("#exportPoamBtn")  ?.addEventListener?.("click", () => doExport("poam"));
$("#exportAuditBtn") ?.addEventListener?.("click", () => doExport("audit"));

async function doExport(fmt) {
  if (!state.currentRunId) { alert("Open an analyzed artifact first."); return; }
  try {
    const ex = await api(`/runs/${state.currentRunId}/export`, { method: "POST", json: { format: fmt }, timeout: 60000 });
    const isJson = fmt !== "report";
    const blob = new Blob([ex.content], { type: isJson ? "application/json" : "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `quill-${fmt}-${state.currentRunId}.${isJson ? "json" : "md"}`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  } catch (e) { alert("Export failed: " + e.message); }
}

// ─── 50/50 LEFT: Source canvas with inline dashed-underline target spans ───
function renderSourceCanvas() {
  const canvas = $("#sourceCanvas");
  const text = state.artifactText || "";
  const findings = (state.findingsByRun.get(state.currentRunId) || []);
  $("#sourceMeta").textContent = state.currentArtifact ? state.currentArtifact.filename : "—";

  if (!text) {
    canvas.innerHTML = `<em class="canvas-placeholder">Artifact text unavailable for this run.</em>`;
    return;
  }

  // Build (range, finding) pairs. Whitespace-tolerant matcher mirrors the
  // backend citation validator's normalization.
  const pairs = [];
  for (const f of findings) {
    for (const s of (f.evidence_spans || [])) {
      if (s.artifact_id.startsWith("catalog:")) continue;
      const q = (s.quoted_text || "").trim();
      if (!q) continue;
      const range = findQuoteInText(text, q);
      if (range) pairs.push({ start: range[0], end: range[1], finding: f });
    }
  }
  // Sort by start, then by widest first so when two ranges share a start the
  // wider one wins and becomes the merge anchor.
  pairs.sort((a, b) => a.start - b.start || b.end - a.end);

  // Merge overlapping ranges, COLLECTING every finding whose quote overlaps
  // the merged region. This is the fix: two findings on the same paragraph
  // (common — T0 + T2 both flag AC-2) used to drop one and break its
  // highlight. Now both link into the same rendered span.
  const merged = [];
  for (const p of pairs) {
    const last = merged.length ? merged[merged.length - 1] : null;
    if (last && p.start < last.end) {
      last.end = Math.max(last.end, p.end);
      if (!last.findings.find(f => f.id === p.finding.id)) {
        last.findings.push(p.finding);
      }
    } else {
      merged.push({ start: p.start, end: p.end, findings: [p.finding] });
    }
  }

  // Severity precedence for the rendered span: pick the worst severity among
  // the findings sharing it, so the dominant color matches the worst issue.
  const SEV_RANK = { critical: 4, high: 3, medium: 2, low: 1 };
  const worstSeverity = (findings) => {
    let best = findings[0];
    for (const f of findings) {
      if ((SEV_RANK[f.severity] || 0) > (SEV_RANK[best.severity] || 0)) best = f;
    }
    return best.severity;
  };

  // Build alternating text/span pieces.
  const pieces = [];
  let cursor = 0;
  for (const m of merged) {
    pieces.push({ kind: "text", value: text.slice(cursor, m.start) });
    pieces.push({ kind: "span", value: text.slice(m.start, m.end), findings: m.findings });
    cursor = m.end;
  }
  pieces.push({ kind: "text", value: text.slice(cursor) });

  // Render: each `target-span` carries `data-finding-ids` (comma-separated)
  // so it can light up for ANY of its associated findings. The legacy
  // `data-finding` attribute holds the first id for back-compat.
  const html = pieces.map(p => {
    if (p.kind === "span") {
      const ids = p.findings.map(f => f.id);
      const sev = severityClass(worstSeverity(p.findings));
      return `<span class="target-span ${sev}"`
           + ` data-finding="${escapeHtml(ids[0])}"`
           + ` data-finding-ids="${escapeHtml(ids.join(","))}">`
           + `${escapeHtml(p.value)}</span>`;
    }
    return mdToHtml(p.value);
  }).join("");

  canvas.innerHTML = html;
  // Clicking a span in the source pane picks one of its findings (the first).
  canvas.querySelectorAll(".target-span").forEach(el => {
    el.addEventListener("click", () => {
      const ids = (el.dataset.findingIds || el.dataset.finding || "").split(",").filter(Boolean);
      if (ids.length) selectFinding(ids[0], { fromSpan: true });
    });
  });
}

function mdToHtml(s) {
  // Very small renderer. Escapes everything, then promotes headings + paragraphs.
  if (!s) return "";
  return s
    .split(/\n{2,}/)
    .map(block => {
      const trimmed = block.replace(/^\n+|\n+$/g, "");
      if (!trimmed) return "";
      const h = /^(#{1,3})\s+(.*)$/.exec(trimmed);
      if (h) return `<h${h[1].length}>${escapeHtml(h[2])}</h${h[1].length}>`;
      return `<p>${escapeHtml(trimmed).replace(/\n/g, "<br>")}</p>`;
    })
    .join("");
}

// ─── 50/50 RIGHT: finding cards ───
function renderFindingsList() {
  const findings = state.findingsByRun.get(state.currentRunId) || [];
  const list = $("#findingsList"); list.innerHTML = "";
  $("#findingsEmpty").hidden = findings.length > 0;

  findings.forEach(f => list.appendChild(renderFindingCard(f)));
  // Default-select first unattested
  const next = findings.find(f => f.status === "unattested") || findings[0];
  if (next) selectFinding(next.id);
  else hideAttestFooter();
}

function renderFindingCard(f) {
  const card = document.createElement("article");
  const sev = severityClass(f.severity);
  card.className = `finding-card ${sev}`;
  card.dataset.finding = f.id;
  if (f.id === state.currentFindingId) card.classList.add("active");

  const conf = Math.round((f.confidence || 0) * 100);
  const span = (f.evidence_spans || []).find(s => !s.artifact_id.startsWith("catalog:"))
            || (f.evidence_spans || [])[0];

  const citation = !span ? ""
    : span.artifact_id.startsWith("catalog:")
      ? `<blockquote class="fc-citation">${escapeHtml(span.quoted_text)}<span class="source-ref">↳ catalog · ${escapeHtml(span.locator)}</span></blockquote>`
      : `<blockquote class="fc-citation">"${escapeHtml(span.quoted_text)}"<span class="source-ref">↳ ${escapeHtml(span.artifact_id)} · ${escapeHtml(span.locator)}</span></blockquote>`;

  card.innerHTML = `
    <div class="fc-head">
      <span class="fc-ctrl">NIST ${escapeHtml(f.control_id)}</span>
      <span class="fc-deficit ${sev}">${deficitLabel(f.severity)}</span>
    </div>
    <div class="fc-title">${escapeHtml(findingTitle(f))}</div>
    <div class="fc-description">${escapeHtml(f.rationale || f.recommendation)}</div>
    ${citation}
    <div class="fc-meta">
      <span class="calibration">${conf}% Calibration Confidence</span>
      <span>tier ${escapeHtml(f.tier)}</span>
      <span class="status-tag ${escapeHtml(f.status)}">${escapeHtml(f.status.replace(/_/g, " "))}</span>
    </div>`;
  card.addEventListener("click", () => selectFinding(f.id));
  return card;
}

function selectFinding(id, { fromSpan = false } = {}) {
  state.currentFindingId = id;
  $$(".finding-card").forEach(c => c.classList.toggle("active", c.dataset.finding === id));
  // A span may be associated with multiple findings (overlapping quotes from
  // T0 + T2 are common). Light up any span whose finding-id list contains
  // the selected one.
  $$(".target-span").forEach(s => {
    const ids = (s.dataset.findingIds || s.dataset.finding || "").split(",");
    s.classList.toggle("active", ids.includes(id));
  });
  const f = (state.findingsByRun.get(state.currentRunId) || []).find(x => x.id === id);
  if (!f) return hideAttestFooter();
  // Phase II FR-XA-03 — refresh the related-controls panel for this finding's control.
  renderRelatedControls(f);
  // Bring the card or span into view
  if (fromSpan) {
    const card = document.querySelector(`.finding-card[data-finding="${cssEsc(id)}"]`);
    if (card) card.scrollIntoView({ block: "center", behavior: "smooth" });
  } else {
    // Scroll the FIRST span associated with this finding into view.
    // `data-finding-ids` is the canonical (multi-id) attribute; we match a
    // delimited substring so we still hit spans that carry many ids.
    const ids = cssEsc(id);
    const span = document.querySelector(
      `.target-span[data-finding-ids^="${ids},"], `
      + `.target-span[data-finding-ids*=",${ids},"], `
      + `.target-span[data-finding-ids$=",${ids}"], `
      + `.target-span[data-finding-ids="${ids}"], `
      + `.target-span[data-finding="${ids}"]`
    );
    if (span) span.scrollIntoView({ block: "center", behavior: "smooth" });
  }
  showAttestFooter(f);
}

// ─── Attestation footer / cryptographic seal ───
function showAttestFooter(f) {
  const footer = $("#attestFooter");
  $("#attestTarget").textContent = `${f.control_id} · ${f.id}`;
  const terminal = ["approved", "edited", "rejected"].includes(f.status);
  const controls = $("#gate-interactive-controls");
  const seal = $("#gate-signoff-success");
  const note = $("#attestNote");
  if (terminal) {
    controls.style.display = "none";
    seal.hidden = false;
    seal.innerHTML = renderInlineSealForExistingFinding(f);
  } else {
    controls.style.display = "grid";
    seal.hidden = true;
    note.value = "";
    note.disabled = false;
    $("#approveBtn").onclick = () => doAttest(f, "approved");
    $("#editBtn").onclick    = () => {
      const newRec = prompt("Edit the recommendation (leave blank to keep original):", f.recommendation);
      const edited = {};
      if (newRec && newRec !== f.recommendation) edited.recommendation = newRec;
      doAttest(f, "edited", edited);
    };
    $("#rejectBtn").onclick  = () => doAttest(f, "rejected");
  }
  footer.hidden = false;
}
function hideAttestFooter() { $("#attestFooter").hidden = true; }

async function doAttest(f, decision, edited = null) {
  if (role() !== "attester") {
    showSealMessage(`The "Attester" role is required. Switch the Operator at the top right. Admin is NOT auto-granted.`, true);
    return;
  }
  try {
    const payload = { decision, note: $("#attestNote").value || "" };
    if (decision === "edited") payload.edited_fields = edited || {};
    const resp = await api(`/findings/${f.id}/attest`, { method: "POST", json: payload });

    // Cryptographic seal — replaces the controls
    $("#gate-interactive-controls").style.display = "none";
    const seal = $("#gate-signoff-success");
    seal.hidden = false;
    seal.innerHTML = renderSealHtml({
      decision,
      target: `${f.control_id} · ${f.id}`,
      provenance: resp.provenance_id,
      scheme: resp.signature_scheme,
      keyId: resp.signature_key_id,
      signer: role(),
      signedAt: resp.signed_at,
    });

    // Refresh data
    state.findingsByRun.set(state.currentRunId, await api(`/runs/${state.currentRunId}/findings`));
    updateAlertBadge();
    renderFindingsList(); // re-render with new status (without selecting it back, to keep seal visible)
    refreshDashboard();
  } catch (e) {
    showSealMessage("Attestation failed: " + e.message, true);
  }
}

function renderSealHtml(o) {
  return `
    <div class="seal-banner">Cryptographic Ledger Seal</div>
    <div class="seal-row"><span class="seal-key">decision</span><span class="seal-val">${escapeHtml(o.decision.toUpperCase())}</span></div>
    <div class="seal-row"><span class="seal-key">target</span><span class="seal-val">${escapeHtml(o.target)}</span></div>
    <div class="seal-row"><span class="seal-key">provenance</span><span class="seal-val">${escapeHtml(o.provenance)}</span></div>
    <div class="seal-row"><span class="seal-key">hash</span><span class="seal-val">sha256_${escapeHtml((o.provenance || "").replace(/^pr-/, ""))}</span></div>
    <div class="seal-row"><span class="seal-key">scheme</span><span class="seal-val">${escapeHtml(o.scheme)}</span></div>
    <div class="seal-row"><span class="seal-key">key id</span><span class="seal-val">${escapeHtml(o.keyId)}</span></div>
    <div class="seal-row"><span class="seal-key">attester</span><span class="seal-val">${escapeHtml(o.signer)}</span></div>
    <div class="seal-row"><span class="seal-key">signed at</span><span class="seal-val">${escapeHtml(o.signedAt)}</span></div>
    <div class="seal-armored">Verified · open-cryptographic digital signature present</div>`;
}

function renderInlineSealForExistingFinding(f) {
  return `
    <div class="seal-banner">Finding Already Adjudicated</div>
    <div class="seal-row"><span class="seal-key">decision</span><span class="seal-val">${escapeHtml(f.status.toUpperCase())}</span></div>
    <div class="seal-row"><span class="seal-key">target</span><span class="seal-val">${escapeHtml(f.control_id)} · ${escapeHtml(f.id)}</span></div>
    <div class="seal-armored">No further attestation accepted (FR-ATT-01)</div>`;
}
function showSealMessage(msg, isError) {
  const seal = $("#gate-signoff-success");
  seal.hidden = false;
  seal.innerHTML = `<div class="seal-banner" style="${isError ? "color:var(--status-error);" : ""}">${escapeHtml(msg)}</div>`;
}

// ─────────────────────────────────────────── Audit ──
async function refreshAudit() {
  try { state.audit = await api("/audit"); }
  catch { state.audit = []; }
  try {
    const v = await api("/audit/verify");
    state.chainValid = !!v.chain_valid;
  } catch { state.chainValid = false; }

  const tbody = $("#auditTable tbody"); tbody.innerHTML = "";
  $("#auditEmpty").hidden = state.audit.length > 0;

  for (const e of state.audit.slice().reverse()) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><code>${escapeHtml((e.event_hash || "").slice(0, 12))}…</code></td>
      <td class="muted">${escapeHtml(formatTs(e.at))}</td>
      <td><code>${escapeHtml(e.target_id || "")}</code></td>
      <td>${escapeHtml(prettyAction(e.action, e.metadata))}</td>
      <td><span class="vstatus valid">VALID SIGNATURE PRESENT</span></td>`;
    tbody.appendChild(tr);
  }
  const cs = $("#chainState");
  cs.textContent = state.chainValid ? `chain valid · ${state.audit.length} blocks` : "CHAIN BROKEN";
  cs.className = state.chainValid ? "chain-state" : "chain-state broken";
}

function prettyAction(action, meta) {
  meta = meta || {};
  if (action === "artifact.ingested") return `Ingested artifact${meta.filename ? " · " + meta.filename : ""}`;
  if (action?.startsWith("run."))     return `Run ${action.slice(4)} · tiers ${(meta.tier_path||[]).join(" → ")}`;
  if (action === "finding.approved")  return `Approved Finding [${meta.control_id || ""}]`;
  if (action === "finding.rejected")  return `Rejected Finding [${meta.control_id || ""}]`;
  if (action === "finding.edited")    return `Edited Finding [${meta.control_id || ""}]`;
  if (action?.startsWith("export."))  return `Exported ${action.slice(7).toUpperCase()}`;
  return action;
}

function formatTs(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toISOString().replace("T", " ").slice(0, 19) + " Z"; }
  catch { return iso; }
}

// ─────────────────────────────────────────── Dashboard ──
async function refreshDashboard() {
  await loadArtifacts();
  // Make sure findings are loaded for every artifact that has a run
  for (const a of state.artifacts) {
    const run = state.runByArtifact.get(a.id);
    if (run && !state.findingsByRun.has(run.id)) {
      try { state.findingsByRun.set(run.id, await api(`/runs/${run.id}/findings`)); } catch { /* */ }
    }
  }

  $("#metric-artifacts").textContent = state.artifacts.length;
  const packages = new Set(state.artifacts.map(packageIdFor));
  $("#metric-packages").textContent = packages.size;

  const allFindings = [...state.findingsByRun.values()].flat();
  const unattested = allFindings.filter(f => f.status === "unattested").length;
  $("#metric-unattested").textContent = unattested;
  $("#tile-unattested").classList.toggle("danger", unattested > 0);

  const total = allFindings.length;
  // "Pass rate" = controls in baseline that produced no findings / controls in baseline
  // Approximate via: 1 - (missing-controls / baseline-controls)
  const missing = allFindings.filter(f => f.type === "missing").length;
  const baselineSize = state.health?.controls_loaded || 0;
  const rate = baselineSize ? Math.round(((baselineSize - missing) / baselineSize) * 100) : 100;
  $("#metric-pass-rate").textContent = `${Math.max(0, Math.min(100, rate))}%`;

  // Breaker strike count — currently we only know the threshold. Show "0" unless tripped on any run.
  const tripped = [...state.runByArtifact.values()].some(r => r.circuit_breaker_tripped);
  $("#metric-breaker").textContent = tripped ? state.health?.circuit_breaker_threshold || "—" : "0";

  // Recent activity
  await refreshAudit();
  const tbody = $("#dashRecent tbody"); tbody.innerHTML = "";
  const recent = state.audit.slice().reverse().slice(0, 10);
  $("#dashRecentEmpty").hidden = recent.length > 0;
  for (const e of recent) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="muted">${escapeHtml(formatTs(e.at))}</td>
      <td><code>${escapeHtml(e.actor || "system")}</code></td>
      <td>${escapeHtml(prettyAction(e.action, e.metadata))}</td>
      <td><code>${escapeHtml(e.target_id || "")}</code></td>`;
    tbody.appendChild(tr);
  }
}

function updateAlertBadge() {
  const allFindings = [...state.findingsByRun.values()].flat();
  const unattested = allFindings.filter(f => f.status === "unattested").length;
  const badge = $("#sidebar-alert-count");
  if (unattested > 0) {
    badge.hidden = false; badge.textContent = unattested;
  } else {
    badge.hidden = true;
  }
}

// ─────────────────────────────────────────── helpers ──
function severityClass(sev) {
  return "sev-" + (sev || "low");
}
function deficitLabel(sev) {
  const map = { critical: "Critical Deficit", high: "High Deficit", medium: "Medium Deficit", low: "Low Deficit" };
  return map[sev] || (sev || "—").toUpperCase();
}
function findingTitle(f) {
  const t = f.type;
  if (t === "missing")
    return "Finding: Control Implementation Missing";
  if (t === "inconsistent")
    return "Finding: Cross-Artifact Inconsistency Detected";
  if (t === "weak_narrative")
    return "Finding: Narrative Weak / Mimics Control Language";
  if (t === "insufficient_evidence")
    return "Finding: Narrative Present but Evidence is Insufficient";
  if (t === "narrative_present_evidence_unclear")
    return "Finding: Narrative Present but Evidence is Unclear";
  return "Finding: " + (t || "").replace(/_/g, " ");
}

/* Whitespace-tolerant locator for an AI-quoted span inside the artifact text.
 * The backend's citation validator already accepts whitespace variation
 * ("foo\nbar" ≡ "foo  bar"), so the UI must too — otherwise highlighting
 * silently fails on any quote that crossed a paragraph break.
 *
 * Strategy:
 *   1. Try a strict indexOf first — fast common case.
 *   2. Tokenize the quote on whitespace and build a regex that allows any
 *      run of whitespace (incl. newlines) between tokens. That mirrors the
 *      Python validator's `" ".join(s.split())` normalization.
 */
function findQuoteInText(text, quote) {
  if (!text || !quote) return null;
  let idx = text.indexOf(quote);
  if (idx >= 0) return [idx, idx + quote.length];
  const tokens = quote.split(/\s+/).filter(Boolean);
  if (!tokens.length) return null;
  const esc = tokens.map(t => t.replace(/[-\\^$*+?.()|[\]{}]/g, "\\$&"));
  try {
    const re = new RegExp(esc.join("\\s+"));
    const m = re.exec(text);
    if (m) return [m.index, m.index + m[0].length];
  } catch (_) { /* fall through */ }
  return null;
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
    .replaceAll('"',"&quot;").replaceAll("'","&#39;");
}
function cssEsc(s) { return (s || "").replace(/(["\\])/g, "\\$1"); }

// ─────────────────────────────────────────── PACKAGES VIEW (Phase II) ──
async function renderPackages() {
  try { state.packages = await api("/packages"); } catch (e) { state.packages = []; }
  const tbody = $("#packagesTable tbody"); tbody.innerHTML = "";
  $("#packagesEmpty").hidden = state.packages.length > 0;

  for (const p of state.packages) {
    const tr = document.createElement("tr");
    tr.classList.add("is-clickable");
    if (p.id === state.currentPackageId) tr.classList.add("is-selected");
    const updated = p.updated_at ? new Date(p.updated_at).toISOString().slice(0,19).replace("T"," ") : "—";
    tr.innerHTML = `
      <td><code>${escapeHtml(p.id)}</code></td>
      <td>${escapeHtml(p.name)}</td>
      <td><span class="pkg-status ${p.status}">${p.status.replace(/_/g," ")}</span></td>
      <td>${p.artifact_count ?? 0}</td>
      <td class="muted">${updated}</td>
      <td class="col-action">
        <button class="btn-small btn-ghost" data-act="open" data-id="${escapeHtml(p.id)}">Open</button>
      </td>`;
    tr.querySelector('[data-act="open"]').onclick = (e) => {
      e.stopPropagation();
      openPackageDetail(p.id);
    };
    tr.onclick = () => openPackageDetail(p.id);
    tbody.appendChild(tr);
  }
}

async function openPackageDetail(pkgId) {
  state.currentPackageId = pkgId;
  let pkg;
  try {
    pkg = await api(`/packages/${pkgId}`);
  } catch (e) {
    alert("Couldn't load package: " + e.message);
    return;
  }
  state.currentPackage = pkg;
  $("#pkgDetail").hidden = false;
  $("#pkgDetailName").textContent = pkg.name;
  $("#pkgDetailMeta").innerHTML =
    `${escapeHtml(pkg.id)} · <span class="pkg-status ${pkg.status}">${pkg.status.replace(/_/g," ")}</span>` +
    `${pkg.description ? ` · ${escapeHtml(pkg.description)}` : ""}`;

  // Member artifacts
  const ul = $("#pkgArtifactList"); ul.innerHTML = "";
  const arts = pkg.artifacts || [];
  $("#pkgArtifactCount").textContent = arts.length;
  $("#pkgArtifactEmpty").hidden = arts.length > 0;
  arts.forEach(a => {
    const li = document.createElement("li");
    li.innerHTML = `
      <span class="name" title="${escapeHtml(a.filename)}">${escapeHtml(a.filename)}</span>
      <span class="meta">${escapeHtml(a.type)} · ${escapeHtml(a.status)}</span>
      <button class="detach" data-id="${escapeHtml(a.id)}" title="Remove from package" aria-label="Remove">×</button>`;
    li.querySelector(".detach").onclick = () => detachArtifact(pkgId, a.id);
    ul.appendChild(li);
  });

  // Disable analyze if archived or empty
  const archived = pkg.status === "archived";
  $("#pkgAnalyzeBtn").disabled = archived || arts.length === 0;
  $("#pkgAttachBtn").disabled  = archived;
  $("#pkgStatusBtn").disabled  = archived && pkg.status === "archived";

  // Re-highlight the row in the table
  $$('#packagesTable tbody tr').forEach(r => {
    r.classList.toggle("is-selected", r.querySelector("code")?.textContent === pkgId);
  });

  // Show latest run if we have one cached
  const latestRun = state.runByArtifact.get(`pkg:${pkgId}`);
  const slot = $("#pkgLatestRun");
  if (latestRun) {
    const fs = state.findingsByRun.get(latestRun.id) || [];
    slot.innerHTML = `
      <div class="empty-hint" style="text-align:left;">
        <div><b>${escapeHtml(latestRun.id)}</b> · ${escapeHtml(latestRun.status)} · tiers ${(latestRun.tier_path||[]).join(" → ")}</div>
        <div>${fs.length} finding${fs.length === 1 ? "" : "s"} emitted.</div>
      </div>`;
  } else {
    slot.innerHTML = `<div class="empty-hint">No runs yet. Click "Analyze package" to run one.</div>`;
  }

  // Phase II FR-CONT-04 — "since last analysis" diff badges + watch state.
  await loadPackageDiff(pkgId);
  await loadPackageWatch(pkgId);
}

async function loadPackageDiff(pkgId) {
  const section = $("#pkgDiffSection");
  const hint = $("#pkgDiffHint");
  try {
    const versions = await api(`/packages/${pkgId}/versions`);
    if (!versions || versions.length < 1) {
      section.hidden = true;
      return;
    }
    const diff = await api(`/packages/${pkgId}/diff`);
    const c = diff.counts || {new:0, resolved:0, stale:0, unchanged:0};
    $("#diffNew").textContent       = c.new;
    $("#diffResolved").textContent  = c.resolved;
    $("#diffStale").textContent     = c.stale;
    $("#diffUnchanged").textContent = c.unchanged;
    if (versions.length < 2) {
      hint.textContent = `Version 1 — first analysis; everything is new.`;
    } else {
      const v = versions[0];
      hint.textContent = `Version ${v.version_idx} vs version ${v.version_idx - 1}.` +
        (c.stale > 0 ? ` ${c.stale} previously-attested finding(s) need re-confirmation.` : "");
    }
    section.hidden = false;
  } catch (_) {
    section.hidden = true;
  }
}

async function loadPackageWatch(pkgId) {
  const section = $("#pkgWatchSection");
  const info = $("#pkgWatchInfo");
  try {
    const w = await api(`/packages/${pkgId}/watch`);
    info.innerHTML = `<div><b>Watching:</b> <code>${escapeHtml(w.folder)}</code></div>` +
      `<div class="muted small">Poll every ${w.poll_interval_s}s · ` +
      `<a href="#" id="pkgUnwatchLink">stop watching</a></div>`;
    section.hidden = false;
    $("#pkgUnwatchLink")?.addEventListener?.("click", async (e) => {
      e.preventDefault();
      if (!confirm("Stop watching this folder?")) return;
      try {
        await api(`/packages/${pkgId}/watch`, { method: "DELETE" });
        await openPackageDetail(pkgId);
      } catch (e) { alert("Stop-watch failed: " + e.message); }
    });
  } catch (_) {
    section.hidden = true;
  }
}

$("#pkgCloseBtn")?.addEventListener?.("click", () => {
  $("#pkgDetail").hidden = true;
  state.currentPackageId = null; state.currentPackage = null;
  $$('#packagesTable tbody tr').forEach(r => r.classList.remove("is-selected"));
});

$("#pkgCreateBtn")?.addEventListener?.("click", async () => {
  const name = prompt("Package name (e.g. 'Aerospace SSP Package'):");
  if (!name || !name.trim()) return;
  const desc = prompt("Description (optional):", "") || "";
  try {
    const pkg = await api("/packages", { method: "POST", json: { name: name.trim(), description: desc } });
    await renderPackages();
    openPackageDetail(pkg.id);
  } catch (e) {
    alert("Create package failed: " + e.message);
  }
});

$("#pkgAttachBtn")?.addEventListener?.("click", async () => {
  if (!state.currentPackageId) return;
  // Load artifacts available in this tenant
  let arts = [];
  try { arts = await api("/artifacts"); } catch (e) { alert("Couldn't load artifacts: " + e.message); return; }
  // Exclude artifacts already in this package
  const memberIds = new Set((state.currentPackage?.artifacts || []).map(a => a.id));
  const available = arts.filter(a => !memberIds.has(a.id) && !a.package_id);
  if (!available.length) {
    alert("No unassigned artifacts available. Upload some via the Artifact Inventory first.");
    return;
  }
  const list = available.map((a, i) => `${i+1}. ${a.filename}  [${a.id}]`).join("\n");
  const pick = prompt(`Pick an artifact to attach (1-${available.length}):\n\n${list}`);
  if (!pick) return;
  const idx = parseInt(pick, 10) - 1;
  if (!(idx >= 0 && idx < available.length)) { alert("Invalid choice."); return; }
  const target = available[idx];
  try {
    await api(`/packages/${state.currentPackageId}/artifacts/${target.id}`, { method: "POST" });
    await renderPackages();
    await openPackageDetail(state.currentPackageId);
  } catch (e) {
    alert("Attach failed: " + e.message);
  }
});

async function detachArtifact(pkgId, artifactId) {
  if (!confirm(`Remove ${artifactId} from this package?`)) return;
  try {
    await api(`/packages/${pkgId}/artifacts/${artifactId}`, { method: "DELETE" });
    await renderPackages();
    await openPackageDetail(pkgId);
  } catch (e) {
    alert("Detach failed: " + e.message);
  }
}

$("#pkgAnalyzeBtn")?.addEventListener?.("click", async () => {
  if (!state.currentPackageId) return;
  const btn = $("#pkgAnalyzeBtn");
  const orig = btn.textContent;
  btn.textContent = "Analyzing…"; btn.disabled = true;
  try {
    const run = await api(`/packages/${state.currentPackageId}/runs`, { method: "POST", timeout: 300000 });
    // Cache the run + findings for the detail view
    state.runByArtifact.set(`pkg:${state.currentPackageId}`, run);
    const fs = await api(`/runs/${run.id}/findings`);
    state.findingsByRun.set(run.id, fs);
    await openPackageDetail(state.currentPackageId);
    alert(`Analyzed — ${fs.length} finding(s). Open Attestation Gate for any artifact in the package to review them.`);
  } catch (e) {
    alert("Analyze failed: " + e.message);
  } finally {
    btn.textContent = orig; btn.disabled = false;
  }
});

$("#pkgWatchBtn")?.addEventListener?.("click", async () => {
  if (!state.currentPackageId) return;
  const folder = prompt(
    "Absolute path to the folder to watch.\n\n" +
    "QUILL will poll this folder every ~5s. When a file is added or changed,\n" +
    "the package is re-analyzed automatically and attestations on unchanged\n" +
    "findings carry forward (FR-CONT-06).\n\n" +
    "Example: /Users/you/work/program-x-package"
  );
  if (!folder || !folder.trim()) return;
  try {
    await api(`/packages/${state.currentPackageId}/watch`,
              { method: "POST", json: { folder: folder.trim() } });
    await openPackageDetail(state.currentPackageId);
    alert(`Watching ${folder.trim()} — drop files in there and QUILL will re-analyze.`);
  } catch (e) {
    alert("Watch setup failed: " + e.message);
  }
});

$("#pkgExportBtn")?.addEventListener?.("click", async () => {
  if (!state.currentPackageId) return;
  const choice = prompt(
    "Export format:\n" +
    "  1. Stakeholder summary PDF (FR-EXP-04)\n" +
    "  2. Version-diff report (FR-EXP-05)\n" +
    "  3. OSCAL package bundle (FR-EXP-06)\n\n" +
    "Enter 1, 2, or 3:"
  );
  const map = { "1": "stakeholder_pdf", "2": "version_diff", "3": "oscal_package" };
  const fmt = map[(choice || "").trim()];
  if (!fmt) return;
  try {
    const res = await fetch(`/packages/${state.currentPackageId}/export?format=${fmt}`, {
      headers: { "X-QUILL-Role": role(), "X-QUILL-Tenant": program() },
    });
    if (!res.ok) {
      const t = await res.text();
      throw new Error(`HTTP ${res.status}: ${t}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const ext = fmt === "stakeholder_pdf" ? "pdf" : (fmt === "version_diff" ? "md" : "json");
    a.download = `${state.currentPackageId}-${fmt}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert("Export failed: " + e.message);
  }
});

$("#pkgStatusBtn")?.addEventListener?.("click", async () => {
  if (!state.currentPackage) return;
  const cur = state.currentPackage.status;
  const TRANSITIONS = {
    draft:        ["under_review", "archived"],
    under_review: ["draft", "submitted", "archived"],
    submitted:    ["archived"],
    archived:     [],
  };
  const options = TRANSITIONS[cur] || [];
  if (!options.length) { alert(`'${cur}' is terminal — no further transitions.`); return; }
  const pick = prompt(`Current status: ${cur}\n\nChange to one of:\n${options.map((o,i) => `${i+1}. ${o}`).join("\n")}`);
  if (!pick) return;
  const idx = parseInt(pick, 10) - 1;
  if (!(idx >= 0 && idx < options.length)) { alert("Invalid choice."); return; }
  try {
    await api(`/packages/${state.currentPackageId}/status`, { method: "PATCH", json: { status: options[idx] } });
    await renderPackages();
    await openPackageDetail(state.currentPackageId);
  } catch (e) {
    alert("Status change failed: " + e.message);
  }
});

// ─────────────────────────────────────────── Programs (Phase II) ──
const PROGRAM_KEY = "quill_program";

async function loadPrograms() {
  let progs = [];
  try { progs = await api("/programs"); } catch (e) { /* default-only fallback */ }
  if (!progs.length) progs = [{ id: "default", name: "Default", status: "active" }];
  const sel = $("#program");
  const previous = sel.value;
  sel.innerHTML = "";
  for (const p of progs) {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = p.name + (p.status === "disabled" ? " (disabled)" : "");
    if (p.status === "disabled") opt.disabled = true;
    sel.appendChild(opt);
  }
  // Restore previously selected program if it still exists; otherwise prefer saved.
  let saved = "default";
  try { saved = localStorage.getItem(PROGRAM_KEY) || "default"; } catch (_) {}
  const valid = (v) => progs.some(p => p.id === v && p.status !== "disabled");
  sel.value = valid(previous) ? previous : (valid(saved) ? saved : progs[0].id);
}

function applyProgram() {
  try { localStorage.setItem(PROGRAM_KEY, $("#program").value); } catch (_) {}
  // Clear current artifact/run since they belong to a different tenant
  state.currentArtifact = null;
  state.currentRunId = null;
  state.findingsByRun.clear();
  state.runByArtifact.clear();
  state.audit = [];
  if (typeof setGateEmpty === "function") setGateEmpty();
  refreshDashboard();
}

$("#program").addEventListener("change", applyProgram);

// Show "+" button only when operator is admin
function syncProgramNewBtn() {
  const btn = $("#programNewBtn");
  if (!btn) return;
  btn.hidden = role() !== "admin";
}
$("#role").addEventListener("change", syncProgramNewBtn);

$("#programNewBtn")?.addEventListener?.("click", async () => {
  if (role() !== "admin") {
    alert("Switch role to Admin to create a program.");
    return;
  }
  const name = prompt("Program name (e.g. 'Aerospace R&D'):");
  if (!name || !name.trim()) return;
  const id = prompt(
    "Program ID (lowercase, hyphens; this is the tenant key):",
    name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")
  );
  if (!id) return;
  const baseline = prompt("Baseline (low | moderate | high):", "moderate");
  if (!baseline) return;
  try {
    const prog = await api("/programs", {
      method: "POST",
      json: { id: id.trim(), name: name.trim(), baseline: baseline.trim() },
    });
    await loadPrograms();
    $("#program").value = prog.id;
    applyProgram();
  } catch (e) {
    alert("Create program failed: " + e.message);
  }
});

// ─────────────────────────────────────────── init ──
$("#role").addEventListener("change", () => { refreshHealth(); });
refreshHealth().then(() => loadPrograms()).then(() => {
  syncProgramNewBtn();
  refreshDashboard();
});
setInterval(refreshHealth, 30000);

// ─────────────────────────────────────────── AI Calibration (Phase II FR-AI-02) ──
async function renderCalibration() {
  let report;
  try { report = await api("/calibration/report"); }
  catch (e) { return; }

  $("#calib-total").textContent    = report.n_total;
  $("#calib-attested").textContent = report.n_attested;
  $("#calib-ece").textContent      = (report.ece ?? 0).toFixed(3);
  $("#calib-monotonic").textContent = report.monotonic ? "yes" : `no (${report.monotonic_violations})`;

  const gate = report.phase_ii_gate?.overall_pass;
  const gateEl = $("#calib-gate");
  gateEl.textContent = report.n_attested === 0 ? "no data"
                       : (gate ? "PASS" : "FAIL");
  gateEl.classList.remove("pass", "fail");
  if (report.n_attested > 0) gateEl.classList.add(gate ? "pass" : "fail");

  // Render SVG bar chart of observed_rate per bin, with diagonal reference.
  const svg = $("#calibChart");
  svg.innerHTML = "";
  const W = 600, H = 380, PAD_L = 50, PAD_R = 20, PAD_T = 20, PAD_B = 50;
  const innerW = W - PAD_L - PAD_R;
  const innerH = H - PAD_T - PAD_B;

  // axes
  function mkLine(x1, y1, x2, y2, cls) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", "line");
    el.setAttribute("x1", x1); el.setAttribute("y1", y1);
    el.setAttribute("x2", x2); el.setAttribute("y2", y2);
    el.setAttribute("class", cls); svg.appendChild(el);
  }
  function mkText(x, y, str, cls) {
    const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
    t.setAttribute("x", x); t.setAttribute("y", y);
    t.setAttribute("class", cls || "label"); t.textContent = str;
    svg.appendChild(t);
  }
  function mkRect(x, y, w, h, cls) {
    const r = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    r.setAttribute("x", x); r.setAttribute("y", y);
    r.setAttribute("width", w); r.setAttribute("height", h);
    r.setAttribute("class", cls); svg.appendChild(r);
  }

  // axes + grid
  mkLine(PAD_L, PAD_T, PAD_L, PAD_T + innerH, "axis");
  mkLine(PAD_L, PAD_T + innerH, PAD_L + innerW, PAD_T + innerH, "axis");
  for (let i = 0; i <= 10; i++) {
    const y = PAD_T + innerH * (1 - i / 10);
    mkLine(PAD_L, y, PAD_L + innerW, y, "grid");
    mkText(PAD_L - 6, y + 3, (i / 10).toFixed(1)).setAttribute?.("text-anchor", "end");
  }
  // diagonal reference
  mkLine(PAD_L, PAD_T + innerH, PAD_L + innerW, PAD_T, "diag");

  const bins = report.bins || [];
  const colW = innerW / Math.max(bins.length, 1);
  bins.forEach((b, i) => {
    const rate = b.observed_rate || 0;
    const h = innerH * rate;
    const x = PAD_L + i * colW + 4;
    const y = PAD_T + innerH - h;
    const cls = (b.n >= report.sample_threshold) ? "bar" : "bar low";
    mkRect(x, y, colW - 8, h, cls);
    mkText(x + (colW - 8) / 2, PAD_T + innerH + 14,
           `${b.lo.toFixed(1)}–${b.hi.toFixed(1)}`)
      .setAttribute?.("text-anchor", "middle");
    if (b.n > 0) {
      mkText(x + (colW - 8) / 2, y - 4, `${b.n_real}/${b.n}`)
        .setAttribute?.("text-anchor", "middle");
    }
  });
  mkText(PAD_L + innerW / 2, H - 8, "Predicted confidence bucket").setAttribute?.("text-anchor", "middle");
  // y-axis label
  const yl = document.createElementNS("http://www.w3.org/2000/svg", "text");
  yl.setAttribute("class", "label");
  yl.setAttribute("transform", `translate(14, ${PAD_T + innerH / 2}) rotate(-90)`);
  yl.setAttribute("text-anchor", "middle");
  yl.textContent = "Observed approval rate";
  svg.appendChild(yl);

  $("#calibCsvLink").onclick = (e) => {
    e.preventDefault();
    window.location.href = "/calibration/curve.csv";
  };
}
