# Plan 03: Stat Weights and Stat Budget Optimizer

Status: proposed. Size: M (two sessions: stat weights, then budget optimizer). Risk: low (inputs only). Depends on plan 00.

## 1. Summary (for humans)

Two questions every player asks:

1. **"Which stat is worth more for me right now?"** -> **Stat weights.** The sim adds and removes a small amount of one stat (for example +/- 250 Critical Rating), runs both versions on the same seeds, and reports "DPS per 1 rating point" for Mastery, Power, Critical Rating, Alacrity Rating and Accuracy Rating, with error bars. It can also express everything relative to Mastery ("1 Crit = 0.62 Mastery").
2. **"How should I split my Critical / Alacrity / Accuracy budget?"** -> **Budget optimizer.** In SWTOR gear, those three "tertiary" stats are interchangeable through enhancements and augments. The optimizer keeps their sum fixed and searches for the split with the highest DPS, honoring rules like "Accuracy must be at least 110%" and "GCD must be 1.4 s". It is smart about GCD tiers: Alacrity mostly matters when it crosses a 0.1 s GCD threshold, so it tests the minimum Alacrity for each tier instead of a blind grid.

Both run on the shared experiment engine (plan 00), natively and in the browser build.

### What the user sees

- Sidebar section "3. Character Stats & Sheet": two new buttons, **Stat Weights** and **Optimize Tertiary Stats**.
- Each opens a modal with a few options and an estimated cost ("~1,650 fights, about 2 min on 8 cores"), then shows progress in the header bar like a batch.
- Results open in a new results tab **Stat Analysis**:
  - Stat weights: horizontal bars with 95% error bars, a table (stat, current value, DPS per point, +/- CI, relative to Mastery), and warnings (for example "Alacrity +/-250 crosses a GCD tier, the weight is not smooth").
  - Budget: a ranked table of allocations (Crit / Alacrity / Accuracy rating, resulting Crit %, Alacrity %, Accuracy %, GCD, mean DPS, delta vs current with CI), a "Use this split" button that writes the three ratings into the stat inputs, and in grid mode a heatmap.

## 2. Scope and non-goals

In scope: two experiment kinds (`"stat_weights"`, `"stat_budget"`), UI, CLI flags, tests.

Not in scope:
- Changing how ratings turn into percentages (`combat_curves.py`, `Player.recalculate_stats` are frozen).
- Modeling actual gear pieces (which enhancement gives what). The optimizer works on rating totals; the user maps the result to gear.
- Replacing `src/diminishing_returns/` (that tool fits curves for research plots; leave it alone).

## 3. Rules that apply

- Rule 1: only inputs (`stats_override`) change. Percentages come from the frozen code via `preview_character_stats`.
- Rule 9: no damage code changes, so no DPS before/after needed; still confirm the baseline variant reproduces a normal batch.

## 4. Current state (facts)

- Stat inputs: the simulator sends all stat inputs as `stats_override` (`tools/simulator_ui.html :: getStatsOverrideFromInputs`, around line 2147). Keys used (`web_gui.py :: DEFAULT_STAT_KEYS`, around line 92): `Mastery`, `Power`, `Force Power`, `Tech Power`, `Critical Rating`, `Alacrity Rating`, `Accuracy Rating`, `Main_hand_min`, `Main_hand_max`, `Off_hand_min`, `Off_hand_max`.
- `_resolve_simulation_inputs_from_payload` applies `stats_override` on top of the stats file (around lines 617-625).
- `preview_character_stats(payload)` (around line 641) runs `prepare_simulation` without a fight and returns `computed_player_stats` from `_extract_computed_player_stats` (around line 473): `crit_chance_pct`, `crit_multiplier_pct`, `alacrity_pct`, `accuracy_pct`, `gcd_seconds`, and the ratings. It is the cheap way to know the GCD and Accuracy % of a candidate split.
- GCD is rounded up to the next 0.1 s (`Player.calculate_gcd` docstring: "rounded up to the nearest tenth of a second as ingame"). GCD as a function of Alacrity rating is therefore a non-increasing step function.
- Accuracy % and GCD are both monotone in their rating (more rating never lowers Accuracy % or raises the GCD). The binary searches below rely on that; verify it with a quick scan (section 8, check 2) before relying on it.

## 5. Design

### 5.1 Kind `"stat_weights"`

Request:

```json
{
  "kind": "stat_weights",
  "payload": { "...simulate payload from the form..." },
  "options": {
    "stats": ["Mastery", "Power", "Critical Rating", "Alacrity Rating", "Accuracy Rating"],
    "delta": 250,
    "iterations": 300,
    "normalize_to": "Mastery"
  }
}
```

Defaults as shown. `stats` may also include `Force Power` / `Tech Power` (weapon bonus stat). Bounds: `10 <= delta <= 2000`, `20 <= iterations <= 5000`.

`build`:
1. Resolve the base payload once (also validates it) and read the current value of each stat from the merged stats (stats file + `stats_override`). Write a helper `current_stats(payload) -> dict` that does exactly what the resolver does (load `stats_path`, overlay `stats_override`) without running anything.
2. Variants:
   - `baseline`: no overrides.
   - For each stat `s` with current value `v`: `"{s}:+"` with `stats_override {s: v + d}` and `"{s}:-"` with `{s: v - d}`.
   - If `v - d < 0`, use a **forward difference** instead: only `"{s}:+"` and mark `meta.method = "forward"`.
3. Preview each `"Alacrity Rating"` and `"Accuracy Rating"` variant with `preview_character_stats` and store `gcd_seconds` and `accuracy_pct` in `meta`. Store the baseline preview too.
4. `kind_state`: `{"stats", "delta", "iterations", "normalize_to"}`.

`next_jobs`: round 0 -> every active variant `(0, iterations)`; then `[]`.

`finalize`, per stat:
- Pair the plus and minus runs **by seed**: `w_i = (dps_plus_i - dps_minus_i) / (2 * d)` (central) or `w_i = (dps_plus_i - dps_base_i) / d` (forward).
- `weight = mean(w)`, `se = standard_error(w)`, `ci95 = Z95 * se`, `n = len(w)`.
- `relative = weight / weight[normalize_to]` when the normalizer's weight is positive and significant; otherwise `null` with a note.
- Notes:
  - `"crosses_gcd_tier"` when the plus or minus variant's `gcd_seconds` differs from the baseline's: "The +/-d range crosses a GCD tier (1.40 s -> 1.30 s). This weight mixes a tier jump with the smooth gain; use the budget optimizer for Alacrity decisions."
  - `"accuracy_capped"` when the baseline `accuracy_pct >= 110.0`: "Accuracy is at or above 110%; extra Accuracy only helps against defenses the dummy may not have."
  - `"not_significant"` when `abs(weight) < ci95`.
- Also report `dps_plus`, `dps_minus`, `dps_base` means and the baseline summary.

Result:

```json
{
  "kind": "stat_weights",
  "delta": 250, "iterations": 300, "base_seed": 42,
  "baseline": {"mean": 31000.2, "ci95": 85.1, "gcd_seconds": 1.4, "accuracy_pct": 110.2},
  "rows": [
    {"stat": "Mastery", "current": 16834, "method": "central", "weight": 0.512, "se": 0.031, "ci95": 0.061,
     "relative": 1.0, "dps_plus": 31128.0, "dps_minus": 30872.1, "notes": []}
  ],
  "warnings": []
}
```

Cost: `(2k + 1) * iterations` fights for `k` stats (default 11 * 300 = 3,300).

### 5.2 Kind `"stat_budget"`

Request:

```json
{
  "kind": "stat_budget",
  "payload": { "...": "..." },
  "options": {
    "total": null,
    "step": 100,
    "mode": "smart",
    "grid_step": 500,
    "min_accuracy_pct": null,
    "gcd_targets": "all",
    "iterations": 200,
    "refine_rounds": 3
  }
}
```

- `total`: tertiary budget; default = current Crit + Alacrity + Accuracy rating.
- `step`: rating granularity for refinement (the user's gear chunk size; see open question 1).
- `mode`: `"smart"` (default) or `"grid"`.
- `min_accuracy_pct`: e.g. `110.0`; `null` = no constraint.
- `gcd_targets`: `"all"` or a list like `[1.4, 1.3]`.
- `iterations`: fights per candidate per round.

Helper (pure, injectable so tests can fake it):

```python
PreviewFn = Callable[[dict[str, float]], dict]   # stat overrides -> computed_player_stats


def make_preview_fn(base_payload: dict) -> PreviewFn:
    """Wraps web_gui.preview_character_stats with an LRU cache keyed by the rounded overrides."""


def min_rating_for(preview: PreviewFn, stat_key: str, fixed: dict, lo: int, hi: int,
                   predicate: Callable[[dict], bool], step: int) -> int | None:
    """Smallest rating r in [lo, hi] (multiple of step) with predicate(preview({**fixed, stat_key: r})) True.

    Binary search; assumes predicate is monotone in r (False ... False True ... True).
    Returns None when predicate(preview(hi)) is False.
    """
```

**Smart candidate generation** (`build`):

1. `acc_min`: if `min_accuracy_pct` is set, `min_rating_for(preview, "Accuracy Rating", fixed={"Alacrity Rating": 0, "Critical Rating": total}, lo=0, hi=total, predicate=lambda s: s["accuracy_pct"] >= min_accuracy_pct, step=step)`. If `None`, fail the build with "Accuracy target unreachable with this budget". If no constraint, `acc_min = 0`.
2. GCD tiers available: preview at Alacrity 0 and at Alacrity `total - acc_min`; the set of tiers is every 0.1 s value between those two GCDs (inclusive). Filter by `gcd_targets`.
3. For each tier `g` (descending GCD, i.e. ascending Alacrity): `alac_min(g) = min_rating_for(preview, "Alacrity Rating", fixed={"Accuracy Rating": acc_min, "Critical Rating": 0}, lo=0, hi=total - acc_min, predicate=lambda s: s["gcd_seconds"] <= g + 1e-9, step=step)`.
   - Note: Critical Rating does not affect GCD, so holding it at 0 during the search is fine; the real candidate puts the remainder into Crit.
4. Base candidates: for each tier, `(acc = acc_min, alac = alac_min(g), crit = total - acc - alac)`. Plus the **current** allocation (always included, marked `is_current`).
5. Neighbors of each base candidate (kept only if all three values are `>= 0`, the accuracy constraint holds, and the GCD stays in the same tier):
   - `alac + step`, `alac + 2 * step` (Alacrity above the tier minimum still speeds up cast bars, channels, cooldowns and regen).
   - `acc + step`, `acc + 2 * step` (only if `min_accuracy_pct` is null or Accuracy matters: always include; the sim decides).
   - Crit absorbs the difference.
6. Deduplicate by `(crit, alac, acc)`. Every candidate becomes a variant with `stats_override {"Critical Rating": crit, "Alacrity Rating": alac, "Accuracy Rating": acc}` and `meta` = `{crit, alac, acc, preview: {crit_chance_pct, alacrity_pct, accuracy_pct, gcd_seconds}}`.

**Grid mode** (`build`): all `(acc, alac)` on a `grid_step` lattice with `acc + alac <= total`, `crit = total - acc - alac`, filtered by the constraints using `preview`. Warn if more than 120 candidates and cap at 200.

**Rounds** (`next_jobs`):
- Round 0: every active candidate gets `(0, iterations)`.
- Rounds 1 .. `refine_rounds` (smart mode only): take the best candidate by mean DPS; generate its six neighbors on `step` (move `step` between each ordered pair of stats: crit->alac, crit->acc, alac->crit, alac->acc, acc->crit, acc->alac), keep valid new ones, add them as variants, give them `(0, iterations)` so they share seeds with everyone. Stop early if no new candidate was added or the best candidate did not change from the previous round.
- Extra confirmation round (last): if the top two candidates' paired difference is not significant, add `iterations` more fights to both (`start_run_id = n_current`) once, so the final ranking is better resolved.

`finalize`: ranked list (mean DPS descending) with `vs_current` from `compare_to_baseline` (baseline = the current allocation), preview percentages, GCD, and flags `is_current`, `is_best`. For grid mode also return `grid: {"acc_values": [...], "alac_values": [...], "dps": [[...]]}` for the heatmap (null cells for invalid points).

### 5.3 UI

- Buttons in "3. Character Stats & Sheet" (around line 1220, next to "Calc Sheet"): `Stat Weights`, `Optimize Tertiary Stats`.
- Modals (`statWeightsModal`, `statBudgetModal`) with inputs mirroring the options; show an estimate:
  - fights = variants x iterations (+ refinement upper bound),
  - time = fights x (last batch `elapsed_wall_ms / iterations` if a batch ran this session, else "unknown") / cores.
- Run: `POST /api/experiment` with the request above. Reuse the header progress bar and Cancel button (poll `/api/progress`; `mode === "EXPERIMENT"`; show `detail`).
- New results tab **Stat Analysis** (`tabStatAnalysis`) rendering whichever analysis ran last:
  - `renderStatWeights(result)`: horizontal bar chart (SVG): one bar per stat from 0 to `weight`, a thin error bar `weight +/- ci95`, label on the right; table below.
  - `renderStatBudget(result)`: table; "Use this split" button calls `applyStatsToInputs({"Critical Rating": crit, "Alacrity Rating": alac, "Accuracy Rating": acc})` then `refreshComputedStats()`. In grid mode a heatmap (SVG rects, color scale from `--bg-input` to `--accent`; invalid cells hatched/empty).
- Keep the results in `RUN_HISTORY`? No: experiments are not runs. Store them in `LAST_STAT_ANALYSIS` only.

### 5.4 CLI

Add to `main.py` (they print ASCII tables and exit):

```
.\tools\pyclean.exe main.py hatred_14gcd --stat-weights [--iterations 300] [--delta 250]
.\tools\pyclean.exe main.py hatred_14gcd --stat-budget [--iterations 200] [--step 100] [--min-accuracy 110] [--grid]
```

Implementation: build the payload from the loaded `RunConfig` (write `payload_from_config(config) -> dict` in `experiments.py`; it mirrors the keys of `buildPayloadFromForm`), call `run_experiment_blocking`, and print with `print_stat_weights(result)` / `print_stat_budget(result)` (ASCII only; `[WARN]` for notes).

## 6. Step-by-step implementation

Session 1 (stat weights):

1. Baseline test run. Confirm plan 00 is merged (experiments module exists).
2. `current_stats(payload)` helper (in `experiments.py` or a new `src/swtorsim/stat_analysis.py`; recommended: new module `stat_analysis.py` holding both kinds so `experiments.py` stays generic). Register kinds on import; make sure `experiments.py` imports `stat_analysis` (or `run_experiment_blocking` imports all kind modules lazily) so the kinds are registered in every process.
3. Kind `"stat_weights"`: `build`, `next_jobs`, `finalize` (section 5.1).
4. Unit tests with fake results (no fights) for the weight math; one small end-to-end smoke test.
5. UI: button, modal, Stat Analysis tab, bar chart, table.
6. CLI `--stat-weights`.
7. Docs, CHANGELOG.

Session 2 (budget):

8. `make_preview_fn`, `min_rating_for` with tests using a fake preview function.
9. Monotonicity scan (section 8, check 2) on two configs; if either curve is not monotone, stop and report (the binary search would be wrong).
10. Kind `"stat_budget"` smart + grid.
11. UI table, "Use this split", heatmap.
12. CLI `--stat-budget`.
13. Docs, CHANGELOG.

## 7. Tests

New file `tests/test_stat_analysis.py`:

Stat weights:
- `test_weight_variants_central_and_forward`: base with `Accuracy Rating = 100`, `delta = 250` -> Accuracy uses forward difference (no minus variant); Mastery gets plus and minus.
- `test_current_stats_merges_override_over_file`.
- `test_weight_math_central`: fake results where `dps_plus = 1000 + seed`, `dps_minus = 900 + seed` on seeds 0..9 and `delta = 50` -> `weight = 1.0`, `se = 0`, significant.
- `test_weight_math_pairs_by_seed`: plus and minus with shuffled seed order give the same weight.
- `test_relative_to_mastery_null_when_mastery_not_significant`.
- `test_gcd_tier_note`: fake previews with different `gcd_seconds` for the Alacrity variants -> note present.
- `test_stat_weights_smoke`: `run_experiment_blocking(..., cores=1)` with `stats = ["Mastery"]`, `iterations = 2`, `dummy_hp = 150_000` -> one row, finite numbers.

Budget:
- `test_min_rating_for_finds_threshold`: fake preview where `accuracy_pct = 100 + rating / 100` -> threshold for 110% with step 100 is 1000.
- `test_min_rating_for_returns_none_when_unreachable`.
- `test_smart_candidates_sum_to_total_and_meet_constraints`: fake preview with GCD tiers at alacrity 0 / 1500 / 3200; every candidate sums to `total`, meets accuracy, and each tier's base candidate uses the tier's minimum Alacrity.
- `test_current_allocation_always_included`.
- `test_refine_round_adds_neighbors_and_stops_when_best_unchanged` (fake results).
- `test_grid_mode_respects_cap`.

## 8. Verification

1. Full suite passes.
2. **Monotonicity scan** (scratchpad script): for `hatred_14gcd` and `carnage_14gcd`, call `preview_character_stats` for Alacrity Rating 0..6000 step 100 and Accuracy Rating 0..6000 step 100. Confirm `gcd_seconds` never increases and `accuracy_pct` never decreases. Record the tier thresholds found (useful sanity numbers for the CHANGELOG).
3. **Sanity of weights**: on `hatred_14gcd` with 300 iterations, weights should be positive for Mastery, Power and Critical Rating. Compare `100 * weight_crit` with a direct check: run two plain batches (`stats_override` Crit +100 vs current, same seed, 300 iterations) and confirm the paired difference agrees within its CI.
4. **Budget**: on `hatred_14gcd`, with `min_accuracy_pct = 110`, the result's best split must satisfy 110% Accuracy and its GCD must be one of the tiers; "Use this split" updates the inputs and the mini sheet shows the predicted GCD/Accuracy.
5. Cancel mid-run; the UI recovers.
6. WASM: same request, same numbers.

## 9. Docs

- `docs/user_guide.md`: section "Stat Weights and Tertiary Optimizer" explaining what the numbers mean, the GCD-tier caveat, and that results are for the dummy and the current rotation.
- `ARCHITECTURE.md`: row for `swtorsim/stat_analysis.py` (`StatWeightsKind, StatBudgetKind, make_preview_fn, min_rating_for, current_stats`), UI functions, CLI flags.
- `CHANGELOG.md`: one entry per session.

## 10. Done when

- [ ] Stat weights run natively, in WASM and from the CLI, with CIs and notes.
- [ ] Budget optimizer (smart and grid) respects constraints, includes the current split, and can apply a result to the inputs.
- [ ] Monotonicity verified and recorded.
- [ ] Tests, docs, CHANGELOG done.

## 11. Open questions for the user

1. What rating step should the optimizer use by default? It should match how much tertiary stat one enhancement/augment swap actually moves in current gear (the plan defaults to 100; please give the real chunk sizes for Live 7.9 and PTS 8.0).
2. Should Accuracy default to a 110% minimum for melee/ranged disciplines and 100% for Force/Tech ones, or always "no constraint" unless the user sets one?
3. Are Force Power / Tech Power (weapon/offhand bonus) relevant for your weight comparisons, or only the five gear stats?
