/**
 * SwtorSim Pyodide WebAssembly Simulation Worker
 *
 * Runs the complete SwtorSim combat engine inside a browser Web Worker via Pyodide.
 * Handles blueprint hydration, catalog discovery, stat recalculations, and simulations.
 */

/* global importScripts, loadPyodide, self */

importScripts("https://cdn.jsdelivr.net/pyodide/v0.27.2/full/pyodide.js");

let pyodideInstance = null;
let isReady = false;

/**
 * Initializes Pyodide, downloads the bundled game assets, and hydrates the engine.
 */
async function initPyodideWorker(assetsUrl = "swtorsim_assets.zip") {
  try {
    self.postMessage({ type: "STATUS", text: "Initializing Python WebAssembly environment..." });
    pyodideInstance = await loadPyodide({
      indexURL: "https://cdn.jsdelivr.net/pyodide/v0.27.2/full/"
    });

    self.postMessage({ type: "STATUS", text: "Fetching game data & blueprints (~4.8 MB)..." });
    const resp = await fetch(assetsUrl);
    if (!resp.ok) {
      throw new Error(`Failed to load ${assetsUrl}: HTTP ${resp.status}`);
    }
    const archiveBuffer = await resp.arrayBuffer();

    self.postMessage({ type: "STATUS", text: "Unpacking game engine in virtual memory..." });
    try {
      pyodideInstance.FS.mkdirTree("/home/pyodide/SwtorSim");
    } catch (e) {
      // directory already exists
    }
    pyodideInstance.unpackArchive(archiveBuffer, "zip", { extractDir: "/home/pyodide/SwtorSim" });

    self.postMessage({ type: "STATUS", text: "Hydrating SwtorSim engine..." });
    await pyodideInstance.runPythonAsync(`
import sys, os
os.chdir("/home/pyodide/SwtorSim")
if "/home/pyodide/SwtorSim" not in sys.path:
    sys.path.insert(0, "/home/pyodide/SwtorSim")

import src.swtorsim.pyodide_bridge as bridge

def js_progress_proxy(running, mode, completed, total, pct):
    try:
        import js
        js.postSimulationProgress(bool(running), str(mode), int(completed), int(total), float(pct))
    except Exception:
        pass

bridge.register_js_progress_callback(js_progress_proxy)
`);

    isReady = true;
    self.postMessage({ type: "READY" });
  } catch (err) {
    console.error("Pyodide worker initialization failed:", err);
    self.postMessage({ type: "ERROR", error: err.toString() });
  }
}

// Global JS hook invoked directly from Python progress updates
self.postSimulationProgress = function (running, mode, completed, total, pct) {
  self.postMessage({
    type: "PROGRESS",
    running: Boolean(running),
    mode: String(mode),
    completed: Number(completed),
    total: Number(total),
    pct: Number(pct)
  });
};

self.onmessage = async function (event) {
  const { id, action, payload, assetsUrl } = event.data || {};

  if (action === "INIT") {
    await initPyodideWorker(assetsUrl || "swtorsim_assets.zip");
    return;
  }

  if (!isReady || !pyodideInstance) {
    self.postMessage({ id, error: "Pyodide Web Worker is not ready yet." });
    return;
  }

  if (action === "WRITE_VIRTUAL_FILE") {
    try {
      const { path: vPath, content } = payload || {};
      const fullPath = vPath.startsWith("/") ? vPath : `/home/pyodide/SwtorSim/${vPath}`;
      const lastSlash = fullPath.lastIndexOf("/");
      if (lastSlash > 0) {
        const dir = fullPath.substring(0, lastSlash);
        try {
          pyodideInstance.FS.mkdirTree(dir);
        } catch (_e) {}
      }
      const dataStr = typeof content === "string" ? content : JSON.stringify(content, null, 2);
      pyodideInstance.FS.writeFile(fullPath, dataStr);
      self.postMessage({ id, result: { ok: true, path: vPath } });
    } catch (err) {
      console.error("Error in WRITE_VIRTUAL_FILE:", err);
      self.postMessage({ id, error: err.toString() });
    }
    return;
  }

  if (action === "DELETE_VIRTUAL_FILE") {
    try {
      const { path: vPath } = payload || {};
      const fullPath = vPath.startsWith("/") ? vPath : `/home/pyodide/SwtorSim/${vPath}`;
      try {
        pyodideInstance.FS.unlink(fullPath);
      } catch (_e) {}
      self.postMessage({ id, result: { ok: true, path: vPath } });
    } catch (err) {
      console.error("Error in DELETE_VIRTUAL_FILE:", err);
      self.postMessage({ id, error: err.toString() });
    }
    return;
  }

  try {
    const payloadStr = JSON.stringify(payload || {});
    pyodideInstance.globals.set("_action_name", action);
    pyodideInstance.globals.set("_payload_json", payloadStr);

    const resultJson = await pyodideInstance.runPythonAsync(`
import src.swtorsim.pyodide_bridge as bridge
bridge.dispatch(_action_name, _payload_json)
`);
    const result = JSON.parse(resultJson);
    self.postMessage({ id, result });
  } catch (err) {
    console.error(`Error running action ${action}:`, err);
    self.postMessage({ id, error: err.toString() });
  }
};
