# Plan 07: Shareable Build Links

Status: proposed. Size: S-M (one session). Risk: none to the engine formulas; one new optional input on the run request (an inline rotation). Works best after plans 01 (adrenal) and 06 (encounter) so their fields travel too, but does not depend on them (unknown keys are simply carried).

## 1. Summary (for humans)

Sharing a setup today means exporting a run config JSON file and sending it, and the other person also needs your build file and your rotation file. This plan adds a **Share** button that produces a single link containing the whole setup: class, discipline, skill tree, tactical, implants, relics, adrenal, every stat input, engine toggles, encounter, and the rotation itself. Opening the link restores everything. The setup is packed into the part of the URL after `#`, which browsers never send to any server, so it works with the zero-server web release (GitHub Pages and similar) and with the local app.

The person opening the link does **not** need the rotation file. The rotation travels inside the link, is held in memory by the page, and is sent with each run request. Nothing is written to disk unless the user chooses to save it.

### What the user sees

- Header: a **Share** button (next to Export Config).
- A modal with the link in a read-only box, a **Copy** button, the link size, two checkboxes, and an **Import** box where a link or code can be pasted:
  - "Include rotation", **on** by default.
  - "Include run settings (mode, iterations, seed)", **off** by default. When off, the person opening the link keeps their own mode, iterations and seed.
- Opening a link (or pasting one) shows a confirmation summary: "Assassin / Hatred, Tactical X, Implants A + B, Relics R1 + R2, rotation 'BasicMaliPS' (from link). Apply?" Apply fills the form.
- The rotation select then shows an entry `Shared: BasicMaliPS`, selected. Simulate works right away. A **Save as custom rotation** button next to the select saves it to the user's custom rotations if they want to keep it.

## 2. Scope and non-goals

In scope: encode/decode, Share modal, import on page load and from paste, in-memory shared rotation, inline rotation on the run request (native and WASM), optional save of a shared rotation, input validation, a small read-only endpoint the **sender** uses to read a rotation file's raw JSON.

Not in scope: short links (would need a server), sharing simulation *results*, sharing between different app versions beyond a version field and graceful errors, inline rotations in run config files or the CLI (they keep requiring `rotation_path`).

## 3. Rules that apply

- Rule 11: a shared rotation is never written to disk on import. It is written only when the user clicks **Save as custom rotation**, and then only as a **custom** file (`data/rotations/custom/...`, or browser storage in WASM). Built-in files are never overwritten.
- Privacy: the share object contains no names or personal data (only game FQNs, numbers and the rotation). Do not add anything else.
- Security: decoded content is untrusted input, on the page **and** on the server (the inline rotation reaches Python). Validate types, sizes and strings before using them; never `eval`; never insert decoded strings into `innerHTML` unescaped.

## 4. Current state (facts)

- `tools/simulator_ui.html :: buildExportRunConfigObject()` (around line 3438) returns the full run config object: class/spec, `spec_path`, `stats_path`, `stats_override` (all stat inputs), `rotation_path`, `choices`, `tactical_fqn`, `legendary_fqns`, `relic_fqns`, mode, iterations, duration, level, dummy HP, seed, toggles, combat distance.
- `buildPayloadFromForm()` (around line 2352) builds the run request; it sends `rotation_path: rotationSelect.value`. `updateSimulateButtonState()` (around line 3541) disables Simulate when the rotation select has no value.
- `applyPresetRunConfig(path, fallbackParsed)` fetches `/api/run_config?path=...` (a server-side file) and applies the returned bundle to the form. There is no "apply from an object" function.
- The engine side reads rotations only from disk:
  - `RunConfig.rotation_path` is a required key (`src/swtorsim/run_config.py`, `_REQUIRED_CONFIG_KEYS`), and `validate_run_config` fails when that file does not exist.
  - `web_gui.py :: _resolve_simulation_inputs_from_payload` (around line 500) resolves `payload["rotation_path"]` and later calls `load_rotation_from_json(rotation_path)` (around line 627; `config_load.py` just reads the JSON file).
  - Every run entry goes through that function: `execute_simulation_from_payload` (native TEST and BATCH), `execute_simulation_slice` and `aggregate_batch_slices` (WASM workers). So an inline rotation added there reaches every path.
  - The native batch process pool is reused while its `pool_key` is unchanged (around line 1305); the key includes `config.rotation_path` but not the rotation content.
- Custom files: `POST /api/custom_file/import` (`web_gui.py`) writes `data/rotations/custom/<class>/<spec>/<file>.json` natively; in WASM `pyodide_client.js` stores it in `localStorage` (`swtor_custom_files`) and syncs it to every worker. After import the catalog must be reloaded (`loadCatalog(true)`).
- Rotation file validation in the UI: `validateRotationFile(obj)` (around line 3789; accepts a non-empty array, or an object with `sequence` / `rotation` / `steps` / `priority`).
- The native simulator server has no endpoint returning a rotation file's raw JSON. (The Rotation Builder server has `/api/rotation`, which returns a normalized form; in WASM `/api/rotation` maps to `LOAD_ROTATION`.)
- Stats: `validate_run_config` requires `stats_path` to be an existing file. A shared link from someone using a custom build file would fail on another machine unless the importer swaps in an existing build file; that is safe because `stats_override` carries every stat input and overrides the file.

## 5. Design

### 5.1 Share object (version 1)

```json
{
  "v": 1,
  "app": "swtorsim",
  "env": "live",
  "rc": { "...buildExportRunConfigObject() output..." },
  "rotation": {
    "name": "MyRotation.json",
    "content": "...rotation JSON exactly as in the file (array or object)..."
  }
}
```

`rotation` is `null` when "Include rotation" is unchecked (it is checked by default). The sender's `rotation_path` stays in `rc` only as a hint for the "not included" case (section 5.5).

Run settings: `mode`, `iterations` and `seed` are deleted from `rc` unless "Include run settings" is checked (unchecked by default). Duration, dummy HP, level, toggles and combat distance always travel: they describe the fight, not the run.

### 5.2 Encoding

`code = "1." + mode + "." + base64url(bytes)` where:
- `mode = "z"`: `bytes = deflate-raw(UTF-8(JSON.stringify(obj)))` via `CompressionStream("deflate-raw")`.
- `mode = "j"`: no compression (fallback when `CompressionStream` is missing).
- base64url = standard base64 with `+` -> `-`, `/` -> `_`, no `=` padding.

Link = `location.origin + location.pathname + location.search + "#b=" + code`.

Limits: refuse to decode codes longer than 200,000 characters or that inflate to more than 2 MB.

```js
async function encodeShareCode(obj) { ... }   // -> "1.z.xxxx"
async function decodeShareCode(code) { ... }  // -> obj (throws Error with a user-readable message)
function base64UrlEncode(bytes) { ... }
function base64UrlDecode(str) { ... }          // -> Uint8Array
async function deflateRaw(bytes) { ... }       // CompressionStream, collect with new Response(stream).arrayBuffer()
async function inflateRaw(bytes) { ... }       // DecompressionStream
```

### 5.3 Validation of a decoded object

```js
function validateShareObject(obj) -> string | null   // error message or null
```

- `obj.v === 1`, `obj.app === "swtorsim"`, `obj.env in {"live", "pts"}`.
- `obj.rc` is an object; string fields are strings shorter than 300 chars; FQN fields match `/^[a-z0-9_.]+$/`; paths match `/^data\/[A-Za-z0-9_\-./ ()]+\.json$/` and contain no `..`; numbers are finite; `legendary_fqns` length 0-2, `relic_fqns` length 0-2; `choices` values are 1, 2 or 3; `stats_override` values are finite numbers.
- `obj.rotation` is `null` or has a `name` matching `/^[A-Za-z0-9_\-. ()]+\.json$/` and a `content` that passes `validateRotationFile` **and** every string inside it (ability ids, block names, rule names, buff names) matches `/^[\w\s\-+'().:/%,&!?#]*$/` and is shorter than 200 chars. Reject otherwise ("Shared rotation contains unexpected characters"). This blocks HTML injection through rotation names that other parts of the UI render with `innerHTML`.

### 5.4 Applying an object

Refactor `applyPresetRunConfig` into two functions with identical behavior for the existing caller:

```js
async function fetchRunConfigBundle(path) { ... }          // the current fetch + error handling
async function applyRunConfigBundle(bundle) { ... }        // the current apply logic
async function applyPresetRunConfig(path, fallbackParsed = null) {
  const bundle = await fetchRunConfigBundle(path);         // keep the same status/error messages
  await applyRunConfigBundle(bundle, fallbackParsed);
}
```

For a share object build a bundle-like object:

```js
const bundle = {
  run_config: rc,
  class_name: rc.class_name || rc.class,
  spec: rc.spec || rc.spec_name,
  stats: {},                       // stats come from stats_override
  stats_override: rc.stats_override || {},
  choices: rc.choices || {},
};
```

Before applying:
1. Switch environment if `obj.env !== currentEnvironment` (call `setEnvironment(obj.env)` and wait for the catalog reload).
2. Run settings: if `rc.mode` / `rc.iterations` / `rc.seed` are missing, fill them from the current form (`CURRENT_MODE`, `iterationsInput`, `seedInput`) before applying. This is needed because the current apply logic calls `setSimMode((rc.mode || "TEST").toUpperCase())`, which would reset a BATCH user to TEST. Do it in the share path only, so preset loading stays exactly as today. The confirmation summary says "Run settings: yours" or lists the shared ones.
3. `stats_path`: if not in `CATALOG.builds` paths, replace it with the first catalog build whose path is not under `/custom/` (any works; `stats_override` overrides every value) and mention it in the confirmation summary.
4. Then `applyRunConfigBundle(bundle)`.
5. Then the rotation (section 5.5), after the bundle so the spec's rotation list is already populated.

### 5.5 Shared rotation in memory

Page state:

```js
let SHARED_ROTATION = null;   // { name, content } or null
const SHARED_ROTATION_VALUE = "__shared__";
```

- If `obj.rotation` is included: set `SHARED_ROTATION`, add (or replace) an option `value="__shared__"`, label `Shared: <name without .json>` (set with `textContent`) at the top of `rotationSelect`, and select it. No file is read, compared or written.
- If `obj.rotation` is null: select `rc.rotation_path` if it exists in `CATALOG.rotations`; otherwise warn "Rotation not included and not found here" and leave the rotation select unchanged.
- `updateRotationOptionsForCurrentSpec` keeps the shared option while the class/discipline stays the same as in the link; changing class or discipline drops it and clears `SHARED_ROTATION` (the rotation belongs to that discipline).
- A refresh loses in-memory state. To keep that simple, the hash is **not** cleared after import: a refresh shows the confirmation again. Applying a preset or importing another link replaces it.

Run request: in `buildPayloadFromForm()`, when `rotationSelect.value === "__shared__"`, send `rotation_inline: SHARED_ROTATION.content` and `rotation_path: ""` instead of the select value. Everything else is unchanged.

Other places that use the selected rotation:
- `updateSimulateButtonState`: `"__shared__"` counts as a selected rotation.
- Export Config: run config files need a real `rotation_path`. When the shared rotation is selected, Export Config asks "Save the shared rotation as a custom rotation first?" and exports with the saved path on yes (default; see open question 3).
- Delete-custom-file and "edit in Rotation Builder" controls are disabled for the shared entry (it has no file).
- Share while the shared rotation is selected: `buildShareObject` uses `SHARED_ROTATION` directly (no fetch), so links can be passed on.

**Save as custom rotation** (button next to the select, shown only for the shared entry): `POST /api/custom_file/import` (`category: "rotations"`, `class_folder` / `spec_folder` from the spec, `filename`: `SHARED_ROTATION.name`; if that name already exists, use `<stem>_shared.json`, then `<stem>_shared_2.json`, ...), reload the catalog, select the new path, drop the shared entry.

### 5.6 Engine input: inline rotation

`RunConfig` gets one optional field (not a formula; no stat routing involved):

```python
rotation_inline: Any = None   # rotation JSON sent with the request; used instead of rotation_path
```

- `validate_run_config`: when `rotation_inline is not None`, skip the `rotation_path` file check and instead require `rotation_inline` to be a non-empty list, or a dict with a list `sequence` / `rotation` / `steps` / `priority` (same shapes as `validateRotationFile`). Otherwise unchanged. `load_run_config` (files, CLI) never sets it, so run config files keep requiring `rotation_path`.
- `web_gui.py :: _resolve_simulation_inputs_from_payload`: read `payload.get("rotation_inline")`. When present, refuse it if its JSON exceeds 2 MB ("Inline rotation is too large"), pass it to `RunConfig`, keep `rotation_path=""`, and use it as `rotation_config` instead of `load_rotation_from_json(rotation_path)`. When absent, behavior is exactly as today.
- Native batch pool key: add a content fingerprint, for example `hashlib.sha256(json.dumps(rotation_inline, sort_keys=True).encode()).hexdigest()` (or `None`), next to `config.rotation_path`, so two different shared rotations never reuse one pool.
- WASM: the payload is already JSON-forwarded to the primary worker and every slice worker (`execute_simulation_slice`, `aggregate_batch_slices`), so no bridge change is needed. Check that `pyodide_client.js` forwards the payload as-is (no field whitelist).

### 5.7 Endpoint: raw rotation file (sender only)

The sender's page needs the rotation's content to put it in the link. Native `GET /api/rotation_file?path=<rel>` and WASM bridge action `READ_ROTATION_FILE`:

```python
def read_rotation_file(rel_path: str) -> dict:
    """Raw JSON of a rotation file under data/rotations/ (refuses any other location)."""
    target = _resolve_workspace_path(rel_path)
    root = (SWTORSIM_ROOT / "data" / "rotations").resolve()
    try:
        target.resolve().relative_to(root)
    except ValueError:
        raise ValueError("Only files under data/rotations/ can be read.")
    if not target.is_file() or target.suffix.lower() != ".json":
        raise FileNotFoundError(f"Rotation file not found: {rel_path}")
    return {"path": _to_workspace_rel(target), "content": load_json_file(str(target))}
```

Return 404 for missing files, 400 for refused paths. In WASM, add the `/api/rotation_file` intercept that calls `callPrimaryWorker("READ_ROTATION_FILE", {path})`. (Note the virtual FS in WASM includes the user's custom files, synced from `localStorage`.) The receiver never calls it.

### 5.8 UI

- Header button `<button class="btn btn-sm" id="shareBtn" type="button" onclick="openShareModal()">Share</button>` next to "Export Config".
- Modal `shareModal`: read-only `<input id="shareLinkInput">`, Copy button (`navigator.clipboard.writeText`, fallback: select the input and `document.execCommand("copy")`), size label ("2.1 KB"), "Include rotation" checkbox (checked by default) and "Include run settings (mode, iterations, seed)" checkbox (unchecked by default), both re-encode on change, Import textarea + "Import" button (accepts a full link or the bare code; extract with `/#b=([^&\s]+)/` or take the trimmed text).
- On startup: in the final `loadCatalog(false)` call at the end of the script, chain `.then(() => maybeImportFromHash())`. `maybeImportFromHash` reads `location.hash` and imports (the hash stays; see 5.5).
- **Save as custom rotation** button next to the rotation select, visible only while the shared entry is selected.
- Confirmation summary uses `textContent` (not `innerHTML`) for every decoded value.

## 6. Step-by-step implementation

1. Baseline tests and DPS baseline (`tools/dps_baseline.py --save`), since the run input path changes.
2. Engine input: `RunConfig.rotation_inline`, `validate_run_config` branch, `_resolve_simulation_inputs_from_payload`, pool key fingerprint. Python tests.
3. `read_rotation_file` + `GET /api/rotation_file` (native) + bridge action + JS intercept. Python tests.
4. Refactor `applyPresetRunConfig` into `fetchRunConfigBundle` / `applyRunConfigBundle`; check the existing preset loading and file import still work (manual).
5. Encode/decode helpers, `buildShareObject()` (async: fetches the rotation content through the new endpoint, or uses `SHARED_ROTATION`), `validateShareObject`.
6. Share modal, Copy, Import box, startup hash import, confirmation.
7. Shared rotation entry, `rotation_inline` in `buildPayloadFromForm`, Simulate button state, Export Config prompt, Save as custom rotation (section 5.5).
8. DPS compare (`--compare`), manual checks (section 8), docs, CHANGELOG.

## 7. Tests

Python, new file `tests/test_share_links.py`:
- `test_inline_rotation_runs_without_rotation_file`: payload with `rotation_inline` and `rotation_path: ""` runs a TEST sim.
- `test_inline_rotation_matches_file_rotation`: same seed, the content of a built-in rotation inline vs. its `rotation_path` gives identical DPS and ability breakdown.
- `test_inline_rotation_rejects_bad_shapes`: empty list, a string, a dict without a step list, and an over-size payload are refused with readable errors.
- `test_run_config_file_still_requires_rotation_path`: `load_run_config` on a file without `rotation_path` still fails.
- `test_pool_key_differs_for_different_inline_rotations`.
- `test_read_rotation_file_returns_raw_json` for a built-in rotation.
- `test_read_rotation_file_refuses_outside_rotations` (`data/builds/L80_14gcd_red.json`, `../AGENTS.md`, an absolute path to `src/swtorsim/engine.py`).
- `test_read_rotation_file_missing_is_not_found`.

JavaScript has no harness. Verify manually in the browser console (section 8, check 2).

## 8. Verification

1. Full suite passes; DPS compare shows no change for every saved run config (no config uses `rotation_inline`).
2. Console round trip: `const o = buildExportRunConfigObject(); const c = await encodeShareCode({v:1, app:"swtorsim", env:currentEnvironment, rc:o, rotation:null}); JSON.stringify((await decodeShareCode(c)).rc) === JSON.stringify(o)` is `true`.
3. Native: Share with default checkboxes -> copy -> open the link in a new tab -> confirm -> the form matches (class, spec, skill tree, gear, stats, toggles), the rotation shows as `Shared: ...`, and a TEST run with the same seed gives the same DPS as in the original tab. BATCH run too.
4. Run settings: with "Include run settings" off, set the receiving tab to BATCH, 500 iterations, seed 7, open the link: all three stay. With it on, they take the sender's values.
5. No file needed: share a setup that uses a rotation under `data/rotations/custom/`; delete that file (or use the WASM build in a private window); open the link; Simulate works and the DPS matches, and no file appears under `data/rotations/custom/` (or in `swtor_custom_files`). Then Save as custom rotation creates exactly one file and selects it.
6. Two different shared rotations run back to back in BATCH give their own results (pool not reused).
7. Malicious input: craft a code whose rotation block name is `<img src=x onerror=alert(1)>`; import must be refused with the "unexpected characters" message.
8. Oversized code is refused with a readable error.
9. WASM build: repeat 3, 4, 5 and 6.

## 9. Docs

- `docs/user_guide.md`: "Sharing a setup" paragraph (what is included, that nothing is uploaded, that a shared rotation runs straight from the link and is saved only if you click Save).
- `ARCHITECTURE.md`: `simulator_ui.html` row (`openShareModal, encodeShareCode, decodeShareCode, validateShareObject, applyRunConfigBundle, maybeImportFromHash, saveSharedRotation`), `web_gui.py` row (`read_rotation_file`, `GET /api/rotation_file`, `rotation_inline` on the run request), `run_config.py` row (`RunConfig.rotation_inline`), bridge action.
- `CHANGELOG.md`.

## 10. Done when

- [ ] Share produces a working link natively and in WASM; Copy works.
- [ ] Opening or pasting a link restores the full setup and runs the shared rotation without any rotation file on the receiver's side.
- [ ] Nothing is written to disk on import; Save as custom rotation writes one custom file.
- [ ] Untrusted input is validated on the page and on the server; the injection test is refused.
- [ ] Existing preset loading, run config files and the CLI unchanged; DPS compare unchanged.
- [ ] Tests, docs, CHANGELOG.

## 11. Decisions

- Rotation is included by default ("Include rotation" checked).
- Mode, iterations and seed are optional and left out by default ("Include run settings" unchecked).

## 12. Open questions for the user

1. Export Config while a shared rotation is selected: ask to save it first (plan default), or let run config files carry an inline rotation too?
