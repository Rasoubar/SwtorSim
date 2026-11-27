# Plan 08: Precision Mode and Significance Testing

Status: proposed. Size: S (one session). Risk: none to the engine. Depends on plan 00 step 2 only (`src/swtorsim/stats_utils.py`); the rest of plan 00 is not needed.

## 1. Summary (for humans)

Two everyday annoyances:

1. **"How many iterations do I need?"** Too few and the average is noisy; too many and you wait. **Precision mode** answers it for you: "keep running until the 95% confidence interval is within +/- 0.1% of the mean (at most 5,000 fights)". It stops as soon as the target is reached.
2. **"Is this +0.4% real or just luck?"** The Compare tab shows deltas but not whether they are meaningful. This plan adds a **significance** verdict to every comparison between two BATCH runs: "+124 DPS +/- 61 (95%), significant" or "+20 DPS +/- 61, within noise". When both runs used the same seeds (same base seed and overlapping iterations), the comparison is **paired**, which is much more precise.

### What the user sees

- In "1. Execution Mode & Target", under the iterations input (BATCH mode): a checkbox **Run until precise**, a field "Target CI +/- [0.1] %", and "Max fights [5000]". With it checked, the iterations field becomes the minimum.
- After a precision run, the Monte Carlo tab shows "Stopped at 1,850 fights: CI +/- 0.098% (target 0.1%)" or "Reached max fights: CI +/- 0.14%".
- The DPS KPI's delta badge vs the pinned baseline gets a suffix: "(significant)" in normal color or "(within noise)" greyed out. The comparison table in "Run History & Compare" gets a summary line with the full numbers and the method (paired / unpaired).

## 2. Scope and non-goals

In scope: adaptive iteration count for BATCH (native and WASM), result metadata, significance computation in the UI, a Python reference implementation and tests.

Not in scope: per-ability significance in the comparison table (possible later; ability DPS columns stay as they are).

## 3. Rules that apply

- Rule 9: fixed-iteration batches must be unchanged. A precision run that stops at N fights must give exactly the same numbers as a fixed run of N fights with the same seed (that is the determinism guarantee; test it).

## 4. Current state (facts)

- Native batch: `web_gui.py :: _run_batch_monte_carlo_detailed` (around line 1229) builds `payloads = [(i, seed, duration, dummy_hp) for i in range(iterations)]` and runs them in chunks on the warm pool. Fight `i` uses seed `base_seed + i`.
- Aggregation: `_aggregate_batch_results` (around line 1342) computes `std_dev` as the population SD and `ci_95 = 1.96 * std_dev / sqrt(n)`.
- WASM batch: `pyodide_client.js :: executeBatchMultiCore` (around line 526) splits `iterations` once across workers; each worker runs `SIMULATE_SLICE` with `start_run_id` and `slice_count`; worker 0 aggregates with `AGGREGATE_BATCH` and `total_iterations`.
- Iterations are capped at 10,000 by the resolver (`max(1, min(10_000, ...))`, around line 533).
- BATCH results include `all_dps` in run-id order. After plan 02 they also include `all_seeds`. If plan 02 is not done yet, this plan adds `all_seeds` itself (same definition: `[r.get("seed") for r in harvested]`).
- UI: `PINNED_BASELINE` and `ACTIVE_RESULT` hold full result objects; `formatDeltaBadge(currentVal, baseVal, suffix)` (around line 2448) renders the delta; `renderHistoryAndComparison` (around line 3068) renders the comparison table.

## 5. Design

### 5.1 Payload

```json
"precision": {"target_ci_pct": 0.1, "max_iterations": 5000}
```

Only used when `mode == "BATCH"`. `iterations` acts as the minimum (and as the first round's size). Validation: `0.01 <= target_ci_pct <= 10`, `iterations <= max_iterations <= 10000`.

### 5.2 Stopping rule (identical in Python and JS)

After each round, with `n` fights done:

```
mean = average(dps)
sd   = population SD (same as _aggregate_batch_results)
ci   = 1.96 * sd / sqrt(n)
ci_pct = ci / mean * 100
stop if n >= max_iterations or (n >= min_iterations and ci_pct <= target_ci_pct)
```

Using the population SD keeps the reported `ci_95` and the stopping rule consistent with what the Monte Carlo tab already shows.

Round sizes: first round = `iterations`; then estimate the required total `n_req = ceil((1.96 * sd / (target_ci_pct / 100 * mean)) ** 2)`; next round adds `clamp(n_req - n, cores, n)` fights (at most doubling, at least one fight per core), never exceeding `max_iterations`. Rounds continue the run ids (`start = n`), so seeds never repeat and the final set is exactly runs `0 .. N-1`.

### 5.3 Native implementation

Refactor `_run_batch_monte_carlo_detailed`'s run loop into a helper that runs a range:

```python
def _run_batch_range(pool_or_none, start: int, count: int, config, sim_context, cores, progress_total) -> list[dict]:
    """Runs fights start .. start+count-1 (same chunking, cancel and progress behavior as today)."""
```

Then:

```python
precision = _normalize_precision(payload.get("precision"), iterations)   # in the resolver; stored on the config or sim_inputs
harvested = _run_batch_range(..., 0, iterations, ...)
while precision and not _precision_reached(harvested, precision):
    extra = _next_round_size(harvested, precision, cores)
    harvested += _run_batch_range(..., len(harvested), extra, ...)
```

- `_precision_reached`, `_next_round_size`: pure functions next to `_compute_histogram_bins` (tested).
- Progress: total shown = `max_iterations` for precision runs (the bar may finish early); pass `detail=f"CI +/- {ci_pct:.3f}% (target {target}%)"` once plan 00 adds the `detail` argument (otherwise skip the detail).
- `_aggregate_batch_results(harvested, config, wall_ms, len(harvested), computed_stats)` then adds:
  ```json
  "precision": {"target_ci_pct": 0.1, "achieved_ci_pct": 0.098, "stopped": "target" | "max_iterations", "rounds": 3}
  ```
  and `iterations` is the actual count.

### 5.4 WASM implementation

In `executeBatchMultiCore`, when `payload.precision` is set:

```js
let harvested = [];
let next = minIterations;
while (true) {
  const roundResults = await runBatchRoundAcrossWorkers(payload, harvested.length, next);  // slices with start_run_id offset
  harvested.push(...roundResults);
  const verdict = precisionVerdict(harvested.map(r => r.dps), payload.precision, minIterations);   // same rule as 5.2
  if (verdict.stop) break;
  next = verdict.nextRound;
}
// AGGREGATE_BATCH with all_harvested = harvested, total_iterations = harvested.length, plus precision metadata
```

Pass the precision metadata to `AGGREGATE_BATCH` (add an optional `precision_meta` field to `aggregate_batch_slices`'s payload and include it in the result) so both modes return the same shape.

### 5.5 Significance in the UI

Pure JS function mirroring `stats_utils.compare_samples` (plan 00, section 5.1):

```js
/**
 * Compares two BATCH results. Paired when both have all_seeds and share >= 10 seeds, else Welch.
 * Returns {method, n, diff, se, ci95, z, p, significant, diff_pct, small_sample}.
 */
function compareBatchResults(cur, base) { ... }
```

Formulas (write them out in the code comment exactly as in `stats_utils.py`):
- Paired: `d_i = cur.dps[seed] - base.dps[seed]` over shared seeds; `diff = mean(d)`; `se = sd_sample(d) / sqrt(n)`.
- Welch: `diff = mean(a) - mean(b)`; `se = sqrt(var_sample(a) / n_a + var_sample(b) / n_b)`.
- `ci95 = 1.959964 * se`; `z = diff / se`; `p = erfc(|z| / sqrt(2))` (implement `erfc` with the Abramowitz-Stegun 7.1.26 approximation, error < 1.5e-7; note it in a comment); `significant = n >= 2 && |diff| > ci95`.

UI changes:
- `renderAllResultPanels`: when both `res` and `PINNED_BASELINE` are BATCH with `all_dps`, append to the DPS sub-line: `+124.0 +/- 61.2 (paired, significant)` or `(within noise)` (muted style).
- `renderHistoryAndComparison`: above the ability table, a summary row with method, n, diff, CI, p (3 significant digits), and a one-line explanation: "Paired: both runs share 500 seeds, so luck mostly cancels."
- TEST vs anything: show "Single runs cannot be compared statistically; use BATCH."

### 5.6 Sidebar

In `batchIterationsRow` (around line 1070): checkbox `precisionToggle`, inputs `precisionTargetInput` (default 0.1) and `precisionMaxInput` (default 5000). `buildPayloadFromForm` adds `precision` only when the checkbox is on and mode is BATCH. `applyPresetRunConfig` / `buildExportRunConfigObject` read/write `rc.precision`.

## 6. Step-by-step implementation

1. Baseline tests. Ensure `stats_utils.py` exists (plan 00 step 2); if not, create just that module and its tests first.
2. Python: `_normalize_precision`, `_precision_reached`, `_next_round_size`; refactor the run loop into `_run_batch_range`; precision loop; result metadata; `all_seeds` if missing.
3. Determinism test (section 7) and same-seed identity for fixed batches.
4. WASM: round loop in `executeBatchMultiCore`, `precisionVerdict` in JS, `precision_meta` passthrough.
5. UI: sidebar controls, Monte Carlo tab status line, `compareBatchResults`, KPI suffix, comparison summary.
6. Manual checks, docs, CHANGELOG.

## 7. Tests

New file `tests/test_precision_mode.py`:
- `test_precision_reached_rule` with synthetic dps lists (CI just below / just above target; max reached).
- `test_next_round_size_bounds` (never above max, at least `cores`, at most doubling).
- `test_precision_run_equals_fixed_run_of_same_length`: payload `hatred_14gcd`, `dummy_hp = 150_000`, precision target very loose so it stops after the first round of 6 fights, compare `all_dps` with a fixed 6-iteration batch: identical. Then a target that forces a second round; compare with a fixed run of the resulting N: identical. Keep the test fast and free of process spawning: give `_run_batch_range` an in-process mode (`pool_or_none=None` runs the fights sequentially in the current process, exactly like the existing `iterations <= 1 or emscripten` branch) and drive the precision loop with it.
- `test_fixed_batch_has_no_precision_key`.
- `test_compare_samples_paired_vs_welch` lives in `tests/test_stats_utils.py` (plan 00); add a case with two batch-like dicts to make sure the JS port has a Python reference with known numbers. Copy those exact numbers into a comment next to `compareBatchResults` so the JS can be checked by hand.

## 8. Verification

1. Full suite passes.
2. Same-seed identity: a fixed 50-iteration batch gives the same `all_dps` as before.
3. Precision run on `hatred_14gcd` with target 0.2%: stops; the reported `achieved_ci_pct` equals `ci_95 / dps * 100` from the result.
4. Pin a 500-fight batch, run another 500-fight batch with the same seed and a +100 Crit change: the badge says paired and (very likely) significant. Run the same setup twice with different seeds and no change: "within noise" in at least 19 of 20 tries (spot check a few).
5. Console check of `compareBatchResults` against the numbers copied from the Python test.
6. WASM: precision run stops at the same N with the same numbers as native.

## 9. Docs

- `docs/user_guide.md`: "Precision mode" and "Reading comparisons" paragraphs (what paired means, why "within noise" is not "equal").
- `ARCHITECTURE.md`: `web_gui.py` row (`_run_batch_range, _precision_reached, _next_round_size`, result `precision`), `pyodide_client.js` row (round loop, `precisionVerdict`), `simulator_ui.html` row (`compareBatchResults`).
- `CHANGELOG.md`.

## 10. Done when

- [ ] Precision mode stops at the target or the cap, natively and in WASM, with identical numbers.
- [ ] A precision run equals a fixed run of the same length (test).
- [ ] Significance verdict in the KPI and the comparison tab, paired when possible.
- [ ] Tests, docs, CHANGELOG.

## 11. Open questions for the user

1. Default target: +/- 0.1% (suggested) or +/- 0.2%?
2. Should significance use 95% (suggested) or let the user choose 90/95/99%?
