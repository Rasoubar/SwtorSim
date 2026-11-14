# SwtorSim Standalone In-Browser Web Release Guide (Pyodide WebAssembly)

This document provides the authoritative technical reference for SwtorSim's zero-install, 100% client-side web release running entirely in the browser via Pyodide (Python WebAssembly) and a multi-threaded Web Worker pool.

---

## 1. Architectural Overview & Dual-Mode Runtime

SwtorSim operates in a **dual-mode architecture**:

```
+--------------------------------------------------------------------------+
|                        Unified Browser Frontend                          |
|             (simulator_ui.html  /  rotation_builder.html)                 |
+--------------------------------------------------------------------------+
                                    |
            Transparent Fetch Interceptor (pyodide_client.js)
                                    |
          +-------------------------+-------------------------+
          |                                                   |
   [ Native Mode ]                                     [ WASM Mode ]
  (localhost:8765 / CLI)                          (Static host / GitHub Pages)
          |                                                   |
  Node / OS Process                                   Multi-Core Web Worker Pool
  CPython 3.13 Bare-Metal                             Pyodide 0.27.2 (WASM)
  `multiprocessing.Pool`                              Chunked Slices & In-Memory Merging
```

1. **Native Desktop Mode (`● Native`)**:
   - Running locally via `python -m swtorsim.web_gui` on custom ports.
   - All `/api/*` fetch requests bypass the client bridge and route directly to Python's built-in `ThreadingHTTPServer`.
   - Monte Carlo batch runs use bare-metal OS processes via `multiprocessing.Pool`.
2. **In-Browser WebAssembly Mode (`● Web`)**:
   - Hosted statically on any static server (GitHub Pages, Cloudflare Pages, Netlify, or `python -m http.server 8080 -d dist`).
   - `pyodide_client.js` intercepts all `/api/*` requests in JavaScript, routing them asynchronously to Pyodide Web Workers.
   - Zero servers or backend daemons required; 100% client-side computation.

---

## 2. Multi-Core Web Worker Pool Architecture

Python WebAssembly (Pyodide/Emscripten) does not support OS process spawning (`os.fork()`) or the standard `multiprocessing` module. To achieve full multi-core performance in the browser, SwtorSim implements a dynamic Web Worker Pool at the JavaScript layer:

```
                            [ Web UI Dashboard ]
                                     |
                          [ pyodide_client.js ]
                     Dynamic Core Pool Manager (1 to 32 Cores)
                                     |
         +-------------------+-------+-------+-------------------+
         |                   |               |                   |
   [ Worker 0 ]        [ Worker 1 ]    [ Worker 2 ]  ...   [ Worker N-1 ]
   Pyodide WASM        Pyodide WASM    Pyodide WASM        Pyodide WASM
   (Hydration / Slice) (Slice 1)       (Slice 2)           (Slice N-1)
         |                   |               |                   |
         +-------------------+-------+-------+-------------------+
                                     |
                           (All Slices Merged)
                                     |
                                [ Worker 0 ]
                       `AGGREGATE_BATCH` Computes Final:
                       - DPS Mean, Min, Max, StdDev, IQR
                       - Damage & Ability Breakdown Tables
                       - Pre-binned DPS Histograms
```

### Key Concurrency Features:
- **Automatic Concurrency Detection**: Queries `navigator.hardwareConcurrency` and defaults to all physical/logical CPU threads (e.g. 16, 24, 32).
- **In-Browser Core Selector**: A sleek header dropdown allows the user to choose their active worker count (`1`, `2`, `4`, `8`, `12`, `16`, `Max`). Excess workers are terminated immediately to free RAM, while additional workers are provisioned on demand. Preferences are saved in `localStorage`.
- **Worker Pool Warm-up Gating (`ensureAllWorkersReady`)**: Prevents race conditions where batch runs start before secondary workers finish booting. If clicked during boot, the button indicates `⏳ Warming Cores (N/Total)...` until 100% of the active pool is online.
- **Chunked Slicing (`SIMULATE_SLICE`)**: The coordinator divides total iterations evenly across active workers, executing them simultaneously on separate CPU threads.
- **Batch Merging (`AGGREGATE_BATCH`)**: Harvested run summaries from all workers are merged and passed to Worker 0 for statistical reduction and DPS histogram generation.

---

## 3. High-Performance Execution & Verbosity Suppression

In browser WebAssembly, string formatting and virtual I/O calls to `/dev/null` carry a heavy performance cost. SwtorSim implements two major engine optimizations:

1. **Batch Verbosity Suppression**:
   - `Simulation.__init__` and `prepare_simulation` accept `verbose: bool = True`.
   - In batch runs (`_batch_worker_task`), `verbose=False` is passed.
   - All combat hit logging, DoT expirations, buff clears, and cast messages across `events.py` and `abilities.py` are guarded with `if getattr(sim, "verbose", True):`.
   - This eliminates hundreds of thousands of string allocations and virtual file writes per batch run.
2. **Lazy Plotting**:
   - `matplotlib.pyplot` in `src/swtorsim/tester.py` is loaded lazily only when CLI histogram plots are requested, eliminating heavy graphical wheel downloads in browser mode.

---

## 4. Packaging & Asset Bundle (`tools/bundle_pyodide_assets.py`)

Raw GOM node dumps (`data/extractor/extracted/`, ~400 MB) and Jedipedia hash binaries are excluded from the distribution. The packaging pipeline extracts only runtime dependencies into `dist/swtorsim_assets.zip`:

| Component | Path in Archive | Purpose |
|---|---|---|
| Engine Code | `src/swtorsim/` | Simulation engine, modifiers, curves, and bridge |
| Live Blueprints | `data/extractor/parsed/` | Parsed abilities, talents, and passives |
| PTS Blueprints | `data/extractor/pts/` | PTS 8.0 parsed blueprints and disciplines |
| Preset Rotations | `data/rotations/` | Default class priority lists |
| Base Builds | `data/builds/` | Baseline class stat allocations |
| Run Configs | `data/run_config/` | Preset simulation configurations |

- **Archive Size**: ~4.83 MB compressed (containing 5,065 simulator-ready JSONs).
- **Virtual Mount**: Mounted in worker virtual memory using Emscripten MEMFS at `/home/pyodide/`.
- **Cross-Platform Case Resilience**: Filesystem lookups in `config_load.py` and `web_gui.py` employ case-insensitive fallback logic to prevent POSIX MEMFS case mismatches.

---

## 5. Web Release Build Pipeline (`tools/build_web_release.py`)

Building the complete release requires a single command:

```powershell
python tools/build_web_release.py
```

### Build Steps Executed:
1. Compresses engine and blueprints into `dist/swtorsim_assets.zip`.
2. Copies `tools/web/sim_worker.js` and `tools/web/pyodide_client.js` to `dist/`.
3. Injects the client bridge into `tools/simulator_ui.html` and `data/rotation_builder_ui.html`.
4. Outputs standalone static entrypoints into `dist/index.html` and `dist/rotation_builder.html`.

---

## 6. Testing & Deployment

### Local Static Preview
To run the static web build locally without a Python backend server:
```powershell
python -m http.server 8080 -d dist
```
Navigate to [http://localhost:8080](http://localhost:8080).

### Deploying to Production
Publish the contents of `dist/` directly to any static web hosting provider:
- **GitHub Pages**: Set source directory to `dist/` or deploy via GitHub Actions.
- **Cloudflare Pages / Vercel / Netlify**: Configure publish directory as `dist/`.
- **Static Hosting**: Supports Amazon S3, Google Cloud Storage, or standard Nginx/Apache static web roots.
