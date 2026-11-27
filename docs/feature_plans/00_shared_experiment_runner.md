# Plan 00: Shared Experiment Runner

Status: proposed. Size: M (two sessions: Python core, then WASM orchestration). Risk: low (no engine or math change).

## 1. Summary (for humans)

Several planned features ask the same question in different ways: "if I change X, how much does DPS change, and is the difference real?"

- Stat weights (plan 03): change one stat by +/- 250 rating.
- Top Gear (plan 04): swap tacticals, implants, relics, talents.
- Precision compare (plan 08): compare two setups fairly.
- Rotation tuner (plan 09): try many small rotation edits.
- Fit HP to fight length (plan 06): run a short pilot, adjust HP, run again.

All of them need an **experiment**: a list of **variants** of one setup, each run many times **on the same seeds**, plus statistics that compare each variant to a baseline. This plan builds that machinery once:

1. `src/swtorsim/stats_utils.py`: small, pure statistics helpers (mean, SD, SE, 95% CI, paired difference, Welch difference, p-value).
2. `src/swtorsim/experiments.py`: an experiment "driver" that decides which fights to run, round by round, plus a native executor that runs them on a process pool.
3. One HTTP endpoint (`POST /api/experiment`) and three Pyodide bridge actions so the same experiments run in the browser build.
4. Two small, behavior-preserving refactors in `web_gui.py`: the single-fight body of `_batch_worker_task` becomes a reusable function, and payloads may carry an in-memory rotation (`rotation_inline`).

### What the user sees

Nothing new by itself. This plan ships infrastructure plus one generic experiment kind (`"variants"`) used by tests. Plans 03, 04, 06, 08 and 09 add the visible features.

## 2. Scope and non-goals

In scope:
- Statistics helpers.
- Experiment driver protocol (start / advance) with pluggable "kinds".
- Native executor (multiprocessing pool, cancel, progress).
- WASM executor (job queue across existing Pyodide workers).
- `rotation_inline` payload support.
- Generic kind `"variants"`.

Not in scope:
- Any change to fight results. Every existing endpoint must return byte-identical numbers for the same seed after this plan.
- The CLI `Tester` path (`src/swtorsim/tester.py`): leave it alone.
- Feature-specific kinds (they belong to plans 03, 04, 06, 09).

## 3. Rules that apply

- AGENTS.md rule 1: no math changes. This plan only moves code that runs a fight; it must not change what the fight computes.
- Rule 9: same-seed identity check after the refactor (section 8).
- Rule 12: test helpers go in `tests/`, scratch checks in the scratchpad.

## 4. Current state (facts)

- One fight in a batch is `_batch_worker_task(args)` in `src/swtorsim/web_gui.py` (around lines 1099-1197). It accepts either a 4-tuple `(run_id, base_seed, duration, dummy_hp)` (context from the module global `_WORKER_SIM_CONTEXT`) or a 9-tuple carrying the full context. It:
  - applies `settings_dict` toggles (`set_stem_matching`, `set_projectile_flight_time`, `set_default_combat_distance`, `set_in_flashpoint_operation`),
  - seeds `random` with `base_seed + run_id`,
  - silences stdout, calls `prepare_simulation(rotation_config, stats_config, loadout_blueprints, dummy_hp, debuff_module, verbose=False, seed=worker_seed, precast=..., pre_combat=...)`, sets `combat_distance` on player and target, runs `sim.run_timed(duration, target)`,
  - returns `run_id + 1`, `dps`, `total_damage`, `elapsed`, `abilities`, `total_execute_damage`, `execute_duration`, `execute_abilities`, `stall_count`, `total_stalled_time`, `permanent_stall`, `seed`.
- The batch pool `get_or_create_simulation_pool(cores, sim_context, pool_key)` (around line 1056) is rebuilt whenever its key (loadout, stats, settings) changes. Rebuilding spawns new processes, which is slow on Windows. Running 20 variants through it would rebuild the pool 20 times. Experiments therefore need their own pool whose workers build variant contexts on demand.
- `_resolve_simulation_inputs_from_payload(payload)` (around line 505) resolves and validates a payload. It caches loadouts in `_BLUEPRINT_LOADOUT_CACHE`. It always loads the rotation from `rotation_path` (around line 627).
- WASM: `execute_simulation_slice` (around line 1509) resolves the payload inside the worker for every slice, so workers already know how to build a context from a payload.
- Cancel: `_SIM_CANCEL` (`threading.Event`, around line 122), set by `POST /api/simulate_cancel`. Progress: `_update_simulation_progress(running, mode, completed, total)` (around line 140), read by `GET /api/progress`.
- The existing batch result computes `std_dev` with the population formula (divide by n) and `ci_95 = 1.96 * std_dev / sqrt(n)` (around lines 1402-1440). Keep that unchanged for the BATCH display. The new helpers use the sample formula (divide by n - 1), which is the right one for inference; the difference is negligible at batch sizes but document it.

## 5. Design

### 5.1 `src/swtorsim/stats_utils.py` (new, pure)

No imports from the simulator. Everything takes plain lists of floats.

```python
"""Pure statistics helpers for comparing Monte Carlo DPS samples (no simulator imports)."""

import math
from typing import Iterable, Sequence

Z95 = 1.959963984540054  # two-sided 95% normal quantile


def mean(values: Sequence[float]) -> float:
    """Arithmetic mean; 0.0 for an empty sequence."""
    return sum(values) / len(values) if values else 0.0


def sample_sd(values: Sequence[float]) -> float:
    """Sample standard deviation (n - 1 denominator); 0.0 when n < 2."""
    n = len(values)
    if n < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))


def standard_error(values: Sequence[float]) -> float:
    """Standard error of the mean; 0.0 when n < 2."""
    n = len(values)
    return sample_sd(values) / math.sqrt(n) if n >= 2 else 0.0


def normal_two_sided_p(z: float) -> float:
    """Two-sided p-value of a standard normal z score."""
    if math.isinf(z):
        return 0.0
    return math.erfc(abs(z) / math.sqrt(2.0))


def percentile(sorted_values: Sequence[float], p: float) -> float:
    """Linear-interpolated percentile of an already sorted list (same rule as web_gui._percentile)."""
    ...


def summarize(values: Sequence[float]) -> dict:
    """n, mean, sd, se, ci95 (half width), min, max, median, p10, p25, p75, p90."""
    ...


def paired_difference(a_by_seed: dict[int, float], b_by_seed: dict[int, float]) -> dict:
    """Mean of (a - b) over seeds present in both samples.

    Returns {"method": "paired", "n", "diff", "se", "ci95", "z", "p", "significant", "diff_pct"}.
    diff_pct is diff / mean(b over the common seeds) * 100 (0.0 if that mean is 0).
    significant is True when n >= 2 and abs(diff) > Z95 * se.
    """
    ...


def welch_difference(a: Sequence[float], b: Sequence[float]) -> dict:
    """mean(a) - mean(b) with SE sqrt(var_a / n_a + var_b / n_b); same keys as paired_difference, method "welch"."""
    ...


def compare_samples(a_seeds, a_values, b_seeds, b_values, min_pairs: int = 10) -> dict:
    """Uses paired_difference when at least min_pairs seeds are shared, else welch_difference."""
    ...
```

Edge cases to define and test:
- `se == 0` and `diff == 0` -> `z = 0.0`, `p = 1.0`, `significant = False`.
- `se == 0` and `diff != 0` (all differences identical) -> `z = math.inf`, `p = 0.0`, `significant = True` if n >= 2.
- Fewer than 2 values -> `se = 0`, `significant = False`.
- The normal approximation is slightly optimistic for n < 30. Add a `"small_sample": n < 30` flag so UIs can show "approximate".

### 5.2 Fight runner refactor (in `web_gui.py`)

Extract the body of `_batch_worker_task` into a function with an explicit context argument:

```python
def run_fight_from_context(
    ctx: dict[str, Any],
    run_id: int,
    base_seed: int | None,
    duration: float,
    dummy_hp: int,
    lean: bool = False,
) -> dict[str, Any]:
    """Runs one seeded fight from a prepared simulation context (same steps as the batch worker).

    lean=True skips the per-ability summaries (abilities / execute_abilities) to keep results small.
    """
```

- Body: exactly the current code of `_batch_worker_task` from `set_stem_matching(...)` to the return dict, reading `rotation_config`, `stats_config`, `loadout_blueprints`, `debuff_module`, `settings_dict` from `ctx`.
- When `lean` is True, omit `abilities`, `execute_abilities` from the returned dict (keep every scalar).
- `_batch_worker_task(args)` keeps its signature and both tuple forms, builds `ctx` (from `_WORKER_SIM_CONTEXT` or from the 9-tuple) and returns `run_fight_from_context(ctx, run_id, base_seed, duration, dummy_hp)`.
- Also add a helper that builds the context dict, because `_run_batch_monte_carlo_detailed` (around line 1247) and `execute_simulation_slice` (around line 1515) both construct the same `settings_dict` / `sim_context` by hand:

```python
def build_fight_context(config: RunConfig, sim_inputs: dict[str, Any]) -> dict[str, Any]:
    """The sim_context dict used by batch workers: rotation, stats, loadout, debuffs, settings_dict."""
```

  Replace the two hand-built copies with calls to it. Same keys, same values.

### 5.3 `rotation_inline` (in `_resolve_simulation_inputs_from_payload`)

After `rotation_config = load_rotation_from_json(rotation_path)` (around line 627):

```python
inline = payload.get("rotation_inline")
if inline is not None:
    rotation_config = _validated_inline_rotation(inline)
```

```python
def _validated_inline_rotation(inline: Any) -> Any:
    """Deep-copies an in-memory rotation (bare step list or dict wrapper) after a shape check."""
    if isinstance(inline, list):
        steps = inline
    elif isinstance(inline, dict):
        steps = inline.get("sequence") or inline.get("steps")
    else:
        steps = None
    if not isinstance(steps, list) or not steps or not all(isinstance(s, dict) and s.get("type") for s in steps):
        raise ValueError("rotation_inline must be a non-empty step list or a dict with a 'sequence' list.")
    return copy.deepcopy(inline)
```

- `rotation_path` is still required and still validated (the inline rotation is "the file at rotation_path, edited in memory"). Document this in the docstring.
- Plans 07 (share links) and 09 (rotation tuner) use this.

### 5.4 Experiment model

All state is plain JSON (dicts, lists, numbers, strings) so it can travel between the browser and Pyodide workers.

```text
state = {
  "kind": "variants",
  "experiment_id": "<uuid4 hex>",
  "round": 0,                       # number of completed rounds
  "base_seed": 42,
  "duration": 1000,
  "dummy_hp": 6000000,
  "baseline_id": "baseline",
  "variants": {
     "<variant_id>": {
        "label": "Human readable label",
        "payload": { ...full simulate payload for this variant... },
        "fingerprint": "<16 hex chars>",
        "meta": { ...kind-specific info, e.g. {"stat": "Critical Rating", "delta": 250} },
        "status": "active" | "eliminated" | "invalid",
        "error": "only when invalid"
     }
  },
  "results": {
     "<variant_id>": {"seeds": [...], "dps": [...], "elapsed": [...], "stalled": [...], "deadlocked": [...]}
  },
  "kind_state": { ...anything the kind needs between rounds... }
}

job = {"variant_id": "...", "start_run_id": 0, "count": 100}
job_result = {"variant_id": "...", "runs": [lean run dict, ...]}
```

- Results are stored column-wise (`seeds`, `dps`, ...) to keep the JSON small (a lean run is 5 numbers, not a dict with 12 keys).
- `stalled` is `1` if `stall_count > 0` else `0`; `deadlocked` is `1` if `permanent_stall` else `0`.
- Run ids are absolute: fight `k` of every variant uses seed `base_seed + k`. A round that "adds 100 more fights" to a variant uses `start_run_id = len(results[vid]["seeds"])`. This keeps every variant on the same seeds (paired comparisons) and makes results independent of how rounds were split.

### 5.5 Driver API (`src/swtorsim/experiments.py`)

```python
"""Experiment driver: runs variants of one simulation setup on shared seeds and compares them."""

EXPERIMENT_KINDS: dict[str, "ExperimentKind"] = {}


class ExperimentKind:
    """Plug-in interface. Subclasses implement build / next_jobs / finalize."""

    name: str = ""

    def build(self, body: dict) -> dict:
        """Returns the initial state (section 5.4) from a request body."""
        raise NotImplementedError

    def next_jobs(self, state: dict) -> list[dict]:
        """Jobs for the next round; [] when the experiment is finished."""
        raise NotImplementedError

    def finalize(self, state: dict) -> dict:
        """The JSON result returned to the caller."""
        raise NotImplementedError


def register_kind(kind: ExperimentKind) -> ExperimentKind: ...

def start_experiment(body: dict) -> dict:
    """{"state", "jobs"} for the first round (or {"done": True, "result"} if nothing to run)."""

def advance_experiment(state: dict, job_results: list[dict]) -> dict:
    """Stores job results, increments round, and returns the next {"state", "jobs"} or {"done": True, "result"}."""

def run_job(job: dict, variant: dict, state: dict, lean: bool = True) -> dict:
    """Executes one job in the current process (used by pool workers, Pyodide workers and the 1-core path)."""

def run_experiment_blocking(body: dict, cores: int | None = None) -> dict:
    """Native loop: start -> execute jobs on a process pool -> advance, until done. Honors _SIM_CANCEL."""
```

Helper functions (all pure, all tested):

```python
RUNTIME_KEYS = ("mode", "iterations", "seed")

def apply_overrides(base_payload: dict, overrides: dict) -> dict:
    """Deep copy of base_payload with overrides applied.

    stats_override is merged key by key. A choices override is merged and written to both
    'choices' and 'choices_override' (the resolver prefers choices_override). Every other
    key is replaced.
    """

def payload_fingerprint(payload: dict) -> str:
    """First 16 hex chars of sha1 over the canonical JSON of payload minus RUNTIME_KEYS."""

def empty_results() -> dict:
    """{"seeds": [], "dps": [], "elapsed": [], "stalled": [], "deadlocked": []}"""

def append_runs(results: dict, runs: list[dict]) -> None:
    """Appends lean run dicts column-wise, keeping columns sorted by seed (dedupe by seed)."""

def variant_summary(results: dict) -> dict:
    """stats_utils.summarize(dps) plus stalled_runs, deadlocked_runs, avg_elapsed."""

def compare_to_baseline(state: dict, variant_id: str) -> dict:
    """stats_utils.compare_samples between a variant and the baseline on their shared seeds."""
```

Context caching inside a worker process (native pool worker, Pyodide worker, or the parent in 1-core mode):

```python
_CONTEXT_CACHE: "collections.OrderedDict[str, dict]" = OrderedDict()
_CONTEXT_CACHE_MAX = 64

def context_for_payload(payload: dict, fingerprint: str) -> dict:
    """Resolves the payload once per process (LRU by fingerprint) into a fight context.

    Uses web_gui._resolve_simulation_inputs_from_payload + web_gui.build_fight_context and
    also stores 'duration' and 'dummy_hp' from the resolved RunConfig.
    """
```

`run_job` then loops `run_id` over `range(start_run_id, start_run_id + count)` and calls `web_gui.run_fight_from_context(ctx, run_id, state["base_seed"], duration, dummy_hp, lean=lean)`.

Import direction: `experiments.py` imports `web_gui` at module top. `web_gui.py` imports `experiments` lazily inside the request handler (and `pyodide_bridge.py` imports it at top, which is fine because the bridge already imports `web_gui`). This avoids a circular import.

### 5.6 Native executor

Inside `run_experiment_blocking`:

1. `step = start_experiment(body)`.
2. Get the experiment pool: a module-level `multiprocessing.Pool` (separate from `web_gui._GLOBAL_SIMULATION_POOL`) created once per core count, with no heavy initializer. Register its cleanup with `atexit`, like `cleanup_simulation_pool`.
3. For each round:
   - Split every job into chunks of `chunk = max(1, ceil(total_runs_in_round / (cores * 4)))` runs. Interleave variants when submitting (round-robin) so progress and cancellation are balanced.
   - Submit `pool.apply_async(_experiment_chunk_task, (variant_payload, fingerprint, variant_id, start, count, base_seed, lean))`.
   - `_experiment_chunk_task` is a module-level function (picklable) that calls `context_for_payload` then the fight loop, and returns `{"variant_id", "runs"}`.
   - Poll like `_run_batch_monte_carlo_detailed` does (around lines 1317-1332): check `_SIM_CANCEL` every 50 ms; on cancel terminate the experiment pool (it is rebuilt next time) and raise `web_gui.SimulationCancelled`.
   - Update progress: `_update_simulation_progress(True, "EXPERIMENT", done_runs, total_runs, detail=f"Round {r + 1}: {n_variants} variants")`.
   - `step = advance_experiment(state, results)`.
4. Always finish with `_update_simulation_progress(False, "EXPERIMENT", ...)` in a `finally`.
5. **1-core / emscripten path**: when `cores == 1`, or `sys.platform == "emscripten"`, run chunks in-process with `run_job`. Tests use this path (no process spawning).

`_update_simulation_progress` gains an optional `detail: str = ""` argument stored in `_SIM_PROGRESS["detail"]`. Existing callers are unaffected. The JS poller in `runSimulation` ignores unknown fields.

### 5.7 HTTP endpoint (native)

In `SimulatorRequestHandler.do_POST`:

```python
if route == "/api/experiment":
    from src.swtorsim.experiments import run_experiment_blocking
    try:
        result = run_experiment_blocking(payload)
    except SimulationCancelled:
        result = {"cancelled": True}
    self._send_json(result)
    return
```

Request body: `{"kind": "<kind>", "payload": {<simulate payload>}, "options": {...}}` plus kind-specific keys. Errors from `build` (unknown kind, invalid options) raise `ValueError` and become `{"error": "..."}` with status 500 through the existing `except Exception` (consider returning 400 for `ValueError`; keep consistent with the other handlers, which use 500).

### 5.8 WASM executor

`src/swtorsim/pyodide_bridge.py :: dispatch`, new actions:

| Action | Payload | Returns |
|---|---|---|
| `EXPERIMENT_START` | request body | `start_experiment(body)` |
| `EXPERIMENT_JOB` | `{"job", "variant", "state_header"}` where `state_header` = `{"base_seed", "experiment_id"}` | `run_job(job, variant, state_header, lean=True)` |
| `EXPERIMENT_ADVANCE` | `{"state", "job_results"}` | `advance_experiment(state, job_results)` |

Send only the variant and a tiny state header with each job, not the whole state.

`tools/web/pyodide_client.js`:

```js
async function executeExperimentMultiCore(body) {
  await state.readyPromise;
  await ensureAllWorkersReady();
  let step = await callPrimaryWorker("EXPERIMENT_START", body);
  if (step && step.error) throw new Error(step.error);
  while (!step.done) {
    const results = await runExperimentJobs(step.state, step.jobs);   // job queue below
    step = await callPrimaryWorker("EXPERIMENT_ADVANCE", { state: step.state, job_results: results });
    if (step && step.error) throw new Error(step.error);
  }
  state.latestProgress.running = false;
  return step.result;
}

async function runExperimentJobs(expState, jobs) {
  // 1. Split jobs into chunks (same sizing rule as native: ceil(totalRuns / (workers * 4))).
  // 2. Each ready worker pulls the next chunk from a shared queue when it finishes the previous one.
  // 3. Update state.latestProgress = {running: true, mode: "EXPERIMENT", completed, total, detail}.
  // 4. Return [{variant_id, runs}, ...] merged per chunk (order does not matter; Python dedupes by seed).
}
```

Intercept in the `window.fetch` override, next to `/api/simulate`:

```js
if (pathname === "/api/experiment") {
  const body = JSON.parse(options.body || "{}");
  state.cancelRequested = false;
  try {
    const result = await executeExperimentMultiCore(body);
    return new Response(JSON.stringify(result), { status: result && result.error ? 400 : 200, headers: { "Content-Type": "application/json" } });
  } catch (err) {
    if (state.cancelRequested) {
      return new Response(JSON.stringify({ cancelled: true }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    throw err;
  }
}
```

Cancellation already terminates all workers (`cancelActiveSimulation`); a pending `callSpecificWorker` rejects, which lands in the `catch` above.

### 5.9 Generic kind `"variants"`

Request:

```json
{
  "kind": "variants",
  "payload": { "...base simulate payload..." },
  "variants": [
    {"id": "baseline", "label": "Current setup", "overrides": {}},
    {"id": "crit_plus_500", "label": "+500 Crit", "overrides": {"stats_override": {"Critical Rating": 4258}}}
  ],
  "baseline_id": "baseline",
  "iterations": 100
}
```

- `build`: validates ids are unique, `baseline_id` exists, `1 <= iterations <= 10000`; builds payloads with `apply_overrides`; reads `seed`, `duration`, `dummy_hp` from the base payload (defaults 42 / 1000 / 6,000,000 as in the resolver); validates each variant by calling `_resolve_simulation_inputs_from_payload` once in the parent (catch `ValueError` / `FileNotFoundError` -> `status = "invalid"`, `error = str(exc)`).
- `next_jobs`: round 0 -> one job per active variant `(0, iterations)`; afterwards `[]`.
- `finalize`: `{"kind", "iterations", "base_seed", "variants": [{id, label, status, error?, summary, vs_baseline}], "baseline_id"}`, sorted by mean DPS descending, baseline flagged.

## 6. Step-by-step implementation

Session 1 (Python):

1. Baseline: run the test suite; record the count. Run the same-seed reference in section 8 *before* editing and save the numbers in the scratchpad.
2. Create `src/swtorsim/stats_utils.py` (section 5.1) and `tests/test_stats_utils.py` (section 7). Run the new tests.
3. In `web_gui.py`, add `build_fight_context` and `run_fight_from_context`; make `_batch_worker_task`, `_run_batch_monte_carlo_detailed` and `execute_simulation_slice` use them. Do not change any behavior.
4. Run the full suite and the same-seed identity check (section 8). Must be identical.
5. Add `rotation_inline` support (section 5.3) with tests.
6. Add the optional `detail` argument to `_update_simulation_progress` and store it in `_SIM_PROGRESS`.
7. Create `src/swtorsim/experiments.py`: helpers, driver, `run_job`, `context_for_payload`, native executor with the 1-core path, kind `"variants"`.
8. Add `POST /api/experiment` to `SimulatorRequestHandler.do_POST`.
9. Tests for the driver and the end-to-end smoke test (section 7).
10. Update `ARCHITECTURE.md` (new rows for `stats_utils.py`, `experiments.py`, `/api/experiment`, `run_fight_from_context`, `build_fight_context`, `rotation_inline`), `CHANGELOG.md`.

Session 2 (WASM):

11. Bridge actions in `pyodide_bridge.py`.
12. `executeExperimentMultiCore`, `runExperimentJobs` and the `/api/experiment` intercept in `pyodide_client.js`.
13. Build and smoke-test the web release (`.\tools\pyclean.exe tools/build_web_release.py`, then serve `dist/` on port 8080 and run a `"variants"` experiment from the browser console with `fetch("/api/experiment", {...})`). Compare the numbers to the native endpoint for the same body: they must be identical (same seeds, same engine).
14. Update `docs/pyodide_web_release.md` if it lists bridge actions; update `ARCHITECTURE.md` rows for `pyodide_client.js` / `pyodide_bridge.py`.

## 7. Tests

`tests/test_stats_utils.py` (pure, fast):
- `test_mean_sd_se_known_values`: values `[1, 2, 3, 4]` -> mean 2.5, sample SD `sqrt(5/3)`, SE `sqrt(5/3)/2`.
- `test_paired_difference_uses_common_seeds_only`: a = {1: 10, 2: 12, 3: 14}, b = {2: 11, 3: 12, 4: 99} -> n = 2, diff = 1.5.
- `test_paired_zero_variance_nonzero_diff_is_significant`: all diffs = 5 -> z = inf, p = 0, significant.
- `test_paired_identical_samples_not_significant`: diff 0, se 0 -> p = 1, not significant.
- `test_welch_matches_hand_computation`.
- `test_normal_p_value_at_1_96_is_about_0_05` (assertAlmostEqual, places=3).
- `test_compare_samples_falls_back_to_welch_without_shared_seeds`.
- `test_percentile_matches_web_gui_rule` (same interpolation as `_aggregate_batch_results._percentile`).

`tests/test_experiments.py`:
- `test_apply_overrides_merges_stats_and_choices` (stats merged per key; choices written to both keys; other keys replaced; base not mutated).
- `test_fingerprint_ignores_runtime_keys` (mode / iterations / seed changes keep the fingerprint; a stat change alters it).
- `test_append_runs_dedupes_by_seed_and_keeps_order`.
- `test_variants_kind_plans_one_round` (fake state; round 0 jobs = one per active variant, round 1 = []).
- `test_invalid_variant_is_marked_not_run` (bad tactical FQN -> status "invalid", no job).
- `test_finalize_reports_paired_delta` (inject fake results; check `vs_baseline.diff`).
- `test_run_fight_from_context_is_deterministic`: resolve a payload built from `data/run_config/hatred_14gcd.json` with `dummy_hp = 200_000`; two calls with the same run id give identical `dps`; `lean=True` drops `abilities`.
- `test_batch_worker_task_matches_run_fight_from_context`: `_batch_worker_task((3, 42, 1000, 200_000))` with `_WORKER_SIM_CONTEXT` set equals `run_fight_from_context(ctx, 3, 42, 1000, 200_000)` for every scalar key.
- `test_rotation_inline_replaces_file_rotation` and `test_rotation_inline_rejects_bad_shape`.
- `test_blocking_variants_smoke`: `run_experiment_blocking(body, cores=1)` with two variants, `iterations = 2`, `dummy_hp = 150_000` -> both variants have n = 2, baseline `vs_baseline.diff == 0`.

Helper for building payloads from a run config file (put it at the top of the test file):

```python
def payload_from_run_config(rel_path: str, **extra) -> dict:
    """Simulate payload equivalent to a data/run_config file (no stats_override)."""
    raw = json.loads((ROOT / rel_path).read_text(encoding="utf-8"))
    payload = {
        "environment": raw.get("environment", "live"),
        "spec_path": raw["spec_path"], "stats_path": raw["stats_path"], "rotation_path": raw["rotation_path"],
        "choices": raw.get("choices") or {}, "tactical_fqn": raw["tactical_fqn"],
        "legendary_fqns": raw["legendary_fqns"], "relic_fqns": raw.get("relic_fqns", []),
        "level": raw.get("level", 80), "dummy_hp": raw.get("dummy_hp", 6_000_000),
        "training_dummy_armor_debuff": raw.get("training_dummy_armor_debuff", True),
        "enable_stem_matching": raw.get("enable_stem_matching", True),
    }
    payload.update(extra)
    return payload
```

## 8. Verification

1. Full suite passes (count = baseline + new tests).
2. **Same-seed identity of the refactor**: before step 3 and after step 4, run in the scratchpad:
   ```python
   from src.swtorsim.web_gui import execute_simulation_from_payload
   res = execute_simulation_from_payload({**payload, "mode": "BATCH", "iterations": 20, "seed": 42})
   print(res["all_dps"])
   ```
   for `hatred_14gcd` and `carnage_14gcd`. The two `all_dps` lists must be identical. Also compare a TEST run's `combat_log` for seed 42.
3. Native endpoint smoke test: start `main.py --web --no-browser`, then POST a `"variants"` body with `curl` or the browser console and check the result shape.
4. Cancel: start a large `"variants"` experiment, hit `POST /api/simulate_cancel`, and confirm `{"cancelled": true}` and that a following normal batch still works (the batch pool is separate).
5. WASM parity (session 2): same body, same numbers.

## 9. Docs

- `ARCHITECTURE.md`: rows for `swtorsim/stats_utils.py`, `swtorsim/experiments.py` (`start_experiment, advance_experiment, run_job, run_experiment_blocking, EXPERIMENT_KINDS`), the endpoint, the bridge actions, `executeExperimentMultiCore`.
- `CHANGELOG.md`: one entry per session.
- `TODO.md`: nothing to add (this is not open work once done).

## 10. Done when

- [ ] `stats_utils.py` and `experiments.py` exist with the API above.
- [ ] `_batch_worker_task`, `_run_batch_monte_carlo_detailed`, `execute_simulation_slice` use `run_fight_from_context` / `build_fight_context`, with identical same-seed output.
- [ ] `rotation_inline` works and is validated.
- [ ] `POST /api/experiment` works natively and in WASM with identical numbers.
- [ ] Cancel and progress work for experiments.
- [ ] All tests pass; ARCHITECTURE and CHANGELOG updated.

## 11. Open questions for the user

1. Default core count for experiments: use all cores (like batches) or leave one free so the UI stays responsive? (Suggested default: all cores, same as batches.)
2. Should experiments share the batch "Cancel" button (simplest: yes, same `_SIM_CANCEL`)?
