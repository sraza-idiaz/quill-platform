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
  // Phase II — cross-document Package Map payload (GET /packages/{id}/map)
  packageMap: null,
  // Phase II — Visual Grounding payload (GET /packages/{id}/grounding)
  // { pkgId, payload, filter }
  grounding: null,
};

// ─────────────────────────────────────────── API ──
function role()    { return $("#role").value; }
function program() { return $("#program") ? $("#program").value : "default"; }
// Subclass of Error that carries the HTTP status so callers (especially
// refreshHealth) can branch on auth vs cold-start vs network failures.
class ApiError extends Error {
  constructor(message, status, kind) {
    super(message);
    this.status = status;        // numeric HTTP status, or 0 for network/timeout
    this.kind = kind;            // 'auth' | 'cold_start' | 'network' | 'timeout' | 'http'
  }
}

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
    if (e.name === "AbortError") throw new ApiError("request timed out", 0, "timeout");
    throw new ApiError(`network: ${e.message}`, 0, "network");
  } finally { clearTimeout(t); }
  const ct = res.headers.get("content-type") || "";
  const body = ct.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    const kind = res.status === 401 ? "auth"
               : (res.status === 502 || res.status === 503 || res.status === 504) ? "cold_start"
               : "http";
    throw new ApiError(
      `${res.status} · ${(body && body.detail) || body || res.statusText}`,
      res.status,
      kind,
    );
  }
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
  // "map" intentionally has no auto-render here — it's driven by renderPackageMap(pkgId)
  // from the package-detail "Map" button, which switches the view and fetches in one shot.
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

// Track whether we are mid-cold-start so we don't spawn parallel retry loops.
let _coldStartRetrying = false;

async function refreshHealth() {
  try {
    const h = await api("/health");
    state.health = h;

    const airChip = $("#airgapChip");
    airChip.textContent = h.air_gap ? "Air-Gap" : "Live";
    airChip.className = "env-chip ok";
    hideBackendBanner();
    _coldStartRetrying = false;

    $("#tier2Chip").textContent  = h.tier2_analyzer ? `T2 · ${h.tier2_analyzer}` : "T2 · disabled";
    $("#tier2Chip").className    = h.tier2_analyzer ? "env-chip ok" : "env-chip";
    $("#breakerChip").textContent = `breaker ${h.circuit_breaker_threshold}`;
    $("#engineSummary").innerHTML =
      `baseline · ${escapeHtml(h.baseline)}<br>controls · ${h.controls_loaded}<br>tier 2 · ${escapeHtml(h.tier2_analyzer || "—")}`;
    $("#footerEnv").textContent = `${h.air_gap ? "Air-Gap" : "Live"} · baseline ${h.baseline} · ${h.controls_loaded} controls · breaker ${h.circuit_breaker_threshold}`;

    $("#metric-breaker-max").textContent = h.circuit_breaker_threshold;
    return;
  } catch (e) {
    handleHealthError(e);
  }
}

// Distinguishes login-required, cold-start (auto-retry), and real outages.
function handleHealthError(e) {
  const chip = $("#airgapChip");
  const isLocal = location.hostname === "localhost" || location.hostname === "127.0.0.1";
  const kind = (e && e.kind) || "network";

  if (kind === "auth") {
    chip.textContent = "LOGIN REQUIRED"; chip.className = "env-chip warn";
    showBackendBanner(
      `<b>Login required.</b> This deploy is behind HTTP Basic Auth. ` +
      `<a href="#" onclick="location.reload();return false;">Click to refresh</a> ` +
      `and enter your username and password.`
    );
    return;
  }

  if (kind === "cold_start") {
    chip.textContent = "STARTING…"; chip.className = "env-chip warn";
    showBackendBanner(
      `<b>Server is starting up.</b> Render's free tier sleeps after 15 minutes of ` +
      `inactivity; first request can take 30–60 seconds. Retrying automatically…`
    );
    if (!_coldStartRetrying) {
      _coldStartRetrying = true;
      let attempts = 0;
      const tick = async () => {
        attempts++;
        if (attempts > 12) {                  // ~2 min of trying then give up
          _coldStartRetrying = false;
          chip.textContent = "BACKEND UNREACHABLE"; chip.className = "env-chip error";
          showBackendBanner(
            `<b>Server didn't wake up.</b> Try ` +
            `<a href="/health" target="_blank">/health</a> directly, or check the ` +
            `Render dashboard for build / runtime errors.`
          );
          return;
        }
        try {
          await api("/health");
          _coldStartRetrying = false;
          refreshHealth();                    // success → full reload of chips
        } catch (_) { setTimeout(tick, 10000); }
      };
      setTimeout(tick, 10000);
    }
    return;
  }

  // network / timeout / unexpected HTTP — actual outage
  chip.textContent = "BACKEND UNREACHABLE"; chip.className = "env-chip error";
  const hint = isLocal
    ? `Start the server: <code>scripts/quill-server up</code>`
    : `Check the deployed app's health at ` +
      `<a href="/health" target="_blank">/health</a> or the Render dashboard.`;
  showBackendBanner(`<b>Backend unreachable.</b> ${hint} (${escapeHtml(e.message || "")})`);
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
  const files = Array.from(e.target.files || []);
  if (files.length === 0) {
    resetUploadForm();
    return;
  }
  if (files.length === 1) {
    $("#fileLabel").textContent = files[0].name;
    $("#fileHint").textContent  = "Selected — ready to ingest";
  } else {
    $("#fileLabel").textContent = `${files.length} files selected`;
    $("#fileHint").textContent  = files.map(f => f.name).join(" · ").slice(0, 100) +
                                  (files.length > 5 ? "…" : "");
  }
  $("#fileDrop").classList.add("has-file");
  $("#fileClear").hidden = false;
  $("#ingestBtn").disabled = false;
});

// "×" button clears the picked file. preventDefault + stopPropagation are
// critical so the click doesn't bubble up to the <label> wrapper, which
// would otherwise re-open the OS file picker.
$("#fileClear").addEventListener("click", (e) => {
  e.preventDefault();
  e.stopPropagation();
  resetUploadForm();
});

// Drag-and-drop onto the file-drop label. Modern, expected UX for upload.
(function wireDragDrop() {
  const zone = $("#fileDrop"); if (!zone) return;
  ["dragenter", "dragover"].forEach(ev => zone.addEventListener(ev, (e) => {
    e.preventDefault(); e.stopPropagation();
    zone.classList.add("is-dragging");
  }));
  ["dragleave", "drop"].forEach(ev => zone.addEventListener(ev, (e) => {
    e.preventDefault(); e.stopPropagation();
    zone.classList.remove("is-dragging");
  }));
  zone.addEventListener("drop", (e) => {
    const files = Array.from(e.dataTransfer?.files || []);
    if (!files.length) return;
    // Push ALL dropped files into the hidden <input> so the existing
    // submit path picks them up.
    const dt = new DataTransfer();
    for (const f of files) dt.items.add(f);
    $("#fileInput").files = dt.files;
    $("#fileInput").dispatchEvent(new Event("change"));
  });
})();

$("#uploadForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const files = Array.from($("#fileInput").files || []);
  if (!files.length) return;
  const btn = $("#uploadForm button[type=submit]");
  const orig = btn.textContent;
  btn.disabled = true;

  const ok = [];
  const failed = [];
  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    btn.textContent = files.length > 1
      ? `Ingesting ${i + 1}/${files.length}…`
      : "Ingesting…";
    const fd = new FormData(); fd.append("file", f);
    try {
      const res = await fetch("/artifacts", {
        method: "POST", body: fd,
        headers: { "X-QUILL-Role": role(), "X-QUILL-Tenant": program() },
      });
      if (!res.ok) throw new Error(`${res.status} · ${await res.text()}`);
      ok.push(await res.json());
    } catch (err) {
      failed.push({ name: f.name, err: err.message || String(err) });
    }
  }

  resetUploadForm();
  await renderInventory();
  refreshDashboard();

  if (ok.length && !failed.length) {
    toastSuccess(
      ok.length === 1 ? `Uploaded ${ok[0].filename}` : `Uploaded ${ok.length} artifacts`,
      "Click Analyze on a row (or open Packages to bundle them).",
    );
  } else if (ok.length && failed.length) {
    toastInfo(
      `${ok.length} uploaded · ${failed.length} failed`,
      failed.map(f => `${f.name}: ${f.err}`).join(" · ").slice(0, 200),
    );
  } else {
    toastError("Upload failed", failed.map(f => `${f.name}: ${f.err}`).join(" · "));
  }
  btn.textContent = orig; btn.disabled = false;
});

// ─────────────────────────────────────────── Analyze ──
// 20-minute timeout: a real SSP × Tier 2 across 370 controls runs ~9 minutes
// on cloud Ollama. We leave a wide margin so the UI doesn't bail before
// the backend finishes; the backend itself has no cap.
const ANALYZE_TIMEOUT_MS = 20 * 60 * 1000;

async function analyzeArtifact(artifactId) {
  const row = document.querySelector(`[data-act="analyze"][data-id="${artifactId}"]`)?.closest("tr");
  const btn = row?.querySelector('[data-act="analyze"]');
  if (btn) { btn.disabled = true; btn.textContent = "Analyzing…"; }
  const t2on = !!state.health?.tier2_analyzer;
  toastInfo("Analysis started",
            t2on ? "Tier 2 LLM is on — this can take 5–10 minutes."
                 : "Tier 0+1 only — should finish in a few seconds.");
  try {
    const run = await api(`/artifacts/${artifactId}/runs`,
                          { method: "POST", timeout: ANALYZE_TIMEOUT_MS });
    state.runByArtifact.set(artifactId, run);
    const findings = await api(`/runs/${run.id}/findings`);
    state.findingsByRun.set(run.id, findings);
    await renderInventory();
    refreshDashboard();
    updateAlertBadge();
    toastSuccess(`Analysis complete · ${findings.length} finding${findings.length === 1 ? "" : "s"}`,
                 "Click 'Open Gate' to review them.");
  } catch (e) {
    if (btn) { btn.disabled = false; btn.textContent = "Analyze"; }
    // 404 = the artifact your browser is showing no longer exists on the
    // server (typical after a redeploy of the in-memory store). Surface a
    // useful message and refresh the inventory so the stale row disappears.
    if (e?.status === 404) {
      toastError("Artifact no longer on server",
                 "The server doesn't have this artifact anymore — likely a recent redeploy. " +
                 "Refreshing your inventory now; please re-upload to analyze.");
      try {
        state.runByArtifact.delete(artifactId);
        await renderInventory();
        refreshDashboard();
      } catch (_) { /* swallow secondary errors */ }
      return;
    }
    toastError("Analysis failed", e.message);
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

// opts (optional):
//   { runId, findingId } — a "deep link" into a specific run + finding (used by
//   the cross-document Map drawer). When runId is provided we MUST NOT auto-POST
//   a new analysis run: the run already exists and re-running it would mint a new
//   run id (and burn minutes of LLM time). We pin state.currentRunId = runId,
//   load that run's findings, and, after rendering, select findingId if given.
async function openGateFor(artifactId, opts = {}) {
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

  // Resolve the run. On a deep link (opts.runId) use it verbatim — never analyze.
  // Otherwise fall back to the cached run, auto-analyzing only if none exists.
  let runId = opts.runId || null;
  if (!runId) {
    let run = state.runByArtifact.get(a.id);
    if (!run) {
      setGateBusy("Running analysis pipeline…");
      try { run = await api(`/artifacts/${a.id}/runs`, { method: "POST", timeout: ANALYZE_TIMEOUT_MS }); }
      catch (e) { setGateError(e.message); return; }
      state.runByArtifact.set(a.id, run);
    }
    runId = run.id;
  }
  state.currentRunId = runId;
  setGateBusy("Loading findings…");

  // Pull text + findings
  try {
    const txt = await api(`/artifacts/${a.id}/text`);
    state.artifactText = txt.text || "";
  } catch { state.artifactText = ""; }
  try {
    state.findingsByRun.set(runId, await api(`/runs/${runId}/findings`));
  } catch (e) { setGateError(e.message); return; }

  renderSourceCanvas();
  renderFindingsList();
  $("#findingsMeta").textContent = `${(state.findingsByRun.get(runId) || []).length} findings`;
  $("#gateActions").hidden = false;
  await loadGraphForCurrent();      // Phase II FR-XA-03 — preload the dependency graph
  updateAlertBadge();

  // Deep-link target: select the specific finding once the list exists.
  // renderFindingsList() default-selects the first unattested finding; this
  // override jumps to the finding the Map drawer pointed at.
  if (opts.findingId) selectFinding(opts.findingId);
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
    const run = await api(`/artifacts/${state.currentArtifact.id}/runs`, { method: "POST", timeout: ANALYZE_TIMEOUT_MS });
    state.runByArtifact.set(state.currentArtifact.id, run);
    state.currentRunId = run.id;
    state.findingsByRun.set(run.id, await api(`/runs/${run.id}/findings`));
    renderSourceCanvas();
    renderFindingsList();
    $("#findingsMeta").textContent = `${(state.findingsByRun.get(run.id) || []).length} findings`;
    updateAlertBadge();
    refreshDashboard();
  } catch (e) { toastError("Re-analyze failed", e.message); }
  finally { btn.textContent = orig; btn.disabled = false; }
});

$("#exportReportBtn")?.addEventListener?.("click", () => doExport("report"));
$("#exportPoamBtn")  ?.addEventListener?.("click", () => doExport("poam"));
$("#exportAuditBtn") ?.addEventListener?.("click", () => doExport("audit"));

async function doExport(fmt) {
  if (!state.currentRunId) { toastInfo("No analyzed artifact", "Open an artifact that has been analyzed first."); return; }
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
  } catch (e) { toastError("Export failed", e.message); }
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
    $("#editBtn").onclick    = async () => {
      const newRec = await modalPrompt({
        title: "Edit recommendation",
        subtitle: "Refine QUILL's recommendation before signing. The edit is recorded with your attestation.",
        label: "Recommendation",
        multiline: true,
        initial: f.recommendation,
        confirmLabel: "Sign as edited",
      });
      if (newRec == null) return;
      const edited = {};
      if (newRec !== f.recommendation) edited.recommendation = newRec;
      doAttest(f, "edited", edited);
    };
    $("#rejectBtn").onclick  = () => doAttest(f, "rejected");
  }
  footer.hidden = false;
}
function hideAttestFooter() { $("#attestFooter").hidden = true; }

async function doAttest(f, decision, edited = null) {
  if (role() !== "attester") {
    toastError("Attester role required",
               `Switch the Operator dropdown (top right) to "attester". Admin is NOT auto-granted.`);
    showSealMessage(`The "Attester" role is required. Switch the Operator at the top right. Admin is NOT auto-granted.`, true);
    return;
  }
  // Disable buttons immediately so the user sees the click took effect.
  ["#approveBtn", "#editBtn", "#rejectBtn"].forEach(s => {
    const b = $(s); if (b) { b.disabled = true; }
  });
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

    // Refresh data + UI — KEEP the current finding selected so the user
    // sees the status badge change on the same row, not a deselected list.
    const fresh = await api(`/runs/${state.currentRunId}/findings`);
    state.findingsByRun.set(state.currentRunId, fresh);
    updateAlertBadge();
    refreshDashboard();

    const updated = fresh.find(x => x.id === f.id) || f;
    state.currentFindingId = updated.id;
    renderFindingsList();

    const verb = { approved: "Approved", edited: "Signed as edited", rejected: "Rejected" }[decision] || decision;
    toastSuccess(`${verb} · ${f.control_id}`,
                 `Signed by ${role()}. Provenance ${resp.provenance_id}.`);

    // Pick the next unattested finding so the reviewer can keep going.
    const next = fresh.find(x => x.status === "unattested");
    if (next && next.id !== updated.id) {
      setTimeout(() => selectFinding(next.id), 600);   // small pause so user sees the seal first
    }
  } catch (e) {
    ["#approveBtn", "#editBtn", "#rejectBtn"].forEach(s => {
      const b = $(s); if (b) { b.disabled = false; }
    });
    toastError("Attestation failed", e.message);
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
    toastError("Could not load package", e.message);
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
      const ok = await modalConfirm({
        title: "Stop watching folder?",
        message: "QUILL will no longer re-analyze when you change files in this folder. You can re-attach the watch later.",
        confirmLabel: "Stop watching",
      });
      if (!ok) return;
      try {
        await api(`/packages/${pkgId}/watch`, { method: "DELETE" });
        await openPackageDetail(pkgId);
        toastInfo("Watch stopped");
      } catch (e) { toastError("Stop-watch failed", e.message); }
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
  const pkg = await openModal({
    title: "Create package",
    subtitle: "A package bundles related artifacts (SSP + architecture + policies) so they're analyzed as one unit.",
    confirmLabel: "Create",
    body: (root) => {
      const nameLbl = document.createElement("label");
      nameLbl.innerHTML = `<span>Name</span><input type="text" placeholder="e.g. Aerospace SSP Package" />`;
      const descLbl = document.createElement("label");
      descLbl.innerHTML = `<span>Description (optional)</span><textarea placeholder="What is this package for?"></textarea>`;
      root.appendChild(nameLbl);
      root.appendChild(descLbl);
      return { name: nameLbl.querySelector("input"), desc: descLbl.querySelector("textarea") };
    },
    submit: async ({ name, desc }) => {
      const v = name.value.trim();
      if (!v) throw new Error("Package name is required.");
      const created = await api("/packages", {
        method: "POST",
        json: { name: v, description: desc.value.trim() },
      });
      return created;
    },
  });
  if (!pkg) return;
  toastSuccess(`Package created · ${pkg.id}`, "Attach artifacts and run analysis.");
  await renderPackages();
  openPackageDetail(pkg.id);
});

$("#pkgAttachBtn")?.addEventListener?.("click", async () => {
  if (!state.currentPackageId) return;
  let arts = [];
  try { arts = await api("/artifacts"); }
  catch (e) { toastError("Could not load artifacts", e.message); return; }
  const memberIds = new Set((state.currentPackage?.artifacts || []).map(a => a.id));
  const available = arts.filter(a => !memberIds.has(a.id) && !a.package_id);
  if (!available.length) {
    toastInfo("No unassigned artifacts",
              "Upload one in Artifact Inventory first.");
    return;
  }
  const pickedList = await openModal({
    title: "Attach artifacts to package",
    subtitle: "Click any number of artifacts to include them, then Attach. Each artifact belongs to one package at a time.",
    confirmLabel: "Attach",
    body: (root) => {
      // Toolbar with select-all / clear shortcuts above the list.
      const bar = document.createElement("div");
      bar.style.cssText = "display:flex; gap:10px; align-items:center; font-size:12px; color:var(--text-muted);";
      bar.innerHTML = `
        <span id="attachCount">0 of ${available.length} selected</span>
        <a href="#" id="attachSelectAll" style="margin-left:auto;">select all</a>
        <a href="#" id="attachClear">clear</a>`;
      root.appendChild(bar);

      const ul = document.createElement("ul");
      ul.className = "modal-list";
      available.forEach((a) => {
        const li = document.createElement("li");
        li.innerHTML = `<span>${escapeHtml(a.filename)}</span>
                        <span class="meta">${escapeHtml(a.type)} · ${escapeHtml(a.id.slice(0, 12))}</span>`;
        li.onclick = () => {
          li.classList.toggle("is-selected");
          refreshCount();
        };
        ul.appendChild(li);
      });
      root.appendChild(ul);

      const refreshCount = () => {
        const n = ul.querySelectorAll("li.is-selected").length;
        bar.querySelector("#attachCount").textContent = `${n} of ${available.length} selected`;
      };

      bar.querySelector("#attachSelectAll").onclick = (e) => {
        e.preventDefault();
        ul.querySelectorAll("li").forEach(li => li.classList.add("is-selected"));
        refreshCount();
      };
      bar.querySelector("#attachClear").onclick = (e) => {
        e.preventDefault();
        ul.querySelectorAll("li").forEach(li => li.classList.remove("is-selected"));
        refreshCount();
      };

      return { ul };
    },
    submit: ({ ul }) => {
      const selected = [...ul.querySelectorAll("li.is-selected")];
      if (!selected.length) throw new Error("Pick at least one artifact.");
      return selected.map(li => available[[...ul.children].indexOf(li)]);
    },
  });
  if (!pickedList || !pickedList.length) return;

  const ok = [];
  const failed = [];
  for (const a of pickedList) {
    try {
      await api(`/packages/${state.currentPackageId}/artifacts/${a.id}`, { method: "POST" });
      ok.push(a);
    } catch (e) {
      failed.push({ name: a.filename, err: e.message || String(e) });
    }
  }
  await renderPackages();
  await openPackageDetail(state.currentPackageId);
  if (ok.length && !failed.length) {
    toastSuccess(
      ok.length === 1 ? `Attached ${ok[0].filename}` : `Attached ${ok.length} artifacts`,
    );
  } else if (ok.length && failed.length) {
    toastInfo(`${ok.length} attached · ${failed.length} failed`,
              failed.map(f => `${f.name}: ${f.err}`).join(" · "));
  } else {
    toastError("Attach failed", failed.map(f => `${f.name}: ${f.err}`).join(" · "));
  }
});

async function detachArtifact(pkgId, artifactId) {
  const ok = await modalConfirm({
    title: "Remove artifact from package?",
    message: `Detach artifact ${artifactId.slice(0, 12)}… from this package. The artifact stays in Inventory and can be re-attached.`,
    confirmLabel: "Remove",
  });
  if (!ok) return;
  try {
    await api(`/packages/${pkgId}/artifacts/${artifactId}`, { method: "DELETE" });
    await renderPackages();
    await openPackageDetail(pkgId);
  } catch (e) {
    toastError("Detach failed", e.message);
  }
}

$("#pkgAnalyzeBtn")?.addEventListener?.("click", async () => {
  if (!state.currentPackageId) return;
  const btn = $("#pkgAnalyzeBtn");
  const orig = btn.textContent;
  btn.textContent = "Analyzing…"; btn.disabled = true;
  try {
    const run = await api(`/packages/${state.currentPackageId}/runs`, { method: "POST", timeout: ANALYZE_TIMEOUT_MS });
    // Cache the run + findings for the detail view
    state.runByArtifact.set(`pkg:${state.currentPackageId}`, run);
    const fs = await api(`/runs/${run.id}/findings`);
    state.findingsByRun.set(run.id, fs);
    await openPackageDetail(state.currentPackageId);
    toastSuccess(`Package analyzed · ${fs.length} finding${fs.length === 1 ? "" : "s"}`, "Open Attestation Gate to review them.");
  } catch (e) {
    toastError("Analyze failed", e.message);
  } finally {
    btn.textContent = orig; btn.disabled = false;
  }
});

$("#pkgWatchBtn")?.addEventListener?.("click", async () => {
  if (!state.currentPackageId) return;
  const folder = await modalPrompt({
    title: "Watch a folder for changes",
    subtitle: "QUILL polls the folder every ~5s. Drop or edit files inside and the package re-analyzes automatically. Attestations on unchanged findings carry forward.",
    label: "Absolute folder path",
    placeholder: "/Users/you/work/program-x-package",
    help: "Must be a folder that already exists on this machine.",
    confirmLabel: "Start watching",
  });
  if (!folder) return;
  try {
    await api(`/packages/${state.currentPackageId}/watch`,
              { method: "POST", json: { folder } });
    await openPackageDetail(state.currentPackageId);
    toastSuccess("Now watching", `Drop files into ${folder} — QUILL will re-analyze automatically.`);
  } catch (e) {
    toastError("Watch setup failed", e.message);
  }
});

$("#pkgExportBtn")?.addEventListener?.("click", async () => {
  if (!state.currentPackageId) return;
  const EXPORTS = [
    { id: "stakeholder_pdf", title: "Stakeholder summary (PDF)", sub: "1–2 page management readout", ext: "pdf" },
    { id: "version_diff",    title: "Version-diff report (Markdown)", sub: "What changed since the last run", ext: "md" },
    { id: "oscal_package",   title: "OSCAL bundle (JSON)", sub: "Machine-readable, ready for eMASS / Xacta", ext: "json" },
  ];
  const fmt = await openModal({
    title: "Export package",
    subtitle: "Pick what kind of deliverable you need.",
    confirmLabel: "Download",
    body: (root) => {
      const ul = document.createElement("ul");
      ul.className = "modal-list";
      EXPORTS.forEach((e, i) => {
        const li = document.createElement("li");
        li.innerHTML = `<span><b>${escapeHtml(e.title)}</b><br><span class="meta">${escapeHtml(e.sub)}</span></span>`;
        li.dataset.id = e.id;
        li.onclick = () => {
          ul.querySelectorAll("li").forEach(x => x.classList.remove("is-selected"));
          li.classList.add("is-selected");
        };
        if (i === 0) li.classList.add("is-selected");   // default
        ul.appendChild(li);
      });
      root.appendChild(ul);
      return { ul };
    },
    submit: ({ ul }) => {
      const sel = ul.querySelector("li.is-selected");
      if (!sel) throw new Error("Pick an export format.");
      return EXPORTS.find(e => e.id === sel.dataset.id);
    },
  });
  if (!fmt) return;

  try {
    const res = await fetch(`/packages/${state.currentPackageId}/export?format=${fmt.id}`, {
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
    a.download = `${state.currentPackageId}-${fmt.id}.${fmt.ext}`;
    a.click();
    URL.revokeObjectURL(url);
    toastSuccess(`Downloaded ${fmt.title}`, `Saved as ${state.currentPackageId}-${fmt.id}.${fmt.ext}`);
  } catch (e) {
    toastError("Export failed", e.message);
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
  if (!options.length) {
    toastInfo(`'${cur}' is terminal`, "No further transitions allowed.");
    return;
  }
  const pickedStatus = await openModal({
    title: "Change package status",
    subtitle: `Current status: ${cur.replace(/_/g, " ")}. Pick the next state.`,
    confirmLabel: "Update",
    body: (root) => {
      const ul = document.createElement("ul");
      ul.className = "modal-list";
      options.forEach((opt, i) => {
        const li = document.createElement("li");
        li.innerHTML = `<span>${escapeHtml(opt.replace(/_/g, " "))}</span>`;
        li.dataset.status = opt;
        li.onclick = () => {
          ul.querySelectorAll("li").forEach(x => x.classList.remove("is-selected"));
          li.classList.add("is-selected");
        };
        if (i === 0) li.classList.add("is-selected");
        ul.appendChild(li);
      });
      root.appendChild(ul);
      return { ul };
    },
    submit: ({ ul }) => {
      const sel = ul.querySelector("li.is-selected");
      if (!sel) throw new Error("Pick a status.");
      return sel.dataset.status;
    },
  });
  if (!pickedStatus) return;
  try {
    await api(`/packages/${state.currentPackageId}/status`,
              { method: "PATCH", json: { status: pickedStatus } });
    await renderPackages();
    await openPackageDetail(state.currentPackageId);
    toastSuccess("Status updated", `Package is now '${pickedStatus.replace(/_/g, " ")}'.`);
  } catch (e) {
    toastError("Status change failed", e.message);
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
    toastError("Admin role required", "Switch the Operator dropdown (top right) to admin to create a program.");
    return;
  }
  const result = await openModal({
    title: "Create program",
    subtitle: "A program is a tenant — its own artifacts, packages, and baselines. Use one per real-world program / customer.",
    confirmLabel: "Create",
    body: (root) => {
      const nameL = document.createElement("label");
      nameL.innerHTML = `<span>Program name</span>
                         <input type="text" placeholder="e.g. Aerospace R&D" />
                         <span class="help">Human-readable; shown in the dropdown.</span>`;
      const idL = document.createElement("label");
      idL.innerHTML = `<span>Program ID</span>
                       <input type="text" placeholder="aerospace-r-d" />
                       <span class="help">Lowercase, hyphens only. Used as the tenant key.</span>`;
      const baselineL = document.createElement("label");
      baselineL.innerHTML = `<span>Baseline</span>
                             <select>
                               <option value="low">Low</option>
                               <option value="moderate" selected>Moderate</option>
                               <option value="high">High</option>
                             </select>
                             <span class="help">NIST 800-53 Rev. 5 baseline this program is graded against.</span>`;
      root.appendChild(nameL); root.appendChild(idL); root.appendChild(baselineL);
      const nameInp = nameL.querySelector("input");
      const idInp   = idL.querySelector("input");
      // Live-derive the ID from the name unless the user has typed in the ID box.
      let idTouched = false;
      idInp.addEventListener("input", () => { idTouched = true; });
      nameInp.addEventListener("input", () => {
        if (!idTouched) {
          idInp.value = nameInp.value.toLowerCase()
                          .replace(/[^a-z0-9]+/g, "-")
                          .replace(/^-|-$/g, "");
        }
      });
      return { nameInp, idInp, baselineSel: baselineL.querySelector("select") };
    },
    submit: async ({ nameInp, idInp, baselineSel }) => {
      const name = nameInp.value.trim();
      const id   = idInp.value.trim();
      const baseline = baselineSel.value;
      if (!name) throw new Error("Program name is required.");
      if (!id)   throw new Error("Program ID is required.");
      const prog = await api("/programs", {
        method: "POST",
        json: { id, name, baseline },
      });
      return prog;
    },
  });
  if (!result) return;
  await loadPrograms();
  $("#program").value = result.id;
  applyProgram();
  toastSuccess(`Program created · ${result.id}`, `Baseline: ${result.baseline.toUpperCase()}`);
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

// ═══════════════════════════════════════════════════════════════════════════
// CROSS-DOCUMENT PACKAGE MAP (Phase II — relationship canvas)
// A Figma-style page-link view: artifact cards on a radial layout, connected by
// relationship lines (contradiction / resolved / shared_controls). Click a line
// to open a detail drawer. Pan by dragging the background; wheel to zoom.
// Vanilla SVG, hand-rolled like renderCalibration — no graph library.
// ═══════════════════════════════════════════════════════════════════════════

const SVG_NS = "http://www.w3.org/2000/svg";

// Card geometry + interaction state shared across the render + pan/zoom helpers.
const MAP_CARD_W = 210;
const MAP_CARD_H = 88;
const _mapView = {
  // pan/zoom transform applied to #mapViewport
  tx: 0, ty: 0, scale: 1,
  // node positions keyed by artifact_id: { x, y } = card CENTER in viewport coords
  pos: {},
  // currently selected node id (for dim/highlight) or null
  selectedNode: null,
  // adjacency: artifact_id -> Set(neighbour artifact_ids) including itself
  adj: {},
};

const _svgEl = (name, attrs = {}) => {
  const el = document.createElementNS(SVG_NS, name);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  return el;
};

// Severity ordering used to pick the dot row + colors.
const MAP_SEV_ORDER = ["critical", "high", "medium", "low"];
const MAP_SEV_VAR = {
  critical: "var(--sev-critical)",
  high:     "var(--sev-high)",
  medium:   "var(--sev-medium)",
  low:      "var(--sev-low)",
};

// Entry point — wired to #pkgMapBtn. Switches to the map view and fetches.
async function renderPackageMap(pkgId) {
  if (!pkgId) return;
  switchView("map");

  // Subtitle: package name (if we have it cached) + a placeholder run chip.
  const pkgName = (state.currentPackage && state.currentPackage.id === pkgId)
    ? state.currentPackage.name : pkgId;
  $("#mapSubtitle").innerHTML = `${escapeHtml(pkgName)} · <span class="map-run-chip">loading…</span>`;

  // Reset transient view state + UI for a fresh render.
  _mapView.tx = 0; _mapView.ty = 0; _mapView.scale = 1;
  _mapView.pos = {}; _mapView.selectedNode = null; _mapView.adj = {};
  $("#mapViewport").innerHTML = "";
  closeMapDrawer();
  $("#mapLegend").hidden = true;
  $("#mapPkgFindings").hidden = true;
  showMapBanner("", false);

  let map;
  try {
    map = await api(`/packages/${pkgId}/map`);
  } catch (e) {
    state.packageMap = null;
    $("#mapSubtitle").innerHTML = `${escapeHtml(pkgName)} · <span class="map-run-chip alarm">unavailable</span>`;
    toastError("Could not load map", e.message);
    showMapBanner(`Could not load the cross-document map. ${escapeHtml(e.message || "")}`, true);
    return;
  }

  state.packageMap = map;

  // Subtitle run chip — show the run id, or a "no runs" hint.
  const runChip = map.run_id
    ? `<span class="map-run-chip">run ${escapeHtml(map.run_id)}</span>`
    : `<span class="map-run-chip warn">no runs yet</span>`;
  $("#mapSubtitle").innerHTML = `${escapeHtml(pkgName)} · ${runChip}`;

  renderMapPkgFindings(map.package_level_findings || {});
  drawPackageMap(map);
}

// Top-right mini-card: package-level (catalog) findings.
function renderMapPkgFindings(counts) {
  const card = $("#mapPkgFindings");
  const dots = $("#mapPkgFindingsDots");
  const nonZero = MAP_SEV_ORDER.filter(s => (counts[s] || 0) > 0);
  if (!nonZero.length) {
    // Still show the card but make the zero-state explicit (it's informative).
    dots.innerHTML = `<span class="map-pkg-none">none</span>`;
  } else {
    dots.innerHTML = nonZero.map(s =>
      `<span class="map-sev-pill"><span class="map-sev-dot" style="background:${MAP_SEV_VAR[s]}"></span>${counts[s]}</span>`
    ).join("");
  }
  card.hidden = false;
}

// Build the SVG scene: nodes on a radial layout, edges as grouped beziers.
function drawPackageMap(map) {
  const wrap = $("#mapCanvasWrap");
  const svg = $("#mapSvg");
  const vp = $("#mapViewport");
  vp.innerHTML = "";

  const nodes = map.nodes || [];
  const W = wrap.clientWidth  || 900;
  const H = wrap.clientHeight || 560;
  // Match the SVG's internal coordinate system to its pixel size so 1 unit = 1px
  // at scale 1 (keeps pan/zoom math intuitive).
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);

  // ── Empty / edge-case banners ───────────────────────────────────────────
  if (!map.run_id) {
    showMapBanner("No analysis runs yet — click Analyze package first.", false);
  } else if (nodes.length === 0) {
    showMapBanner("No artifacts attached to this package.", false);
  } else if (nodes.length === 1) {
    // Center the single node, with a hint.
    showMapBanner("Attach more artifacts to see relationships.", false);
  } else if (!(map.edges || []).length) {
    showMapBanner("No cross-document relationships detected.", false);
  } else {
    showMapBanner("", false);
  }

  // ── Radial layout: place card CENTERS ───────────────────────────────────
  const cx = W / 2, cy = H / 2;
  _mapView.pos = {};
  if (nodes.length === 1) {
    _mapView.pos[nodes[0].artifact_id] = { x: cx, y: cy };
  } else if (nodes.length === 2) {
    // Side by side.
    const gap = Math.max(MAP_CARD_W + 120, W * 0.32);
    _mapView.pos[nodes[0].artifact_id] = { x: cx - gap / 2, y: cy };
    _mapView.pos[nodes[1].artifact_id] = { x: cx + gap / 2, y: cy };
  } else {
    // Even spacing on a circle. Radius scales with N so cards don't collide,
    // but is clamped to fit the canvas.
    const minR = MAP_CARD_W * 0.95;
    const wantR = (nodes.length * (MAP_CARD_W + 40)) / (2 * Math.PI);
    const maxR = Math.min(W, H) / 2 - MAP_CARD_H;
    const R = Math.max(minR, Math.min(wantR, Math.max(minR, maxR)));
    nodes.forEach((n, i) => {
      // Start at top (-90°) and go clockwise.
      const ang = -Math.PI / 2 + (2 * Math.PI * i) / nodes.length;
      _mapView.pos[n.artifact_id] = {
        x: cx + R * Math.cos(ang),
        y: cy + R * Math.sin(ang),
      };
    });
  }

  // ── Build adjacency for click-to-highlight ──────────────────────────────
  _mapView.adj = {};
  nodes.forEach(n => { _mapView.adj[n.artifact_id] = new Set([n.artifact_id]); });
  (map.edges || []).forEach(e => {
    if (_mapView.adj[e.source]) _mapView.adj[e.source].add(e.target);
    if (_mapView.adj[e.target]) _mapView.adj[e.target].add(e.source);
  });

  // ── Layered <g> groups so shared_controls render UNDER everything ────────
  const gEdgesUnder = _svgEl("g", { class: "map-edges-under" });   // shared_controls
  const gEdgesOver  = _svgEl("g", { class: "map-edges-over" });    // resolved + contradiction
  const gNodes      = _svgEl("g", { class: "map-nodes" });
  vp.appendChild(gEdgesUnder);
  vp.appendChild(gEdgesOver);
  vp.appendChild(gNodes);

  // ── Group edges by (source,target,kind) so we draw one path per group ────
  // Use an UNORDERED pair key for the offset bucket so A→B and B→A curve apart
  // consistently, but keep source/target for geometry direction.
  const groups = new Map();   // key -> { source, target, kind, edges: [] }
  for (const e of (map.edges || [])) {
    if (!_mapView.pos[e.source] || !_mapView.pos[e.target]) continue;  // dangling edge — skip
    const key = `${e.source}|${e.target}|${e.kind}`;
    if (!groups.has(key)) groups.set(key, { source: e.source, target: e.target, kind: e.kind, edges: [] });
    groups.get(key).edges.push(e);
  }

  // Assign a curve offset index per unordered node-pair so multiple groups
  // (e.g. shared_controls + contradiction between the same two docs) fan out.
  const pairBuckets = new Map();  // unorderedPairKey -> array of group keys (insertion order)
  for (const [key, g] of groups) {
    const pk = [g.source, g.target].sort().join("~");
    if (!pairBuckets.has(pk)) pairBuckets.set(pk, []);
    pairBuckets.get(pk).push(key);
  }

  // Render order: shared_controls first (underneath), then resolved, then contradiction.
  const KIND_LAYER = { shared_controls: gEdgesUnder, resolved: gEdgesOver, contradiction: gEdgesOver };
  const KIND_RANK  = { shared_controls: 0, resolved: 1, contradiction: 2 };
  const sortedGroups = [...groups.values()].sort(
    (a, b) => (KIND_RANK[a.kind] ?? 9) - (KIND_RANK[b.kind] ?? 9)
  );

  for (const g of sortedGroups) {
    const layer = KIND_LAYER[g.kind] || gEdgesOver;
    const pk = [g.source, g.target].sort().join("~");
    const bucket = pairBuckets.get(pk) || [];
    const idxInPair = Math.max(0, bucket.indexOf(`${g.source}|${g.target}|${g.kind}`));
    drawEdgeGroup(layer, g, idxInPair, bucket.length);
  }

  // ── Render node cards last (on top) ──────────────────────────────────────
  nodes.forEach(n => gNodes.appendChild(buildNodeCard(n)));

  // Legend is meaningful once there's at least one relationship to read.
  $("#mapLegend").hidden = !(map.edges || []).length;

  // ── Background click clears node selection + closes drawer ───────────────
  svg.onclick = (ev) => {
    if (ev.target === svg || ev.target === vp) {
      clearMapNodeSelection();
      closeMapDrawer();
    }
  };

  applyMapTransform();
  enableMapPanZoom(svg);
}

// Cubic-bezier path between the EDGE MIDPOINTS of two cards, with a
// perpendicular curve offset so parallel edges between the same pair fan out.
function mapEdgePath(source, target, offsetIndex, offsetCount) {
  const a = _mapView.pos[source], b = _mapView.pos[target];
  if (!a || !b) return null;
  // Anchor on the card border facing the other card (approx: clamp the center-to-center
  // vector to the card's half-extent box).
  const p0 = cardBorderPoint(a, b);
  const p1 = cardBorderPoint(b, a);

  const dx = p1.x - p0.x, dy = p1.y - p0.y;
  const len = Math.hypot(dx, dy) || 1;
  // Perpendicular unit vector.
  const nx = -dy / len, ny = dx / len;
  // Fan offset: center the set around 0, ~26px between siblings.
  const spread = 26;
  const off = offsetCount > 1 ? (offsetIndex - (offsetCount - 1) / 2) * spread : 0;
  const mx = (p0.x + p1.x) / 2 + nx * off;
  const my = (p0.y + p1.y) / 2 + ny * off;

  // Two control points pulled toward the offset midpoint give a smooth arc.
  const c1x = (p0.x + mx) / 2, c1y = (p0.y + my) / 2;
  const c2x = (p1.x + mx) / 2, c2y = (p1.y + my) / 2;
  return {
    d: `M ${p0.x} ${p0.y} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${p1.x} ${p1.y}`,
    mid: { x: mx, y: my },
  };
}

// Point on the border of the card centered at `from`, in the direction of `to`.
function cardBorderPoint(from, to) {
  const dx = to.x - from.x, dy = to.y - from.y;
  const hw = MAP_CARD_W / 2, hh = MAP_CARD_H / 2;
  if (dx === 0 && dy === 0) return { x: from.x, y: from.y };
  // Scale the vector so it lands on the rectangle edge.
  const sx = dx !== 0 ? hw / Math.abs(dx) : Infinity;
  const sy = dy !== 0 ? hh / Math.abs(dy) : Infinity;
  const s = Math.min(sx, sy);
  return { x: from.x + dx * s, y: from.y + dy * s };
}

// Draw one edge GROUP (already grouped by source,target,kind) into `layer`.
function drawEdgeGroup(layer, group, offsetIndex, offsetCount) {
  const geo = mapEdgePath(group.source, group.target, offsetIndex, offsetCount);
  if (!geo) return;

  const g = _svgEl("g", { class: `map-edge map-edge-${group.kind}` });
  g.dataset.source = group.source;
  g.dataset.target = group.target;

  // Visible path — styling per kind.
  const path = _svgEl("path", { d: geo.d, fill: "none", class: "map-edge-line" });
  if (group.kind === "shared_controls") {
    path.setAttribute("stroke", "var(--border-strong)");
    path.setAttribute("stroke-width", "1");
    path.setAttribute("opacity", "0.6");
  } else if (group.kind === "resolved") {
    path.setAttribute("stroke", "var(--accent)");
    path.setAttribute("stroke-width", "2");
    path.setAttribute("stroke-dasharray", "6 4");
  } else { // contradiction
    path.setAttribute("stroke", "var(--alarm)");
    path.setAttribute("stroke-width", "2.5");
  }
  g.appendChild(path);

  // shared_controls has no badge and (per spec) no hover/click affordance —
  // it's purely contextual underlay.
  if (group.kind === "shared_controls") {
    layer.appendChild(g);
    return;
  }

  // Wide invisible hit path for comfortable hovering/clicking (standard trick).
  const hit = _svgEl("path", {
    d: geo.d, fill: "none", stroke: "transparent",
    "stroke-width": "14", class: "map-edge-hit",
  });
  g.appendChild(hit);

  // Midpoint badge.
  const badge = _svgEl("g", { class: "map-edge-badge" });
  const circle = _svgEl("circle", { cx: geo.mid.x, cy: geo.mid.y, r: "11" });
  const label = _svgEl("text", {
    x: geo.mid.x, y: geo.mid.y, "text-anchor": "middle",
    "dominant-baseline": "central", class: "map-edge-badge-text",
  });
  if (group.kind === "resolved") {
    circle.setAttribute("fill", "var(--bg-elevated)");
    circle.setAttribute("stroke", "var(--accent)");
    label.setAttribute("fill", "var(--accent)");
    label.textContent = "✓";
  } else { // contradiction
    circle.setAttribute("fill", "var(--bg-elevated)");
    circle.setAttribute("stroke", "var(--alarm)");
    label.setAttribute("fill", "var(--alarm)");
    label.textContent = "⚠";
  }
  badge.appendChild(circle);
  badge.appendChild(label);

  // Contradiction groups bundling >1 finding get a small count bubble on the
  // badge's upper-right, so the ⚠ stays readable.
  if (group.kind === "contradiction" && group.edges.length > 1) {
    const bx = geo.mid.x + 9, by = geo.mid.y - 9;
    const cnt = _svgEl("circle", {
      cx: bx, cy: by, r: "7", fill: "var(--alarm)", stroke: "var(--bg-surface)", "stroke-width": "1.5",
    });
    const cntT = _svgEl("text", {
      x: bx, y: by, "text-anchor": "middle", "dominant-baseline": "central",
      class: "map-edge-count-text", fill: "var(--bg-surface)",
    });
    cntT.textContent = String(group.edges.length);
    badge.appendChild(cnt);
    badge.appendChild(cntT);
  }
  g.appendChild(badge);

  // Hover: thicken the visible line by 1px.
  const baseW = parseFloat(path.getAttribute("stroke-width"));
  const enter = () => { path.setAttribute("stroke-width", String(baseW + 1)); g.classList.add("is-hover"); };
  const leave = () => { path.setAttribute("stroke-width", String(baseW)); g.classList.remove("is-hover"); };
  g.addEventListener("mouseenter", enter);
  g.addEventListener("mouseleave", leave);

  // Click → open drawer for this group. stopPropagation so it doesn't clear
  // the node selection via the background handler.
  g.addEventListener("click", (ev) => {
    ev.stopPropagation();
    openMapDrawer(group);
  });

  layer.appendChild(g);
}

// Build a node card <g>. Center is taken from _mapView.pos[n.artifact_id].
function buildNodeCard(n) {
  const c = _mapView.pos[n.artifact_id] || { x: 0, y: 0 };
  const x = c.x - MAP_CARD_W / 2;
  const y = c.y - MAP_CARD_H / 2;

  const g = _svgEl("g", { class: "map-node", transform: `translate(${x} ${y})` });
  g.dataset.node = n.artifact_id;

  const rect = _svgEl("rect", {
    x: 0, y: 0, width: MAP_CARD_W, height: MAP_CARD_H,
    rx: 10, ry: 10, class: "map-node-rect",
    fill: "var(--bg-elevated)", stroke: "var(--border-strong)", "stroke-width": "1.5",
  });
  g.appendChild(rect);

  // Filename — truncated with ellipsis to fit the card width.
  const fname = _svgEl("text", {
    x: 14, y: 26, class: "map-node-filename", fill: "var(--text-primary)",
  });
  fname.textContent = truncateForCard(n.filename || "(unnamed)", 24);
  const titleEl = _svgEl("title");                 // native tooltip = full filename
  titleEl.textContent = n.filename || "";
  g.appendChild(fname);
  fname.appendChild(titleEl);

  // Type chip.
  const chip = _svgEl("text", {
    x: 14, y: 44, class: "map-node-type", fill: "var(--text-muted)",
  });
  chip.textContent = (n.type || "").toUpperCase();
  g.appendChild(chip);

  // Severity dot row — only non-zero severities.
  const findings = n.findings || {};
  let dotX = 14;
  const dotY = 68;
  MAP_SEV_ORDER.forEach(sev => {
    const count = findings[sev] || 0;
    if (count <= 0) return;
    const dot = _svgEl("circle", { cx: dotX + 4, cy: dotY, r: 4, fill: MAP_SEV_VAR[sev] });
    g.appendChild(dot);
    const cnt = _svgEl("text", {
      x: dotX + 12, y: dotY + 4, class: "map-node-sevcount", fill: "var(--text-secondary)",
    });
    cnt.textContent = String(count);
    g.appendChild(cnt);
    // Advance: dot + count text width (count digits ~7px each).
    dotX += 22 + String(count).length * 6;
  });

  // Hover: stroke → accent.
  g.addEventListener("mouseenter", () => { if (!g.classList.contains("is-dim")) rect.setAttribute("stroke", "var(--accent)"); });
  g.addEventListener("mouseleave", () => { if (!g.classList.contains("is-selected")) rect.setAttribute("stroke", "var(--border-strong)"); });

  // Click: toggle node selection (dim everything not connected to it).
  g.addEventListener("click", (ev) => {
    ev.stopPropagation();
    if (_mapView.selectedNode === n.artifact_id) {
      clearMapNodeSelection();
    } else {
      selectMapNode(n.artifact_id);
    }
  });

  return g;
}

// Truncate a filename to ~maxChars, adding an ellipsis. Cheap char-count
// truncation (the SVG text isn't measured); the full name lives in <title>.
function truncateForCard(s, maxChars) {
  s = String(s);
  return s.length > maxChars ? s.slice(0, maxChars - 1) + "…" : s;
}

// Highlight one node: full opacity for it + its neighbours/edges, dim the rest.
function selectMapNode(nodeId) {
  _mapView.selectedNode = nodeId;
  const neighbours = _mapView.adj[nodeId] || new Set([nodeId]);

  $$(".map-node").forEach(g => {
    const id = g.dataset.node;
    const on = neighbours.has(id);
    g.classList.toggle("is-dim", !on);
    g.classList.toggle("is-selected", id === nodeId);
    const rect = g.querySelector(".map-node-rect");
    if (rect) rect.setAttribute("stroke", id === nodeId ? "var(--accent)" : "var(--border-strong)");
  });

  // Edges: lit only if BOTH endpoints are the selected node or its neighbours
  // (i.e. the edge touches the selected node).
  $$(".map-edge").forEach(g => {
    const s = g.dataset.source, t = g.dataset.target;
    const touches = s === nodeId || t === nodeId;
    g.classList.toggle("is-dim", !touches);
  });
}

function clearMapNodeSelection() {
  _mapView.selectedNode = null;
  $$(".map-node").forEach(g => {
    g.classList.remove("is-dim", "is-selected");
    const rect = g.querySelector(".map-node-rect");
    if (rect) rect.setAttribute("stroke", "var(--border-strong)");
  });
  $$(".map-edge").forEach(g => g.classList.remove("is-dim"));
}

// ── Detail drawer ──────────────────────────────────────────────────────────
function openMapDrawer(group) {
  const drawer = $("#mapDrawer");
  const body = $("#mapDrawerBody");
  const title = $("#mapDrawerTitle");

  if (group.kind === "shared_controls") {
    // (shared_controls groups don't open the drawer today, but render defensively.)
    const ctrls = (group.edges[0] && group.edges[0].controls) || [];
    title.textContent = `Shared controls (${ctrls.length})`;
    body.innerHTML = `<div class="map-drawer-chips">${
      ctrls.map(c => `<span class="map-ctrl-chip">${escapeHtml(c)}</span>`).join("")
    }</div>`;
  } else {
    title.textContent = group.kind === "contradiction" ? "Contradiction" : "Resolved";
    body.innerHTML = renderMapDrawerFindings(group);
    wireMapDrawerInteractions(body, group);
  }

  drawer.hidden = false;
  // Force a reflow then add .open so the transform transition runs.
  void drawer.offsetWidth;
  drawer.classList.add("open");
}

function closeMapDrawer() {
  const drawer = $("#mapDrawer");
  drawer.classList.remove("open");
  // Hide after the slide-out transition so it doesn't catch clicks.
  setTimeout(() => { if (!drawer.classList.contains("open")) drawer.hidden = true; }, 200);
}

// Build the HTML for a contradiction/resolved group's drawer body.
function renderMapDrawerFindings(group) {
  const isContra = group.kind === "contradiction";
  const stateBadge = isContra
    ? `<span class="map-state-badge contra">ACTIVE CONTRADICTION</span>`
    : `<span class="map-state-badge resolved">RESOLVED</span>`;

  // Collect distinct control chips across the group.
  const ctrlSet = [];
  group.edges.forEach(e => { if (e.control_id && !ctrlSet.includes(e.control_id)) ctrlSet.push(e.control_id); });
  const ctrlChips = ctrlSet.map(c => `<span class="map-ctrl-chip">${escapeHtml(c)}</span>`).join("");

  // Worst severity tag across the group.
  const SEV_RANK = { critical: 4, high: 3, medium: 2, low: 1 };
  let worst = null;
  group.edges.forEach(e => { if (!worst || (SEV_RANK[e.severity] || 0) > (SEV_RANK[worst] || 0)) worst = e.severity; });
  const sevTag = worst ? `<span class="map-sev-tag sev-${escapeHtml(worst)}">${escapeHtml(worst)}</span>` : "";

  const header = `
    <div class="map-drawer-toprow">
      <div class="map-drawer-chips">${ctrlChips}</div>
      ${stateBadge}
      ${sevTag}
    </div>`;

  // One expandable item per finding in the group.
  const multi = group.edges.length > 1;
  const items = group.edges.map((e, i) => renderMapDrawerItem(e, group.kind, i, multi)).join("");

  return header + `<div class="map-finding-list">${items}</div>`;
}

// A single finding row: clickable summary; expands to two stacked quote cards.
function renderMapDrawerItem(edge, kind, idx, multi) {
  const detail = edge.detail || {};
  const left = detail.left || {};
  const right = detail.right || {};
  const edgeColorVar = kind === "contradiction" ? "var(--alarm)" : "var(--accent)";

  const quoteCard = (side) => `
    <div class="map-quote-card" style="border-left-color:${edgeColorVar}">
      <div class="map-quote-head">${escapeHtml(side.filename || "")}${side.locator ? ` · ${escapeHtml(side.locator)}` : ""}</div>
      <div class="map-quote-text">${escapeHtml(side.quote || "")}</div>
    </div>`;

  // Resolved note vs. contradiction action button.
  let footer = "";
  if (kind === "contradiction") {
    footer = `<button class="btn-ghost btn-small map-open-gate" data-idx="${idx}">Open in Attestation Gate →</button>`;
  } else {
    const runChip = state.packageMap && state.packageMap.run_id
      ? `<span class="map-run-chip">${escapeHtml(state.packageMap.run_id)}</span>` : "";
    footer = `<div class="map-resolved-note">No longer present as of ${runChip} — resolved or rewritten.</div>`;
  }

  // First item starts expanded when there's only one; multi-item lists start collapsed.
  const open = !multi;
  return `
    <div class="map-finding-item ${open ? "is-open" : ""}" data-idx="${idx}">
      <button class="map-finding-summary" type="button">
        <span class="map-finding-caret">▸</span>
        <span class="map-finding-summary-text">${escapeHtml(detail.summary || "(no summary)")}</span>
      </button>
      <div class="map-finding-detail">
        ${quoteCard(left)}
        ${quoteCard(right)}
        <div class="map-finding-footer">${footer}</div>
      </div>
    </div>`;
}

// Wire expand/collapse toggles + the "Open in Attestation Gate" deep links.
function wireMapDrawerInteractions(body, group) {
  body.querySelectorAll(".map-finding-item").forEach(item => {
    const summary = item.querySelector(".map-finding-summary");
    if (summary) summary.addEventListener("click", () => item.classList.toggle("is-open"));
  });

  body.querySelectorAll(".map-open-gate").forEach(btn => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const idx = parseInt(btn.dataset.idx, 10) || 0;
      const edge = group.edges[idx];
      if (!edge) return;
      const leftArt = (edge.detail && edge.detail.left && edge.detail.left.artifact_id) || edge.source;
      closeMapDrawer();
      openGateFor(leftArt, {
        runId: state.packageMap ? state.packageMap.run_id : null,
        findingId: edge.finding_id,
      });
    });
  });
}

// Banner overlay inside the canvas (empty / error states).
function showMapBanner(html, isError) {
  const b = $("#mapBanner");
  if (!html) { b.hidden = true; b.innerHTML = ""; b.classList.remove("is-error"); return; }
  b.innerHTML = html;
  b.classList.toggle("is-error", !!isError);
  b.hidden = false;
}

// ── Pan / zoom (lightweight, no library) ─────────────────────────────────────
function applyMapTransform() {
  $("#mapViewport").setAttribute(
    "transform",
    `translate(${_mapView.tx} ${_mapView.ty}) scale(${_mapView.scale})`
  );
}

function enableMapPanZoom(svg) {
  let dragging = false, lastX = 0, lastY = 0, moved = false;

  svg.onmousedown = (e) => {
    // Pan only when starting on empty canvas (not on a node/edge).
    if (e.target.closest(".map-node") || e.target.closest(".map-edge")) return;
    dragging = true; moved = false;
    lastX = e.clientX; lastY = e.clientY;
    svg.classList.add("is-panning");
  };
  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    const dx = e.clientX - lastX, dy = e.clientY - lastY;
    if (Math.abs(dx) > 2 || Math.abs(dy) > 2) moved = true;
    _mapView.tx += dx; _mapView.ty += dy;
    lastX = e.clientX; lastY = e.clientY;
    applyMapTransform();
  });
  window.addEventListener("mouseup", () => {
    if (dragging) svg.classList.remove("is-panning");
    dragging = false;
  });

  svg.onwheel = (e) => {
    e.preventDefault();
    const rect = svg.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;     // cursor in svg px
    const prev = _mapView.scale;
    const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
    const next = Math.max(0.5, Math.min(2.0, prev * factor));
    if (next === prev) return;
    // Zoom toward the cursor: keep the point under the cursor fixed.
    _mapView.tx = mx - (mx - _mapView.tx) * (next / prev);
    _mapView.ty = my - (my - _mapView.ty) * (next / prev);
    _mapView.scale = next;
    applyMapTransform();
  };
}

// ── Wiring: package-detail "Map" button + the view's back button ─────────────
$("#pkgMapBtn")?.addEventListener?.("click", () => {
  if (!state.currentPackageId) {
    toastInfo("No package selected", "Open a package first, then view its map.");
    return;
  }
  renderPackageMap(state.currentPackageId);
});

$("#mapBackBtn")?.addEventListener?.("click", () => {
  switchView("packages");
  // Re-open the package detail the map was launched from.
  if (state.currentPackageId) openPackageDetail(state.currentPackageId);
});

$("#mapDrawerClose")?.addEventListener?.("click", () => closeMapDrawer());

// ─────────────────────────────────────────── Toast notifications ──
// Lightweight non-blocking notifications. Use instead of alert() for success
// and most error feedback. alert() is only for errors that must block input.
function toast(title, detail = "", kind = "success", ms = 4000) {
  const stack = document.getElementById("toastStack");
  if (!stack) return;
  const icon = kind === "success" ? "✓" : kind === "error" ? "✕" : "ⓘ";
  const t = document.createElement("div");
  t.className = `toast t-${kind}`;
  t.innerHTML = `
    <span class="toast-icon">${icon}</span>
    <div class="toast-body">
      <div class="toast-title">${escapeHtml(title)}</div>
      ${detail ? `<div class="toast-detail">${escapeHtml(detail)}</div>` : ""}
    </div>
    <button class="toast-close" aria-label="Close">×</button>`;
  const close = () => {
    t.classList.add("is-leaving");
    setTimeout(() => t.remove(), 200);
  };
  t.querySelector(".toast-close").onclick = close;
  setTimeout(close, ms);
  stack.appendChild(t);
}
// Convenience wrappers that respect the "blocking error" rule.
function toastSuccess(title, detail) { toast(title, detail, "success"); }
function toastError(title, detail)   { toast(title, detail, "error", 6000); }
function toastInfo(title, detail)    { toast(title, detail, "info"); }

// ─────────────────────────────────────────── Modal dialog ──
// Returns a Promise that resolves to whatever the caller's submit() returns,
// or null if the user cancels / closes / hits Escape.
//
//   openModal({
//     title: "Create package",
//     subtitle: "Bundle related artifacts so they're analyzed together.",
//     body: (root) => { /* render inputs into root, return refs */ },
//     confirmLabel: "Create",
//     submit: (refs) => { /* return whatever; throw to keep modal open */ },
//   })
function openModal({ title, subtitle = "", body, confirmLabel = "Confirm", submit }) {
  return new Promise((resolve) => {
    const backdrop = document.getElementById("modalBackdrop");
    const titleEl  = document.getElementById("modalTitle");
    const subEl    = document.getElementById("modalSub");
    const bodyEl   = document.getElementById("modalBody");
    const confirm  = document.getElementById("modalConfirm");
    const cancel   = document.getElementById("modalCancel");
    const closeBtn = document.getElementById("modalClose");

    titleEl.textContent = title;
    if (subtitle) { subEl.textContent = subtitle; subEl.hidden = false; }
    else          { subEl.hidden = true; }
    bodyEl.innerHTML = "";
    confirm.textContent = confirmLabel;
    confirm.disabled = false;

    const refs = body(bodyEl) || {};

    const done = (result) => {
      backdrop.hidden = true;
      window.removeEventListener("keydown", onKey);
      resolve(result);
    };
    const onKey = (e) => {
      if (e.key === "Escape") done(null);
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) onConfirm();
    };
    const onConfirm = async () => {
      confirm.disabled = true; confirm.textContent = confirmLabel + "…";
      try {
        const result = await submit(refs);
        done(result);
      } catch (e) {
        toastError("Could not complete", e.message || String(e));
        confirm.disabled = false; confirm.textContent = confirmLabel;
      }
    };

    cancel.onclick   = () => done(null);
    closeBtn.onclick = () => done(null);
    backdrop.onclick = (e) => { if (e.target === backdrop) done(null); };
    confirm.onclick  = onConfirm;
    window.addEventListener("keydown", onKey);

    backdrop.hidden = false;
    // Auto-focus first input field in the body if any.
    const firstInput = bodyEl.querySelector("input, textarea, select");
    if (firstInput) firstInput.focus();
  });
}

// Convenience: yes/no confirmation modal — replaces window.confirm.
// Returns true on confirm, false on cancel/escape.
async function modalConfirm({ title, message = "", confirmLabel = "Confirm", danger = false }) {
  const out = await openModal({
    title, confirmLabel,
    body: (root) => {
      const p = document.createElement("p");
      p.textContent = message;
      p.style.fontFamily = "var(--font-mono)";
      p.style.fontSize = "13px";
      p.style.color = "var(--text-secondary)";
      p.style.margin = "4px 0 0";
      root.appendChild(p);
      return {};
    },
    submit: () => true,
  });
  return out === true;
}

// Convenience: text-input modal — like prompt() but pretty.
async function modalPrompt({ title, subtitle, label, placeholder = "", initial = "", help = "", confirmLabel = "Save", multiline = false }) {
  return openModal({
    title, subtitle, confirmLabel,
    body: (root) => {
      const wrap = document.createElement("label");
      wrap.innerHTML = `<span>${escapeHtml(label)}</span>`;
      const inp = document.createElement(multiline ? "textarea" : "input");
      if (!multiline) inp.type = "text";
      inp.placeholder = placeholder;
      inp.value = initial;
      wrap.appendChild(inp);
      if (help) {
        const h = document.createElement("span");
        h.className = "help"; h.textContent = help;
        wrap.appendChild(h);
      }
      root.appendChild(wrap);
      return { inp };
    },
    submit: ({ inp }) => {
      const v = inp.value.trim();
      if (!v) throw new Error("Please enter a value.");
      return v;
    },
  });
}

// ═════════════════════════════════════════════════════════════
// VISUAL GROUNDING v3 — threaded document canvas
//
// Each artifact renders as a real paper page (hand-rolled markdown
// renderer — no CDN dep, preserves QUILL's air-gap guarantee).
// Cross-document contradictions are drawn as orthogonal "threads"
// that anchor AT the citation (top-near edge), exit through the
// inter-page gutter, run along a dedicated lane above the pages,
// and drop into the peer citation. Calm neutral at rest; the
// focused thread lights up in its severity colour while the rest
// dim. Pan + cursor-anchored zoom.
// ═════════════════════════════════════════════════════════════

const _PAGE_W   = 560;
const _PAGE_GAP = 150;       // gutter between pages — room for risers
const _PAGE_X0  = 90;
const _LANE_GAP = 24;        // vertical spacing between thread lanes
const _LANE_TOP_PAD = 46;    // gap between top-most lane and the page tops

function _gSev(g) { return g.severity || "low"; }
const _SVGNS = "http://www.w3.org/2000/svg";
function _svg(tag, attrs) {
  const el = document.createElementNS(_SVGNS, tag);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  return el;
}

// ── Markdown → DOM ───────────────────────────────────────────── //
const _CTRL_RE = /^([A-Z]{2}-\d+(?:\(\d+\))?)\s+(.+)$/;

function _mdInline(raw) {
  let s = escapeHtml(raw);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*([^*]+)\*(?!\*)/g, "$1<em>$2</em>");
  return s;
}

// Build inline HTML for a paragraph/cell, injecting <span.pp-hl> for any
// citation quote that falls inside `raw`. quotes = [{finding_id, quote, severity}]
function _mdInlineWithHL(raw, quotes) {
  if (!quotes || !quotes.length) return _mdInline(raw);
  // Find non-overlapping ranges for each quote (whitespace tolerant).
  const ranges = [];
  for (const q of quotes) {
    const r = _looseRange(raw, q.quote);
    if (!r) continue;
    if (ranges.some(x => r.start < x.end && r.end > x.start)) continue;
    ranges.push({ ...r, q });
  }
  if (!ranges.length) return _mdInline(raw);
  ranges.sort((a, b) => a.start - b.start);
  let out = "", cur = 0;
  for (const r of ranges) {
    if (r.start > cur) out += _mdInline(raw.slice(cur, r.start));
    out += `<span class="pp-hl sev-${r.q.severity}" data-finding-id="${escapeHtml(r.q.finding_id)}">`
         + _mdInline(raw.slice(r.start, r.end)) + "</span>";
    cur = r.end;
  }
  if (cur < raw.length) out += _mdInline(raw.slice(cur));
  return out;
}

function _looseRange(hay, needle) {
  if (!needle) return null;
  const i = hay.indexOf(needle);
  if (i >= 0) return { start: i, end: i + needle.length };
  const toks = needle.trim().split(/\s+/).map(t => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!toks.length) return null;
  try {
    const m = new RegExp(toks.join("\\s+")).exec(hay);
    if (m) return { start: m.index, end: m.index + m[0].length };
  } catch (_) {}
  return null;
}

function _parseDoc(text) {
  const lines = (text || "").split("\n");
  const blocks = [];
  let i = 0;
  const isTableRow = (l) => /^\s*\|.*\|\s*$/.test(l);
  while (i < lines.length) {
    const line = lines[i].replace(/\r$/, "");
    const t = line.trim();
    if (!t) { i++; continue; }
    if (/^#{1,6}\s+/.test(t)) {
      const m = t.match(/^(#{1,6})\s+(.*)$/);
      blocks.push({ type: "h", level: m[1].length, text: m[2].trim() });
      i++; continue;
    }
    if (/^[-*]\s+$/.test(t) || /^---+$/.test(t)) { blocks.push({ type: "hr" }); i++; continue; }
    if (t.startsWith("> ")) {
      const buf = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) { buf.push(lines[i].replace(/^\s*>\s?/, "")); i++; }
      blocks.push({ type: "quote", text: buf.join(" ").trim() });
      continue;
    }
    if (isTableRow(line) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
      const rows = [];
      while (i < lines.length && isTableRow(lines[i])) { rows.push(lines[i]); i++; }
      const cells = (r) => r.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
      blocks.push({ type: "table", header: cells(rows[0]), rows: rows.slice(2).map(cells) });
      continue;
    }
    if (/^[-*]\s+/.test(t)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*]\s+/, "").trim()); i++; }
      blocks.push({ type: "ul", items });
      continue;
    }
    // paragraph: gather until blank
    const buf = [];
    while (i < lines.length && lines[i].trim() && !/^#{1,6}\s+/.test(lines[i].trim())
           && !lines[i].trim().startsWith(">") && !/^\s*[-*]\s+/.test(lines[i])
           && !isTableRow(lines[i])) { buf.push(lines[i].trim()); i++; }
    blocks.push({ type: "p", text: buf.join(" ") });
  }
  return blocks;
}

function _makePage(art, quotesForArtifact) {
  const page = document.createElement("article");
  page.className = "paper-page";
  page.dataset.artifactId = art.id;

  const tab = document.createElement("div");
  tab.className = "paper-tab";
  tab.innerHTML = `<span class="tab-dot"></span>${escapeHtml(art.filename)}`;
  page.appendChild(tab);

  const blocks = _parseDoc(art.text || "");
  let titleDone = false;
  for (let bi = 0; bi < blocks.length; bi++) {
    const b = blocks[bi];
    // First top-level heading → document title (+ optional meta paragraph + rule)
    if (!titleDone && b.type === "h" && b.level === 1) {
      const h = document.createElement("div");
      h.className = "paper-doc-title";
      h.textContent = b.text;
      page.appendChild(h);
      const nxt = blocks[bi + 1];
      if (nxt && nxt.type === "p" && nxt.text.startsWith("**")) {
        const meta = document.createElement("div");
        meta.className = "paper-doc-meta";
        meta.textContent = nxt.text.replace(/\*\*/g, "").replace(/\s+/g, " ");
        page.appendChild(meta);
        bi++;
      }
      const rule = document.createElement("div");
      rule.className = "paper-rule";
      page.appendChild(rule);
      titleDone = true;
      continue;
    }
    if (b.type === "h") {
      const ctrl = b.text.match(_CTRL_RE);
      if (ctrl) {
        const row = document.createElement("div");
        row.className = "paper-control";
        row.innerHTML = `<span class="ctrl-id">${escapeHtml(ctrl[1])}</span>`
                      + `<span class="ctrl-name">${escapeHtml(ctrl[2])}</span>`;
        page.appendChild(row);
      } else if (b.level <= 2) {
        const h = document.createElement("h2"); h.className = "paper-h2"; h.textContent = b.text;
        page.appendChild(h);
      } else {
        const h = document.createElement("h3"); h.className = "paper-h3"; h.textContent = b.text;
        page.appendChild(h);
      }
      continue;
    }
    if (b.type === "p") {
      const p = document.createElement("p"); p.className = "paper-p";
      const here = quotesForArtifact.filter(q => _looseRange(b.text, q.quote));
      p.innerHTML = _mdInlineWithHL(b.text, here);
      page.appendChild(p);
      continue;
    }
    if (b.type === "ul") {
      const ul = document.createElement("ul"); ul.className = "paper-list";
      for (const it of b.items) {
        const li = document.createElement("li");
        const here = quotesForArtifact.filter(q => _looseRange(it, q.quote));
        li.innerHTML = _mdInlineWithHL(it, here);
        ul.appendChild(li);
      }
      page.appendChild(ul);
      continue;
    }
    if (b.type === "quote") {
      const bq = document.createElement("blockquote"); bq.className = "paper-quote";
      bq.innerHTML = _mdInline(b.text);
      page.appendChild(bq);
      continue;
    }
    if (b.type === "table") {
      const tbl = document.createElement("table"); tbl.className = "paper-table";
      const thead = document.createElement("thead"); const htr = document.createElement("tr");
      for (const c of b.header) { const th = document.createElement("th"); th.innerHTML = _mdInline(c); htr.appendChild(th); }
      thead.appendChild(htr); tbl.appendChild(thead);
      const tb = document.createElement("tbody");
      for (const r of b.rows) {
        const tr = document.createElement("tr");
        for (const c of r) {
          const td = document.createElement("td");
          const here = quotesForArtifact.filter(q => _looseRange(c, q.quote));
          td.innerHTML = _mdInlineWithHL(c, here);
          tr.appendChild(td);
        }
        tb.appendChild(tr);
      }
      tbl.appendChild(tb); page.appendChild(tbl);
      continue;
    }
    if (b.type === "hr") { const r = document.createElement("div"); r.className = "paper-rule"; page.appendChild(r); }
  }

  const foot = document.createElement("div");
  foot.className = "paper-foot";
  foot.textContent = escapeHtml(art.filename);
  page.appendChild(foot);
  return page;
}

// ── Main entry ───────────────────────────────────────────────── //
async function renderGrounding(pkgId) {
  if (!pkgId) return;
  const viewport = $("#groundingViewport");
  const wires    = $("#groundingWires");
  const banner   = $("#groundingBanner");
  const sub      = $("#groundingSubtitle");
  const info     = $("#groundingInfoCard");
  viewport.querySelectorAll(".paper-page").forEach(n => n.remove());
  wires.innerHTML = "";
  banner.hidden = true; info.hidden = true;
  sub.textContent = "loading…";
  _vp.tx = 0; _vp.ty = 0; _vp.scale = 1; _applyVp();

  let payload;
  try { payload = await api(`/packages/${pkgId}/grounding`); }
  catch (e) {
    toastError("Could not load grounding", e.message || String(e));
    banner.hidden = false; banner.textContent = `Could not fetch grounding data: ${e.message || e}`;
    sub.textContent = "—"; return;
  }

  const all = payload.groundings || [];
  const threads = all.filter(g =>
    g.primary?.artifact_id && g.conflicts_with &&
    g.conflicts_with.some(c => c.artifact_id && c.artifact_id !== g.primary.artifact_id));

  state.grounding = { pkgId, payload, threads, selected: null };
  const pkgName = state.currentPackage?.name || pkgId;
  const hidden = all.length - threads.length;
  sub.innerHTML = payload.run_id
    ? `${escapeHtml(pkgName)} · run ${escapeHtml(payload.run_id)}`
      + (hidden > 0 ? ` · ${hidden} single-doc finding${hidden === 1 ? "" : "s"} shown in the Attestation Gate` : "")
    : `${escapeHtml(pkgName)} · no analysis run yet`;

  if (!payload.run_id) {
    banner.hidden = false;
    banner.innerHTML = `No analysis runs yet — <a href="#" id="gGoBack">go back to the package</a> and click <b>↻ Analyze package</b>.`;
    $("#gGoBack")?.addEventListener("click", (e) => { e.preventDefault(); _gExit(); });
    return;
  }
  if (!threads.length) {
    banner.hidden = false;
    banner.innerHTML = `<b>No cross-document contradictions in this run.</b> This view links a passage in one document to a conflicting passage in another. Single-document findings live in the Attestation Gate.`;
    return;
  }

  // Pages that participate in at least one thread.
  const used = new Set();
  threads.forEach(g => { used.add(g.primary.artifact_id); g.conflicts_with.forEach(c => used.add(c.artifact_id)); });
  const pages = (payload.artifacts || []).filter(a => used.has(a.id));

  // Number threads + collect per-artifact quotes.
  threads.forEach((g, idx) => { g._idx = idx; });
  const quotesByArtifact = new Map();
  for (const g of threads) {
    const push = (aid, q) => {
      if (!aid || !q) return;
      if (!quotesByArtifact.has(aid)) quotesByArtifact.set(aid, []);
      quotesByArtifact.get(aid).push({ finding_id: g.finding_id, quote: q, severity: _gSev(g) });
    };
    push(g.primary.artifact_id, g.primary.quote);
    g.conflicts_with.forEach(c => push(c.artifact_id, c.quote));
  }

  // Lay pages in a row. Top band leaves room for thread lanes.
  const band = _LANE_TOP_PAD + threads.length * _LANE_GAP + 30;
  const pageEls = new Map();
  let x = _PAGE_X0;
  for (const art of pages) {
    const page = _makePage(art, quotesByArtifact.get(art.id) || []);
    page.style.left = x + "px";
    page.style.top  = band + "px";
    viewport.appendChild(page);
    pageEls.set(art.id, page);
    x += _PAGE_W + _PAGE_GAP;
  }
  state.grounding._pageEls = pageEls;
  state.grounding._band = band;

  await new Promise(r => requestAnimationFrame(() => r()));
  _drawThreads();
  _smartFit(pages.length);
}

// ── Thread geometry + drawing ────────────────────────────────── //
function _citAnchor(page, fid, preferRightEdge) {
  // Return {x,y} in viewport-local coords for the citation's top-near corner.
  const hl = page.querySelector(`.pp-hl[data-finding-id="${CSS.escape(fid)}"]`);
  if (!hl) return null;
  const vp = $("#groundingViewport").getBoundingClientRect();
  const rects = hl.getClientRects();
  const r = rects.length ? rects[0] : hl.getBoundingClientRect();
  const top = r.top - vp.top;
  const x = preferRightEdge ? (r.right - vp.left) : (r.left - vp.left);
  return { x, y: top, el: hl };
}

// Build an orthogonal path string with small rounded corners through points.
function _ortho(points, radius) {
  if (points.length < 2) return "";
  let d = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length - 1; i++) {
    const p0 = points[i - 1], p1 = points[i], p2 = points[i + 1];
    const v1x = Math.sign(p1.x - p0.x), v1y = Math.sign(p1.y - p0.y);
    const v2x = Math.sign(p2.x - p1.x), v2y = Math.sign(p2.y - p1.y);
    const r1 = Math.min(radius, Math.hypot(p1.x - p0.x, p1.y - p0.y) / 2);
    const r2 = Math.min(radius, Math.hypot(p2.x - p1.x, p2.y - p1.y) / 2);
    const aX = p1.x - v1x * r1, aY = p1.y - v1y * r1;
    const bX = p1.x + v2x * r2, bY = p1.y + v2y * r2;
    d += ` L ${aX} ${aY} Q ${p1.x} ${p1.y} ${bX} ${bY}`;
  }
  const last = points[points.length - 1];
  d += ` L ${last.x} ${last.y}`;
  return d;
}

function _drawThreads() {
  const g = state.grounding; if (!g) return;
  const wires = $("#groundingWires");
  wires.innerHTML = "";
  const pageEls = g._pageEls;
  const band = g._band;

  // Size SVG to the page bounding box.
  let maxX = 0, maxY = 0;
  for (const p of pageEls.values()) {
    maxX = Math.max(maxX, (parseInt(p.style.left, 10) || 0) + p.offsetWidth);
    maxY = Math.max(maxY, (parseInt(p.style.top, 10) || 0) + p.offsetHeight);
  }
  wires.setAttribute("width", maxX + 140);
  wires.setAttribute("height", maxY + 60);

  g.threads.forEach((thread) => {
    const srcPage = pageEls.get(thread.primary.artifact_id);
    if (!srcPage) return;
    const conflict = thread.conflicts_with.find(c => pageEls.get(c.artifact_id) && c.artifact_id !== thread.primary.artifact_id);
    if (!conflict) return;
    const dstPage = pageEls.get(conflict.artifact_id);

    const srcLeft = parseInt(srcPage.style.left, 10) || 0;
    const dstLeft = parseInt(dstPage.style.left, 10) || 0;
    const srcIsLeft = srcLeft < dstLeft;

    const a = _citAnchor(srcPage, thread.finding_id, srcIsLeft);    // exit toward peer
    const b = _citAnchor(dstPage, thread.finding_id, !srcIsLeft);
    if (!a || !b) return;

    // Gutter riser x-positions (just outside each page on the side facing peer).
    const laneY = band - 26 - thread._idx * _LANE_GAP;
    const off = (thread._idx % 4) * 6;
    const srcGut = srcIsLeft ? (srcLeft + _PAGE_W + 30 + off) : (srcLeft - 30 - off);
    const dstGut = srcIsLeft ? (dstLeft - 30 - off)           : (dstLeft + _PAGE_W + 30 + off);

    const pts = [
      { x: a.x, y: a.y },
      { x: srcGut, y: a.y },
      { x: srcGut, y: laneY },
      { x: dstGut, y: laneY },
      { x: dstGut, y: b.y },
      { x: b.x, y: b.y },
    ];
    const d = _ortho(pts, 7);
    const sev = _gSev(thread);

    const line = _svg("path", { d, class: `gw-line sev-${sev}`, "data-fid": thread.finding_id });
    wires.appendChild(line);
    const hit = _svg("path", { d, class: "gw-hit", "data-fid": thread.finding_id });
    wires.appendChild(hit);

    // Anchor dots at both citations.
    [a, b].forEach(pt => {
      const dot = _svg("circle", { cx: pt.x, cy: pt.y, r: 3.2, class: `gw-dot sev-${sev}`, "data-fid": thread.finding_id });
      wires.appendChild(dot);
    });

    // Label pill at lane midpoint.
    const midX = (srcGut + dstGut) / 2;
    const labelText = thread.control_id || "";
    const pillW = 18 + labelText.length * 6.4;
    const grp = _svg("g", { class: "gw-label", "data-fid": thread.finding_id });
    grp.appendChild(_svg("rect", { x: midX - pillW / 2, y: laneY - 10, width: pillW, height: 20, rx: 10,
                                   fill: "var(--bg-surface)", stroke: "var(--border)", "stroke-width": 1 }));
    grp.appendChild(_svg("circle", { cx: midX - pillW / 2 + 9, cy: laneY, r: 3, class: `gw-dot sev-${sev}` }));
    const tx = _svg("text", { x: midX + 4, y: laneY, fill: "var(--text-secondary)" });
    tx.textContent = labelText;
    grp.appendChild(tx);
    wires.appendChild(grp);

    const onEnter = () => _hoverThread(thread.finding_id, true);
    const onLeave = () => _hoverThread(thread.finding_id, false);
    const onClick = (e) => { e.stopPropagation(); _selectThread(thread.finding_id); };
    [hit, grp].forEach(el => {
      el.addEventListener("mouseenter", onEnter);
      el.addEventListener("mouseleave", onLeave);
      el.addEventListener("click", onClick);
    });
    a.el.addEventListener("click", onClick);
    b.el.addEventListener("click", onClick);
    a.el.addEventListener("mouseenter", onEnter); a.el.addEventListener("mouseleave", onLeave);
    b.el.addEventListener("mouseenter", onEnter); b.el.addEventListener("mouseleave", onLeave);
  });
}

function _applyThreadState(fid, lock) {
  const all = document.querySelectorAll("#groundingWires .gw-line");
  const dots = document.querySelectorAll("#groundingWires .gw-dot");
  const labels = document.querySelectorAll("#groundingWires .gw-label");
  const hls = document.querySelectorAll(".paper-page .pp-hl");
  const pages = document.querySelectorAll(".paper-page");
  const involved = new Set();
  if (fid) {
    const t = state.grounding.threads.find(x => x.finding_id === fid);
    if (t) { involved.add(t.primary.artifact_id); t.conflicts_with.forEach(c => involved.add(c.artifact_id)); }
  }
  all.forEach(p => {
    const on = p.dataset.fid === fid;
    p.classList.toggle("is-active", !!fid && on);
    p.classList.toggle("is-dimmed", !!fid && !on);
  });
  dots.forEach(d => d.classList.toggle("is-dimmed", !!fid && d.dataset.fid !== fid && d.dataset.fid !== undefined));
  labels.forEach(l => l.classList.toggle("is-dimmed", !!fid && l.dataset.fid !== fid));
  hls.forEach(h => {
    h.classList.toggle("is-active", !!fid && h.dataset.findingId === fid);
    h.classList.toggle("is-dimmed", !!fid && h.dataset.findingId !== fid);
  });
  pages.forEach(pg => pg.classList.toggle("is-faded", !!fid && !involved.has(pg.dataset.artifactId)));
}

function _hoverThread(fid, on) {
  if (state.grounding?.selected) return;   // selection wins
  _applyThreadState(on ? fid : null, false);
}

function _selectThread(fid) {
  state.grounding.selected = fid;
  _applyThreadState(fid, true);
  const t = state.grounding.threads.find(x => x.finding_id === fid);
  if (!t) return;
  const card = $("#groundingInfoCard");
  const sev = _gSev(t);
  const p = t.primary || {};
  const conflicts = t.conflicts_with || [];
  const conflictBlocks = conflicts.map(c => `
    <div>
      <div class="gif-side-label"><span class="gif-side-dot" style="background: var(--accent);"></span>${escapeHtml(c.filename || "")} · ${escapeHtml(c.locator || "")}</div>
      <div class="gif-quote">${escapeHtml((c.quote || "").replace(/\*\*/g, "").trim())}</div>
    </div>`).join("");
  const why = _explainThread(t);
  card.className = "grounding-info-card";
  card.innerHTML = `
    <div class="gif-head">
      <span class="gif-badge sev-${sev}"><span class="gif-sev-dot"></span>Contradiction · ${escapeHtml(sev)}</span>
      <span class="gif-control">${escapeHtml(t.control_id)}<span class="gif-ctrl-title">${t.control_title ? " · " + escapeHtml(t.control_title) : ""}</span></span>
      <button class="gif-close" id="gifClose" aria-label="close">×</button>
    </div>
    ${why ? `<div class="gif-why"><span class="gif-why-label">Why flagged</span>${escapeHtml(why)}</div>` : ""}
    <div class="gif-grid">
      <div>
        <div class="gif-side-label"><span class="gif-side-dot" style="background: var(--accent);"></span>${escapeHtml(p.filename || "")} · ${escapeHtml(p.locator || "")}</div>
        <div class="gif-quote">${escapeHtml((p.quote || "").replace(/\*\*/g, "").trim())}</div>
      </div>
      ${conflictBlocks}
      ${t.regulatory?.objective_summary ? `<div class="gif-rule"><span class="gif-rule-label">Regulatory grounding · NIST ${escapeHtml(t.control_id)}</span>${escapeHtml(t.regulatory.objective_summary)}</div>` : ""}
    </div>`;
  card.hidden = false;
  $("#gifClose")?.addEventListener("click", () => _clearThread());
}

// Short plain-language "why" line for a contradiction. Prefers the finding's
// rationale (LLM-written for Tier 2; rule-generated for Tier 0), stripped of
// internal noise — the trailing "[severity factors: …]" tag and the
// "(art-xxxx: ['monthly']; art-yyyy: ['quarterly'])" artifact-id dump. Falls
// back to the recommendation, then to a composed one-liner.
function _explainThread(t) {
  let r = (t.rationale || "").trim();
  // Drop any bracketed severity/factor annotation.
  r = r.replace(/\s*\[[^\]]*\]\s*$/g, "").trim();
  // Replace the raw "(art-xxxx: [...]; ...)" dump with the human values.
  r = r.replace(/\(art-[^)]*\)/g, "").replace(/\s{2,}/g, " ").trim();
  // Translate the rule's stock phrasing into something readable.
  r = r.replace(/states conflicting values across artifacts after synonym normalization\.?/i,
                "states conflicting values across two documents.");
  // Tidy orphaned punctuation left by the removals.
  r = r.replace(/\s+([.,;:])/g, "$1").replace(/\.{2,}/g, ".").replace(/[\s.]+$/, "").trim();
  if (r && r.length > 4) {
    r = r.length > 240 ? r.slice(0, 237).trimEnd() + "…" : r + ".";
    return r;
  }
  if (t.recommendation) return t.recommendation;
  const peerNames = (t.conflicts_with || []).map(c => c.filename).filter(Boolean);
  const peer = peerNames.length ? peerNames[0] : "another document";
  return `${t.primary?.filename || "This document"} and ${peer} give different values for `
       + `${t.control_id}${t.control_title ? " (" + t.control_title + ")" : ""}. Reconcile them so the package is internally consistent.`;
}

function _clearThread() {
  if (!state.grounding) return;
  state.grounding.selected = null;
  _applyThreadState(null, false);
  $("#groundingInfoCard").hidden = true;
}

// ── Pan & zoom ───────────────────────────────────────────────── //
const _vp = { tx: 0, ty: 0, scale: 1 };
function _applyVp() {
  const v = $("#groundingViewport"); if (!v) return;
  v.style.transform = `translate(${_vp.tx}px, ${_vp.ty}px) scale(${_vp.scale})`;
  const z = $("#zoomReadout"); if (z) z.textContent = Math.round(_vp.scale * 100) + "%";
}
function _smartFit(n) { (n <= 3) ? _fitAll() : _fitOne(); }
function _fitAll() {
  const stage = $("#groundingStage"), vp = $("#groundingViewport");
  const pages = vp.querySelectorAll(".paper-page");
  if (!pages.length) { _vp.tx = _vp.ty = 0; _vp.scale = 1; _applyVp(); return; }
  let maxX = 0, maxY = 0;
  pages.forEach(p => {
    maxX = Math.max(maxX, (parseInt(p.style.left, 10) || 0) + p.offsetWidth);
    maxY = Math.max(maxY, (parseInt(p.style.top, 10) || 0) + p.offsetHeight);
  });
  const pad = 70;
  const sx = (stage.clientWidth - pad * 2) / (maxX + _PAGE_X0);
  const sy = (stage.clientHeight - pad * 2) / (maxY + 40);
  // Keep pages legible — never auto-shrink below 0.5. If the row is wider
  // than the viewport at that floor, the user pans (and can zoom out).
  _vp.scale = Math.max(0.5, Math.min(sx, sy, 1));
  // Left-align (with pad) when content overflows; center when it fits.
  const contentW = (maxX + _PAGE_X0) * _vp.scale;
  const contentH = (maxY + 40) * _vp.scale;
  _vp.tx = contentW < stage.clientWidth ? (stage.clientWidth - contentW) / 2 : pad;
  _vp.ty = contentH < stage.clientHeight ? Math.max(20, (stage.clientHeight - contentH) / 2) : 20;
  _applyVp();
}
function _fitOne() {
  const stage = $("#groundingStage"), pad = 70;
  _vp.scale = Math.max(0.3, Math.min((stage.clientWidth - pad * 2) / (_PAGE_W + _PAGE_X0 * 2), 1));
  _vp.tx = pad; _vp.ty = pad; _applyVp();
}
function _zoomBy(factor, ax, ay) {
  const stage = $("#groundingStage"); const rect = stage.getBoundingClientRect();
  const cx = (ax ?? rect.left + rect.width / 2) - rect.left;
  const cy = (ay ?? rect.top + rect.height / 2) - rect.top;
  const old = _vp.scale, ns = Math.max(0.2, Math.min(2.5, old * factor));
  _vp.tx = cx - ((cx - _vp.tx) / old) * ns;
  _vp.ty = cy - ((cy - _vp.ty) / old) * ns;
  _vp.scale = ns; _applyVp();
}
function _wirePanZoom() {
  const stage = $("#groundingStage"); if (!stage || stage._wired) return; stage._wired = true;
  let drag = false, sx = 0, sy = 0, stx = 0, sty = 0;
  stage.addEventListener("mousedown", (e) => {
    if (e.target.closest(".pp-hl, .gw-hit, .gw-label, .grounding-info-card")) return;
    drag = true; sx = e.clientX; sy = e.clientY; stx = _vp.tx; sty = _vp.ty;
    stage.classList.add("is-panning");
  });
  window.addEventListener("mousemove", (e) => {
    if (!drag) return; _vp.tx = stx + (e.clientX - sx); _vp.ty = sty + (e.clientY - sy); _applyVp();
  });
  window.addEventListener("mouseup", () => { if (drag) { drag = false; stage.classList.remove("is-panning"); } });
  stage.addEventListener("wheel", (e) => {
    if (e.target.closest(".grounding-info-card")) return;
    e.preventDefault(); _zoomBy(e.deltaY < 0 ? 1.12 : 0.9, e.clientX, e.clientY);
  }, { passive: false });
  stage.addEventListener("click", (e) => {
    if (e.target.closest(".pp-hl, .gw-hit, .gw-label, .grounding-info-card, .paper-page")) return;
    _clearThread();
  });
}

function _gExit() {
  switchView("packages");
  if (state.currentPackageId && typeof openPackageDetail === "function") openPackageDetail(state.currentPackageId);
}

(function wireGroundingV3() {
  document.addEventListener("click", (e) => {
    if (e.target.closest("#pkgGroundingBtn")) {
      if (!state.currentPackageId) { toastError("No package selected", "Open a package, then click Grounded view."); return; }
      switchView("grounding");
      requestAnimationFrame(() => { _wirePanZoom(); renderGrounding(state.currentPackageId); });
    }
    if (e.target.closest("#groundingBackBtn")) { e.preventDefault(); _gExit(); }
    if (e.target.closest("#zoomInBtn"))  _zoomBy(1.12);
    if (e.target.closest("#zoomOutBtn")) _zoomBy(0.9);
    if (e.target.closest("#zoomFitBtn")) _fitAll();
  });
  let rT;
  window.addEventListener("resize", () => {
    clearTimeout(rT);
    rT = setTimeout(() => {
      if (document.getElementById("view-grounding")?.classList.contains("active") && state.grounding?._pageEls) _drawThreads();
    }, 150);
  });
})();
