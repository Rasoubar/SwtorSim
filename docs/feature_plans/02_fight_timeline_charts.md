# Plan 02: Fight Timeline Charts and Seed Replay

Status: proposed. Size: S-M (one session). Risk: none to the engine (UI plus a small result payload addition).

## 1. Summary (for humans)

Today a single TEST run shows tables (ability breakdown, combat log) and a buff/debuff Gantt chart, and a BATCH run shows a DPS histogram. There is no way to *see* how the fight unfolded: when DPS dipped, when the resource ran dry, when the rotation stalled, when the execute phase started.

This plan adds a **Fight Timeline** tab with three stacked charts that share one time axis:

1. **DPS over time**: a rolling-window DPS line (5 / 10 / 15 / 30 s, selectable) and the running-average DPS line.
2. **Target HP %**, with the execute phase (below 30%) shaded.
3. **Resource** (Force / Energy / Heat / Rage / Focus) as a step line.

Overlays on all three: rotation stall windows (amber), deadlock (red), and later the encounter windows from plan 06. Hovering shows a crosshair with the exact values; clicking jumps to the combat log at that moment.

It also adds an **activity summary** (how much of the fight the GCD was busy), and makes the BATCH histogram interactive: click a bar to see which seeds landed there and replay any of them as a TEST run. "Replay worst run" and "Replay best run" buttons go on the Monte Carlo tab.

Finally it fixes a pre-existing bug: the "Inspect seed" buttons in the stall banner call `triggerSimulation()`, which does not exist.

### What the user sees

- A new results tab "Fight Timeline" (TEST runs). Controls: rolling window chips (5s / 10s / 15s / 30s), "Show stalls" toggle.
- KPI row inside the tab: "GCD active", "Idle (stalled)", "Casts per minute", "Peak 10s DPS".
- Monte Carlo tab: clicking a histogram bar opens a small list of seeds in that bin with "Replay" buttons; two buttons "Replay worst run (seed N)" and "Replay best run (seed M)".

## 2. Scope and non-goals

In scope: the new tab, chart helpers, small additions to the TEST and BATCH result payloads, the seed replay fix, WASM parity (automatic, same Python functions).

Not in scope:
- Changing the existing Buffs & Debuffs Gantt (it already draws effect windows; this plan links to it instead of duplicating it).
- Charting libraries. Use inline SVG like `renderMonteCarloTab`.
- Batch-level time series (average DPS curve over many fights). Possible later; not needed now.

## 3. Rules that apply

- Rule 1: nothing here touches combat math.
- Rule 9: the payload additions must not change any number; do a same-seed check on one config.
- Rule 5: no console output added.

## 4. Current state (facts)

- TEST result (`src/swtorsim/web_gui.py :: _run_single_test_detailed`, around lines 709-1041) already contains everything the charts need:
  - `combat_log`: list of events sorted by time, with `time` (fight-relative seconds, pre-pull negative), `category` (`"cast"`, `"damage"`, `"stall"`, `"deadlock"`), `ability`, `damage`, `is_crit`, `target_hp_pct`, `resource`.
  - `stalls.events`: `{start, end, duration, step_index, step_info, recovered}` (fight-relative).
  - `execute_phase.start_time` (fight-relative) when the target went below 30%.
  - `duration` (fight length), `pre_combat_duration`.
  - `cast_timeline.casts`: one row per cast with `combat_time`, `gcd`, `busy`, `end_time` / `combat_end_time`, `triggers_gcd` (see `src/swtorsim/cast_timeline.py :: CastTimelineRecorder`).
  - `buffs`: effect windows (already drawn by `renderBuffsTab`, around line 2852).
- BATCH result (`_aggregate_batch_results`, around lines 1342-1499) has `all_dps` (in run-id order, because `harvested` is sorted by `run_id` before aggregation), `histogram_bins` (`{x0, x1, count, pct}` from `_compute_histogram_bins`, around line 1200), `min_dps`, `max_dps`, and stall seeds. It does **not** expose which seed produced which DPS, and the bins carry no seeds.
- Each harvested run has `seed` (`base_seed + run_id`; see `_batch_worker_task`). A TEST run with that seed reproduces the batch fight: TEST calls `random.seed(config.seed)` then `prepare_simulation(..., seed=config.seed, config=config)`; batch calls `random.seed(worker_seed)` then `prepare_simulation(..., seed=worker_seed, precast=..., pre_combat=...)`; `prepare_simulation` reseeds with the given seed before building the `Simulation`, and the TEST-only wrappers (`_make_cast_wrapper`, `CastTimelineRecorder`, the `log_damage` wrapper) do not draw random numbers. Step 3 below adds a test that proves this.
- Bug: `tools/simulator_ui.html :: applySeedAndRun` (around line 2644) calls `triggerSimulation()`, which is not defined anywhere. The function that runs a simulation is `runSimulation()` (around line 2357).
- Result rendering: `renderAllResultPanels(res)` (around line 2457) calls one render function per tab. Tabs: buttons in `<nav class="tabs-bar">` (around line 1396), panes after it.

## 5. Design

### 5.1 Series computed in the browser (no new backend data for the TEST charts)

From `res.combat_log`, keep events with `time >= 0` (fight time). Sample on a fixed grid of `step = 0.5` s from 0 to `res.duration`.

- **Cumulative damage** `C(t)` = sum of `damage` for damage events with `time <= t`.
- **Running-average DPS** `A(t) = C(t) / t` for `t > 0` (start the line at `t = min(5, duration)` to avoid the huge spike near 0).
- **Rolling DPS** `R(t) = (C(t) - C(t - w)) / w` for `t >= w` (`w` = selected window). For `t < w` use `C(t) / t` with a dashed style to show it is "warming up".
- **HP %**: last `target_hp_pct` of any event with `time <= t` (start at 100).
- **Resource**: last `resource` of any event with `time <= t` (step line). Note that resource is only sampled at events, which is fine for display.

Use a two-pointer sweep over the sorted events so the whole computation is O(events + samples). Fights are at most a few thousand events.

### 5.2 Activity KPIs (browser, from `cast_timeline.casts`)

- **GCD active %**: union of intervals `[combat_time, combat_time + max(gcd, busy)]` over casts with `combat_time >= 0`, clipped to `[0, duration]`, divided by `duration`. (`busy` covers cast bars and channels; `gcd` covers instants.)
- **Idle (stalled) s**: `res.stalls.total_stalled_time`.
- **Casts per minute**: casts with `combat_time >= 0` that `triggers_gcd`, times 60 / duration.
- **Peak 10 s DPS**: max of `R(t)` with `w = 10` (computed independently of the selected window).

### 5.3 Chart helper

Write one reusable function; plans 03, 04 and 06 reuse it.

```js
/**
 * Renders a line/step chart as an SVG string.
 * opts = {
 *   width: 780, height: 180, padL: 56, padR: 16, padT: 14, padB: 26,
 *   xMin, xMax, yMin, yMax,                // yMin/yMax optional -> auto from series
 *   xLabel: "s", yFormat: v => string,
 *   series: [{ name, points: [[x, y], ...], color: "var(--accent)", step: false, dashed: false, width: 2 }],
 *   bands:  [{ x0, x1, color: "var(--amber)", opacity: 0.15, label }],   // shaded vertical ranges
 *   vlines: [{ x, color, label, dashed: true }],
 *   id: "dpsChart"                          // used by the hover handler
 * }
 */
function svgLineChart(opts) { ... }
```

Implementation notes:
- Build `path d` strings with `M`/`L` (and horizontal-then-vertical segments for `step: true`).
- Y axis: 4 gridlines with labels from `yFormat`; X axis: ticks every `niceStep(xMax - xMin)` seconds (write `niceStep` to pick 10 / 15 / 30 / 60 s).
- Colors only from CSS variables. Bands use `fill-opacity`.
- Add an invisible full-size `<rect class="chart-hit">` on top for mouse events.

Hover: one `mousemove` listener per chart container converts `clientX` to time, finds the nearest sample index, and updates (a) a vertical crosshair line in **all three charts** (same time axis), and (b) a small floating tooltip `div` with time, rolling DPS, average DPS, HP %, resource. Click: store `LOG_FOCUS_TIME = t`, call `switchTab("tabCombatLog")`, and let `renderCombatLog` scroll to and highlight the first row with `ev.time >= LOG_FOCUS_TIME` (add a `data-time` attribute on rows; use `scrollIntoView({block: "center"})` and a CSS class `log-row-focus` that fades out).

Note: `renderCombatLog` shows only the first 1,500 filtered events. When the focus time is beyond the displayed rows, show a hint "Event at t=... is beyond the first 1,500 rows; narrow the filter".

### 5.4 Batch payload additions (`web_gui.py`)

In `_aggregate_batch_results`:

- `all_seeds`: list parallel to `all_dps` (`[r.get("seed") for r in harvested]`). Plan 08 also uses it.
- `min_seed`, `max_seed`: seeds of the min and max DPS runs.
- Histogram bins gain `seeds`: up to 12 seeds per bin, chosen as the bin's lowest-DPS and highest-DPS runs alternately (deterministic order). Implement by giving `_compute_histogram_bins(values, seeds=None)` an optional `seeds` list; when `None`, output is exactly the current output (keep the function backward compatible).

Size impact: `all_seeds` doubles the size of `all_dps` (at most 10,000 integers); acceptable.

`aggregate_batch_slices` (WASM path) calls the same `_aggregate_batch_results`, so WASM gets the same fields.

### 5.5 TEST payload: nothing required

Optional, only if hovering feels sparse: add nothing. The combat log is already dense enough.

## 6. Step-by-step implementation

1. **Baseline.** Test suite count. Save a TEST result for `hatred_14gcd` seed 42 (scratchpad: `execute_simulation_from_payload` -> `json.dump`) and a BATCH result with 20 iterations.

2. **Fix the replay bug** (`tools/simulator_ui.html :: applySeedAndRun`): replace `triggerSimulation();` with `runSimulation();`. Justification for the change log: the function was undefined, so every "Inspect seed" button threw a ReferenceError.

3. **Prove replay reproduces a batch fight** with a test (section 7, `test_seed_replay_matches_batch_run`). If it fails, stop and report: something in TEST mode differs from batch mode, and the replay feature would be misleading.

4. **Backend payload additions** (section 5.4). Keep `_compute_histogram_bins(values)` behavior identical when called without seeds.

5. **New tab markup**: add a tab button after "Monte Carlo Distribution":
   ```html
   <button class="tab-btn" data-tab="tabTimeline" onclick="switchTab('tabTimeline')">
     Fight Timeline <span class="tab-badge" id="badgeTimeline">TEST</span>
   </button>
   ```
   and a pane:
   ```html
   <div class="tab-content" id="tabTimeline">
     <div id="timelineContent">
       <div class="empty-state">Run a <b>TEST (Single Run)</b> simulation to see DPS, target HP and resource over time.</div>
     </div>
   </div>
   ```

6. **JS**: add `let TIMELINE_WINDOW = 10;`, `let TIMELINE_SHOW_STALLS = true;`, `let LOG_FOCUS_TIME = null;` near the other globals (around line 1565). Implement `buildTimelineSeries(res, windowSec)`, `computeActivityKpis(res)`, `svgLineChart(opts)`, `niceStep(span)`, `renderTimelineTab()`, `attachTimelineHover(containerId, series)`, `setTimelineWindow(w)`. Call `renderTimelineTab()` from `renderAllResultPanels`.

7. **Combat log focus**: in `renderCombatLog`, add `data-time="${ev.time}"` to each `<tr>`; after `container.innerHTML = html`, if `LOG_FOCUS_TIME !== null`, find the first row with `parseFloat(row.dataset.time) >= LOG_FOCUS_TIME`, add class `log-row-focus`, scroll it into view, then set `LOG_FOCUS_TIME = null`. Add the CSS:
   ```css
   .log-row-focus { outline: 2px solid var(--accent); animation: logFocusFade 2.5s ease-out forwards; }
   @keyframes logFocusFade { from { background: var(--accent-bg); } to { background: transparent; } }
   ```

8. **Histogram interaction** (`renderMonteCarloTab`, around line 2744): give each bar `data-bin="${idx}"` and `style="cursor:pointer"`; on click, render a small panel under the chart listing `bins[idx].seeds` as buttons `Seed N` calling `applySeedAndRun(N)`. Add two buttons to the "Worst Run" and "Best Run" KPI cards: `Replay (seed ${r.min_seed})` / `Replay (seed ${r.max_seed})`. Hide them when the fields are missing (results loaded from history before this change).

9. **Encounter hook for plan 06**: make `renderTimelineTab` read optional `res.encounter.windows` (`[{kind, start, end}]`) and draw them as bands with a per-kind color (`moving` = cyan, `out_of_range` = purple, `untargetable` = red). Until plan 06 lands this array is absent, so draw nothing.

10. Check in the browser (section 8), then tests, docs, CHANGELOG.

## 7. Tests

New file `tests/test_timeline_payload.py`:

- `test_histogram_bins_without_seeds_unchanged`: `_compute_histogram_bins([1.0, 2.0, 3.0, 10.0])` equals the exact current output (hard-code the expected list once from the baseline run).
- `test_histogram_bins_with_seeds_cover_every_bin_member_up_to_cap`: 100 synthetic values and seeds; every seed listed in a bin belongs to a value inside that bin; at most 12 per bin.
- `test_aggregate_exposes_seed_fields`: build a fake `harvested` list (3 runs with `dps`, `seed`, `elapsed`, `total_damage`, `abilities: {}`) and a minimal `RunConfig`; `_aggregate_batch_results` returns `all_seeds`, `min_seed`, `max_seed` consistent with `all_dps`.
- `test_seed_replay_matches_batch_run`: resolve the `hatred_14gcd` payload with `dummy_hp = 300_000`; set `web_gui._WORKER_SIM_CONTEXT` from `build_fight_context` (plan 00) or construct it like `_run_batch_monte_carlo_detailed` does if plan 00 is not done yet; run `_batch_worker_task((5, 42, 1000, 300_000))`; then run `_run_single_test_detailed(config_with_seed_47, sim_inputs)`; assert `round(test["total_damage"]) == round(batch["total_damage"])` and the durations match to 0.01 s.

There is no JavaScript test harness in the repo. Keep chart math in small pure JS functions (`buildTimelineSeries`, `computeActivityKpis`) and verify them manually against the combat log (section 8, check 3).

## 8. Verification

1. Full suite passes.
2. Same-seed identity: the saved TEST and BATCH results from step 1 match the new ones on every pre-existing field (`dps`, `all_dps`, `breakdown`, `histogram_bins` x0/x1/count/pct).
3. Manual math check: in a TEST run, pick t = 60 s; sum damage events with `0 <= time <= 60` from "Export .TXT" (or the browser console: `ACTIVE_RESULT.combat_log.filter(e => e.category === "damage" && e.time >= 0 && e.time <= 60).reduce((s, e) => s + e.damage, 0) / 60`) and compare with the tooltip's running-average DPS at 60 s.
4. Browser, light and dark themes: lines, bands and labels readable; hover crosshair moves in all three charts; clicking jumps to the log; window chips re-render.
5. Stalls: run `data/run_config/sniper_marksmanship_config_test.json`-style configs or any rotation known to stall (the TODO's marksmanship deadlock config, if present) and confirm amber/red bands appear where the stall banner says.
6. BATCH: click a bar, replay a seed, and confirm the TEST DPS equals that run's DPS (hover the bar's tooltip / compare with `ACTIVE_RESULT.all_dps[ACTIVE_RESULT.all_seeds.indexOf(seed)]` from the previous batch result in history).
7. "Inspect seed" buttons in the stall banner now work.
8. WASM build: repeat 4 and 6.

## 9. Docs

- `ARCHITECTURE.md`: `tools/simulator_ui.html` row (new functions `renderTimelineTab, buildTimelineSeries, svgLineChart, computeActivityKpis`), `web_gui.py` row (`_compute_histogram_bins(values, seeds=None)`, batch fields `all_seeds, min_seed, max_seed`).
- `docs/user_guide.md`: one paragraph describing the Fight Timeline tab and seed replay.
- `CHANGELOG.md`: entry "Simulator Page: Fight Timeline Charts and Seed Replay" (mention the `triggerSimulation` fix explicitly).

## 10. Done when

- [ ] Fight Timeline tab renders DPS / HP / resource with stall bands, hover, click-to-log.
- [ ] Activity KPIs shown.
- [ ] Histogram bars list seeds; replay works and reproduces the batch fight (test proves it).
- [ ] `applySeedAndRun` fixed.
- [ ] Same-seed identity on existing fields; tests, docs, CHANGELOG done.

## 11. Open questions for the user

1. Default rolling window: 10 s (suggested) or 15 s?
2. Should the Fight Timeline tab also be shown for BATCH runs using the median-DPS seed automatically replayed? (Suggested: no; keep BATCH light and offer the replay buttons.)
