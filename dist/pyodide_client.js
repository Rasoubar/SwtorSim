/**
 * SwtorSim Client-Side Pyodide Bridge & Multi-Core Web Worker Pool
 *
 * Automatically detects whether the simulator is running against a local Python
 * HTTP server (web_gui.py) or running standalone in the browser via Pyodide WebAssembly.
 *
 * In WebAssembly mode:
 * - Automatically detects CPU cores via navigator.hardwareConcurrency.
 * - Spins up a pool of Pyodide Web Workers executing across multiple CPU cores in parallel.
 * - Transparently intercepts '/api/*' requests, queues them until Worker 0 is ready,
 *   and divides Monte Carlo batches across workers.
 */

/* global Worker, Response, navigator */

(function () {
  "use strict";

  if (window.location.protocol === "file:") {
    console.warn("[SwtorSim] Running via file:// protocol. Web Workers and fetch may be blocked by browser CORS policy.");
  }

  const urlParams = new URLSearchParams(window.location.search);
  const forcedBackend = urlParams.get("backend");

  let isNativeServer = false;
  if (forcedBackend === "wasm") {
    isNativeServer = false;
  } else if (forcedBackend === "native") {
    isNativeServer = true;
  } else if (
    (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") &&
    window.location.port !== "" &&
    window.location.port !== "8080"
  ) {
    isNativeServer = true;
  }

  const isBuilderPage = window.location.pathname.includes("rotation_builder") || (typeof document !== "undefined" && document.title && document.title.includes("Rotation Builder"));

  // Determine concurrency:
  // Rotation Builder uses 1 dedicated worker for instant catalog/loadout discovery and fast 30s preview.
  // Combat Simulator uses multi-core worker pool for parallel Monte Carlo simulations.
  const hardwareCores = typeof navigator !== "undefined" && navigator.hardwareConcurrency ? navigator.hardwareConcurrency : 4;
  let savedCores = null;
  try {
    const raw = localStorage.getItem("swtor_wasm_cores");
    if (raw) savedCores = parseInt(raw, 10);
  } catch (_e) {}

  const defaultCores = savedCores && savedCores >= 1 && savedCores <= hardwareCores ? savedCores : hardwareCores;
  const targetPoolSize = isBuilderPage ? 1 : Math.max(1, defaultCores);

  let resolveReady, rejectReady;
  const readyPromise = new Promise((resolve, reject) => {
    resolveReady = resolve;
    rejectReady = reject;
  });

  function loadCustomFilesFromStorage() {
    try {
      const raw = localStorage.getItem("swtor_custom_files");
      if (!raw) return {};
      const files = JSON.parse(raw);
      const sanitized = {};
      let changed = false;
      for (const [k, content] of Object.entries(files)) {
        if (!k.includes("/custom/")) {
          changed = true;
          let newKey = k;
          if (k.startsWith("data/rotations/")) {
            newKey = k.replace("data/rotations/", "data/rotations/custom/");
          } else if (k.startsWith("data/Choices/") || k.startsWith("data/choices/")) {
            newKey = k.replace(/^data\/[Cc]hoices\//, "data/Choices/custom/");
          } else if (k.startsWith("data/builds/")) {
            newKey = k.replace("data/builds/", "data/builds/custom/");
          } else if (k.startsWith("data/run_config/")) {
            newKey = k.replace("data/run_config/", "data/run_config/custom/");
          }
          if (!files[newKey]) {
            sanitized[newKey] = content;
          }
        } else {
          sanitized[k] = content;
        }
      }
      if (changed) {
        localStorage.setItem("swtor_custom_files", JSON.stringify(sanitized));
      }
      return sanitized;
    } catch (_e) {
      return {};
    }
  }

  function saveCustomFilesToStorage(filesMap) {
    try {
      localStorage.setItem("swtor_custom_files", JSON.stringify(filesMap));
    } catch (_e) {}
  }

  const state = {
    mode: isNativeServer ? "native" : "pyodide",
    targetPoolSize: targetPoolSize,
    workers: [],
    isReady: isNativeServer,
    readyPromise: isNativeServer ? Promise.resolve() : readyPromise,
    customFiles: loadCustomFilesFromStorage(),
    latestProgress: { running: false, mode: "TEST", completed: 0, total: 1, pct: 0.0 }
  };

  // --- UI Helpers ---

  function updateBackendBadge(label, className) {
    let badge = document.getElementById("swtor-backend-badge");
    if (!badge) {
      const headerControls = document.querySelector(".header-controls") || document.querySelector("header");
      if (headerControls) {
        badge = document.createElement("div");
        badge.id = "swtor-backend-badge";
        badge.style.fontSize = "11px";
        badge.style.fontWeight = "600";
        badge.style.padding = "2px 7px";
        badge.style.borderRadius = "4px";
        badge.style.border = "1px solid var(--border)";
        badge.style.letterSpacing = "0.2px";
        badge.style.display = "inline-flex";
        badge.style.alignItems = "center";
        badge.style.gap = "5px";
        badge.style.cursor = "default";
        badge.style.userSelect = "none";
        headerControls.prepend(badge);
      }
    }
    if (badge) {
      const readyCount = state.workers ? state.workers.filter(w => w.isReady).length : 0;
      const isWarming = label && label.includes("Warming");

      const dotStyle = (color) => `display:inline-block; width:6px; height:6px; border-radius:50%; background:${color}; flex-shrink:0;`;

      if (className === "badge-native" || state.mode === "native") {
        badge.style.background = "var(--green-bg)";
        badge.style.color = "var(--green)";
        badge.style.borderColor = "var(--green)";
        badge.title = "Running on Native CPython with OS multiprocessing.Pool";
        badge.innerHTML = `<span style="${dotStyle('var(--green)')}"></span><span>Native</span>`;
      } else if (isWarming) {
        badge.style.background = "var(--amber-bg)";
        badge.style.color = "var(--amber)";
        badge.style.borderColor = "var(--amber)";
        badge.title = isBuilderPage
          ? "Warming Web Worker environment..."
          : `Warming Web Workers (${readyCount}/${state.targetPoolSize} cores online)...`;
        badge.innerHTML = `<span style="${dotStyle('var(--amber)')}"></span><span>${isBuilderPage ? "Warming" : `Warming (${readyCount}/${state.targetPoolSize})`}</span>`;
      } else {
        badge.style.background = "var(--accent-bg)";
        badge.style.color = "var(--accent)";
        badge.style.borderColor = "var(--accent)";
        badge.title = isBuilderPage
          ? "Running In-Browser via Pyodide WebAssembly"
          : `Running In-Browser via Pyodide WebAssembly (${readyCount}/${state.targetPoolSize} cores online)`;
        badge.innerHTML = `<span style="${dotStyle('var(--accent)')}"></span><span>Web</span>`;
      }
      if (state.mode === "pyodide" && !isBuilderPage) {
        updateCoreSelectorUI();
      }
    }
  }

  function updateCoreSelectorUI() {
    if (state.mode !== "pyodide" || isBuilderPage) {
      const existing = document.getElementById("swtor-core-selector-container");
      if (existing) existing.remove();
      return;
    }
    let container = document.getElementById("swtor-core-selector-container");
    if (!container) {
      const headerControls = document.querySelector(".header-controls") || document.querySelector("header");
      if (headerControls) {
        container = document.createElement("div");
        container.id = "swtor-core-selector-container";
        container.style.display = "inline-flex";
        container.style.alignItems = "center";
        container.style.gap = "4px";
        container.style.marginLeft = "4px";

        const label = document.createElement("label");
        label.htmlFor = "swtor-core-select";
        label.textContent = "Cores:";
        label.style.fontSize = "11px";
        label.style.color = "#ffffff";
        label.style.fontWeight = "600";

        const select = document.createElement("select");
        select.id = "swtor-core-select";
        select.style.fontSize = "11px";
        select.style.padding = "2px 6px";
        select.style.background = "var(--bg-input)";
        select.style.color = "var(--text-main)";
        select.style.border = "1px solid var(--border)";
        select.style.borderRadius = "4px";
        select.style.cursor = "pointer";

        // Generate core choices based on detected hardware concurrency
        const coreOptions = [];
        if (hardwareCores > 1) coreOptions.push(1);
        [2, 4, 8, 12, 16, 24, 32].forEach(n => {
          if (hardwareCores >= n && !coreOptions.includes(n)) coreOptions.push(n);
        });
        if (!coreOptions.includes(hardwareCores)) coreOptions.push(hardwareCores);
        coreOptions.sort((a, b) => a - b);

        coreOptions.forEach(optVal => {
          const opt = document.createElement("option");
          opt.value = optVal;
          if (optVal === hardwareCores) {
            opt.textContent = `${optVal} (Max)`;
          } else {
            opt.textContent = `${optVal}`;
          }
          select.appendChild(opt);
        });

        select.value = state.targetPoolSize;
        select.addEventListener("change", (e) => {
          const chosen = parseInt(e.target.value, 10);
          if (chosen && chosen > 0) {
            setTargetPoolSize(chosen);
          }
        });

        container.appendChild(label);
        container.appendChild(select);

        const badge = document.getElementById("swtor-backend-badge");
        if (badge && badge.parentNode) {
          badge.parentNode.insertBefore(container, badge.nextSibling);
        } else {
          headerControls.prepend(container);
        }
      }
    } else {
      const select = document.getElementById("swtor-core-select");
      if (select && parseInt(select.value, 10) !== state.targetPoolSize) {
        select.value = state.targetPoolSize;
      }
    }
  }

  function setTargetPoolSize(newSize) {
    newSize = Math.max(1, Math.min(newSize, hardwareCores));
    state.targetPoolSize = newSize;
    try {
      localStorage.setItem("swtor_wasm_cores", String(newSize));
    } catch (_e) {}

    // Trim workers beyond newSize to instantly release browser memory
    while (state.workers.length > newSize) {
      const w = state.workers.pop();
      try {
        w.worker.terminate();
        console.log(`[SwtorSim] Terminated worker #${w.index} to free RAM.`);
      } catch (_e) {}
    }

    // Expand workers if secondary workers have been initialized
    if (secondaryWorkersStarted && state.workers.length < newSize) {
      for (let i = state.workers.length; i < newSize; i++) {
        const secWorker = createWorkerInstance(i);
        state.workers.push(secWorker);
      }
    }

    const readyCount = state.workers.filter(w => w.isReady).length;
    updateBackendBadge(`Pyodide [WASM Multi-Core: ${readyCount}/${state.targetPoolSize} Cores]`, "badge-wasm");
  }

  function showLoadingOverlay(initialText) {
    let overlay = document.getElementById("swtor-loading-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "swtor-loading-overlay";
      overlay.style.position = "fixed";
      overlay.style.top = "0";
      overlay.style.left = "0";
      overlay.style.width = "100vw";
      overlay.style.height = "100vh";
      overlay.style.backgroundColor = "rgba(88, 171, 223, 0.85)";
      overlay.style.backdropFilter = "blur(4px)";
      overlay.style.zIndex = "99999";
      overlay.style.display = "flex";
      overlay.style.flexDirection = "column";
      overlay.style.alignItems = "center";
      overlay.style.justifyContent = "center";
      overlay.style.color = "#0c2138";
      overlay.style.fontFamily = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";

      overlay.innerHTML = `
        <div style="background:var(--bg-card); border:1px solid var(--border); border-radius:8px; padding:28px 36px; text-align:center; max-width:440px; box-shadow:0 12px 32px rgba(12,33,56,0.25);">
          <div style="font-size:16px; font-weight:700; margin-bottom:12px; color:var(--accent); display:flex; align-items:center; justify-content:center; gap:8px;">
            <span>SwtorSim WebAssembly</span>
          </div>
          <div id="swtor-loading-text" style="font-size:13px; color:var(--text-muted); margin-bottom:18px;">${initialText}</div>
          <div style="width:100%; height:4px; background:var(--bg-base); border-radius:2px; overflow:hidden;">
            <div id="swtor-loading-progress" style="width:100%; height:100%; background:linear-gradient(90deg, #58abdf, #ff7818); animation:pulseBar 1.5s infinite linear;"></div>
          </div>
        </div>
      `;
      if (document.body) {
        document.body.appendChild(overlay);
      } else {
        window.addEventListener("DOMContentLoaded", () => document.body.appendChild(overlay));
      }
    }
  }

  function updateLoadingOverlay(text) {
    const el = document.getElementById("swtor-loading-text");
    if (el) el.textContent = text;
  }

  function hideLoadingOverlay() {
    const overlay = document.getElementById("swtor-loading-overlay");
    if (overlay) overlay.remove();
  }

  // --- Worker Lifecycle & Pool Manager ---

  function createWorkerInstance(index) {
    let resolveWorkerReady, rejectWorkerReady;
    const workerReadyPromise = new Promise((res, rej) => {
      resolveWorkerReady = res;
      rejectWorkerReady = rej;
    });

    const wState = {
      index,
      worker: new Worker("sim_worker.js"),
      isReady: false,
      readyPromise: workerReadyPromise,
      pendingRequests: new Map(),
      requestId: 0,
      completedRuns: 0
    };

    wState.worker.onmessage = function (event) {
      const data = event.data || {};

      if (data.type === "STATUS") {
        if (index === 0) updateLoadingOverlay(data.text);
        return;
      }

      if (data.type === "PROGRESS") {
        wState.completedRuns = Number(data.completed) || 0;
        updateAggregatedProgress();
        return;
      }

      if (data.type === "READY") {
        syncCustomFilesToWorker(wState).catch(err => {
          console.error(`Error syncing custom files to worker #${index}:`, err);
        }).finally(() => {
          wState.isReady = true;
          resolveWorkerReady();

          const readyCount = state.workers.filter(w => w.isReady).length;
          if (index === 0) {
            state.isReady = true;
            hideLoadingOverlay();
            console.log(`[SwtorSim] Primary Pyodide Worker is ready.`);
            if (resolveReady) resolveReady();
            // Spawn secondary workers in background
            initSecondaryWorkers();
          } else {
            console.log(`[SwtorSim] Secondary Pyodide Worker #${index} ready (${readyCount}/${state.targetPoolSize} cores online).`);
          }
          updateBackendBadge(`Pyodide [WASM Multi-Core: ${readyCount}/${state.targetPoolSize} Cores]`, "badge-wasm");
        });
        return;
      }

      if (data.type === "ERROR") {
        console.error(`[SwtorSim Worker #${index} Error]`, data.error);
        if (index === 0) {
          hideLoadingOverlay();
          alert("Simulation Engine Initialization Error:\n" + data.error);
          if (rejectReady) rejectReady(new Error(data.error));
        }
        rejectWorkerReady(new Error(data.error));
        return;
      }

      if (data.id !== undefined && wState.pendingRequests.has(data.id)) {
        const { resolve, reject } = wState.pendingRequests.get(data.id);
        wState.pendingRequests.delete(data.id);
        if (data.error) {
          reject(new Error(data.error));
        } else {
          resolve(data.result);
        }
      }
    };

    wState.worker.onerror = function (err) {
      console.error(`[SwtorSim Worker #${index} Failure]`, err);
      if (index === 0 && rejectReady) rejectReady(err);
      rejectWorkerReady(err);
    };

    wState.worker.postMessage({ action: "INIT", assetsUrl: "swtorsim_assets.zip?v=1793958757" });
    return wState;
  }

  let secondaryWorkersStarted = false;
  function initSecondaryWorkers() {
    if (isBuilderPage || state.targetPoolSize <= 1) return;
    if (secondaryWorkersStarted) return;
    secondaryWorkersStarted = true;
    for (let i = 1; i < state.targetPoolSize; i++) {
      const secWorker = createWorkerInstance(i);
      state.workers.push(secWorker);
    }
  }

  async function ensureAllWorkersReady() {
    await state.readyPromise;
    if (state.targetPoolSize <= 1) return;
    if (!secondaryWorkersStarted) {
      initSecondaryWorkers();
    }
    // Ensure all workers up to targetPoolSize are created
    while (state.workers.length < state.targetPoolSize) {
      const secWorker = createWorkerInstance(state.workers.length);
      state.workers.push(secWorker);
    }

    const activeWorkers = state.workers.slice(0, state.targetPoolSize);
    const pending = activeWorkers.filter(w => !w.isReady);
    if (pending.length > 0) {
      const runBtn = document.getElementById("runSimBtn");
      const updateWarmingStatus = () => {
        const readyCount = activeWorkers.filter(w => w.isReady).length;
        if (runBtn) runBtn.textContent = `⏳ Warming Cores (${readyCount}/${state.targetPoolSize})...`;
        updateBackendBadge(`Pyodide [Warming Cores: ${readyCount}/${state.targetPoolSize}]`, "badge-wasm");
      };
      updateWarmingStatus();
      await Promise.all(activeWorkers.map(w => w.readyPromise.then(() => {
        updateWarmingStatus();
      })));
    }
    const readyCount = activeWorkers.filter(w => w.isReady).length;
    updateBackendBadge(`Pyodide [WASM Multi-Core: ${readyCount}/${state.targetPoolSize} Cores]`, "badge-wasm");
  }

  function updateAggregatedProgress() {
    const totalRuns = state.latestProgress.total || 1;
    let completedRuns = 0;
    const activeWorkers = state.workers.slice(0, state.targetPoolSize);
    activeWorkers.forEach(w => {
      completedRuns += (w.completedRuns || 0);
    });
    const safeCompleted = Math.min(totalRuns, completedRuns);
    const pct = Math.round((safeCompleted / totalRuns) * 100.0 * 10) / 10;
    state.latestProgress.completed = safeCompleted;
    state.latestProgress.pct = pct;
  }

  async function syncCustomFilesToWorker(wState) {
    const customFiles = state.customFiles || {};
    const entries = Object.entries(customFiles);
    for (const [vPath, content] of entries) {
      try {
        await callSpecificWorker(wState, "WRITE_VIRTUAL_FILE", { path: vPath, content });
      } catch (err) {
        console.error(`Failed to sync custom file ${vPath} to worker #${wState.index}:`, err);
      }
    }
  }

  function callSpecificWorker(wState, action, payload) {
    return new Promise((resolve, reject) => {
      const id = ++wState.requestId;
      wState.pendingRequests.set(id, { resolve, reject });
      wState.worker.postMessage({ id, action, payload });
    });
  }

  async function callPrimaryWorker(action, payload) {
    await state.readyPromise;
    return await callSpecificWorker(state.workers[0], action, payload);
  }

  // --- Multi-Core Parallel Batch Dispatcher ---

  async function executeBatchMultiCore(payload) {
    await state.readyPromise;

    // Gate: guarantee 100% of the worker pool is warm and ready before running
    await ensureAllWorkersReady();

    const totalIterations = Math.max(1, parseInt(payload.iterations, 10) || 50);

    // Get active pool workers up to chosen targetPoolSize
    const activeWorkers = state.workers.slice(0, state.targetPoolSize).filter(w => w.isReady);
    const numWorkers = Math.min(activeWorkers.length, totalIterations);

    // If only 1 worker ready, execute sequentially on Worker 0
    if (numWorkers <= 1) {
      return await callSpecificWorker(state.workers[0], "SIMULATE", payload);
    }

    // Reset progress tracking counters across active workers
    activeWorkers.forEach(w => { w.completedRuns = 0; });
    state.latestProgress = {
      running: true,
      mode: "BATCH",
      completed: 0,
      total: totalIterations,
      pct: 0.0
    };

    // Divide iterations evenly across ready hardware workers
    const baseCount = Math.floor(totalIterations / numWorkers);
    const remainder = totalIterations % numWorkers;
    let currentStartId = 0;

    const t0 = performance.now();
    const slicePromises = [];

    for (let i = 0; i < numWorkers; i++) {
      const sliceCount = baseCount + (i < remainder ? 1 : 0);
      const workerState = activeWorkers[i];
      const slicePayload = {
        ...payload,
        start_run_id: currentStartId,
        slice_count: sliceCount
      };
      currentStartId += sliceCount;

      slicePromises.push(callSpecificWorker(workerState, "SIMULATE_SLICE", slicePayload));
    }

    // Execute slices simultaneously across multiple CPU cores
    const sliceResults = await Promise.all(slicePromises);
    const wallMs = Math.round(performance.now() - t0);

    // Merge all harvested runs from all worker threads
    const allHarvested = [];
    for (const res of sliceResults) {
      if (res && res.error) {
        throw new Error(res.error);
      }
      if (Array.isArray(res.harvested)) {
        allHarvested.push(...res.harvested);
      }
    }

    // Hand the complete harvested dataset to Worker 0 to compute final report & breakdowns
    const finalReport = await callSpecificWorker(state.workers[0], "AGGREGATE_BATCH", {
      payload: payload,
      all_harvested: allHarvested,
      wall_ms: wallMs,
      total_iterations: totalIterations
    });

    state.latestProgress.running = false;
    return finalReport;
  }

  // --- Fetch Interceptor ---
  const originalFetch = window.fetch;

  window.fetch = async function (resource, options = {}) {
    const urlStr = typeof resource === "string" ? resource : (resource && resource.url) || "";

    if (state.mode === "native" || !urlStr.startsWith("/api/")) {
      return originalFetch.apply(this, arguments);
    }

    const url = new URL(urlStr, window.location.origin);
    const pathname = url.pathname;

    try {
      const isBuilder = window.location.pathname.includes("rotation_builder") || (document.title && document.title.includes("Rotation Builder"));

      if (pathname === "/api/launch_rotation_builder") {
        return new Response(JSON.stringify({ ok: true, url: "rotation_builder.html" }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (pathname === "/api/catalog") {
        let result;
        const env = url.searchParams.get("env") || "live";
        if (isBuilder) {
          result = await callPrimaryWorker("GET_BUILDER_CATALOG", { env });
        } else {
          result = await callPrimaryWorker("GET_CATALOG", { env });
        }
        const isError = result && (result.error !== undefined);
        return new Response(JSON.stringify(result), {
          status: isError ? 400 : 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (pathname === "/api/class_gear") {
        const specPath = url.searchParams.get("spec_path") || "";
        const env = url.searchParams.get("env") || "live";
        const result = await callPrimaryWorker("GET_CLASS_GEAR", { spec_path: specPath, env });
        const isError = result && (result.error !== undefined);
        return new Response(JSON.stringify(result), {
          status: isError ? 400 : 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (pathname === "/api/build_stats") {
        const path = url.searchParams.get("path") || "";
        let statsObj = null;

        if (state.customFiles[path]) {
          try {
            const parsed = JSON.parse(state.customFiles[path]);
            statsObj = parsed.stats || parsed;
          } catch (_e) {}
        }

        if (statsObj) {
          return new Response(JSON.stringify({ ok: true, path, stats: statsObj }), {
            status: 200,
            headers: { "Content-Type": "application/json" }
          });
        }

        const result = await callPrimaryWorker("GET_BUILD_STATS", { path });
        const isError = result && (result.error !== undefined);
        return new Response(JSON.stringify(result), {
          status: isError ? 400 : 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (pathname === "/api/run_config") {
        const path = url.searchParams.get("path") || "";
        const env = url.searchParams.get("env") || "live";
        const action = isBuilder ? "LOAD_BUILDER_RUN_CONFIG" : "LOAD_RUN_CONFIG";
        const result = await callPrimaryWorker(action, { path, env });
        const isError = result && (result.error !== undefined);
        return new Response(JSON.stringify(result), {
          status: isError ? 400 : 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (pathname === "/api/rotation") {
        const path = url.searchParams.get("path") || "";
        const result = await callPrimaryWorker("LOAD_ROTATION", { path });
        const isError = result && (result.error !== undefined);
        return new Response(JSON.stringify(result), {
          status: isError ? 400 : 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (pathname === "/api/loadout") {
        const payload = JSON.parse(options.body || "{}");
        const result = await callPrimaryWorker("DISCOVER_LOADOUT", payload);
        const isError = result && (result.error !== undefined);
        return new Response(JSON.stringify(result), {
          status: isError ? 400 : 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (pathname === "/api/preview") {
        const payload = JSON.parse(options.body || "{}");
        const result = await callPrimaryWorker("RUN_ROTATION_PREVIEW", payload);
        const isError = result && (result.error !== undefined);
        return new Response(JSON.stringify(result), {
          status: isError ? 400 : 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (pathname === "/api/rotation/save") {
        const payload = JSON.parse(options.body || "{}");
        const classFolder = String(payload.class_folder || "assassin").trim().toLowerCase();
        const specFolder = String(payload.spec_folder || "hatred").trim().toLowerCase();
        let filename = String(payload.filename || "CustomRotation.json").trim();
        if (!filename.endsWith(".json")) filename += ".json";
        filename = filename.replace(/^.*[\\/]/, "");

        const contentStr = JSON.stringify(payload.steps || [], null, 4);

        const customPath = `data/rotations/custom/${classFolder}/${specFolder}/${filename}`;

        state.customFiles[customPath] = contentStr;
        saveCustomFilesToStorage(state.customFiles);

        // Sync to all currently ready workers (unready workers auto-sync upon ready)
        const readyWorkers = state.workers.filter(w => w.isReady);
        const syncPromises = readyWorkers.map(w =>
          callSpecificWorker(w, "WRITE_VIRTUAL_FILE", { path: customPath, content: contentStr })
        );
        await Promise.all(syncPromises);

        return new Response(JSON.stringify({ ok: true, path: customPath, filename: filename }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (pathname === "/api/preview_stats") {
        const payload = JSON.parse(options.body || "{}");
        const result = await callPrimaryWorker("PREVIEW_STATS", payload);
        const isError = result && (result.error !== undefined);
        return new Response(JSON.stringify(result), {
          status: isError ? 400 : 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (pathname === "/api/progress") {
        return new Response(JSON.stringify(state.latestProgress), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (pathname === "/api/simulate") {
        const payload = JSON.parse(options.body || "{}");
        let result;

        if (payload.mode === "BATCH" && (parseInt(payload.iterations, 10) || 50) > 1) {
          result = await executeBatchMultiCore(payload);
        } else {
          state.latestProgress = {
            running: true,
            mode: "TEST",
            completed: 0,
            total: 1,
            pct: 0.0
          };
          result = await callPrimaryWorker("SIMULATE", payload);
          state.latestProgress.running = false;
        }

        const isError = result && (result.error !== undefined);
        return new Response(JSON.stringify(result), {
          status: isError ? 400 : 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (pathname === "/api/custom_file/import") {
        const payload = JSON.parse(options.body || "{}");
        const category = String(payload.category || "rotations").trim().toLowerCase();
        let filename = String(payload.filename || "custom.json").trim();
        if (!filename.endsWith(".json")) filename += ".json";
        filename = filename.replace(/^.*[\\\/]/, "");

        const classFolder = String(payload.class_folder || "").trim().toLowerCase();
        const specFolder = String(payload.spec_folder || "").trim().toLowerCase();

        let relFolder = "data/rotations/custom";
        if (category === "choices") relFolder = "data/Choices/custom";
        else if (category === "builds") relFolder = "data/builds/custom";
        else if (category === "run_config") relFolder = "data/run_config/custom";

        if (classFolder && specFolder && (category === "rotations" || category === "choices")) {
          relFolder += `/${classFolder}/${specFolder}`;
        }

        const vPath = `${relFolder}/${filename}`;
        const contentStr = typeof payload.content === "string" ? payload.content : JSON.stringify(payload.content, null, 2);

        state.customFiles[vPath] = contentStr;
        saveCustomFilesToStorage(state.customFiles);

        // Sync to all currently ready workers (unready workers auto-sync upon ready)
        const readyWorkers = state.workers.filter(w => w.isReady);
        const syncPromises = readyWorkers.map(w =>
          callSpecificWorker(w, "WRITE_VIRTUAL_FILE", { path: vPath, content: contentStr })
        );
        await Promise.all(syncPromises);

        return new Response(JSON.stringify({ ok: true, path: vPath, filename: filename }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (pathname === "/api/custom_file/delete") {
        const payload = JSON.parse(options.body || "{}");
        const vPath = String(payload.path || "").trim();
        const filename = vPath.split("/").pop();

        for (const k of Object.keys(state.customFiles)) {
          if (k === vPath || k.endsWith("/" + filename)) {
            delete state.customFiles[k];
          }
        }
        saveCustomFilesToStorage(state.customFiles);

        // Delete from all currently ready workers (unready workers will initialize without it)
        const readyWorkers = state.workers.filter(w => w.isReady);
        const delPromises = readyWorkers.map(w =>
          callSpecificWorker(w, "DELETE_VIRTUAL_FILE", { path: vPath })
        );
        await Promise.all(delPromises);

        return new Response(JSON.stringify({ ok: true, path: vPath }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (pathname === "/api/run_config/save" || pathname === "/api/build_stats/save") {
        const payload = JSON.parse(options.body || "{}");
        const filename = payload.filename || "custom_config.json";
        const blob = new Blob([JSON.stringify(payload.config || payload.stats || payload, null, 2)], {
          type: "application/json"
        });
        const downloadUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = downloadUrl;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(downloadUrl);

        return new Response(JSON.stringify({ ok: true, filename, downloaded: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      return new Response(JSON.stringify({ error: `Unhandled WASM route: ${pathname}` }), {
        status: 404,
        headers: { "Content-Type": "application/json" }
      });

    } catch (err) {
      console.error(`[Pyodide Fetch Error] ${pathname}:`, err);
      return new Response(JSON.stringify({ error: err.toString() }), {
        status: 500,
        headers: { "Content-Type": "application/json" }
      });
    }
  };

  // --- Boot Primary Worker Immediately ---
  if (state.mode === "pyodide") {
    showLoadingOverlay("Initializing Python WebAssembly environment...");
    try {
      const primaryWorker = createWorkerInstance(0);
      state.workers.push(primaryWorker);
    } catch (err) {
      hideLoadingOverlay();
      console.error("Failed to start primary Web Worker:", err);
      alert("Failed to initialize Pyodide Web Worker:\n" + err.message);
      if (rejectReady) rejectReady(err);
    }
  }

  // Set header badge and core selector once DOM is ready
  window.addEventListener("DOMContentLoaded", () => {
    if (state.mode === "native") {
      updateBackendBadge("CPython 3.13 [Native Multi-Process]", "badge-native");
    } else {
      const readyCount = state.workers.filter(w => w.isReady).length;
      updateBackendBadge(`Pyodide [WASM Multi-Core: ${readyCount}/${state.targetPoolSize} Cores]`, "badge-wasm");
      if (!isBuilderPage) {
        updateCoreSelectorUI();
      }
    }
  });

  // Cross-tab synchronization via localStorage events & tab focus
  async function reloadCrossTabCustomFiles() {
    state.customFiles = loadCustomFilesFromStorage();
    const activeWorkers = state.workers.filter(w => w.isReady);
    const syncPromises = activeWorkers.map(w => syncCustomFilesToWorker(w));
    await Promise.all(syncPromises);

    if (typeof window.onSwtorCustomFilesChanged === "function") {
      window.onSwtorCustomFilesChanged();
    }
  }

  window.addEventListener("storage", (e) => {
    if (e.key === "swtor_custom_files") {
      reloadCrossTabCustomFiles();
    }
  });

  let lastStorageSnapshot = "";
  try { lastStorageSnapshot = localStorage.getItem("swtor_custom_files") || "{}"; } catch (_e) {}

  window.addEventListener("focus", () => {
    try {
      const currentSnapshot = localStorage.getItem("swtor_custom_files") || "{}";
      if (currentSnapshot !== lastStorageSnapshot) {
        lastStorageSnapshot = currentSnapshot;
        reloadCrossTabCustomFiles();
      }
    } catch (_e) {}
  });

})();
