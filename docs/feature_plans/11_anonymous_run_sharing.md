# Plan 11: Anonymous Run Sharing (record high-DPS rotations and configs from the website)

Status: on hold (built and tested on 2026-11-24, then reverted by request). Size: S (one session). Risk: none to the engine (web client + a Cloudflare Pages Function; no sim code changes).

The complete working code is in the appendices, so reinstating it is mostly copying files back. The appendices are a snapshot from 2026-11-24 (last commit `e7d4bd9`). Re-locate the insertion points with `grep` before applying them.

## 1. Summary (for humans)

The website (`swtorsim.pages.dev`, a static Cloudflare Pages build) runs every simulation in the visitor's browser, so nothing reaches the maintainer. This feature records the setups people use that reach a DPS threshold:

- After a **BATCH** run averaging **60,000+ DPS**, the page quietly sends the run's inputs and DPS numbers to a small Cloudflare Pages Function, which stores them in a D1 database.
- Users can turn it off with a toggle (on by default) in section 4, "Engine Mechanics & Toggles".
- The maintainer exports the table and runs a local tool that re-simulates each row with its stored seed. A row whose DPS does not reproduce is flagged, so faked submissions can't pollute the data.

## 2. What the user sees

- In section 4, a checkbox (web build only, hidden in the local GUI): **"Send anonymous logs of anomalous runs for bug-hunting and rotation research"**, ticked by default. Its `?` tooltip says: "Web version only. After a Batch run averaging 60,000+ DPS, sends the rotation, build, choices and sim settings plus the DPS numbers. Custom file names are replaced with generic ones. No IP address, name or other personal data is collected."
- Nothing else changes. The send is fire-and-forget; errors are swallowed and never affect the simulator.

## 3. Decisions already made with the user (2026-11-24)

- **No IPs or other identifiers.** Only rotations, configs and results. The Function reads no request headers except `Content-Length` and stores no IP, user agent or cookie. (Cloudflare itself still sees IPs, as for any hosted site.)
- **Threshold: 60k average DPS, BATCH runs only.** A single TEST run is too noisy.
- **Opt-out, on by default,** with the label above. The user removed an earlier "(unusually high DPS)" wording from the label. Keep "rotation research" in the label so the stated purpose stays accurate.
- **Data is for private analysis.** Publishing submissions (for example a leaderboard) would need a separate opt-in, because a tuned rotation is arguably the user's own work.
- **Free text is stripped.** Custom file names become `rotation.json` / `build.json`; the class/spec folder is kept. The payload has no other free-text fields (rotation step `name` fields are ability names).

## 4. Current state (facts, 2026-11-24)

- `tools/web/pyodide_client.js` intercepts every `fetch` to `/api/*` in WASM mode and answers it from the workers. Unknown `/api/*` routes return 404, so the submit URL must **not** start with `/api/` (used: `/submit_run`, sent with `originalFetch`).
- The `/api/simulate` route returns BATCH reports with `avg_dps`, `median_dps`, `min_dps`, `max_dps`, `std_dev`, `iterations`, `duration`, `environment`, `class_name`, `spec` (`web_gui.py` `aggregate_batch_slices`).
- The simulate payload (`simulator_ui.html` `buildPayloadFromForm`) references files only by `spec_path`, `stats_path`, `rotation_path`. Choices and `stats_override` are inline. A user's custom files live only in browser storage: `state.customFiles[vPath]`, persisted in `localStorage` `swtor_custom_files`.
- `_resolve_workspace_path` accepts absolute paths, so the verify tool can write custom file contents to a temp dir and point the payload at them.
- `dist/` is committed and the site is on Cloudflare Pages. Pages Functions must sit in `functions/` in the Pages project's **root directory**. That is the repo root if the project is configured as root `/` + output `dist`. **Check the actual Pages project settings first.** Drag-and-drop dashboard uploads do not support Functions.
- No Node.js is on PATH. Atom bundles Node 12 at `C:\Users\Rafael\AppData\Local\atom\app-1.60.0\resources\app\apm\bin\node.exe`, which is good for `--check` and scratch harnesses. Node 12 has no `crypto.subtle` or `Response`, so the harness stubs them, and it can't `--check` ESM, so strip `export ` before checking.

## 5. Design

### 5.1 Client (`tools/web/pyodide_client.js`), Appendix A

- Constants `SHARE_SUBMIT_URL = "/submit_run"`, `SHARE_MIN_DPS = 60000`, `SHARE_STORAGE_KEY = "swtor_share_runs"`, `BUILD_VERSION = "__SWTORSIM_BUILD_VERSION__"` (stamped by the release build).
- `maybeSubmitRun(payload, result)` is called from the `/api/simulate` route right after a successful result (`if (!isError) maybeSubmitRun(payload, result);`). It exits early if:
  - the toggle is off,
  - the run is not BATCH,
  - the result is an error or a cancel, or
  - `avg_dps < 60000`.
- `buildRunSubmission` builds the request body: `{build_version, result: {...numbers}, inputs: {payload, files: {rotation, build}}}`.
  - A **custom** file becomes `{path: <same folder>/rotation.json, custom: true, content}`, and the payload's `rotation_path`/`stats_path` is rewritten to match.
  - A **bundled** file becomes `{path, custom: false, content: null}`.
- `initShareRunsToggle()` runs on `DOMContentLoaded` in WASM mode on the simulator page (next to `updateCoreSelectorUI()`). It reveals `#shareRunsRow` and wires `#toggleShareRuns` to `localStorage`.

### 5.2 UI (`tools/simulator_ui.html`), Appendix B

- A hidden `label.checkbox-row#shareRunsRow` holding `input#toggleShareRuns`, placed after the "In Flashpoint / Operation Instance" toggle in section 4.

### 5.3 Release build (`tools/build_web_release.py`), Appendix B

- One extra replace on the client content: `'"__SWTORSIM_BUILD_VERSION__"'` -> `f'"{build_version}"'`.

### 5.4 Pages Function (`functions/submit_run.js`), Appendix C; schema (`tools/web/submissions_schema.sql`), Appendix D

- `onRequestPost`:
  - Returns 503 without a `SUBMISSIONS_DB` binding and 413 over 256 KB (declared and actual length).
  - Returns 400 on bad JSON or a bad shape.
  - Returns 422 unless the run is BATCH with iterations >= 2, `avg_dps >= 60000` and a numeric seed.
  - Any other method returns 405.
- **Dedup:** SHA-256 of the canonical JSON (sorted keys) of `{payload minus seed and iterations, files}`. `INSERT ... ON CONFLICT(input_hash) DO UPDATE` bumps `submit_count`/`last_seen` and keeps the highest `avg_dps` together with its seed, iterations, inputs and build version. SQLite evaluates every `SET` expression against the pre-update row, so the assignment order doesn't matter.
- **Response:** `{ok: true, id: <first 12 hex chars of hash>}`.

### 5.5 Verify tool (`tools/verify_submissions.py`), Appendix E

- Reads a `wrangler d1 execute --json` export (`[{"results": [...]}]`) or a plain list of rows.
- For each row:
  1. Write the custom file contents to a temp dir.
  2. Set `mode=BATCH` and the stored seed/iterations.
  3. Re-run exactly as the web workers do: `execute_simulation_slice(start_run_id=0, slice_count=iterations)` + `aggregate_batch_slices`.
  4. Compare `avg_dps` within 1.0 DPS.
- Each row prints `[OK]` / `[MISMATCH]` / `[FAIL]`. Filters: `--limit`, `--spec`, `--class-name`. Rows from an older `build_version` may legitimately mismatch after engine changes.

## 6. Step-by-step implementation

1. Baseline test run (AGENTS.md rule 9).
2. Create `functions/submit_run.js` (Appendix C) and `tools/web/submissions_schema.sql` (Appendix D). Both must be CRLF.
3. Insert the client block (Appendix A) before `// --- UI Helpers ---` in `pyodide_client.js`, then add the two one-line hooks (Appendix B diff).
4. Apply the `simulator_ui.html` and `build_web_release.py` edits (Appendix B diff).
5. Create `tools/verify_submissions.py` (Appendix E) and `tests/test_verify_submissions.py` (Appendix F).
6. Syntax-check both JS files with Atom's Node (`--check`; strip `export ` for the Function). Run the scratch harnesses from section 7 in the session scratchpad, not the repo.
7. Full test suite, then docs (section 9), `CHANGELOG.md`, `TODO.md`.
8. Not damage-affecting: no DPS baseline compare needed.

## 7. Tests

- `tests/test_verify_submissions.py` (Appendix F), 4 tests:
  - parses both export formats
  - materializes custom files under generic names
  - a custom copy of `hatred_14gcd`'s rotation reproduces the bundled DPS (3 iterations, 60 s, seed 7)
  - the build-version placeholder is present in the client and in the builder
- On 2026-11-24 the full suite went from 460/460 to 464/464 OK.
- Scratch Node harness for the Function (stub `crypto.subtle.digest` with Node's `crypto`, stub `Response`, and use a fake D1 whose `prepare().bind().run()` records calls). Checked:
  - good run 200
  - same setup with a new seed gives the same hash
  - 59,999 DPS gives 422
  - TEST mode gives 422
  - bad JSON gives 400
  - over 256 KB gives 413
  - no binding gives 503
  - 13 bind values for `?1..?13`
- Scratch Node harness for the client block (slice the source from `// --- Anonymous run sharing` to `// --- UI Helpers ---` and run it through `new Function("state", "localStorage", "originalFetch", ...)`). Checked:
  - only the qualifying run is sent
  - the opt-out is respected
  - a custom `Rafael_secret.json` goes out as `rotation.json`, and the name appears nowhere in the body

## 8. Deployment (user steps in Cloudflare)

1. Create the D1 database, then apply the schema:
   `npx wrangler d1 execute <db-name> --remote --file tools/web/submissions_schema.sql`
2. Pages project -> Settings -> Functions -> D1 bindings: bind it as `SUBMISSIONS_DB`.
3. Confirm the project's root directory contains `functions/` (see section 4).
4. Rebuild `dist/` (`tools/build_web_release.py`) and deploy.
5. Do one 60k+ BATCH run on the live site, check that the row lands in `runs`, then export and run the verify tool:
   `npx wrangler d1 execute <db-name> --remote --json --command "SELECT * FROM runs ORDER BY avg_dps DESC" > runs.json`
   `.\tools\pyclean.exe tools\verify_submissions.py runs.json`

## 9. Docs to update when reinstated

- `ARCHITECTURE.md` file map:
  - add `maybeSubmitRun, buildRunSubmission, initShareRunsToggle` to the `pyodide_client.js` row
  - add rows for `functions/submit_run.js` and `tools/verify_submissions.py`
- `docs/pyodide_web_release.md`: an "Anonymous Run Sharing (Cloudflare Pages only)" subsection under Deploying to Production, covering what is sent, the setup steps and the verify step.
- `TODO.md`: the Cloudflare setup and release item (section 8) until it is deployed.

## 10. Done when

- A real 60k+ BATCH run on the deployed site appears as one row in D1, and the verify tool reports it `[OK]`.
- Turning the toggle off stops submissions. The local native GUI never submits.

## 11. Open questions for the user

- Should "anomalous" also include runs that end in an engine error or warning, or suspiciously low DPS? This was discussed and left unanswered; the built version sends only 60k+ runs.
- Is the Pages project's root directory the repo root (where `functions/` goes)?
- Should the data ever be published (leaderboard)? If yes, add a separate opt-in first.

---

## Appendix A: client block (`tools/web/pyodide_client.js`, insert before `// --- UI Helpers ---`)

```js
  // --- Anonymous run sharing (web build only) ---
  // BATCH runs averaging SHARE_MIN_DPS or more are POSTed to the Pages Function at
  // SHARE_SUBMIT_URL (functions/submit_run.js). Only simulation inputs and DPS numbers
  // are sent; custom file names are replaced with generic ones. Opt-out toggle:
  // #toggleShareRuns, stored as localStorage "swtor_share_runs" ("0" = off).
  const SHARE_SUBMIT_URL = "/submit_run";
  const SHARE_MIN_DPS = 60000;
  const SHARE_STORAGE_KEY = "swtor_share_runs";
  const BUILD_VERSION = "__SWTORSIM_BUILD_VERSION__";

  function isShareRunsEnabled() {
    try {
      return localStorage.getItem(SHARE_STORAGE_KEY) !== "0";
    } catch (_e) {
      return true;
    }
  }

  function setShareRunsEnabled(enabled) {
    try {
      localStorage.setItem(SHARE_STORAGE_KEY, enabled ? "1" : "0");
    } catch (_e) {}
  }

  function findCustomFileContent(path) {
    if (!path) return null;
    if (Object.prototype.hasOwnProperty.call(state.customFiles, path)) return state.customFiles[path];
    const lower = String(path).toLowerCase();
    for (const [k, content] of Object.entries(state.customFiles)) {
      if (k.toLowerCase() === lower) return content;
    }
    return null;
  }

  // Custom files keep their folder (class/spec) but get a generic file name, so a
  // user-chosen name never leaves the browser. Bundled files keep their repo path.
  function snapshotInputFile(path, genericName) {
    const content = findCustomFileContent(path);
    if (content === null) return { path: path || "", custom: false, content: null };
    const dir = String(path).replace(/[^\\/]*$/, "");
    return { path: dir + genericName, custom: true, content: content };
  }

  function buildRunSubmission(payload, result) {
    const rotation = snapshotInputFile(payload.rotation_path, "rotation.json");
    const build = snapshotInputFile(payload.stats_path, "build.json");
    const cleanPayload = Object.assign({}, payload, {
      rotation_path: rotation.path,
      stats_path: build.path
    });
    return {
      build_version: BUILD_VERSION,
      result: {
        avg_dps: result.avg_dps,
        median_dps: result.median_dps,
        min_dps: result.min_dps,
        max_dps: result.max_dps,
        std_dev: result.std_dev,
        iterations: result.iterations,
        duration: result.duration,
        environment: result.environment,
        class_name: result.class_name,
        spec: result.spec
      },
      inputs: {
        payload: cleanPayload,
        files: { rotation: rotation, build: build }
      }
    };
  }

  function maybeSubmitRun(payload, result) {
    try {
      if (!isShareRunsEnabled()) return;
      if (!payload || String(payload.mode || "").toUpperCase() !== "BATCH") return;
      if (!result || result.error !== undefined || result.cancelled) return;
      const avgDps = Number(result.avg_dps);
      if (!Number.isFinite(avgDps) || avgDps < SHARE_MIN_DPS) return;
      const body = JSON.stringify(buildRunSubmission(payload, result));
      // Fire and forget: sharing must never affect the simulator.
      originalFetch(SHARE_SUBMIT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body
      }).catch(() => {});
    } catch (_e) {}
  }

  function initShareRunsToggle() {
    const box = document.getElementById("toggleShareRuns");
    const row = document.getElementById("shareRunsRow");
    if (!box || !row) return;
    row.style.display = "";
    box.checked = isShareRunsEnabled();
    box.addEventListener("change", () => setShareRunsEnabled(box.checked));
  }

```

## Appendix B: edits to tracked files (git diff, 2026-11-24)

```diff
diff --git a/tools/build_web_release.py b/tools/build_web_release.py
index 556e4f4..ea97cde 100644
--- a/tools/build_web_release.py
+++ b/tools/build_web_release.py
@@ -59,6 +59,8 @@ def build_web_release() -> None:
     # Inject cache-busting asset URL into pyodide_client.js
     client_content = client_src.read_text(encoding="utf-8")
     client_content = client_content.replace('"swtorsim_assets.zip"', f'"swtorsim_assets.zip?v={build_version}"')
+    # Stamp the build version into run-sharing submissions (functions/submit_run.js).
+    client_content = client_content.replace('"__SWTORSIM_BUILD_VERSION__"', f'"{build_version}"')
     (DIST_DIR / "pyodide_client.js").write_text(client_content, encoding="utf-8")
     headers_src = WEB_TOOLS_DIR / "_headers"
     if headers_src.is_file():
diff --git a/tools/simulator_ui.html b/tools/simulator_ui.html
index 71b7886..f764b5e 100644
--- a/tools/simulator_ui.html
+++ b/tools/simulator_ui.html
@@ -1413,6 +1413,11 @@
           <span>In Flashpoint / Operation Instance</span>
           <span class="sig-help" title="Marks the fight as inside a Flashpoint or Operation instance for effects and passives that check instance state.">?</span>
         </label>
+        <label class="checkbox-row" id="shareRunsRow" style="display:none;">
+          <input type="checkbox" id="toggleShareRuns" checked>
+          <span>Send anonymous logs of anomalous runs for bug-hunting and rotation research</span>
+          <span class="sig-help" title="Web version only. After a Batch run averaging 60,000+ DPS, sends the rotation, build, choices and sim settings plus the DPS numbers. Custom file names are replaced with generic ones. No IP address, name or other personal data is collected.">?</span>
+        </label>
 
         <div class="form-row" style="margin-top:4px;">
           <div class="form-label">
diff --git a/tools/web/pyodide_client.js b/tools/web/pyodide_client.js
index dbf4882..2dc66f4 100644
--- a/tools/web/pyodide_client.js
+++ b/tools/web/pyodide_client.js
@@ -117,6 +117,103 @@
     cancelRequested: false
   };
 
+  // ... (Appendix A block) ...
   // --- UI Helpers ---
 
   function updateBackendBadge(label, className) {
@@ -844,6 +941,7 @@
         }
 
         const isError = result && (result.error !== undefined);
+        if (!isError) maybeSubmitRun(payload, result);
         return new Response(JSON.stringify(result), {
           status: isError ? 400 : 200,
           headers: { "Content-Type": "application/json" }
@@ -990,6 +1088,7 @@
       updateBackendBadge(`Pyodide [WASM Multi-Core: ${readyCount}/${state.targetPoolSize} Cores]`, "badge-wasm");
       if (!isBuilderPage) {
         updateCoreSelectorUI();
+        initShareRunsToggle();
       }
     }
   });
```

## Appendix C: `functions/submit_run.js`

```js
/**
 * Cloudflare Pages Function: POST /submit_run
 *
 * Stores anonymous BATCH runs from the web simulator that reach the DPS threshold.
 * Only the simulation inputs (payload + custom rotation/build file contents) and the
 * result numbers are stored. No IP, user agent, cookie or other request metadata is
 * read or written.
 *
 * Requires a D1 database bound as SUBMISSIONS_DB (schema: tools/web/submissions_schema.sql).
 * Rows with identical inputs collapse into one row (keyed by a SHA-256 of the inputs);
 * the row keeps the highest reported DPS and the seed that produced it.
 */

const MAX_BODY_BYTES = 256 * 1024;
const MIN_AVG_DPS = 60000;
const MIN_ITERATIONS = 2;
const SCHEMA_VERSION = 1;

function jsonResponse(obj, status) {
  return new Response(JSON.stringify(obj), {
    status: status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" }
  });
}

// Stable JSON (sorted object keys) so identical inputs always hash the same.
function canonicalJson(value) {
  if (Array.isArray(value)) {
    return "[" + value.map(canonicalJson).join(",") + "]";
  }
  if (value && typeof value === "object") {
    const keys = Object.keys(value).sort();
    return "{" + keys.map((k) => JSON.stringify(k) + ":" + canonicalJson(value[k])).join(",") + "}";
  }
  return JSON.stringify(value === undefined ? null : value);
}

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function finiteNumber(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function shortText(v, maxLen) {
  return String(v === undefined || v === null ? "" : v).slice(0, maxLen);
}

export async function onRequestPost(context) {
  const { request, env } = context;

  if (!env.SUBMISSIONS_DB) {
    return jsonResponse({ ok: false, error: "Submissions are not configured." }, 503);
  }

  const declaredLength = Number(request.headers.get("Content-Length") || "0");
  if (declaredLength > MAX_BODY_BYTES) {
    return jsonResponse({ ok: false, error: "Payload too large." }, 413);
  }
  const bodyText = await request.text();
  if (new TextEncoder().encode(bodyText).length > MAX_BODY_BYTES) {
    return jsonResponse({ ok: false, error: "Payload too large." }, 413);
  }

  let body;
  try {
    body = JSON.parse(bodyText);
  } catch (_e) {
    return jsonResponse({ ok: false, error: "Invalid JSON." }, 400);
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return jsonResponse({ ok: false, error: "Invalid submission." }, 400);
  }

  const result = body.result;
  const inputs = body.inputs;
  if (!result || typeof result !== "object" || !inputs || typeof inputs !== "object") {
    return jsonResponse({ ok: false, error: "Missing result or inputs." }, 400);
  }
  const payload = inputs.payload;
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return jsonResponse({ ok: false, error: "Missing simulation payload." }, 400);
  }

  const avgDps = finiteNumber(result.avg_dps);
  const iterations = finiteNumber(result.iterations);
  const seed = finiteNumber(payload.seed);
  if (avgDps === null || avgDps < MIN_AVG_DPS) {
    return jsonResponse({ ok: false, error: "Below threshold." }, 422);
  }
  if (iterations === null || iterations < MIN_ITERATIONS || String(payload.mode || "").toUpperCase() !== "BATCH") {
    return jsonResponse({ ok: false, error: "Only BATCH runs are accepted." }, 422);
  }
  if (seed === null) {
    return jsonResponse({ ok: false, error: "Missing seed." }, 422);
  }

  // Dedup key: everything that defines the setup, except the seed and iteration count,
  // so re-running the same rotation/config updates one row instead of adding new ones.
  const setup = { payload: Object.assign({}, payload), files: inputs.files || {} };
  delete setup.payload.seed;
  delete setup.payload.iterations;
  const inputHash = await sha256Hex(canonicalJson(setup));

  const now = new Date().toISOString();
  const inputsJson = JSON.stringify(inputs);

  await env.SUBMISSIONS_DB.prepare(
    `INSERT INTO runs (
       input_hash, schema_version, build_version, created_at, last_seen, submit_count,
       environment, class_name, spec, avg_dps, median_dps, std_dev, iterations, seed, inputs_json
     ) VALUES (?1, ?2, ?3, ?4, ?4, 1, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)
     ON CONFLICT(input_hash) DO UPDATE SET
       last_seen = excluded.last_seen,
       submit_count = runs.submit_count + 1,
       build_version = CASE WHEN excluded.avg_dps > runs.avg_dps THEN excluded.build_version ELSE runs.build_version END,
       median_dps = CASE WHEN excluded.avg_dps > runs.avg_dps THEN excluded.median_dps ELSE runs.median_dps END,
       std_dev = CASE WHEN excluded.avg_dps > runs.avg_dps THEN excluded.std_dev ELSE runs.std_dev END,
       iterations = CASE WHEN excluded.avg_dps > runs.avg_dps THEN excluded.iterations ELSE runs.iterations END,
       seed = CASE WHEN excluded.avg_dps > runs.avg_dps THEN excluded.seed ELSE runs.seed END,
       inputs_json = CASE WHEN excluded.avg_dps > runs.avg_dps THEN excluded.inputs_json ELSE runs.inputs_json END,
       avg_dps = MAX(runs.avg_dps, excluded.avg_dps)`
  ).bind(
    inputHash,
    SCHEMA_VERSION,
    shortText(body.build_version, 40),
    now,
    shortText(result.environment || payload.environment, 16),
    shortText(result.class_name || payload.class_name, 64),
    shortText(result.spec || payload.spec, 64),
    avgDps,
    finiteNumber(result.median_dps),
    finiteNumber(result.std_dev),
    Math.round(iterations),
    Math.round(seed),
    inputsJson
  ).run();

  return jsonResponse({ ok: true, id: inputHash.slice(0, 12) }, 200);
}

export async function onRequest() {
  return jsonResponse({ ok: false, error: "Method not allowed." }, 405);
}
```

## Appendix D: `tools/web/submissions_schema.sql`

```sql
-- D1 schema for anonymous web-simulator run submissions (functions/submit_run.js).
-- Apply once:  npx wrangler d1 execute <db-name> --remote --file tools/web/submissions_schema.sql
-- No IP, user agent or other request metadata is stored.

CREATE TABLE IF NOT EXISTS runs (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  input_hash      TEXT NOT NULL UNIQUE,
  schema_version  INTEGER NOT NULL,
  build_version   TEXT,
  created_at      TEXT NOT NULL,
  last_seen       TEXT NOT NULL,
  submit_count    INTEGER NOT NULL DEFAULT 1,
  environment     TEXT,
  class_name      TEXT,
  spec            TEXT,
  avg_dps         REAL NOT NULL,
  median_dps      REAL,
  std_dev         REAL,
  iterations      INTEGER NOT NULL,
  seed            INTEGER NOT NULL,
  inputs_json     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_spec_dps ON runs (class_name, spec, avg_dps DESC);
```

## Appendix E: `tools/verify_submissions.py`

```python
r"""Re-simulate anonymous web submissions and flag DPS numbers that do not reproduce.

Submissions come from the web simulator's run sharing (functions/submit_run.js -> D1 table
`runs`). The DPS a browser reports cannot be trusted on its own, but every row stores the
full inputs and the seed, so this tool re-runs each one the same way the web workers do
(execute_simulation_slice + aggregate_batch_slices) and compares the average DPS.

Export the rows first (Cloudflare wrangler CLI, run anywhere):
    npx wrangler d1 execute <db-name> --remote --json --command "SELECT * FROM runs ORDER BY avg_dps DESC" > runs.json

Then, from SwtorSim/:
    .\tools\pyclean.exe tools\verify_submissions.py runs.json
    .\tools\pyclean.exe tools\verify_submissions.py runs.json --limit 20 --spec Annihilation

Runs from an older build_version may legitimately differ if the engine changed since.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.swtorsim.web_gui import aggregate_batch_slices, execute_simulation_slice

DPS_TOLERANCE = 1.0


def load_rows(export_path: Path) -> list[dict[str, Any]]:
    """Accepts a wrangler --json export ([{"results": [...]}]) or a plain list of rows."""
    data = json.loads(export_path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = [data]
    rows: list[dict[str, Any]] = []
    for entry in data:
        if isinstance(entry, dict) and isinstance(entry.get("results"), list):
            rows.extend(r for r in entry["results"] if isinstance(r, dict))
        elif isinstance(entry, dict) and "inputs_json" in entry:
            rows.append(entry)
    return rows


def build_payload(row: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    """Rebuilds the simulate payload, writing custom rotation/build contents to work_dir."""
    inputs = json.loads(row["inputs_json"])
    payload = dict(inputs.get("payload") or {})
    files = inputs.get("files") or {}
    for key, payload_field in (("rotation", "rotation_path"), ("build", "stats_path")):
        snap = files.get(key) or {}
        if snap.get("custom") and isinstance(snap.get("content"), str):
            target = work_dir / f"{key}.json"
            target.write_text(snap["content"], encoding="utf-8")
            payload[payload_field] = str(target)
    payload["mode"] = "BATCH"
    payload["seed"] = int(row["seed"])
    payload["iterations"] = int(row["iterations"])
    return payload


def resimulate(payload: dict[str, Any]) -> float:
    iterations = int(payload["iterations"])
    with contextlib.redirect_stdout(io.StringIO()):
        sliced = execute_simulation_slice(dict(payload, start_run_id=0, slice_count=iterations))
        report = aggregate_batch_slices({
            "payload": payload,
            "all_harvested": sliced["harvested"],
            "wall_ms": 0.0,
            "total_iterations": iterations,
        })
    if "error" in report:
        raise RuntimeError(str(report["error"]))
    return float(report["avg_dps"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("export", type=Path, help="JSON export of the D1 `runs` table")
    parser.add_argument("--limit", type=int, default=0, help="Only check the first N rows (0 = all)")
    parser.add_argument("--spec", default="", help="Only rows whose spec matches (case-insensitive)")
    parser.add_argument("--class-name", default="", help="Only rows whose class matches (case-insensitive)")
    args = parser.parse_args()

    rows = load_rows(args.export)
    if args.spec:
        rows = [r for r in rows if str(r.get("spec", "")).lower() == args.spec.lower()]
    if args.class_name:
        rows = [r for r in rows if str(r.get("class_name", "")).lower() == args.class_name.lower()]
    if args.limit > 0:
        rows = rows[: args.limit]
    if not rows:
        print("[WARN] No rows to verify.")
        return 0

    counts = {"OK": 0, "MISMATCH": 0, "FAIL": 0}
    print(f"{'id':<12}  {'class/spec':<32}  {'claimed':>10}  {'recomputed':>10}  {'build':<12}  status")
    for row in rows:
        row_id = str(row.get("input_hash", ""))[:12]
        label = f"{row.get('class_name', '')}/{row.get('spec', '')}"[:32]
        claimed = float(row.get("avg_dps") or 0.0)
        build = str(row.get("build_version") or "")[:12]
        try:
            with tempfile.TemporaryDirectory(prefix="swtorsim_verify_") as tmp:
                recomputed = resimulate(build_payload(row, Path(tmp)))
            status = "OK" if abs(recomputed - claimed) <= DPS_TOLERANCE else "MISMATCH"
            shown = f"{recomputed:>10.1f}"
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the report
            status = "FAIL"
            shown = f"{'-':>10}"
            print(f"[FAIL] {row_id}: {exc}")
        counts[status] += 1
        print(f"{row_id:<12}  {label:<32}  {claimed:>10.1f}  {shown}  {build:<12}  [{status}]")

    print(f"\n[OK] {counts['OK']} reproduced, [WARN] {counts['MISMATCH']} mismatched, [FAIL] {counts['FAIL']} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## Appendix F: `tests/test_verify_submissions.py`

```python
"""Tests for tools/verify_submissions.py (re-simulating anonymous web run submissions)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import verify_submissions as vs

RUN_CONFIG = ROOT / "data" / "run_config" / "hatred_14gcd.json"


def _base_payload() -> dict:
    payload = json.loads(RUN_CONFIG.read_text(encoding="utf-8"))
    payload.update({"mode": "BATCH", "iterations": 3, "duration": 60, "seed": 7})
    return payload


def _row(payload: dict, files: dict, avg_dps: float) -> dict:
    return {
        "input_hash": "abc123def4567890",
        "class_name": "Assassin",
        "spec": "Hatred",
        "avg_dps": avg_dps,
        "seed": payload["seed"],
        "iterations": payload["iterations"],
        "build_version": "test",
        "inputs_json": json.dumps({"payload": payload, "files": files}),
    }


class VerifySubmissionsTests(unittest.TestCase):
    def test_load_rows_accepts_wrangler_export_and_plain_list(self):
        row = {"inputs_json": "{}", "avg_dps": 1.0}
        with tempfile.TemporaryDirectory() as tmp:
            wrapped = Path(tmp) / "wrapped.json"
            wrapped.write_text(json.dumps([{"results": [row, row], "success": True}]), encoding="utf-8")
            plain = Path(tmp) / "plain.json"
            plain.write_text(json.dumps([row]), encoding="utf-8")
            self.assertEqual(len(vs.load_rows(wrapped)), 2)
            self.assertEqual(len(vs.load_rows(plain)), 1)

    def test_build_payload_materializes_custom_files_with_generic_names(self):
        payload = _base_payload()
        rotation_text = (ROOT / payload["rotation_path"]).read_text(encoding="utf-8")
        payload["rotation_path"] = "data/rotations/assassin/hatred/rotation.json"
        files = {
            "rotation": {"path": payload["rotation_path"], "custom": True, "content": rotation_text},
            "build": {"path": payload["stats_path"], "custom": False, "content": None},
        }
        with tempfile.TemporaryDirectory() as tmp:
            rebuilt = vs.build_payload(_row(payload, files, 0.0), Path(tmp))
            self.assertEqual(Path(rebuilt["rotation_path"]), Path(tmp) / "rotation.json")
            self.assertEqual((Path(tmp) / "rotation.json").read_text(encoding="utf-8"), rotation_text)
            self.assertEqual(rebuilt["stats_path"], payload["stats_path"])
            self.assertEqual(rebuilt["seed"], 7)
            self.assertEqual(rebuilt["iterations"], 3)

    def test_custom_rotation_reproduces_bundled_rotation_dps(self):
        bundled = _base_payload()
        expected = vs.resimulate(bundled)

        custom = dict(bundled)
        rotation_text = (ROOT / bundled["rotation_path"]).read_text(encoding="utf-8")
        custom["rotation_path"] = "data/rotations/assassin/hatred/rotation.json"
        files = {"rotation": {"path": custom["rotation_path"], "custom": True, "content": rotation_text}}
        with tempfile.TemporaryDirectory() as tmp:
            recomputed = vs.resimulate(vs.build_payload(_row(custom, files, expected), Path(tmp)))
        self.assertAlmostEqual(recomputed, expected, delta=vs.DPS_TOLERANCE)
        self.assertGreater(expected, 0.0)

    def test_client_build_version_placeholder_is_stamped_by_release_build(self):
        client = (ROOT / "tools" / "web" / "pyodide_client.js").read_text(encoding="utf-8")
        builder = (ROOT / "tools" / "build_web_release.py").read_text(encoding="utf-8")
        self.assertIn('"__SWTORSIM_BUILD_VERSION__"', client)
        self.assertIn("__SWTORSIM_BUILD_VERSION__", builder)


if __name__ == "__main__":
    unittest.main()
```
