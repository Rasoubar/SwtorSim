# SwtorSim Feature Implementation Plans

This folder holds one implementation plan per proposed feature. Each plan is written so that:

- an implementing agent (for example Claude Sonnet) can follow it step by step without re-deriving the design, and
- a human can read the "Summary" and "What the user sees" sections and understand the feature without reading code.

Plans were written on **2026-11-12** against branch `master` (last commit `7d871a0`). Line numbers quoted in the plans are a snapshot from that date. **Always re-locate code with `grep` before editing**; never trust a line number blindly.

---

## 1. How to use these plans (read this first)

1. **One plan = one change.** Implement one feature per session. Do not mix two plans in one change. The only exception is a plan that explicitly says "do step X of plan NN first".
2. **Read, in this order:** `AGENTS.md` (repo rules), this README, `ARCHITECTURE.md`, then the plan you are implementing.
3. **Follow the AGENTS.md protocol** (rule 9): baseline test run -> implement -> test -> update `CHANGELOG.md` / `TODO.md` -> show diffs with justification. The checklist in section 3 below restates it.
4. **"Open questions" are blocking.** Every plan has an "Open questions for the user" section. If a step depends on one of those answers, stop and ask the user before that step (AGENTS.md rule 0: "If a request or rule is ambiguous, ask; don't assume").
5. **"Stop and report" means stop.** Some steps say "if X happens, stop and report to the user". That is usually because the next move would touch frozen combat math (AGENTS.md rule 1) or extracted data (rule 11).
6. **Code sketches are sketches.** Code blocks show intent, names, and data shapes. Adapt them to the surrounding code style. If a sketch contradicts the real code you find, the real code wins; note the difference in your report.
7. **No git commits** (AGENTS.md rule 0). Leave all changes uncommitted.

---

## 2. The plans

| # | File | Feature | Size | Risk | Depends on |
|---|------|---------|------|------|------------|
| 00 | [00_shared_experiment_runner.md](00_shared_experiment_runner.md) | Shared "experiment" engine: run many variants of one setup on the same seeds and compare them | M | Low (no engine change) | none |
| 01 | [01_adrenals.md](01_adrenals.md) | Equip and use adrenals (already extracted, never wired in) | S-M | Low | none |
| 02 | [02_fight_timeline_charts.md](02_fight_timeline_charts.md) | DPS / HP / resource charts over time, seed replay from the histogram | S-M | None (UI + small payload) | none |
| 03 | [03_stat_weights_and_budget.md](03_stat_weights_and_budget.md) | Stat weights and best split of Crit / Alacrity / Accuracy | M | Low | 00 |
| 04 | [04_top_gear_matrix.md](04_top_gear_matrix.md) | "Top Gear": rank tacticals, implants, relics, adrenals, talents | M | Low | 00 (01 optional) |
| 05 | [05_combat_log_parity.md](05_combat_log_parity.md) | Import a real SWTOR combat log and compare it with the sim | M-L | Low (read-only on math) | none (00 optional) |
| 06 | [06_encounter_scripting.md](06_encounter_scripting.md) | Movement / out-of-range / untargetable windows, raid burst buffs, fit HP to a fight length | M-L | Medium (engine gates) | 00 for "fit HP"; 02 for drawing |
| 07 | [07_share_links.md](07_share_links.md) | Copy a link that restores the whole setup | S | None | none (extend after 01/06) |
| 08 | [08_precision_mode_and_significance.md](08_precision_mode_and_significance.md) | "Run until +/- X DPS" and "is this difference real?" | S | None | 00 step 1 (stats helpers) |
| 09 | [09_rotation_tuner.md](09_rotation_tuner.md) | Automatic rotation tuning (reorder priorities, tune thresholds) | L | Low (no engine change) | 00, 08 recommended |
| 10 | [10_multi_target.md](10_multi_target.md) | Multi-target / cleave simulations | L | High (core execution path) | none, but do last |
| 11 | [11_anonymous_run_sharing.md](11_anonymous_run_sharing.md) | On hold: record 60k+ DPS web runs (rotation + config) anonymously via a Cloudflare Pages Function + D1, with a re-simulating verify tool (full code in appendices) | S | None (web client only) | none |

Sizes: S = under a day of focused agent work, M = one to two sessions, L = several sessions (each plan's phases are separate sessions).

### Recommended order

```
01 Adrenals ----------------------------------------+
02 Timeline charts ---------------------------+     |
00 Shared experiment runner --+               |     |
                              +-- 08 Precision/significance
                              +-- 03 Stat weights & budget
                              +-- 04 Top Gear  <----------------- (01 adds the adrenal axis)
07 Share links  <------------------------------------- (re-extend after 01 and 06)
06 Encounter scripting  <---- (uses 00 for "fit HP", 02 to draw windows)
05 Combat log parity
09 Rotation tuner  <---- (needs 00; 08 recommended)
10 Multi-target  (last; ask the user for an explicit go-ahead first)
```

Why this order: 01 and 02 are small, visible wins with no dependencies. 00 is infrastructure that 03, 04, 06 (fit HP), 08 and 09 reuse, so it goes before them. 10 changes the core execution path and should only start when everything else is stable.

---

## 3. Ground rules checklist (from AGENTS.md, restated)

Tick every box for every plan.

- [ ] **No commits**, no amend/merge/rebase/cherry-pick/revert.
- [ ] **Frozen math** (rule 1): never change formulas in `src/swtorsim/combat_math.py`, `combat_math_unbucketed.py`, `combat_curves.py`, `combat_curves.json`, or `entities.py` `Player.recalculate_stats` / `calculate_gcd` / `calculate_cast_time` / `calculate_channel_duration` / `calculate_cooldown` / `calculate_effect_duration` / `calculate_effect_tick`. Calling them is fine. Stat routing tables (`_CASTER_DAMAGE_DISPATCH`, `_CRIT_CHANCE_DISPATCH`, `_CRIT_DAMAGE_DISPATCH`, `_SKIP_BASE_STATS`, `handle_target_debuffs`) change only on explicit user request.
- [ ] **No magnitude heuristics** (rule 2): honor `Modifier.is_percent`; never write `val / 100.0 if abs(val) > 1.0 else val`.
- [ ] **Stat IDs** (rule 3): verify against `src/extractor/mod_stats.py`; never guess.
- [ ] **Runner** (rule 4): run everything from the repo root with `.\tools\pyclean.exe`. Tests: `.\tools\pyclean.exe -m unittest discover -s tests -p "*test*.py"` (unittest only, no pytest).
- [ ] **ASCII console output** (rule 5): `[OK]`, `[WARN]`, `[FAIL]`; no emojis in anything printed to the console. (Emojis already exist inside the HTML UI; that is browser text, not console output.)
- [ ] **CRLF** (rule 6): Python, HTML, JS and test files are CRLF. Preserve CRLF when editing. New code files must be CRLF. (The Markdown files under `docs/` are currently LF; match the file you edit.)
- [ ] **Stem matching** (rule 7): any new name matching of `x` vs `x_plus` must respect `is_stem_matching_enabled()`.
- [ ] **State files** (rule 8): `TODO.md` holds open work only; `CHANGELOG.md` is append-only (do not read it unless investigating a regression).
- [ ] **Protocol** (rule 9): baseline test run first; 100% pass required; name the tests that cover the change; report pre-existing failures instead of fixing them; for damage-affecting changes report mean DPS before/after on a `data/run_config/` config with the same seed.
- [ ] **Routing** (rule 10): read `ARCHITECTURE.md` before grepping widely. Add rows to it for every new module, endpoint, or UI function the plan introduces.
- [ ] **Extracted data is ground truth** (rule 11): never hand-edit `data/extractor/live|pts/` or `src/extractor/data/`. Fix the extractor and ask the user to re-extract. User files (`data/builds|rotations|run_config|Choices/`) are edited only when the request is about them. **Copy a user file to the scratchpad if a test or DPS check needs a modified version.**
- [ ] **No clutter** (rule 12): no scratch scripts or debug output in the repo. Use the session scratchpad or `tools/debug_sim.py --output <temp path> --no-browser`.

### Baseline at the time of writing

```
.\tools\pyclean.exe -m unittest discover -s tests -p "*test*.py"
Ran 190 tests ... OK
```

The count will grow as plans land. Record your own baseline count at the start of each session.

### How to do the "DPS before/after" check (rule 9)

For any change that can affect damage:

1. Before editing, run a fixed-seed batch on an affected config and save the output to the scratchpad:
   ```
   .\tools\pyclean.exe main.py hatred_14gcd --mode BATCH --iterations 50
   ```
   Read the `Average Performance : X DPS` line.
   Note: `main.py run()` does not forward `config.seed` to `Tester` (see section 6, issue 2), so the CLI always uses seed 42. That is still a valid same-seed comparison.
2. Re-run the identical command after the change and compare.
3. For a stronger check (used by recent CHANGELOG entries), compare every damage event of a TEST run for seeds 42 / 43 / 44 on `hatred_14gcd`, `carnage_14gcd`, `sniper_marksmanship_config_test` and `annitest`. A scratchpad script that calls `src.swtorsim.web_gui.execute_simulation_from_payload` (or `_run_single_test_detailed`) and dumps `combat_log` works well; keep the script in the scratchpad, not the repo.
4. Report both numbers in your final message and in the CHANGELOG entry.

### How to write the CHANGELOG entry

Match the existing style (append at the end of `CHANGELOG.md`):

```
## <Area>: <Short Title>
- What changed, naming `path/file.py :: function` for each touched function, and why.
- Behavior notes (defaults, what stays identical).
- Same-seed check: configs, seeds, result (identical / DPS before -> after).
- Tests: new `tests/test_<name>.py` (N tests: short list). Full suite: <count> pass.
```

---

## 4. Shared conventions for new code

### 4.1 Adding a new HTTP API endpoint (applies to plans 00, 03, 04, 05, 06, 07, 08, 09)

The simulator runs in two modes. Every new endpoint must work in both:

1. **Native mode** (`main.py --web`): add the route to `SimulatorRequestHandler.do_POST` (or `do_GET`) in `src/swtorsim/web_gui.py`. Long-running work runs synchronously in the handler thread (the server is a `ThreadingHTTPServer`), reports progress through `_update_simulation_progress(...)`, and honors `_SIM_CANCEL`.
2. **WASM mode** (static `dist/` build, Pyodide workers): add an action to `dispatch()` in `src/swtorsim/pyodide_bridge.py`, then intercept the URL in the `window.fetch` override in `tools/web/pyodide_client.js` and route it to `callPrimaryWorker(action, payload)` (or to a multi-worker orchestrator for heavy jobs).
3. Add a row to the `ARCHITECTURE.md` module table (endpoint, function names).
4. New Python modules under `src/swtorsim/` are bundled into the web release automatically by `tools/bundle_pyodide_assets.py` (it includes the whole `src/swtorsim` directory). Modules elsewhere (for example `tools/`) are **not** bundled.

### 4.2 Adding UI to the simulator page (`tools/simulator_ui.html`)

- The page is one big HTML file with inline `<style>` and `<script>`. No build step, no frameworks, no external libraries. Charts are hand-written inline SVG (see `renderMonteCarloTab`, around line 2744).
- Use the existing CSS variables (`--accent`, `--text-muted`, `--bg-input`, `--border`, `--green`, `--red`, `--amber`, `--purple`, `--cyan`, ...) so light and dark themes both work. Never hard-code a light-only color.
- Results tabs: buttons live in `<nav class="tabs-bar">` (around line 1396), content panes are `<div class="tab-content" id="tab...">` (around lines 1421-1497), switching is `switchTab(id)`. Every result re-render goes through `renderAllResultPanels(res)` (around line 2457).
- Sidebar sections are `<div class="config-section">` blocks with a `section-header` (around lines 1058-1343). The payload sent to the server is built in `buildPayloadFromForm()` (around line 2234). A loaded run config is applied in `applyPresetRunConfig(path, fallbackParsed)` (around line 2158). Exports use `buildExportRunConfigObject()` (around line 3161).
- Modals: `<div class="modal-backdrop" id="...">` + `openModal(id)` / `closeModal(id)`.
- Check every UI change in both themes (the header has a theme toggle) and in both native and WASM modes when the plan touches an endpoint.

### 4.3 Python style

- Type hints on new functions, one-line docstrings that say what the function does (see existing modules).
- Pure helper functions (no I/O, no globals) wherever possible, so they can be unit tested without running a fight.
- Tests: `unittest`, one new file per feature under `tests/` named `test_<feature>.py`. Use small dummy HP (100k-500k) and few iterations to keep tests fast. The full suite currently runs in about 7 seconds; do not add a test that takes more than a few seconds.

---

## 5. Glossary (for human readers)

- **TEST run**: one simulated fight with a full combat log.
- **BATCH run (Monte Carlo)**: many fights with different random seeds; reports the average and spread of DPS.
- **Seed**: the starting number of the random number generator. The same setup with the same seed always produces the same fight. In a batch, fight number `k` uses seed `base_seed + k` (`web_gui.py :: _batch_worker_task`).
- **Variant**: one version of a setup (for example "+250 Crit Rating" or "Relic A + Relic B").
- **Experiment**: several variants, each run on the same seeds, compared to a baseline variant (plan 00).
- **Paired seeds / common random numbers**: running every variant on the same seeds, so random luck mostly cancels out when you subtract one variant's DPS from another's. This makes comparisons much more precise for the same number of fights.
- **Mean, SD, SE, 95% CI**: average; standard deviation (spread of single fights); standard error (uncertainty of the average, SD / sqrt(n)); 95% confidence interval (about mean +/- 1.96 SE).
- **Statistically significant**: the measured difference is larger than what random luck alone would plausibly produce (here: |difference| > 1.96 SE of the difference).
- **Stat weight**: how much DPS one extra point of a stat adds at the current gear level.
- **GCD tier**: the global cooldown is rounded up to the next 0.1 s (`Player.calculate_gcd`), so Alacrity only changes the GCD at certain thresholds (for example 1.5 s -> 1.4 s -> 1.3 s).
- **Successive halving**: run all candidates briefly, drop the worse half, run the survivors longer, repeat. Saves time when ranking many candidates.
- **WASM / Pyodide mode**: the browser-only build where Python runs inside Web Workers; there is no server.

---

## 6. Pre-existing issues found while researching (report, do not fix unasked)

These were found while writing the plans. Plans that touch the same code say how to handle them; otherwise just mention them to the user.

1. **`applySeedAndRun` calls an undefined function.** `tools/simulator_ui.html` around line 2648 calls `triggerSimulation()`, which is defined nowhere in the file (`grep triggerSimulation` finds only that call). The "Inspect seed" buttons in the stall banner therefore throw a ReferenceError. Plan 02 fixes it (it reuses that function), with justification.
2. **CLI ignores the config seed.** `main.py :: run()` (around line 167) builds `Tester(...)` without `seed=config.seed`, so CLI runs always use the `Tester` default seed 42 (`src/swtorsim/tester.py :: Tester.__init__`, `seed: int = 42`). Not fixed by any plan; tell the user.
3. **Stale user docs.** `docs/user_guide.md` lists rule keys `target_missing_debuff` / `target_hp_below` / `target_hp_above`, but the engine registry (`src/swtorsim/requirements.py :: CONDITION_REGISTRY`, around line 308) uses `target_doesnt_have_debuff` / `target_hp_below_pct` / `target_hp_above_pct`. The guide says `mode: "MONTE_CARLO"`, but `validate_run_config` accepts only `TEST` / `BATCH`. `README.md` says tests run with pytest; AGENTS.md says unittest.
4. **Bloodthirst damage bonus may not be a percent modifier.** `data/extractor/live/parsed/abl/sith_warrior/bloodthirst.json` effect 2 has `modify_stat` `STAT_cbt_damage_done_modifier_percentage` with `amount_percent: 0.0` and `amount_min: 0.1`. `Modifier.from_modify_stat` (`src/swtorsim/modifiers.py`, around line 143) sets `is_percent` only when `amount_percent != 0`, so this becomes `value=0.1, is_percent=False`. Whether the damage dispatch treats that as +10% must be verified before plan 06 offers raid burst buffs. Do not "fix" this with a heuristic (rule 2).
5. **`raid_members` target override is not handled.** `src/swtorsim/abilities.py :: _resolve_target_overrides` (around line 19) handles `party_members` but not `raid_members`, so a `raid_members` branch resolves to the current (enemy) target. Plan 06 avoids the problem by applying the raid buff effect directly to the player.
6. **The "missing" log tools still exist as bytecode.** `tools/__pycache__/parse_combat_log.cpython-313.pyc` and `validate_modifiers_vs_log.cpython-313.pyc` are present. Their docstrings, regexes and function names were recovered (by reading the compiled constants, without running them) and are reproduced in plan 05, so the rebuilt tools can match the originals.

---

## 7. Codebase facts several plans rely on

### 7.1 The simulate payload

`buildPayloadFromForm()` in `tools/simulator_ui.html` (around line 2234) sends this to `POST /api/simulate`:

```json
{
  "environment": "live", "env": "live", "pts": false,
  "class": "Assassin", "class_name": "Assassin", "spec": "Hatred", "spec_name": "Hatred",
  "spec_path": "data/extractor/live/disciplines/assassin/hatred.json",
  "stats_path": "data/builds/L80_14gcd_yellow.json",
  "stats_override": {"Mastery": 16834, "Power": 14503, "Critical Rating": 3758, "...": 0},
  "rotation_path": "data/rotations/assassin/hatred/BasicMaliPS.json",
  "choices": {"23": 2, "27": 1}, "choices_override": {"23": 2, "27": 1},
  "tactical_fqn": "abl.itm.tactical....",
  "legendary_fqns": ["abl.itm.legendary....", "abl.itm.legendary...."],
  "relic_fqns": ["abl.itm.relic....", "abl.itm.relic...."],
  "mode": "TEST", "iterations": 50, "dummy_hp": 6000000, "duration": 1000, "level": 80, "seed": 42,
  "training_dummy_armor_debuff": true, "enable_stem_matching": true,
  "enable_projectile_flight_time": false, "in_flashpoint_operation": true, "combat_distance": 30.0
}
```

`src/swtorsim/web_gui.py :: _resolve_simulation_inputs_from_payload` (around line 505) turns it into a `RunConfig` plus `sim_inputs` (`rotation_config`, `stats_config`, `loadout_blueprints`, `debuff_module`, `selected_fqns`). It validates with `validate_run_config`, caches loadouts in `_BLUEPRINT_LOADOUT_CACHE` keyed by `(env, tuple(selected_fqns))`, and applies `stats_override` on top of the stats file. Note it calls `os.chdir(SWTORSIM_ROOT)` and sets global toggles (`set_stem_matching`, ...).

### 7.2 Batch execution

- Native: `_run_batch_monte_carlo_detailed` (around line 1229) builds a `sim_context`, gets a warm `multiprocessing.Pool` from `get_or_create_simulation_pool(cores, sim_context, pool_key)` (around line 1056; the pool is rebuilt whenever the key changes, which costs process start-up time on Windows), submits chunks of `(run_id, base_seed, duration, dummy_hp)` to `_batch_worker_task` (around line 1099), polls `_SIM_CANCEL`, and aggregates with `_aggregate_batch_results` (around line 1342).
- One fight: `_batch_worker_task` seeds `random` with `base_seed + run_id`, calls `prepare_simulation(...)`, `sim.run_timed(duration, target)`, and returns a dict with `dps`, `total_damage`, `elapsed`, `abilities`, execute-phase data, stall data and `seed`.
- WASM: `tools/web/pyodide_client.js :: executeBatchMultiCore` (around line 526) splits iterations into one slice per worker, each worker runs `SIMULATE_SLICE` (`web_gui.py :: execute_simulation_slice`, around line 1509), then worker 0 runs `AGGREGATE_BATCH` (`aggregate_batch_slices`).
- The CLI (`main.py`) uses a third, separate fight runner: `src/swtorsim/tester.py :: Tester.execute_single_worker_task`. Plans do not change it.

### 7.3 Rotation files

A rotation file is either a bare list of steps or a dict wrapper:

```json
{
  "pre_combat": [ {"ability": "..."}, {"wait": 1.0} ],
  "pull_conditions": { "...rules..." }, "pull_max_wait": 10.0,
  "weave": [ {"ability_id": "...", "rules": {}} ],
  "sequence": [ ...steps... ]
}
```

Step types (`src/swtorsim/rotation.py :: Rotation.build_steps`): `fixed` (`ability_id`), `optional` (`ability_id`, `rules`), `priority_block` (`name`, `pool: [{ability_id, rules, lead_time?}]`), `loop_anchor`. Optional `lead_time` on steps and pool entries. Rule keys are the keys of `CONDITION_REGISTRY` in `src/swtorsim/requirements.py`: `target_hp_below_pct`, `target_hp_above_pct`, `target_has_debuff`, `target_doesnt_have_debuff`, `caster_has_buff`, `caster_does_not_have_buff`, `caster_energy_above`, `caster_energy_below`, `proc_cooldown_above`, `ability_cooldown_under`, `ability_cooldown_above`, `caster_buff_stacks`, `target_debuff_stacks`. The Rotation Builder normalizes files with `src/swtorsim/rotation_builder.py :: normalize_rotation_steps` and writes them with `build_rotation_file_data`.

### 7.4 Ability lookup by rotation id

`Player.build_ability_db` (`src/swtorsim/entities.py`, around line 423) indexes each active ability by its FQN, by `fqn.lower().replace(" ", "_")`, and by `name.lower().replace(" ", "_")`. The Rotation Builder's slug is `ability_name_to_slug(name, fqn)` in `src/swtorsim/cast_timeline.py` (same lowercase/underscore rule).

### 7.5 Fight timing

`Simulation.run_timed` (`src/swtorsim/engine.py`) stops at `combat_start_time + duration` or when the target's HP reaches 0. `combat_start_time` is set by the first `ApplyDamageLand.resolve` (`src/swtorsim/events.py`, around line 50). All times shown in the UI are relative to that moment (pre-combat times are negative).
