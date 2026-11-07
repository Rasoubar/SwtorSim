# Next Steps & Simulation Fixes

## Completed Fixes

### 45. Rotation Stall & Deadlock Telemetry with RNG Seed Tracking (events.py, metrics.py, engine.py, setup.py, tester.py, web_gui.py, test_rotation_stall.py) - [DONE]
- Implemented rotation stall detection in `PlayerReady.resolve` (`src/swtorsim/events.py`):
  - Differentiates early off-GCD lead-time polling (`sim.current_time < player.next_gcd`) from true rotation stalls (`sim.current_time >= player.next_gcd` with `acted is False`).
  - Automatically captures diagnostic context: step index, step class and target ability/priority-block label (`_get_step_diagnostic`), player resource state, and simulation RNG seed.
  - Automatically ends and records the stall duration once any rotational action resolves.
- Added comprehensive stall tracking to `Metrics` (`src/swtorsim/metrics.py`):
  - Added `log_rotation_stall_start`, `log_rotation_stall_end`, and `finalize_stalls` to record transient gaps as well as fight-ending permanent deadlocks.
  - Integrated ASCII status reports (`[WARN] ROTATION STALLS DETECTED`, `[FAIL] ROTATION PERMANENT DEADLOCK`) in `print_metrics`.
- Propagated authoritative `seed` across `Simulation` (`src/swtorsim/engine.py`), `prepare_simulation` (`src/swtorsim/setup.py`), `Tester` (`src/swtorsim/tester.py`), and `src/swtorsim/web_gui.py`.
- Integrated Monte Carlo batch reporting in `Tester._aggregate_results` and `produce_monte_carlo_report`, reporting stalled run percentages, average stalled time per run, and deterministic seeds of any deadlocked runs for immediate reproduction.
- Added 3 unit tests in `tests/test_rotation_stall.py` covering smooth runs, transient gaps, and permanent deadlocks. All 26 engine regression tests passing.

### 44. Integration of ability_cooldown_above Condition & Rotation Builder Tooling (requirements.py, rotation_builder.py, rotation_builder_ui.html, dist/rotation_builder.html, user_guide.md) - [DONE]
- Fixed docstring on `check_ability_cooldown_above` in `src/swtorsim/requirements.py` to correctly indicate strictly above.
- Integrated `ability_cooldown_above` into `data/rotation_builder.py` (`CONDITION_METADATA` and `KNOWN_RULE_KEYS`).
- Added full UI support for `ability_cooldown_above` in `tools/rotation_builder_ui.html` and rebuilt `dist/rotation_builder.html` and `swtorsim_assets.zip` via `tools/build_web_release.py`.
- Added documentation in `docs/user_guide.md` and added unit test assertions in `tests/test_simulation_integration.py`.

### 43. Dynamic Combat Simulator Navigation Link in Rotation Builder UI (tools/rotation_builder_ui.html, dist/rotation_builder.html, src/swtorsim/web_gui.py) - [DONE]
- Replaced the hardcoded `http://127.0.0.1:8000/` return link on the Rotation Builder's "Combat Simulator" navigation button with dynamic port resolution.
- Updated `SimulatorRequestHandler` in `src/swtorsim/web_gui.py` to pass the active Combat Simulator port as `?sim_port=<port>` when launching the Rotation Builder.
- Updated `tools/rotation_builder_ui.html` to capture `sim_port` (persisted in `localStorage`), auto-detect local server ports (`8765..8785`), and open the actual active Combat Simulator instance (defaulting to `8787`), while preserving clean relative `index.html` navigation in static WebAssembly (`dist/`) builds.
- Rebuilt `dist/rotation_builder.html` via `tools/build_web_release.py`.


### 42. Consolidation of Unified Simulation Runner into main.py (main.py, run_sim.py, web_gui.py, README.md, docs/user_guide.md) - [DONE]
- Consolidated all simulator execution workflows into `main.py` as the authoritative root entry point:
  - Web GUI mode: `python main.py --web` (opens default port 8787).
  - Interactive selection menu: `python main.py` (lists saved configs, HP presets, and mode selection with option `[0]` opening the Web GUI).
  - Fast CLI execution: `python main.py <config> --hp <hp> --mode <mode> --iterations <n>`.
  - Step-by-step loadout builder wizard: `python main.py --wizard` (or `--interactive`).
- Replaced redundant implementation in `run_sim.py` with a lightweight, backward-compatible alias directing calls to `main.py`.
- Synchronized documentation in `README.md` and `docs/user_guide.md`.


### 41. Mutually Exclusive Branch Resolution & Conditional Evaluation in Passive Effect Hydration (effects.py, setup.py) - [DONE]
- Unified branch modifier extraction across `ActiveEffect.from_effect_node` and `ActiveEffect.from_effect` via `_resolve_branch_modifiers` in `src/swtorsim/effects.py`, evaluating both `branch.conditions` (`validate_all`) and `run_if_none_ran` fallback chains against `executed_branches` and current stack context (`stack_multiplier`, `current_stacks`, `stacks`, `charges`).
- Separated passive blueprint registration (`player.passive_db` and `stat_changes`) from `entry_effect_ids` execution in `prepare_simulation` (`src/swtorsim/setup.py`), ensuring passive condition checks are independent of dictionary iteration order.
- Added `test_09_high_energy_gas_cylinder_conditional_branch_hydration` in `tests/test_simulation_integration.py`, verifying that `High Energy Gas Cylinder` loads a single `+7%` (`0.07`) Energy Dealt Scale modifier when the player has `Blood Tracker` and a single `+5%` (`0.05`) modifier when `Blood Tracker` is absent.

### 40. Empirical Modifier Bucketing: Test 12 Verification for Caster Type Dealt Scale (`395` / `397`) - [DONE]
- Empirically proved on Advanced Prototype Powertech using `Magnetic Blast` that Caster Type Dealt Scale modifiers (`stat_cbt_damage_dealt_scale_type_energy_modifier_percentage` / GOM `395` and `stat_cbt_damage_dealt_scale_type_kinetic_modifier_percentage` / GOM `397`, granted by *High Energy Gas Cylinder* `+7%`) pool **additively into `BUCKET_1`** alongside general damage done (`79`) and vulnerabilities (`386`, `388`).
- Confirmed against live in-game StarParse data with all module debuffs (Sundered $-20\%$ armor, Susceptible $+5\%$ Tech vuln) and Shock Trooper (`+10%`): observed non-crits `14,921 – 15,271` and crits `*26,895 – *27,538` matched Option A (`14,882 – 15,596` non-crit and `26,789 – 28,073` crit), strictly disproving Option B whose absolute mathematical floor is `15,079` non-crit / `27,144` crit.
- Routed `395` and `397` to `BUCKET_1` in `src/swtorsim/combat_math_unbucketed.py`, logged empirical verification in `docs/modifier_bucketing_log.md`, and marked verified in `docs/modifier_bucketing_master_checklist.md`.

### 39. Universal Off-GCD Early Weave & Web Rotation Builder Integration (`rotation.py`, `entities.py`, `abilities.py`, `events.py`, `rotation_builder.py`, `tools/rotation_builder_ui.html`) - [DONE]
- Generalized off-GCD pre-cast timing across all rotational step types (`FixedAbilityStep`, `OptionalAbilityStep`, and `PriorityBlockStep`), decoupling early weave detection from step optionality. Any upcoming off-GCD ability (`triggers_gcd == False`) is automatically evaluated early during the preceding GCD window (defaulting to 0.25s lead time unless customized or disabled with 0.0s).
- Added `DEFAULT_OFF_GCD_LEAD_TIME: float = 0.25` in `src/swtorsim/rotation.py`. Updated `Rotation.get_next_lead_time` to inspect `player.ability_db` across fixed ability steps, optional steps, and priority block pools.
- Enhanced `FixedAbilityStep.evaluate` and `PriorityBlockStep.evaluate` with early-window safety guards so on-GCD abilities are never cast before GCD while off-GCD abilities can weave early.
- Updated `tools/rotation_builder_ui.html` and compiled release `dist/rotation_builder.html` via `tools/build_web_release.py`:
  - Added visual `Off-GCD (Early Weave)` badges on Fixed and Optional step headers when off-GCD abilities are selected.
  - Added inline `Lead: [ 0.25 ] s` numeric controls to configure or disable lead time per step.
  - Added `Off-GCD (Early Weave)` badges to priority block pool rows.
  - Updated rotation linter to clarify that off-GCD fixed steps pre-cast early and only block if remaining on cooldown.
- Expanded `tests/test_optional_lead_time.py` with 5 targeted tests covering default lead time, explicit zero-lead time, fixed steps, optional steps, and on-GCD safety invariants.


### 38. DotTick Expiration on_pre_remove Lifecycle Execution (src/swtorsim/events.py) - [DONE]
- Fixed DotTick.resolve in src/swtorsim/events.py omitting lueprint.execute_triggered_branches('on_pre_remove', ...) when a ticking effect reaches expiration (	icks_remaining <= 0).
- This caused sub-effects with tick intervals (such as Ferocity_2 with 0.3s duration and 0.3s tick interval) to expire silently without firing their on_pre_remove action (modify_stack_charge -1 on 	ag.abl.sith_warrior.ferocity). As a result, Massacre, Gore, Smash, and Sweeping Slash were failing to decrement Ferocity stacks, allowing subsequent attacks during the 10-second buff window to retain 100% armor penetration and inflating damage output by ~2,100 DPS.
- DotTick.resolve now executes on_pre_remove branches before cleanup, matching EffectExpire.resolve and ensuring accurate dual-wield multi-hit stack consumption.



### 1. Upgrade Condition Validation (`src/swtorsim/requirements.py`) - [DONE]
- Implemented dual-format condition dispatcher, AST logic evaluator (`evaluate_logic`), and extracted condition handlers (`has_ability`, `has_effect`, `if_toughness`, `if_health`, `has_specified_resource_amount`, etc.).

### 2. Standardize `ResourcePool` Interface (`src/swtorsim/resources.py`) - [DONE]
- Standardized on `current_value` in `test_ability_execution.py`.

### 2b. Unify `effects.py` & `effects_temp.py` and Upgrade `Entity.apply_effect` - [DONE]
- Merged `@dataclass ActiveEffect` into `effects.py`, added `ActiveEffect.from_effect()`, deleted `effects_temp.py`, and updated `Entity.apply_effect`.

### 3. Populate or Derive `is_attack` on Ability Branches (`src/swtorsim/abilities.py`) - [DONE]
- Derived `is_attack` in `Branch.from_dict` whenever a branch contains an action with `action_type == "damage"`.

### 3b. Action Type Handling in `execute_single_action` (`src/swtorsim/abilities.py`) - [DONE]
- Added `NOOP_ACTION_TYPES` for non-DPS/physics/movement/CC/visual actions and wired extracted combat action types (`energy_recovery`, `regen_force`, `regen_energy`, `restore_action_points`, `spend_energy`, `spend_force`, `modify_cooldown`, `modify_recharge_time`, `modify_ability_stack_charge`, `remove_effect`, `dispel`, `execute_ability`).

### 4. Terminal / Logging Safety (`src/swtorsim/config_load.py`) - [DONE]
- Replaced Unicode emojis (`✅`, `⚠️`) in `config_load.py` with ASCII indicators (`[OK]`, `[WARN]`) so tests and CLI runs work on default Windows console code pages without `PYTHONUTF8=1`.

### 5. Persistent Effect Lifecycle: `on_apply` Branches & Periodic `on_tick` Scheduling (`abilities.py`, `entities.py`, `events.py`, `effects.py`) - [DONE]
- Verified that `Eradicate` (1 direct + 6 ticks), `Creeping Terror` (direct + periodic ticks), and `Discharge` (direct + periodic ticks) all tick and expire properly.

### 6. Passives, Procs, and `TriggerManager` Integration (`setup.py`, `triggers.py`, `events.py`, `requirements.py`, `entities.py`, `abilities.py`) - [DONE]
- Initialized `sim.triggers = TriggerManager()` in `Simulation.__init__`, subscribed applied effects' non-lifecycle branches in `Entity.apply_effect`, and unsubscribed expired/removed effects in `Entity.cleanup_expired_effects`.
- Activated passive blueprints (`entry_effect_ids` and `stat_changes`) in `prepare_simulation` (`setup.py`), populating `player.passive_db` and applying talent cost/stat modifiers (`Fanaticism`, `Claws of Decay`, etc.) in `Player.calculate_resource_cost`.
- Dispatched `on_damage_dealt` / `on_damage_taken` in `DamageHit.resolve` (passing `attack_type`, `spell_type: 1` for weapon attacks and `3` for spell/Force attacks), `on_ability_post_activate` in `Ability.cast`, and `on_stack_charge_decreased` in `handle_modify_stack_charge`.
- Enforced `spell_type` filtering in `TriggerManager.dispatch` so triggers specifying weapon attacks (`spell_type: 1`, such as `Thrashing Terror`) do not trigger off Force attacks or periodic DoT ticks.
- Updated `check_proc_cooldown_above` (`requirements.py`) to return `False` when the proc buff is currently active (`caster.has_effect(name)`) and otherwise check the remaining ICD duration on the proc's `"lockout"` effect in `caster.effects` (while `Entity.has_effect` excludes `is_passive` and `"lockout"` effects).
- Updated `BasicMaliPS.json` to reference `"assassinate+"`.

### 7. Ability & Effect Targeting Hierarchy (`src/swtorsim/abilities.py`) - [DONE]
- Implemented `_resolve_target_overrides` and separated the player's combat target (`caster.current_target`) from the active ability/effect/branch target (`ability_target` / `effect_target` / `actual_target`).
- Active abilities with `"tag.abl.utility.aggressive_action"` or `"tag.abl.utility.is_basic_attack"` default to the enemy target, while untagged active abilities (`Recklessness`, `Force Speed`, `Deflection`, `Force Shroud`, etc.) default to `caster`.
- Handled `"aoe_sphere"`, `"aoe_cone"`, `"enemies_list"`, and `"primary_target"` overrides in `_resolve_target_overrides` so abilities like `Death Field` (whose Effect #1 sets `target_overrides: [{"type": "caster"}]` before Branch 3 overrides back to `aoe_sphere`) hit the enemy target properly.

### 8. Effect-Level Condition Validation & `effParam_Slots` Weapon Hand Resolution (`abilities.py`, `requirements.py`, `src/extractor/abilities.py`) - [DONE]
- Added `self.conditions` validation at the start of `Effect.execute` in `src/swtorsim/abilities.py` and wired `"has_melee_weapon"`, `"is_dual_wielding"`, and `"is_not_dual_wielding"` in `src/swtorsim/requirements.py`.
- Updated `_decode_action` (`effAction_WeaponDamage`) in `src/extractor/abilities.py` to derive `"hand"` from GOM `effIntListParams["effParam_Slots"]` (`"2"`/`"5"` -> `"main"`, `"3"`/`"4"` -> `"off"`) and re-parsed the 5 affected ability files (`saber_strike_optimize` for Inquisitor & Consular, `agent/leg_shot`, `agent/series_of_shots`, `agent/takedown`).
- Added a guard in `handle_damage_action` (`src/swtorsim/abilities.py`) so true off-hand hits (`hand == "off"`) are skipped when `Off_hand_max <= 0`.

### 9. Modern Modifier Pipeline Integration & Combat Math Scaling (`combat_math.py`, `entities.py`, `modifiers.py`, `events.py`, `effects.py`) - [DONE]
- **Base Character Stat Recalculation**: Updated `Player.recalculate_stats` in `entities.py` to process active `ActiveEffect` instances and untargeted `Modifier` records (`STAT_att_mastery`, `STAT_rtg_attack_power`, `STAT_cbt_force_damage_bonus`, `STAT_cbt_melee_damage_bonus`, `STAT_rtg_crit`, `STAT_rtg_alacrity`, `STAT_rtg_accuracy`). Buffs like `Mark of Power` (+5% Mastery), `Force Training` (+3% bonus damage), and relic procs (`Mastery Surge` +4220, `Power Surge` +4220) now properly modify live combat ratings.
- **Context & Tag Propagation**: Updated `handle_damage_action` and `DamageHit` (`abilities.py`, `events.py`) to preserve `ability_fqn` and `combined_tags` (ability tags, effect tags like `tag.abl.sith_inquisitor.periodic_damage`, and action tags), passing them into `calculate_hit` and `handle_modifiers`.
- **Target Filtering & Stem Matching**: Upgraded `Modifier.applies_to` (`modifiers.py`) to support suffix stems (`_plus`, e.g. `assassinate` &rarr; `assassinate_plus`) and set collections.
- **Hit Modifier Routing & Stat Channels**: Modernized `handle_caster_buffs`, `handle_target_debuffs`, and `handle_mitigation` in `combat_math.py` to evaluate `Modifier` objects from active effects:
  - Additive damage percentage bucket (`STAT_cbt_damage_done_modifier_percentage`, `79`, `386`, etc.) for talents like `Force Dread` (+15% DoT damage), `Crackling Charge` (+30% Discharge damage), `Dreadful Nightmares` (+20% Eradicate), `Fulguration` (+10% Creeping Terror), `Pervasive Death` (+15% Death Field), `Thrashing Blades` (+5%), and `Greased Lightning` (+1–5% tactical stacks).
  - Low-health execute bucket (`STAT_cbt_damage_done_if_target_health_low_modifier_percentage`, `220`) for `Inevitable Demise` (+25% execute damage) and `Languishing Lashes` (+20% execute damage).
  - Channel-specific critical chance routing: separated Melee (`STAT_cbt_melee_critical_chance`, `116`) from Force (`STAT_cbt_force_critical_chance`, `133`), correctly scaling `Coordination` (+5% crit), `Recklessness` (+60% direct Force crit), and `Languishing Lashes` (+20% DoT crit).
  - Channel-specific critical damage routing (`117` vs `134`, `Claws of Decay` +12% crit damage).
  - Stacking scales fix in `ActiveEffect.from_effect` (`effects.py`) to respect `scales_with_stack_charge`.
- **Results**: Overall DPS increased from **15,465.6** to **24,068.4** (with execute DPS reaching **32,039** and dummy TTK dropping from 646.8s to 415.8s). All 16 unit and integration tests passing.

### 10. Dynamic Force Cooldown Reduction & Set Bonus Scaling (`entities.py`, `abilities.py`) - [DONE]
- Updated `Entity.calculate_cooldown` to query `self.effects` for cooldown stat modifiers (`STAT_abl_time_cooldown`, stat `64`) matching ability FQNs/tags.
- Passed `ability=self` to `calculate_cooldown` during `schedule_recharge` and `apply_cooldown_locks` in `abilities.py`.
- Verified that Dynamic Force set bonus properly reduces `Recklessness` cooldown by 15s (from base 90.0s to 75.0s, scaled by alacrity down to 69.8s).
- Verified `Reckless Hatred` charges restore on all critical DoT ticks and `Escalating Terror` (+25% DoT Force Crit Chance) applies via `Assassinate+`.

### 11. Discipline Branch Isolation & Critical Strike Routing Normalization (`combat_math.py`, `effects.py`, `entities.py`) - [DONE]
- **Discipline-Specific Effect Branching**: Updated `ActiveEffect.from_effect` in `effects.py` and `entities.py` to evaluate and filter `branch.conditions` via `validate_all`. Excluded Deception-only Branch 6 from `Recklessness:1` (+60% Force crit for Assassinate), ensuring only Hatred-valid branches apply.
- **Strict Channel Filtering**: Eliminated broad substring checks (`any("force" in str(t).lower())`) in `combat_math.py`, enforcing strict numeric `attack_type` matching (`1 = Melee`, `2 = Ranged`, `3 = Force`, `4 = Tech`). Prevented hybrid attacks (`Leeching Strike`) from double-dipping into Force crit bonuses and receiving duplicate `Coordination` (+10% &rarr; +5%).
- **Verification**: Normalized melee crit rates across Monte Carlo simulations (`Assassinate+` 43.9%, `Leeching Strike` 39.9%), while preserving intended high DoT crit rates (`Creeping Terror` 92.5%, `Discharge` 92.3%, `Eradicate` 90.3%, `Thrashing Terror` 86.8%).
- **Thrashing Terror Mechanics**: Verified that `Leeching Strike` (non-basic melee weapon attack, `weapon_mode: 2`) procs `Thrashing Terror` at a 60% rate whenever `Creeping Terror` is present on the target (boosted by `Deathmark`).

### 12. Fix Trigger Suppression on Passive-Originated Damage Hits (`events.py`) - [DONE]
- Removed `not self.from_proc` trigger gate in `DamageHit.resolve` (`src/swtorsim/events.py`), which previously prevented all abilities with `"type": "passive"` from dispatching `on_damage_dealt` events.
- Enabled `Thrashing Terror` periodic Force damage critical ticks to properly proc `Reckless Hatred` (-2s cooldown per crit on `Recklessness`), consistent with SWTOR game rules.
- Verified that attack type, tag filters, and built-in ICDs naturally prevent proc loops (all 17 unit/integration tests pass with 0 errors).
- Benchmarked 50-fight Monte Carlo with Berserker's Package: average DPS surged from **45,785.8** to **50,823.0 DPS** (+11.0%), execute DPS reached **63,734.5 DPS**, and `Death Field` crit rate reached **98.3%** due to consistent Recklessness uptime.

### 13. Configurable Ability Stem Matching Toggle (`settings.py`, `run_config.py`, `modifiers.py`, `entities.py`, `abilities.py`, `triggers.py`) - [DONE]
- Implemented global/run-config feature toggle `enable_stem_matching` (default: `False`), allowing users to choose whether base ability modifiers (e.g. `assassinate`) automatically stem-match discipline variants (`assassinate_plus`).
- When `enable_stem_matching: false`, `Claws of Decay` only applies to base `assassinate` and does not bleed over to `assassinate+`.
- Benchmarked 50-fight Monte Carlo with stem matching disabled:
  - Average DPS: **49,842.3 DPS** (vs 50,823.0 DPS with stem matching enabled).
  - Execute Phase DPS: **62,175.6 DPS**.

---

## Remaining Next Steps & Codebase Audit Items

### 14. Preserve `is_percent` on `Modifier` & Remove `abs(val) <= 1.0` Heuristics (`modifiers.py`, `entities.py`, `effects.py`) - [DONE]
- Added `is_percent: bool = False` to `Modifier` dataclass and populated it across all factory methods in `src/swtorsim/modifiers.py`.
- Updated `Entity.calculate_cooldown`, `Entity.calculate_resource_cost`, and `Entity.recalculate_stats` in `src/swtorsim/entities.py` to check `mod.is_percent` directly.
- Eliminated the bug where flat 1.0s cooldown reductions and flat 1 Force cost reductions were treated as -100% reductions.
- Fixed GOM `stat_mod_type: 2` (Percentage) detection in `from_modify_meta_stat` and `from_conditional_stat_mod`, ensuring procs like `Raze` (-100% Force cost on Eradicate) correctly zero the ability cost rather than applying -1 flat Force, which previously starved rotation Force and tanked DPS.
- Added specific test coverage in `tests/test_modifier_percentages.py`. All 23 tests pass with 0 errors.

### 15. Respect Action `damage_type` on Melee and Ranged Attacks (`combat_math.py`) - [DONE]
- Fixed `combat_math.calculate_hit` to inspect `action_data.get("damage_type")` rather than forcefully overriding all melee/ranged attacks to Kinetic (`1`).
- Fallback safely assigns Energy (`2`) for lightsaber and blaster weapon attacks when omitted by blueprints, preserving armor mitigation while enabling type-specific debuff scaling.
- Updated `events.py`, `metrics.py`, and `tester.py` to record and report Attack Type (Melee, Force, etc.) and Damage Type (Energy, Kinetic, Internal) in both single-run and macro Monte Carlo tables.
- All 22 tests pass with zero errors.

### 16. Implement Ranged and Tech Combat Channels (`combat_math.py`, `entities.py`) - [DONE]
- Added `Tech Power`, `R_Bonus_Damage`, and `T_Bonus_Damage` to `Player.base_stats` in `src/swtorsim/entities.py`.
- Updated `Entity.recalculate_stats` to parse `STAT_cbt_ranged_damage_bonus` and `STAT_cbt_tech_damage_bonus`, and compute all 4 bonus damage pools (`M_Bonus_Damage`, `R_Bonus_Damage`, `F_Bonus_Damage`, `T_Bonus_Damage`).
- Updated `combat_math.calculate_base_damage` to route each attack channel (`1` Melee, `2` Ranged, `3` Force, `4` Tech) to its corresponding bonus damage pool with graceful fallbacks.
- Updated `combat_math.handle_caster_buffs` to support `stat_cbt_damage_dealt_scale_channel_ranged_modifier_percentage` and `..._tech_...`.
- Added dedicated test suite `tests/test_combat_channels.py`. All 23 test suites pass with zero errors.

### 17. Remove Ghost `target.dots` and Legacy DoT Checks (`entities.py`, `requirements.py`, `events.py`) - [DONE]
- Removed dead `self.dots = {}`, `has_dot`, and `count_active_dots` from `Dummy` in `src/swtorsim/entities.py`.
- Removed legacy unused condition helpers (`check_exact_dot_amount`, `check_has_any_dot`, `has_specific_dot`, `check_dot_absent`) and their entries in `CONDITION_REGISTRY` from `src/swtorsim/requirements.py`.
- Modern SWTOR mechanics now rely exclusively on the canonical GOM tag checking system (`entity_has_effect` with tags).
- Removed dead legacy `del self.target.dots[dot_name]` in `src/swtorsim/events.py`.
- All 23 test suites pass with zero errors.

### 18. Fix Off-hand Base Damage Scaling Formula (`combat_math.py:404-414`) - [DONE]
- Unified off-hand and main-hand formula in `calculate_base_damage`: off-hand sets `weapon_min/max = Off_hand_min/max * 0.3` and runs through the complete ability scaling equation `((amp + 1) * weapon_min/max) + (coeff * damage_bonus) + (shp_min/max * standard_health)`.
- Fully faithful to SWTOR engine mechanics, mathematically consistent with all extracted ability blueprints (where off-hand `coeff` and `shp` are 0.0), and supports off-hand scaling coefficients.
- All 23 test suites pass with zero errors.

### 19. Clean Dead Code in `setup.py` (`setup.py:10-28`) - [DONE]
- Removed dead uncalled `pre_sim_effects` function which contained legacy prototype code mutating ability cooldowns and charges.
- Modern SwtorSim handles dynamic cooldown reductions via `Entity.calculate_cooldown` and charges via blueprints.
- All 23 test suites pass with zero errors.

### 20. Remove Legacy `consume_charges` in `combat_math.py` (`combat_math.py:301-328`) - [DONE]
- Removed uncalled legacy prototype function `consume_charges` and its reference in `handle_modifiers`.
- Stack charges and consumable charges are now handled canonically by GOM triggers (`on_stack_charge_decreased`, `handle_modify_stack_charge`) and `TriggerManager`.
- All 23 test suites pass with zero errors.

### 21. Establish Canonical `spell_type`, `attack_type`, & GOM `effParam_Slots` Routing (`abilities.py`, `extractor/abilities.py`, `events.py`, `triggers.py`, `combat_math.py`) - [DONE]
- Implemented automatic classification in `src/extractor/abilities.py` and `handle_damage_action`:
  - GOM Equipment Slots for weapon attacks:
    - `Slot 5` (Melee Mainhand) & `Slot 3` (Melee Offhand) &rarr; `attack_type = 1` (Melee), `spell_type = 1` (Weapon).
    - `Slot 2` (Ranged Mainhand) & `Slot 4` (Ranged Offhand) &rarr; `attack_type = 2` (Ranged), `spell_type = 1` (Weapon).
  - Tech abilities &rarr; `attack_type = 4` (Tech), `spell_type = 2` (Tech).
  - Force powers &rarr; `attack_type = 3` (Force), `spell_type = 3` (Force).
- Preserved `slots` on decoded action blueprints.
- Updated `events.py` `DamageHit.resolve` to dispatch explicit `spell_type` from action data with canonical fallback.
- Updated `triggers.py` to respect GOM wildcard convention (`spell_type: 1` matches all attacks unless restricted, while `spell_type: 2` is Tech-only and `spell_type: 3` is Force-only; weapon attacks filtered by `weapon_mode: 2`).
- Updated `combat_math.calculate_base_damage` to support graceful bonus damage channel fallbacks.
- Added comprehensive unit tests in `tests/test_combat_channels.py`. All 23 test suites pass with zero errors.

### 22. Unify Target Vulnerabilities into Additive Damage Pool with Multiplicative Execute Phase (`combat_math.py`, `tester.py`) - [DONE]
- Folded all target vulnerabilities (channel vulnerabilities: Force/Tech/Melee/Ranged/Weapon; damage type vulnerabilities: Internal/Elemental/Kinetic/Energy; tag vulnerabilities: AoE/DoT; and general damage received modifier percentage `STAT_cbt_damage_received_modifier_percentage`) directly into `buckets["normal_percentage"]` in `handle_target_debuffs`.
- Preserved `sub_30` (execute phase, $<30\%$ HP damage modifier) in `buckets["sub_30"]` as a multiplicative factor multiplying the entire additive damage pool:
  $$\text{total\_multiplier} = \bigl(1.0 + (\text{DamageDone\%} + \text{Vulnerabilities\%})\bigr) \times \bigl(1.0 + \text{sub\_30}\bigr)$$
- Eliminated redundant `taken = damage_taken_multiplier(...)` call and `* taken` in `calculate_hit`.
- Fixed `±` Unicode encoding crash in Windows consoles within `tester.py:189, 236`.
- Added unit tests in `tests/test_vulnerability_buckets.py` verifying additive vulnerability stacking and multiplicative execute scaling. All 24 test suites pass with zero errors.
- Verified 50-fight Monte Carlo benchmark: **48,374.2 DPS** average, **58,036.9 DPS** in Execute phase.

### 23. Complete Deprecation & Removal of Legacy `EFFECTS` Dictionary and Fallbacks (`combat_math.py`, `entities.py`) - [DONE]
- Completely deleted the hardcoded legacy `EFFECTS` dictionary (lines 5-29) and `alter_modifier` function from `src/swtorsim/combat_math.py`.
- Removed legacy fallback branches (`if effect_id in EFFECTS:`) from `handle_caster_buffs` and `handle_target_debuffs` in `src/swtorsim/combat_math.py`.
- Removed dead `_get_stat_name` in `src/swtorsim/entities.py`.
- Cleaned up legacy `EFFECTS` checks in `consider_recalculation`, `cleanup_expired_effects`, `Player.recalculate_stats`, `calculate_ability_cost`, and `Dummy.recalculate_stats` in `src/swtorsim/entities.py`.
- Modernized all effect handling to rely 100% on GOM-extracted `ActiveEffect` and `Modifier` structures.
- All 24 test suites pass with zero errors.

### 24. Channeled Ability Lifecycle, Periodic Ticks, and Clipping Pipeline (`abilities.py`, `effects.py`, `events.py`, `engine.py`) - [DONE]
- Integrated channel activation detection in `Ability.cast` and `_start_channel`: automatically parses blueprint `"activation": {"type": "channel", "duration": D}`.
- Scaled channel duration and periodic tick intervals by player Alacrity (`scale_time_modifier`).
- Implemented `ActiveChannel` state tracking and modern `ChannelTickEvent` periodic tick execution (evaluating `on_tick` branches across ability effects while supporting legacy action list fallbacks).
- Wired channel clipping / interruption: higher-priority casts cleanly interrupt `active_channel`, safely aborting queued future ticks via identity validation without ghost damage or resource leakage.
- Fixed future event drop bug in `Simulation.run_timed` (`engine.py`) when stepping through time increments.

### 25. Protected Channels & Universal Cast Interruption Rule (`abilities.py`, `tests/test_channels.py`) - [DONE]
- Enforced strict protection by default in `Ability.can_cast`: both GCD and off-GCD abilities (e.g. offensive/defensive cooldowns) return `False` while an active channel or cast is in progress, preventing priority rotations from accidentally self-sabotaging and clipping channels prematurely.
- Added explicit clipping support (`allow_clip: bool = True`) to `can_cast` and `cast`: when clipping is explicitly permitted or forced, activating an ability immediately cancels `active_channel` / `active_cast` and drops remaining ticks.
- Updated `tests/test_channels.py` to verify that both GCD and off-GCD abilities are blocked during channels by default, and that forced/clipping off-GCD casts immediately interrupt the channel and stop future periodic ticks.
- All 25 test suites passing with zero errors.

### 26. Stack & Target Conditions Engine (`requirements.py`, `abilities.py`, `events.py`, `tests/test_stack_conditions.py`) - [DONE]
- Added `get_entity_effect_stacks` in `src/swtorsim/requirements.py` to inspect live stack/charge counts across `entity.effects` and active DoTs matching tags or FQNs.
- Implemented `has_effect_at_stack_charge_count` in `evaluate_single_extracted_condition`: evaluates operator comparisons (`gte`, `gt`, `eq`, `lte`, `lt`) against an external buff or debuff on the specified actor.
- Implemented `if_stack_charge` in `evaluate_single_extracted_condition`: evaluates exact-tier stack matching against current effect executing branches (propagated via `stack_multiplier` and `current_stacks` in `execute_triggered_branches` across `abilities.py` and `events.py`).
- Implemented `is_target_caster` in `evaluate_single_extracted_condition`: distinguishes self-casts (`target is caster`) from hostile enemy casts.
- Implemented `is_casting` in `evaluate_single_extracted_condition`: checks active channels, active cast bars, and optional `ability_spec` matching.
- Added dedicated unit test suite in `tests/test_stack_conditions.py` using actual parsed game blueprints (*Force Barrier*, *Supercharge*, *Shoulder Cannon AP*, *Ballistic Shield*, *Take Cover*, and *Infiltrate*).
- All 26 unit test suites pass with zero errors.

### 27. Transparent CPython 3.13 Windows Runner & Stderr Warning Elimination (`tools/pyclean.cs`, `tools/pyclean.exe`) - [DONE]
- Diagnosed Windows AppContainer/sandbox restriction denying `GetFinalPathNameByHandleW(VOLUME_NAME_DOS)` during Python 3.13 C runtime startup.
- Implemented and compiled `SwtorSim/tools/pyclean.exe` (.NET 4.0 transparent wrapper), filtering the benign startup warning while preserving stdout, all real tracebacks/exceptions, and exit codes, and enforcing UTF-8 CLI IO encoding (`PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1`).
- Eliminates log noise, PowerShell error stream pollution, and delays across unit tests and Monte Carlo parallel worker executions.

### 28. Discipline Critical Damage Routing & Global Stat ID Audit (`combat_math.py`, `entities.py`, `modifiers.py`, `tools/catalog_game_data.py`, `tests/test_discipline_critical_damage.py`) - [DONE]
- Normalized attack types (`is_melee`, `is_ranged`, `is_force`, `is_tech`) across `handle_caster_buffs` and `handle_target_debuffs` to support both integer channel IDs (`1, 2, 3, 4`) and string representations (`"melee"`, `"force"`, etc.).
- Cross-referenced all numeric IDs across the engine with the authoritative `Stat_IDs.xlsx` file and corrected all discrepancies:
  - Added Ranged Critical Damage (`123`) and Tech Critical Damage (`136`) aliases alongside Melee (`117`) and Force (`134`).
  - Corrected Ranged Critical Chance ID from `118` to `122` (118 is Melee Glance Chance).
  - Corrected Bonus Damage IDs in `entities.py` and `combat_math.py`: Melee (`26`), Ranged (`25`), Force (`129`), Tech (`130`).
  - Added Energy cost ID `69` alongside Force cost `68` in `entities.py` and `modifiers.py`.
  - Replaced redundant substring fallback checks in channel vulnerability processing (`handle_target_debuffs`) with clean, direct stat matching.
- Added dedicated unit test suite `tests/test_discipline_critical_damage.py` testing real blueprints (*Vehemence*, *Sever*, *Deadly Cannon*) and exact critical damage formula evaluation.
- Updated `tools/catalog_game_data.py` to recognize all 4 critical damage stats (`STAT_cbt_melee_critical_damage`, `STAT_cbt_ranged_critical_damage`, `STAT_cbt_force_critical_damage`, `STAT_cbt_tech_critical_damage`), regenerating `data/catalog_summary.md` with all 182 occurrences marked **Implemented**.
- Full test suite: all 44 unit tests passing with zero errors.

### 29. Target-State & Rotational Damage Modifiers (`combat_math.py`, `tools/catalog_game_data.py`, `tests/test_target_state_modifiers.py`) - [DONE]
- Implemented `_entity_has_tag(entity, tag_substr)` helper in `src/swtorsim/combat_math.py` to inspect active unexpired effects for status tags (`bleed`, `burn`/`fire`, `stun`/`incapacitate`, `accuracy_reduced`).
- Wired target-state conditional damage modifiers into `handle_caster_buffs`:
  - `STAT_cbt_damage_done_if_target_bleeding_modifier_percentage` (`221`): scales damage when target is bleeding (*Blood Tracker*, *Bloodbath*, *Triumph*).
  - `STAT_cbt_damage_done_if_target_on_fire_modifier_percentage` (`250`): scales damage when target is burning (*Burning Storm*).
  - `STAT_cbt_damage_done_if_target_accuracy_reduced_modifier_percentage` (`389`): scales damage when target accuracy is debuffed (*Torment*, *Psychokinesis*).
  - `STAT_cbt_dual_wield_damage_done_modifier_percentage` (`127`): scales damage when caster is dual-wielding (`Off_hand_max > 0`) (*Dual Wield Mastery*).
  - `STAT_cbt_damage_done_modifier_fixed`: adds flat damage bonuses to `modifiers['flat_damage']`.
- Wired target damage received conditional modifier in `handle_target_debuffs`:
  - `STAT_cbt_damage_received_if_target_stunned_modifier_percentage` (`223`): scales damage received while target is stunned (*Formless Phantom*, *Hitman*, *Intangible Spirit*).
- Added dedicated test suite `tests/test_target_state_modifiers.py` (6 unit tests, all passing).
- Updated `tools/catalog_game_data.py` and regenerated `data/catalog_summary.md`: all 18 occurrences marked **Implemented**.
- Full test suite: 50 unit tests passing with zero errors.
### 30. Objective Classification of Modifiers & Talent Enum Extraction (`src/extractor/talents.py`, `src/swtorsim/modifiers.py`, `tests/test_modifier_percentages.py`) - [DONE]
- Updated `_parse_stat_change` in `src/extractor/talents.py` to preserve `talStatInfoStatEnumType` as `enum_type` independently of `talStatInfoStatValue`.
- Re-parsed all 616 talent JSON files across both `data/extractor/parsed/tal/` and `../data/parsed/tal/` to embed objective enum types (`modStatType_PercentOfBase`, `modStatType_PercentOfCurrent`).
- Eliminated all string substring heuristics (`"percentage" in ...`), hardcoded stat-ID branches (`64`, `68`, `69`), and `-1.0 < val < 1.0` value-range guessing in `src/swtorsim/modifiers.py`.
- Verified via `tests/test_modifier_percentages.py` (5 tests, 0 errors).

### 31. Category C: Resource Cost Modifiers (`src/swtorsim/entities.py`, `tests/test_resource_costs.py`) - [DONE]
- Wired Action Points (`70`, `STAT_abl_cost_action_points`) alongside Force (`68`, `STAT_abl_cost_force`) and Energy (`69`, `STAT_abl_cost_energy`) in `Player.calculate_resource_cost`.
- Ensured cost calculations safely clamp to minimum `0.0`.
- Added dedicated unit test suite `tests/test_resource_costs.py` covering flat and percentage reductions across Force, Energy, and Action Points (7 unit tests, all passing).

### 32. Category B: Cast Time, Channel Time, GCD & Deferred Cast Execution (`src/swtorsim/entities.py`, `src/swtorsim/abilities.py`, `src/swtorsim/events.py`, `tests/test_cast_time_modifiers.py`, `tools/catalog_game_data.py`) - [DONE]
- Initialized `active_channel`, `is_channeling`, `active_cast`, and `is_casting` directly on `Entity`.
- Added `calculate_cast_time(base_cast_time, ability)` to `Player` querying `STAT_abl_time_casting` (`62`) and scaling with Alacrity (respecting `abl_ignore_alacrity`).
- Added `calculate_channel_duration(base_duration, ability)` to `Player` querying `STAT_abl_time_channeling` (`63`) and scaling with Alacrity.
- Upgraded `calculate_gcd(base_gcd, ability)` to evaluate `STAT_abl_time_global_cooldown` (`66`), scale with Alacrity, and round up to the nearest tenth of a second (or return 0.0 if base <= 0).
- Passed `ability=self` in `Ability.apply_cooldown_locks` and wired `calculate_channel_duration` in `_start_channel`.
- Implemented deferred cast-time execution in `Ability.cast`:
  - When `act_type == "cast"` and `scaled_cast_time > 0.0`, sets `caster.active_cast = self`, `caster.is_casting = True`, and schedules `CastFinishEvent` at `sim.current_time + scaled_cast_time`.
  - On completion, `CastFinishEvent` verifies `active_cast is self.ability` (safeguarding against clipping/interruption), executes entry effects, dispatches `on_ability_post_activate`, clears `active_cast` / `is_casting`, and reschedules `PlayerReady`.
  - Interruption/clipping cleanly aborts pending casts without executing effects or dispatching triggers.
- Added dedicated unit test suite `tests/test_cast_time_modifiers.py` covering GCD, Cast Time, Channel Duration modifiers, cast lifecycle, and clipping interruption (9 unit tests, all passing).
- Updated `tools/catalog_game_data.py` with canonical stat names and regenerated `data/catalog_summary.md`.
- Full regression suite: all 66 tests passing with zero errors.
### 33. Channel-Specific Accuracy & Defense Routing (`src/swtorsim/combat_math.py`, `src/swtorsim/entities.py`, `src/swtorsim/abilities.py`, `tools/catalog_game_data.py`, `tests/test_channel_accuracy.py`) - [DONE]
- Cross-referenced authoritative Global IDs in `../Stat_IDs.xlsx` for accuracy and defense stats:
  - `STAT_cbtAccuracy` (`11`)
  - `STAT_cbt_melee_accuracy` (`114`) vs `STAT_cbt_melee_defense` (`115`)
  - `STAT_cbt_ranged_accuracy` (`120`) vs `STAT_cbt_ranged_defense` (`121`)
  - `STAT_cbt_dual_wield_accuracy_modifier_fixed` (`126`)
  - `STAT_rtg_accuracy` (`154`)
  - `STAT_cbt_force_accuracy` (`232`) vs `STAT_cbt_force_defense` (`234`)
  - `STAT_cbt_tech_accuracy` (`233`) vs `STAT_cbt_tech_defense` (`235`)
- Updated `Player.recalculate_stats` in `entities.py` to calculate base channel accuracies (`Melee Accuracy`, `Ranged Accuracy`, `Force Accuracy`, `Tech Accuracy`) from untargeted bonuses.
- Upgraded `accuracy_roll` in `src/swtorsim/combat_math.py`:
  - Dynamically evaluates channel-specific accuracy stats against target defense/resistance.
  - Accounts for 10% base defense on Melee/Ranged vs 0% base resistance on Force/Tech.
  - Handles dynamic and ability-targeted accuracy modifiers on caster, off-hand penalty, and target defense modifiers.
  - Guarantees 100% hit chance when `hit_chance >= 1.0` (eliminating miss RNG for accurate hits).
- Updated `abilities.py:handle_damage_action` to pass `hand`, `attack_type`, `ability_fqn`, `action_tags`, and `target` to `accuracy_roll`.
- Added dedicated unit test suite `tests/test_channel_accuracy.py` verifying channel isolation, defense counteraction, and ability-targeted buffs (6 unit tests, all passing).
- Updated `tools/catalog_game_data.py` with canonical stat names and regenerated `data/catalog_summary.md` (all 92 channel accuracy occurrences marked **Implemented**).
- Full regression suite: all 72 tests passing with zero errors.
### 34. Channel & Damage-Type Scaling Modifiers (`src/swtorsim/combat_math.py`, `tools/catalog_game_data.py`, `tests/test_scaling_modifiers.py`) - [DONE]
- Cross-referenced authoritative Global IDs in `../Stat_IDs.xlsx` for channel/attack type, damage type, and tag scaling modifiers:
  - Channel Damage Dealt: Melee (`407`), Ranged (`405`), Force (`409`, `451`), Tech (`411`, `449`), Weapon (`462`, `450`).
  - Damage Type Dealt: Kinetic (`397`), Energy (`395`), Elemental (`393`), Internal (`399`).
  - Tag-Specific Dealt: AoE (`464`, `454`), DoT (`466`).
  - Fixed Channel Dealt: Melee (`408`), Ranged (`406`), Force (`410`), Tech (`412`).
  - Channel Vulnerabilities: Force (`386`, `456`), Tech (`388`, `459`), Melee (`384`, `458`), Ranged (`382`, `458`), Weapon (`463`).
  - Damage Type Vulnerabilities: Kinetic (`374`), Energy (`372`), Elemental (`370`), Internal (`376`).
  - Tag Vulnerabilities: AoE (`465`, `460`), DoT (`467`).
- Upgraded `handle_caster_buffs` in `src/swtorsim/combat_math.py` to route channel, damage-type, tag-specific, and fixed flat damage modifiers into `buckets['normal_percentage']` and `modifiers['flat_damage']`.
- Upgraded `handle_target_debuffs` in `src/swtorsim/combat_math.py` with full numeric ID support across all vulnerability channels and tags.
- Added dedicated unit test suite `tests/test_scaling_modifiers.py` verifying channel damage dealt, damage type scaling (e.g. *High Energy Cell*), target vulnerabilities (e.g. *Incendiary Round*, *Shrap Bomb*), and tag scaling (7 unit tests, all passing).
- Updated `tools/catalog_game_data.py` with canonical stat names and regenerated `data/catalog_summary.md` (105 scaling stat occurrences marked **Implemented**).
- Full regression suite: all 79 tests passing with zero errors.


### 35. Multiplicative Damage Bucket Discernment & Table-Driven Dispatch Refactoring - [DONE - INITIAL SEPARATION]
- Implemented high-performance table-driven dispatcher dictionary in `src/swtorsim/combat_math.py`:
  - `_CASTER_DAMAGE_DISPATCH`: maps 61 stat IDs/names to `(bucket_key, filter_fn)`.
  - `_CRIT_CHANCE_DISPATCH`: maps 9 stat IDs to channel filters.
  - `_CRIT_DAMAGE_DISPATCH`: maps 9 stat IDs to channel filters.
  - `_SKIP_BASE_STATS`: $O(1)$ set lookup skipping untargeted character attributes handled in `recalculate_stats`.
- Separated damage multipliers into 6 independent orthogonal buckets:
  1. `normal_percentage`: Confirmed additive base pool (Caster General Damage Done + Target Vulnerabilities).
  2. `channel_scaling`: Attack Channel damage dealt (Melee, Ranged, Force, Tech, Weapon).
  3. `damage_type_scaling`: Damage Type scaling (Kinetic, Energy, Elemental, Internal).
  4. `tag_scaling`: Tag-specific scaling (AoE, DoT).
  5. `target_state`: Target state conditionals (Bleed, Fire, Accuracy Reduced, Dual Wield).
  6. `sub_30`: Confirmed independent execute phase multiplier ($<30\%$ HP).
- Verified independent multiplicative compounding: $(1 + 	ext{base}) 	imes (1 + 	ext{channel}) 	imes (1 + 	ext{target\_state}) 	imes \dots$.
- 4 legacy unit assertions in `test_target_state_modifiers.py` that expected target-state bonuses in `normal_percentage` fail as predicted, awaiting live log calibration.
- **Current State**: General percentage bonuses, channel scaling, and target vulnerabilities currently route into `buckets["normal_percentage"]`, while low-health execute is isolated in `buckets["sub_30"]`.
- **Mechanics Note**: SWTOR does not combine all percentage damage increases into a single additive pool.
  - Confirmed bucket 1: General damage done (`STAT_cbt_damage_done_modifier_percentage`, ID `79`) and target debuffs/vulnerabilities share the same additive bucket.
  - Confirmed bucket 2: Low-health execute (`STAT_cbt_damage_done_if_target_health_low_modifier_percentage`, ID `220` / `sub_30`) is an independent multiplicative bucket multiplying total damage.
  - Remaining buckets: Other categories (such as combat stances, attack-channel scalers, damage-type scalers, and tag-specific bonuses) must be isolated into their respective distinct multiplicative buckets.
- **Action Plan (Post-Implementation Roadmap)**:
  1. Complete implementation and cataloging of all remaining modifiers, conditions, and actions across the engine first.
  2. Discern the exact bucket boundaries through combat log analysis and game formula verification.
  3. Refactor `handle_caster_buffs` and `handle_target_debuffs` from linear `if/elif` chains into a high-performance table-driven dispatcher dictionary mapping stat IDs to target bucket keys and evaluation handlers.


### 36. Conditional Stat Modifier Actions (`src/swtorsim/modifiers.py`, `src/swtorsim/effects.py`, `src/swtorsim/combat_math.py`, `tools/catalog_game_data.py`, `tests/test_conditional_stat_mods.py`) - [DONE]
- Implemented and wired extracted action types `apply_conditional_meta_stat_mod` (44 occurrences) and `apply_conditional_stat_mod` (8 occurrences).
- Enhanced `Modifier.from_conditional_stat_mod` and `ActiveEffect.get_effective_modifiers` to preserve `actor` (`3` = target, `1` = caster) and `require_owner` (`require_conditional_tag_applied_by_owner`).
- Upgraded `handle_caster_buffs`, `handle_target_debuffs`, and `accuracy_roll` in `combat_math.py` to evaluate conditional tags on target or caster, verifying ownership when required.
- Added dedicated test suite `tests/test_conditional_stat_mods.py` covering Saboteur (*Aim Assist*, *Shocking Blast*), Concealment (*Crippling Wounds*), self-buff conditions, and conditional accuracy rolls (5 tests, all passing).
- Added `apply_conditional_meta_stat_mod` and `apply_conditional_stat_mod` to `IMPLEMENTED_ACTIONS` in `tools/catalog_game_data.py` and regenerated `data/catalog_summary.md` (all 52 occurrences marked **Implemented**).
- Full regression suite: all 84 tests passing with zero errors.


### 37. Ability & Effect Charge Modifiers (`src/swtorsim/entities.py`, `src/swtorsim/abilities.py`, `src/swtorsim/effects.py`, `src/swtorsim/setup.py`, `tools/catalog_game_data.py`, `tests/test_charge_modifiers.py`) - [DONE]
- Implemented and wired ability charge and effect stack modifiers across all 126 blueprint occurrences:
  - `stat_abl_charges_max` (ID `422`, 28 occurrences)
  - `stat_abl_charges_recharge_time` (ID `423`, 16 occurrences)
  - `STAT_eff_charges_max` (ID `61`, 55 occurrences)
  - `STAT_eff_charges_initial` (ID `60`, 27 occurrences)
- Added `calculate_ability_max_charges` and `calculate_recharge_time` to `Player` (`entities.py`), evaluating live passives, set bonuses, and alacrity scaling.
- Added `apply_charge_modifiers` and upgraded `schedule_recharge` on `Ability` (`abilities.py`) and wired simulation initialization in `setup.py`.
- Upgraded `ActiveEffect.from_effect` (`effects.py`) to scale `max_stacks` and `initial_stacks` based on caster passives (e.g. *Cluster Bombs*, *Ward of the Continuum*).
- Added dedicated test suite `tests/test_charge_modifiers.py` (5 tests, all passing).
- Updated `tools/catalog_game_data.py` and regenerated `data/catalog_summary.md` (all 126 occurrences marked **Implemented**).
- Full regression suite: all 89 tests passing with zero errors.


- Implemented and wired weapon base damage and resource regeneration rate modifiers across all 53 blueprint occurrences:
  - `STAT_cbt_base_weapon_damage_modifier_percentage` (ID `413`, 4 occurrences)
  - `STAT_cbt_force_force_regen_rate` (ID `140`, 16 occurrences)
  - `STAT_cbt_force_force_regen_rate_modifier_percentage` (ID `275`, 7 occurrences)
  - `STAT_cbt_tech_energy_regen_rate` (ID `142`, 8 occurrences)
  - `STAT_cbt_tech_energy_regen_rate_modifier_percentage` (ID `276`, 18 occurrences)
- Upgraded `combat_math.py`:
  - Added `'base_weapon_damage_modifier'` to `handle_modifiers` and populated in `handle_caster_buffs` from stat `413`.
  - In `calculate_base_damage`, scaled weapon damage (`weapon_min` / `weapon_max`) by `(1.0 + weapon_mod)` for Melee and Ranged attacks, leaving Force and Tech attacks untouched.
- Upgraded `entities.py`:
  - Added `calculate_resource_regen(base_rate, pool_type)` to `Player` evaluating flat bonuses and percentage modifiers for Force, Rage, Focus, Energy, Heat, and Ammo pools.
- Upgraded `resources.py` & `events.py`:
  - Updated `StandardPool`, `HeatPool`, and `EnergyPool` `tick_passive_regen` to query `player.calculate_resource_regen`.
  - Passed `player=self.player` from `ResourceTick.resolve`.
- Added dedicated unit test suite `tests/test_weapon_damage_and_regen.py` covering *Single Saber Mastery*, Force regen buffs, *Stim Boost*, *Sniper Volley*, and `ResourceTick` events (5 tests, all passing).
- Added all 5 stats to `IMPLEMENTED_STATS` in `tools/catalog_game_data.py` and regenerated `data/catalog_summary.md`.
- Full regression suite: all 94 tests passing with zero errors.


### 39. Trigger Scaling, Effect Duration/Tick, and Action Resource Gain Modifiers (`triggers.py`, `entities.py`, `abilities.py`, `modifiers.py`, `tools/catalog_game_data.py`, `tests/test_all_three_modifiers.py`) - [DONE]
- Implemented and wired all 3 modifier groups (142 occurrences across the blueprint database):
  1. **Trigger Scaling (18 occurrences)**:
     - `STAT_eff_trigger_proc_chance_percent_modifier_fixed` (ID `228`, 14 occurrences): Modifies trigger proc chance in `TriggerManager.dispatch` (e.g. *Massacre*, *Superheated Gas*, *Overcharge Saber*).
     - `STAT_eff_trigger_rate_limit_modifier_fixed` (ID `229`, 4 occurrences): Modifies internal cooldown rate limit of triggers in `TriggerManager.dispatch` (e.g. *Sweeping Fury*, *Probe Medic*).
  2. **Effect Duration & Tick Rate (120 occurrences)**:
     - `STAT_eff_time_duration` (ID `44`, 98 occurrences): Added `Player.calculate_effect_duration` and wired into `Entity.apply_effect` to scale active DoT/buff durations (e.g. *Lingering Nightmares*, *Lethal Injectors*, *Open Wound*).
     - `STAT_eff_time_tick` (ID `45`, 22 occurrences): Added `Player.calculate_effect_tick` and wired into `Entity.apply_effect` to accelerate periodic tick rates and recalculate total ticks (e.g. *Lightning Barrage*).
  3. **Action Resource Restoration Scaling (4 occurrences)**:
     - `STAT_eff_action_restore_action_points_modifier_percentage` (ID `91`, 2 occurrences) & `STAT_eff_action_restore_action_points_modifier_fixed` (ID `90`): Scales Focus/Rage generated by actions in `handle_resource_gain_action` (e.g. *Blood Rites*, *Searing Meditation*).
     - `STAT_eff_action_restore_force_modifier_percentage` (ID `93`, 2 occurrences) & `STAT_eff_action_restore_force_modifier_fixed` (ID `92`): Scales Force restored by actions (e.g. *Lightning Recovery*).
     - `STAT_eff_action_restore_energy_modifier_percentage` (ID `95`) & `STAT_eff_action_restore_energy_modifier_fixed` (ID `94`): Scales Energy restored by actions.
- Enhanced `Modifier.applies_to` to accept any iterable for `targets` without `isdisjoint` AttributeError.
- Added dedicated test suite `tests/test_all_three_modifiers.py` (4 tests, all passing).
- Added all 10 stats to `IMPLEMENTED_STATS` in `tools/catalog_game_data.py` and regenerated `data/catalog_summary.md`.
- Full regression suite: all 98 tests passing with zero errors.

### 40. Active Alacrity & Activation Time Reductions (`entities.py`, `tools/catalog_game_data.py`, `tests/test_all_three_modifiers.py`) - [DONE]
- Implemented and wired active Alacrity / haste burst modifiers across all 78 blueprint occurrences:
  - `STAT_cbt_spell_casting_reduction_percentage` (ID `256`, 26 occurrences)
  - `STAT_cbt_spell_channeling_reduction_percentage` (ID `257`, 26 occurrences)
  - `stat_cbt_instant_reduction_percentage` (ID `274`, 26 occurrences)
- These represent active haste/alacrity burst buffs (*Polarity Shift*, *Mental Alacrity*, *Stim Boost*, *Burst Volley*, *Supercharged Celerity*, *Zen / Berserk*) and debuffs (*Electro Net*).
- Upgraded `calculate_gcd`, `calculate_cast_time`, and `calculate_channel_duration` in `Player` (`entities.py`):
  - Properly applies `pct_mod -= (val / 100.0 if abs(val) > 1.0 else val)` for targeted and untargeted haste modifiers.
  - Hardened `scaled_gcd = math.ceil(round(gcd * 10, 6)) / 10` to avoid IEEE-754 floating point boundary rounding errors (e.g. `12.000000000000002` bumping 1.2s to 1.3s).
- Added unit tests in `tests/test_all_three_modifiers.py`:
  - `test_active_alacrity_reduction_trio_scaling` validating cast time reduction (2.0s -> 1.6s), channel duration reduction (3.0s -> 2.4s), and GCD reduction (1.5s -> 1.2s), numeric IDs (256, 257, 274), and ability-targeted reductions.
- Added all 3 stats to `IMPLEMENTED_STATS` in `tools/catalog_game_data.py` and regenerated `data/catalog_summary.md` (all 78 occurrences marked **Implemented**).
- Full regression suite: all 103 tests passing with zero errors.

### 41. Alacrity Rating Consumable & Relic Scaling (`STAT_rtg_spell_haste`, ID `255`) (`entities.py`, `combat_math.py`, `tools/catalog_game_data.py`, `tests/test_all_three_modifiers.py`) - [DONE]
- Implemented and wired `STAT_rtg_spell_haste` (ID `255`, 3 occurrences) across all consumable and relic blueprints (*Advanced Kyrprax Alacrity Adrenal*, *Primeval Fatesealer Relic*, *All for One* tactical).
- Mapped to `"Alacrity Rating"` bucket in `Player.recalculate_stats` (`entities.py`) and marked as handled in `combat_math.py`.
- Correctly adds flat Alacrity Rating points, feeding into the non-linear diminishing returns curve (`calc_dr` in `combat_curves.py`) to recalculate character Alacrity percentage and CDR.
- Added unit test `test_stat_rtg_spell_haste_recalculation` to `tests/test_all_three_modifiers.py` verifying flat stacking and DR curve calculation.
- Updated `tools/catalog_game_data.py` and regenerated `data/catalog_summary.md` (marked **Implemented**).
- Full regression suite: all 104 tests passing with zero errors.

### 42. Conditions Catalog 100% Completion (`requirements.py`, `entities.py`, `tools/catalog_game_data.py`, `tests/test_final_conditions.py`) - [DONE]
- Implemented and validated the final 8 condition types across all extracted blueprints, reaching 100% completion (36 of 36 condition types) in the Conditions Catalog:
  1. `if_caster_positioning` (2 occurrences: *Maul* and *Shadow Strike* rear 180-degree positional check behind target): Checks `caster.is_behind_target`, context overrides, or defaults to `True` for dummy/boss DPS simulation.
  2. `is_class` (28 occurrences: character base class validation): Validates player character class against `actor.ability_db` / `actor.character_class`, supporting specific class filters when specified.
  3. `is_creature_type` (4 occurrences: droid vs organic target checks): Validates target creature type (Droid = 3 vs Organic = 1 / Humanoid), respecting `target.is_droid` and `target.creature_type` (e.g. *Sleep Dart* organic-only gating and *Dirty Kick* droid branching).
  4. `if_weapon_mode` (2 occurrences: *Trishin's Retort*): Validates weapon mode (1 = single/primary weapon, 2 = dual-wield/secondary weapon) derived from equipped weapons (`Off_hand_max > 0`) or execution context.
  5. `if_faction` (2 occurrences: *Companion Buff Controller*): Validates character faction (*Empire* vs *Republic*).
  6. `is_not_stealthed` (1 occurrence: *Companion Follow*): Validates that actor is unstealthed, checking both `actor.is_stealthed` and active stealth effects. Also wired `is_stealthed`.
  7. `is_mounted` (1 occurrence: *Sprint*): Validates vehicle mount state (`actor.is_mounted`), honoring negation.
  8. `if_result` (1 occurrence: *Smuggler Dirty Kick*): Validates previous combat hit/action success from execution context (`context["result"]`, `context["is_hit"]`, `not context["missed"]`).
- Added properties to `Player` and `Dummy` in `src/swtorsim/entities.py`: `creature_type`, `is_droid`, `is_stealthed`, `is_mounted`, `is_behind_target`, `character_class`, and `faction`.
- Added all 8 condition types to `IMPLEMENTED_CONDITIONS` in `tools/catalog_game_data.py` and regenerated `data/catalog_summary.md` (all 36 conditions now marked **Implemented**).
- Added dedicated unit test suite `tests/test_final_conditions.py` (8 tests covering all 8 conditions against real parsed blueprints and edge cases, all passing).
- Created authoritative engine documentation file `ENGINE_RULES.md` defining the 9 core simulation rules and operational protocols.
- Full regression suite: all 112 tests passing with zero errors.

### 43. Target-Context Resolution & Combat Stealth Break Pipeline (`abilities.py`, `entities.py`, `events.py`, `requirements.py`, `tests/test_final_conditions.py`) - [DONE]
- **Creature Type Targeting Alignment**: Updated `Ability.can_cast` in `src/swtorsim/abilities.py` to evaluate non-aggressive abilities against `caster` (`ability_target = target if is_aggressive else caster`), mirroring `Ability.cast`. Hardened `requirements.py` so self-posture abilities (*Take Cover*) are not erroneously blocked when fighting Droid targets.
- **Combat Stealth Break Pipeline**: Added `Player.break_stealth(sim)` in `src/swtorsim/entities.py`, automatically clearing `is_stealthed = False` and removing non-combat-stealth buffs while preserving active combat-stealth windows (*Force Camouflage*, *Cloaking Screen*). Wired into aggressive `Ability.cast` and direct `DamageHit.resolve`.
- **Unit Test Coverage**: Expanded `tests/test_final_conditions.py` with tests for *Take Cover* against Droid dummies, manual and automatic `break_stealth` calls on aggressive ability casts, and combat-stealth window preservation.
- Full regression suite: all 112 tests passing with zero errors.

### 44. Tactical Item Fix: Quick Escalation / Hungering Blade (`src/extractor/abilities.py`, `src/swtorsim/abilities.py`, `tests/test_quick_escalation_tactical.py`) - [DONE]
- **Extractor False-Positive Branch Pruning Fix**: Fixed `_is_redundant_self_aoe_branch` in `src/extractor/abilities.py` which had erroneously pruned Sub-effect 1 of Effect 2 and Effect 3 in `dps_burst_01.json` (Quick Escalation / Hungering Blade).
  - Ensured branches containing executable actions (`effActions`) or stack count thresholds (`effParam_Count > 1`) are never treated as redundant self-damage AoE branches.
  - Re-exported `data/extractor/parsed/abl/itm/tactical/sow/inq_con/sin_shad/hat_sen/dps_burst_01.json` restoring Branch 2 with `modify_cooldown: -100%` and `modify_meta_stat: +0.25` on Leeching Strike / Serenity Strike.
- **Lifecycle Trigger Stack-Count Matching**: Updated `Effect.execute_triggered_branches` in `src/swtorsim/abilities.py` to match `t.get("ints", {}).get("count")` or `t.get("count")` on `on_stack_charge_increased` and `on_stack_charge_decreased`. Prevents premature removal of the buff before reaching 4 stacks.
- **Unit Test Coverage**: Added `tests/test_quick_escalation_tactical.py` verifying passive 25% crit bonus, 3 consecutive Leeching Strike cooldown resets with scaling crit bonus (+50%, +75%, +100%), and automatic buff removal at 4 stacks.
- Full regression suite: all 114 tests passing with zero errors.

### 45. Actions Catalog Registration Alignment: `regen_force` & `regen_energy` (`tools/catalog_game_data.py`, `data/catalog_summary.md`) - [DONE]
- Added `regen_force` and `regen_energy` to `IMPLEMENTED_ACTIONS` in `tools/catalog_game_data.py`. Both actions are already fully functional in runtime via `handle_resource_gain_action` (`src/swtorsim/abilities.py`), supporting `amount_percent_of_max`.
- Re-ran `tools/catalog_game_data.py` via `pyclean.exe` to regenerate `data/catalog_summary.md`, completely eliminating all `⚠️ Unhandled` entries across all 59 action types (18 implemented, 41 stubs/no-ops, 0 unhandled).
- Full regression suite: all 114 tests passing with zero errors.

### 46. Projectile Flight Time & Combat Distance Architecture: `invoke_projectile` (`settings.py`, `events.py`, `entities.py`, `abilities.py`, `run_config.py`, `tools/catalog_game_data.py`, `tests/test_invoke_projectile.py`) - [DONE]
- Implemented `invoke_projectile` (161 occurrences) and unified it with the `on_travel_complete` lifecycle trigger:
  - Flight time formula: `time_to_hit = distance in meters / (travel_speed * 10.0)`.
  - Added configurable combat distance (`combat_distance: float = 30.0`) on `Player`, `Dummy`, and `RunConfig`.
  - Added global settings toggles in `settings.py`: `enable_projectile_flight_time` (default `False` for deterministic rotation testing, with flight-time delay available on demand) and `default_combat_distance`.
  - Created `ProjectileImpactEvent` in `src/swtorsim/events.py`, which schedules delayed impact at `sim.current_time + time_to_hit` and triggers `effect.execute_triggered_branches("on_travel_complete")`. When flight time is disabled or distance is 0m, impacts resolve immediately on the same tick.
  - Linked parent `effect` context throughout `Effect.execute_triggered_branches` and `Effect.schedule_timer_branches`.
- Removed `invoke_projectile` from `NOOP_ACTION_TYPES` and added it to `IMPLEMENTED_ACTIONS` in `tools/catalog_game_data.py`.
- Re-ran `tools/catalog_game_data.py` via `pyclean.exe` to regenerate `data/catalog_summary.md` (now 19 implemented action types).
- Added dedicated test suite `tests/test_invoke_projectile.py` (4 tests covering instant impacts, 30m / 4.0 speed delay, 10m / 4.0 speed delay, and point-blank 0m overrides).
- Full regression suite: all 118 tests passing with zero errors.

### 47. Effect Expiration & DoT Refresh: 
eset_timer (bilities.py, effects.py, entities.py, 
equirements.py, 	ools/catalog_game_data.py, 	ests/test_reset_timer.py) - [DONE]
- Implemented 
eset_timer (24 blueprint occurrences), enabling dynamic duration refreshing for both offensive DoTs and defensive buffs:
  - Added handle_reset_timer in src/swtorsim/abilities.py resolving target effect instances from 	arget.effects or caster.effects, targeting both direct name matches (e.g. Corrosive Dart) and sub-effect keys (e.g. Corrosive Dart:2, Cloak of Pain:1).
  - Added duration: float = 0.0 attribute to ActiveEffect (src/swtorsim/effects.py), preserving base effect duration across constructors (rom_effect, rom_effect_node, rom_stat_changes).
  - Re-anchored effect expiration time: ctive_eff.expires_at = current_time + active_eff.duration.
  - Automatically reschedules existing EffectExpire events in simulation priority queue to match the new expiration timestamp.
  - Added is_player: bool and immune_by_resolve: bool explicitly to Entity, Player, and Dummy in src/swtorsim/entities.py, standardizing character identity checks without relying on brittle attribute duck-typing in 
equirements.py.
- Moved 
eset_timer from NOOP_ACTION_TYPES to IMPLEMENTED_ACTIONS in 	ools/catalog_game_data.py.
- Regenerated data/catalog_summary.md (now 20 implemented action types, 39 stubs/no-ops, 0 unhandled).
- Added dedicated test suite 	ests/test_reset_timer.py (4 tests validating Corrosive Dart DoT refresh via Corrosive Followthrough, Cloak of Pain buff refresh on critical hit, Shatter refresh via Hemophilic Slash tactical, and safe no-op handling).
- Full regression suite: all 122 tests passing with zero errors.

### 48. Active Effect Duration Modification: modify_active_duration (extractor/abilities.py, bilities.py, 	ools/catalog_game_data.py, 	ests/test_modify_active_duration.py) - [DONE]
- Implemented modify_active_duration (20 blueprint occurrences across 18 abilities/tacticals/set bonuses):
  - Extractor Fix: Updated _decode_action in src/extractor/abilities.py to extract params['time_interval']. Decodes effTimeIntervalParams key 18 into seconds (duration = ms / 1000.0). Re-exported all affected blueprint files.
  - Runtime Implementation: Added handle_modify_active_duration in src/swtorsim/abilities.py. Supports target actor selection (ctor == 1 for caster/self, ctor == 2 for target), matches active effects by ction['tags'] (or context owner if tags empty), modifies ctive_eff.expires_at += duration_delta, and reschedules EffectExpire in the simulation priority queue.
- Moved modify_active_duration from NOOP_ACTION_TYPES to IMPLEMENTED_ACTIONS in 	ools/catalog_game_data.py.
- Regenerated data/catalog_summary.md (now 21 implemented action types, 38 stubs/no-ops, 0 unhandled).
- Added dedicated test suite 	ests/test_modify_active_duration.py (5 tests covering Systems Upgrade +10.0s extension via Adrenaline Probe, Indomitable tactical +5.0s on Invincible, Projected Shroud +2.0s on Force Shroud, target actor selection e.g. Taunt debuff +3.0s, and safety edge cases).
- Full regression suite: all 127 tests passing with zero errors.

### 49. Cover, Stealth & Combat State Lifecycle: 	ake_cover, 	ake_portable_cover, leave_cover, ecome_stealthed, enter_combat, exit_combat (entities.py, bilities.py, 
equirements.py, 	ools/catalog_game_data.py, 	ests/test_cover_and_stealth.py) - [DONE]
- Implemented 6 core combat state lifecycle action types (35 blueprint occurrences across the game):
  - State Attributes on Entities (src/swtorsim/entities.py): Added is_in_cover: bool, is_in_portable_cover: bool, is_stealthed: bool, and in_combat: bool across Entity, Player, and Dummy. Set Player.creature_type = 4 (player character).
  - Runtime Action Handlers (src/swtorsim/abilities.py): Added handle_take_cover (setting is_in_cover = True), handle_leave_cover (clearing cover flags), handle_become_stealthed (setting is_stealthed = True), handle_enter_combat (in_combat = True), and handle_exit_combat (in_combat = False).
  - Condition Evaluation Wiring (src/swtorsim/requirements.py): Dynamically bound is_in_cover and is_not_in_cover conditions to ctor.is_in_cover. Handled is_creature_type: 4 (matching player character). Resolved passes_conditional for cnd.global.is_in_flashpoint_operation (allowing combat-drop vanishes outside raid instances).
- Moved all 6 action types from NOOP_ACTION_TYPES to IMPLEMENTED_ACTIONS in 	ools/catalog_game_data.py.
- Regenerated data/catalog_summary.md (now 28 implemented action types, 31 stubs/no-ops, 0 unhandled).
- Added dedicated test suite 	ests/test_cover_and_stealth.py (6 tests validating Take Cover, Crouch/portable cover, Leave Cover, Stealth activation, Cloaking Screen combat drop, Enter Combat, and condition validation).
- Full regression suite: all 133 tests passing with zero errors.


### 50. Ability Lifecycle & Channel Clipping Actions: `ability_cancel`, `cooldown`, `global_cooldown` (`abilities.py`, `tools/catalog_game_data.py`, `tests/test_ability_lifecycle_actions.py`) - [DONE]
- Implemented 3 ability lifecycle and lockout action types (67 blueprint occurrences across the game):
  - `ability_cancel` (41 blueprint occurrences): Immediately terminates an active channeled ability (`active_channel.is_finished = True`, `active_channel = None`, `is_channeling = False`) or cancels an active hard cast (`active_cast = None`, `is_casting = False`). Used in abilities like *Series of Shots*, *Suppressive Fire*, *Deadly Onslaught*, and *Forcequake* when resource thresholds fail mid-channel.
  - `cooldown` (24 blueprint occurrences): Triggers an ability cooldown lockout. Resolves ability reference from context or `ints["ability_spec"]`, evaluates duration from blueprint or explicit `floats["duration"]`, respects `bools["ignore_alacrity"]` (skipping alacrity compression for unscaled timers), and locks `caster.cooldowns[name]` in the simulation. Used on ability expiration/removal in *Kolto Overload*, *Shoulder Cannon*, *Hololocate*, and *Jet Charge*.
  - `global_cooldown` (2 blueprint occurrences): Advances `caster.next_gcd` scaled by alacrity CDR (`base_gcd` default 1.5s). Used in abilities like *Take Cover* / *Crouch*.
- Moved `ability_cancel`, `cooldown`, and `global_cooldown` from `NOOP_ACTION_TYPES` to `IMPLEMENTED_ACTIONS` in `tools/catalog_game_data.py`.
- Regenerated `data/catalog_summary.md` (now 31 implemented action types, 28 stubs/no-ops, 0 unhandled).
- Added dedicated test suite `tests/test_ability_lifecycle_actions.py` (6 tests covering channel clipping, cast canceling, alacrity-respecting cooldowns, alacrity-ignoring cooldowns, custom cooldown durations, and global cooldown lockouts).
- Full regression suite: all 139 tests passing with zero errors (100% pass rate).


### 51. Channel Resource & Clipping Architecture Cleanup: Removed Legacy `tick_cost` & Connected `ability_cancel` (`events.py`, `abilities.py`, `tests/test_ability_lifecycle_actions.py`) - [DONE]
- Removed legacy prototype `tick_cost` resource spending/abort block from `ChannelTickEvent.resolve` in `src/swtorsim/events.py`.
- Connected authentic SWTOR blueprint channel lifecycle:
  - Channeled abilities in game data natively use internal branches with `spend_energy` / `spend_force` on `on_tick`, paired with `ability_cancel` conditioned on resource thresholds (`has_specified_resource_amount: lt <threshold>`).
  - Added mid-tick and `on_apply` clipping detection: if `ability_cancel` fires during tick or apply execution, `self.channel.is_finished` halts further `ChannelTickEvent` scheduling and immediately dispatches `PlayerReady` to return the actor to the rotation.
- Added comprehensive unit test in `tests/test_ability_lifecycle_actions.py` (`test_channel_clipping_via_ability_cancel_on_low_resource`) verifying channel termination and resource preservation when energy drops below minimum.
- Full regression suite: all 140 tests passing with zero errors (100% pass rate).


### 52. Engine Custom Action Invoker & Blueprint Extraction: `custom` (`src/swtorsim/abilities.py`, `src/extractor/abilities.py`, `tools/catalog_game_data.py`, `tests/test_custom_ability_invoker.py`) - [DONE]
- Implemented handler for `custom` action types (`handle_custom_action`) in `src/swtorsim/abilities.py` (129 blueprint occurrences):
  - BioWare Programmatic Ability Trigger Hook (`param1: 6855115466292073041`): Used by *Force Cloak* (*Sith Inquisitor* / *Jedi Consular*), *Cloaking Screen* (*Imperial Agent*), *Disappearing Act* (*Smuggler*), and legacy *Shoulder Cannon* (*Bounty Hunter* / *Trooper*) to programmatically invoke secondary root abilities (e.g., triggering `stealth` outside of Operations).
  - Strict Ability Database Lookup: Strictly checks `caster.ability_db.get(spec)` without heuristic or fuzzy-matching fallbacks (Rule 2).
  - Graceful Fallback: Safely no-ops for unrecognized `param1` hooks or abilities not present in `caster.ability_db`.
  - Intentionally kept `ability_activate`, `ability_deactivate`, and `set_posture` as No-Ops / Stubs (GUI quickbar toggle state controllers and visual 3D animation postures without combat mechanics).
- Fixed Blueprint Extractor (`src/extractor/abilities.py`):
  - Updated `_decode_generic_ints` to preserve string FQN ability specs stored by BioWare in `effIntParams` (e.g. `param2` containing `abl.sith_inquisitor.stealth`).
  - Re-exported parsed blueprints for `force_cloak`, `cloaking_screen`, `disappearing_act`, and `shoulder_cannon`.
- Catalog Update:
  - Added `"custom"` to `IMPLEMENTED_ACTIONS` in `tools/catalog_game_data.py`.
  - Regenerated `data/catalog_summary.md` (now 32 implemented actions, 27 no-op/stubs, 0 unhandled).
- Test Coverage:
  - Added `tests/test_custom_ability_invoker.py` (4 tests verifying out-of-operation Force Cloak stealth invocation, in-operation direct stealth bypass, strict `ability_db` lookup safety, and unhandled hook no-ops).
  - Full regression suite: all 145 tests passing with zero errors (100% pass rate).


### 53. Encounter Context Configuration: `in_flashpoint_operation` (`settings.py`, `run_config.py`, `engine.py`, `requirements.py`, `tests/test_custom_ability_invoker.py`) - [DONE]
- Exposed `in_flashpoint_operation` configuration toggle across the simulator stack:
  - Global Settings (`src/swtorsim/settings.py`): Added `IN_FLASHPOINT_OPERATION`, `set_in_flashpoint_operation(bool)`, and `is_in_flashpoint_operation()`.
  - Run Configuration (`src/swtorsim/run_config.py`): Added `in_flashpoint_operation: bool = True` to `RunConfig` dataclass and `load_run_config()` (defaulting to `True` so the simulator operates in an Operation encounter by default).
  - Simulation Engine (`src/swtorsim/engine.py`): `Simulation.__init__` accepts `in_flashpoint_operation` and initializes `self.in_flashpoint_operation` from global settings (`True` by default).
  - Requirement Evaluator (`src/swtorsim/requirements.py`): Updated `passes_conditional` to resolve `in_flashpoint_operation` following a clean hierarchy: `context` -> `sim` instance -> `actor`/`caster` instance -> global `settings`.
- Test Coverage:
  - Added unit tests in `tests/test_custom_ability_invoker.py` and `tests/test_cover_and_stealth.py` validating both operation combat preservation (default) and solo combat drop.
  - Full regression suite: all 148 tests passing with zero errors (100% pass rate).


### 54. Target Immunity & Branch Execution Mechanics: `grant_immunity` (`entities.py`, `effects.py`, `abilities.py`, `tools/catalog_game_data.py`, `tests/test_grant_immunity.py`) - [DONE]
- Implemented `grant_immunity` action handling across the combat engine (108 blueprint occurrences across 78 abilities):
  - Action Registration (`src/swtorsim/abilities.py`): Added `handle_grant_immunity` mapping granted immunity tags (e.g., `tag.abl.debuff.interrupt`, `tag.abl.debuff.root`, `tag.abl.debuff.snare`, `tag.abl.debuff.physics`, `damage_over_time`) onto the target entity or attaching them directly to the active effect lifecycle.
  - Active Effect Tracking (`src/swtorsim/effects.py`): Added `immunities: set[str]` to `ActiveEffect` dataclass so temporary immunities granted alongside duration/aura buffs automatically expire when the effect falls off or is cleansed.
  - Entity Immunity System (`src/swtorsim/entities.py`):
    - Added `_base_immunities: set[str]` and dynamic `immunities` property aggregating base entity immunities with all active effects' immunity sets.
    - Added `has_immunity(tag: str) -> bool` and `is_immune_to_effect(effect) -> bool` matching against effect tags (e.g., matching root, snare, interrupt, dot tags).
    - Added `interrupt(sim=None) -> bool` to `Entity`, preventing cast and channel interruption when `tag.abl.debuff.interrupt` immunity is present.
- Authentic Branch Execution vs Hit-Gating Semantics:
  - Preserved attack miss gating: Missed direct attacks fail the primary damage action, properly aborting subsequent actions in the branch (e.g., DoT application or secondary debuffs conditioned on the attack landing).
  - Immunity Resistance Isolation: When an effect is resisted due to target immunity (`is_immune_to_effect`), `Effect.execute` cleanly drops only the resisted effect without aborting downstream actions in the branch (e.g. resource refunds, secondary buffs, or companion strikes).
- Catalog & Summary:
  - Moved `"grant_immunity"` from `NOOP_ACTION_TYPES` to `IMPLEMENTED_ACTIONS` in `tools/catalog_game_data.py`.
  - Regenerated `data/catalog_summary.md` (33 implemented actions, 26 no-op/stubs, 0 unhandled).
- Test Coverage:
  - Added `tests/test_grant_immunity.py` with 5 targeted unit tests covering effect immunity registration, immunity expiration, effect resistance without branch abortion, attack miss branch abort, and interrupt blocking.
  - Full regression suite: all 153 tests passing with zero errors (100% pass rate).


### 55. Absolute Effect Stack Assignment: `set_effect_stack_charge` (`effects.py`, `abilities.py`, `tools/catalog_game_data.py`, `tests/test_set_effect_stack_charge.py`) - [DONE]
- Implemented `set_effect_stack_charge` action handling across the combat engine (2 occurrences in game blueprints):
  - Blueprint Context: Used by *Ward of the Continuum* (*Darkness Sith Assassin* / *Kinetic Combat Jedi Shadow* tank tactical item `abl.itm.tactical.sow.inq_con.sin_shad.dark_combat.def_sust_01`) to cap remaining Dark Ward / Kinetic Ward stacks at 10 charges upon consumption or expiration.
  - Active Effect Dataclass (`src/swtorsim/effects.py`): Added `set_stacks(self, value: int)` to `ActiveEffect`, encapsulating absolute stack assignment, clamping within `[0, max_stacks]`, and auto-setting `is_expired = True` if stacks reach 0 on an effect with `max_stacks > 0`.
  - Action Handler (`src/swtorsim/abilities.py`):
    - Added `handle_set_effect_stack_charge(sim, caster, target, action, ability=None, context=None)` to parse `floats.amount` (or `amount_min`/`amount_max`/`value`), resolve target effects via context, `tags`, or `ability_spec` across target and caster, and apply `eff.set_stacks(target_stacks)`.
    - Triggers `owner_entity.recalculate_stats()` if the effect has `scales_with_stacks` and modifies stats.
    - Calls `owner_entity.cleanup_expired_effects([owner_key])` if stacks reach 0.
    - Explicitly omits `on_stack_charge_increased` and `on_stack_charge_decreased` trigger dispatches per design, keeping them exclusive to relative delta adjustments (`modify_stack_charge`) and application events.
    - Removed `"set_effect_stack_charge"` from `NOOP_ACTION_TYPES` and wired into `execute_single_action`.
- Catalog & Summary:
  - Added `"set_effect_stack_charge"` to `IMPLEMENTED_ACTIONS` in `tools/catalog_game_data.py`.
  - Regenerated `data/catalog_summary.md` (34 implemented actions, 25 no-op/stubs, 0 unhandled).
- Test Coverage:
  - Added `tests/test_set_effect_stack_charge.py` with 6 unit tests validating absolute stack assignment, clamping to `max_stacks`, zero-stack expiration and cleanup, resolution by tags, stat recalculation on scaling effects, and verifying that stack increase/decrease triggers are never dispatched.
  - Full regression suite: all 159 tests passing with zero errors (100% pass rate).

### 56. Blueprint Trigger Audit, Comprehensive Wiring & Cataloging (`triggers.py`, `events.py`, `abilities.py`, `entities.py`, `tools/catalog_game_data.py`, `tests/test_all_triggers.py`) - [DONE]
- Comprehensive Blueprint Trigger Audit:
  - Scanned all 2,461 parsed SWTOR blueprint files, cataloging all 35 unique trigger types across 8,335 total trigger occurrences.
  - Categorized all 35 triggers into 23 Implemented Combat Triggers (covering 98.5% of combat blueprint branches) and 12 No-Op / Stub Triggers (healing, movement, cutscenes, mounts, inventory UI).
  - Confirmed 0 Unhandled Triggers across the entire SWTOR game data.
- Trigger Engine Wiring & Dispatch Integration:
  - `on_ability_activate`: Wired dispatch in `Ability.cast` at cast initiation prior to channel/cast/instant execution (powering procs like *Overcharged Plasma*, *Shadowcraft*, and *Dodge Stance*).
  - `on_channeling_ended`: Added execution of `on_channeling_ended` branches on ability effects and global event dispatch in `ChannelTickEvent.resolve` (channel completion with `is_successful: True`) as well as in `Ability.cast` clipping and `handle_ability_cancel` (interruption with `is_successful: False`).
  - `on_pre_damage_dealt` & `on_pre_damage_taken`: Wired dispatches in `DamageHit.resolve` immediately before `ApplyDamageLand`, providing pre-damage hit evaluation context for procs like *Winnow*, *Bouncing Eradicate*, *Active Reload*, and *Decoy* absorbs.
  - `on_pre_death`, `on_death`, & `on_kill`: Wired dispatches in `ApplyDamageLand.resolve` upon target HP reducing to `<= 0`, triggering kill resets and resource generation (*Tactical Advantage*, *Upper Hand*, *Centering*, *Fury*).
  - `on_effect_applied` & `on_effect_received`: Wired dispatches in `Entity.apply_effect` broadcasting newly applied and refreshed effects with tags, ability specs, and `include_effect_refreshes` context.
  - `on_effect_dispelled`: Wired dispatch in `handle_buff_remove_action` upon cleansing/dispelling matching active effects.
  - `on_enter_combat` & `on_exit_combat`: Wired dispatches in `handle_enter_combat` and `handle_exit_combat`.
  - `TriggerManager`: Added support for boolean trigger filters (`is_successful`, `include_effect_refreshes`) and actor matching.
- Catalog Summary Integration (`tools/catalog_game_data.py`):
  - Added `IMPLEMENTED_TRIGGERS` (23 types) and `NOOP_TRIGGERS` (12 types) to `catalog_game_data.py`.
  - Generated `## 4. Triggers Catalog` in `data/catalog_summary.md`, documenting all 35 trigger types, blueprint counts, and example blueprints.
- Test Coverage:
  - Added `tests/test_all_triggers.py` with 6 dedicated unit tests covering `on_ability_activate`, channel complete vs clipped `on_channeling_ended`, `on_pre_damage_dealt/taken`, death/kill dispatches, and effect applied/received dispatches.
  - Full regression suite: all 165 tests passing with zero errors (100% pass rate).

### 57. Local Web UI Rotation Builder & Blueprint Auto-Discovery (`data/rotation_builder.py`, `tools/rotation_builder_ui.html`, `tests/test_rotation_builder.py`) - [DONE]
- **Local Web UI & Backend (`data/rotation_builder.py`, `tools/rotation_builder_ui.html`)**:
  - Built a zero-dependency local HTTP server (`launch_web_builder`) and browser UI launched via `.\tools\pyclean.exe data\rotation_builder.py` (with `--cli` fallback for terminal prompt mode).
  - **Blueprint Auto-Discovery (`discover_loadout_catalog`)**: Automatically inspects the selected discipline, skill-tree choices (`23..73`), tactical, legendaries, relics, and sub-abilities to extract:
    - Castable active abilities (`slug`, `fqn`, `name`, `triggers_gcd`, `cooldown`, `energy_cost`, `activation_type`, `max_charges`).
    - Caster buffs & proc buffs (`Recklessness`, `Bloodletting`, `Harnessed Darkness`, `Energize`, `Conspirator's Cloak`, `Lightning Reflexes`, etc. with stack caps and durations).
    - Target debuffs & DoTs (`Creeping Terror`, `Discharge`, `Crushed (Eradicate)`, `Deathmark`, `Unsteady (Force)`, etc.).
    - Procs & internal cooldown lockouts (`Bloodletting`, `Conspirator's Cloak`, etc.).
  - **Load, Normalize, & Edit Existing Rotations (`normalize_rotation_steps`)**:
    - Loads any existing rotation file from `data/rotations/` (such as `BasicMaliPS.json` or `darkness.json`) or local disk.
    - Automatically detects and repairs misplaced rule keys on pool entries (such as `"caster_has_buff"` outside `"rules"` in `darkness.json`).
    - Supports one-click block cloning, step reordering, reusable templates / filler tail macros, guided rule modals for all `CONDITION_REGISTRY` validators, static linting, and a 30s live dry-run simulation preview (`run_dry_run_preview`).
- **Test Coverage (`tests/test_rotation_builder.py`)**:
  - Added 5 unit tests covering workspace catalog loading, Hatred/Darkness blueprint auto-discovery, legendary implant and on-hit/on-use relic selection & discovery, existing rotation normalization, and dry-run simulation preview.
  - Full regression suite: all 176 tests passing with zero errors (100% pass rate).

### 58. Creeping Terror DoT Premature Expiration & Zero-Tick Bug Fix (`requirements.py`, `events.py`, `tests/test_simulation_integration.py`) - [DONE]
- **Root Cause Analysis**:
  - In `src/swtorsim/requirements.py`, the `has_ability` condition evaluator compared `actual_rank = 1 if has_it else 0` against `expected_rank = item.get("ints", {}).get("rank", 1)` via `compare_values(actual_rank, comparison, expected_rank)`.
  - When blueprints contained 0-indexed rank thresholds (`"ints": {"rank": 0}`), unlearned abilities evaluated `has_it = False`, giving `actual_rank = 0` which resulted in `0 >= 0` evaluating to `True`.
  - This false-positive caused `Creeping Terror`'s Effect 3 Branch 8 to trigger an unlearned discipline mod (`finish_them_madness`), calling sub-effect 9 (`name: "Creeping Terror"`).
  - Effect 9 had a 6-charge consumption mechanic without periodic damage branches that overwrote Effect 3 on the target dummy in `target.effects["Creeping Terror"]`.
- **Implementation**:
  - **Condition Fix (`requirements.py`)**: Updated `has_ability` evaluation so that `if not has_it: res = False` before rank comparisons, preventing unlearned abilities from satisfying `>= 0` checks.
  - **Stem Matching Integration (`requirements.py`)**: Added `is_stem_matching_enabled()` support for ability stems in `has_ability`.
- **Verification & Test Coverage**:
  - Added `test_02b_creeping_terror_dot_lifecycle_and_ticks` to `tests/test_simulation_integration.py` verifying Creeping Terror applies to target, executes 1 initial hit + 6 periodic DoT ticks (7 hits total), and remains active across its full alacrity-scaled ~16.6s / 18.0s duration.
  - All 176 tests in the test suite pass cleanly (`0` failures, `0` errors) via `.\tools\pyclean.exe`.

### 59. Target Override Group Resolution (`party_members`, `companion`), `on_enter_combat` Transition & `is_target_caster` Fix (`abilities.py`, `requirements.py`, `tests/test_party_members_target.py`) - [DONE]
- **Target Override Routing**:
  - Handled `party_members` and `companion` in `abilities.py::_resolve_target_overrides`. In single-player simulation, party members and companions resolve to `caster` (the player), preventing group-wide heals (such as `berserk_juyo` / `zen_juyo`) and team buffs from erroneously targeting the enemy target dummy.
- **Combat Entry Transition**:
  - In `Ability.cast`, added check for aggressive ability activation when `not caster.in_combat` to set `caster.in_combat = True` and dispatch `on_enter_combat`, enabling combat-start triggers (such as `Rallying Charge` / Entertainer Package and cylinder passives) to fire automatically.
- **Target Evaluation in `is_target_caster`**:
  - Fixed `requirements.py` condition `is_target_caster` to evaluate the effect's actual `target` argument (`effective_target = target if target is not None else context.get("target")`), rather than letting stale trigger event contexts override the effect recipient.
  - Confirmed that ally-only legendary items like `abl.itm.legendary.generic.healer.entertainer` (Entertainer Package / Rallying Charge) correctly filter out the wearer via `NOT is_target_caster`, preventing the player or the enemy dummy from gaining the buff, while allowing allies to receive it when targeted.
- **Multi-Player Roadmap Documentation**:
  - Created `docs/multi_player_features.md` outlining the architectural checklist for multi-target branch execution, threat/aggro management, independent event loops, and group buff propagation when expanding to multi-player simulation.
- **Verification & Test Coverage**:
  - Created `tests/test_party_members_target.py` with 4 unit tests covering `party_members` target override resolution, Entertainer caster filtering, ally buffing, and aggressive cast combat transition.
  - All 181 tests in the full regression suite pass cleanly (`0` failures, `0` errors) via `.\tools\pyclean.exe`.

### 60. Standalone Combat Simulator Web GUI Dashboard (`src/swtorsim/web_gui.py`, `tools/simulator_ui.html`, `run_sim.py`, `tests/test_web_gui.py`) - [DONE]
- **Backend Server & REST API (`src/swtorsim/web_gui.py`)**:
  - Implemented `SimulatorRequestHandler` and `launch_web_simulator` serving `tools/simulator_ui.html` on `http://127.0.0.1:8766` (auto-scanning ports `8766..8785`).
  - Added `/api/catalog`, `/api/class_gear`, `/api/run_config`, `/api/build_stats`, `/api/preview_stats`, `/api/simulate`, `/api/run_config/save`, `/api/build_stats/save`, and `/api/launch_rotation_builder`.
  - Added `preview_character_stats()` to compute live character sheet values (`gcd_seconds`, `alacrity_pct`, `crit_chance_pct`, `crit_multiplier_pct`, `accuracy_pct`, `M/R/F/T_Bonus_Damage`) with support for inline `stats_override`.
  - Added `_run_single_test_detailed()` (`TEST` mode) capturing full-fight and execute-phase (`<30% HP`) ability breakdowns (including per-ability cast counts and min/max hits), buff/debuff active windows, and structured combat log events.
  - Added `_run_batch_monte_carlo_detailed()` (`BATCH` mode) computing mean, median, std dev, 95% CI, P10/P25/P75/P90 percentiles, histogram bins, and macro ability breakdowns.
- **Frontend Dashboard (`tools/simulator_ui.html`) & CLI Integration (`run_sim.py`)**:
  - Built 5-tab interactive Web GUI: Ability Breakdown (`Full Fight` & `Execute <30% HP`), Monte Carlo Distribution (SVG histogram + percentile cards), Buffs & Debuffs (Gantt active-window timeline + uptime table), Combat Event Log (filterable/searchable + `.txt` export), and Session Run History & Side-by-Side Baseline Comparison.
  - Added `--web` (`-w`), `--port`, `--no-browser`, and interactive menu option `[0] Launch Web GUI Dashboard` to `run_sim.py`.
- **Verification & Test Coverage**:
  - Created `tests/test_web_gui.py` with 5 unit and integration tests covering catalog discovery, class gear filtering, character sheet stat preview with overrides, `TEST` and `BATCH` simulation execution, and HTTP request handler endpoints.
  - All 186 tests in the full regression suite pass cleanly (`0` failures, `0` errors) via `.\tools\pyclean.exe`.


### 61. Monte Carlo Web UI & CLI Performance Optimization & Engine Parity (src/swtorsim/web_gui.py, src/swtorsim/tester.py) - [DONE]
- **Worker Pool Initializer & Micro-Payload IPC (web_gui.py)**:
  - Resolved major Windows IPC serialization bottleneck where _run_batch_monte_carlo_detailed previously pickled and transferred the entire ~175 KB loadout_blueprints dictionary across Windows pipes for every single iteration.
  - Added _init_batch_worker initializer to load static simulation inputs (loadout_blueprints, 
otation_config, stats_config, debuff_module, settings_dict) into worker process globals once upon pool creation.
  - Streamlined per-task IPC payloads into ~40-byte micro-payloads: (run_id, seed, duration, dummy_hp), eliminating 99.9% of IPC queue serialization and pipe I/O.
  - Implemented 1% dynamic chunking (chunksize = max(1, int(round(iterations * 0.01)))) and progress update batching to eliminate worker queue congestion on medium and large iteration runs.
- **Warm Persistent Worker Pool (web_gui.py)**:
  - Implemented get_or_create_simulation_pool with pool_key context hashing (cores, selected_fqns, stats_path, 
otation_path, stats_tuple, settings_tuple, 	raining_dummy_armor_debuff).
  - Eliminates repeated Windows subprocess spawning, DLL loading, and antivirus scanning overhead (~1.5s-3.0s per batch) across repeated Monte Carlo runs.
  - Added clean shutdown termination via texit.register(cleanup_simulation_pool).
- **Engine Parity Alignment (	ester.py)**:
  - Audited schedule_periodic: confirmed player.procs is dead prototype code (initialized to {} in Player.__init__ and never populated anywhere in modern SwtorSim, where passives are handled via player.passive_db, player.effects, entry_effect_ids, and ResourceTick/TriggerManager). Completely removed schedule_periodic from both 	ester.py and web_gui.py to eliminate unnecessary calls and preserve engine cleanliness.
- **Verification & Benchmarks**:
  - Benchmarked 50-fight Hatred 6.0M dummy parse: CLI took 6.023s; Web GUI initial cold run took 8.729s; Web GUI warm persistent run completed in 3.318s (1.82x faster than CLI).
  - Full test suite: 187/187 tests passing with zero errors (100% pass rate) via pyclean.exe.

### Web UI combat log: same-tick cast/damage ordering - [DONE]
- web_gui.py :: _run_single_test_detailed cast wrapper now reserves the log index before calling Ability.cast and inserts the cast event there, so instant-ability damage logged during the cast no longer precedes the Casts X row. Regression assertion added to 	ests/test_web_gui.py. Full suite: 187/187 OK.

### Item 58 - Universal Class Buffs & Hidden Permanent Bonus
- **New module `src/swtorsim/class_buffs.py`**: `apply_class_buffs(player, sim)` grants every player Unnatural Might, Mark of Power, Coordination and Hunter's Boon (the in-game "Hunter's Boon"), built from the extracted `*_passive` blueprints via `ActiveEffect.from_effect_node`. The `tal.legacy.buff_unlock.*` `has_ability` gates are intentionally bypassed; buffs already applied from the loadout (own-class buff) are not duplicated.
- **Hidden permanent bonus**: `+1%` accuracy, `+1%` critical chance, `+1%` critical multiplier (`HIDDEN_BONUSES`), stored in `Player.permanent_bonuses` and applied additively in `Player.recalculate_stats` (accuracy via the shared `Accuracy` bonus so Main/Off/channel accuracy all shift; no change to `combat_math.py`, no new stat IDs).
- **Wiring**: `setup.py :: prepare_simulation` calls `apply_class_buffs` after loadout passives and before the final `recalculate_stats`, so Tester, web GUI and rotation builder all pick it up. Bare `Player(...)` objects keep zero hidden bonus.
- **Verification**: Hatred Assassin now shows `Critical Chance` +0.0100, `Critical Modifier` +0.0100, `Main Accuracy` +0.0100 and all four buffs active; new `tests/test_class_buffs.py` (5 tests); full suite `192/192` passing.


### Item 62 - Live and PTS Dual-Environment Support across Extractor, Engine, CLI, and Web GUI - [DONE]
- **Extractor Isolation & `--parsed-only` Option (`src/extractor/config.py`, `src/extractor/cli.py`)**:
  - Isolated PTS extraction output to `data/extractor/pts/` when `--pts` is passed, preventing it from overwriting Live data (`data/extractor/`).
  - Added `--parsed-only` flag to skip generating the ~400MB raw GOM node dump in `extracted/`, reducing output from >400MB to ~12MB of clean simulator-ready JSONs (`parsed/`, `disciplines/`, `gear_abilities_talents.json`, `relics.json`, `combat_curves.json`).
  - Shared Jedipedia cache files (`hashes.bin`, `gom.js`, `fnv1a64.js`) in `data/extractor/` to prevent re-downloading ~140MB of binary hashes on PTS extraction.
- **Engine Path Resolution & Curve Clamping (`src/swtorsim/settings.py`, `src/swtorsim/combat_curves.py`, `src/swtorsim/run_config.py`, `src/swtorsim/config_load.py`)**:
  - Added global environment toggle `set_data_environment("live" | "pts")` and path resolver `get_extractor_data_dir()`.
  - Added `environment: str = "live"` to `RunConfig` dataclass and `load_run_config(path, environment=...)`.
  - Resolved dynamic paths for `disciplines`, `gear_path`, `relics_path`, `parsed_dir`, and `training_dummy_armor_debuff` based on the active environment.
  - In `combat_curves.py`: added dynamic `_curves(env)` lookup and graceful level clamping in `_level_row` (allowing level 85 configurations to simulate against level 80 live curves without crashing).
- **CLI Runner Support (`run_sim.py`)**:
  - Added `--pts` command-line flag to `run_sim.py`, allowing instant execution against PTS data (e.g. `py run_sim.py hatred_14gcd --pts --hp 1m`).
- **Web GUI Environment Toggle (`src/swtorsim/web_gui.py`, `tools/simulator_ui.html`)**:
  - Parameterized `/api/catalog?env=pts`, `/api/class_gear?env=pts`, `/api/run_config?env=pts`, and simulation payload execution with environment support.
  - Added `[ Live (7.6) | PTS (7.7) ]` toggle buttons in the Web GUI header bar, dynamically updating catalog items and gear choices.
- **Verification**:
  - Executed benchmark comparison on Hatred 14gcd rotation: Live produced `41,160.5 DPS` (41 tacticals cataloged), PTS produced `47,445.7 DPS` (35 tacticals cataloged, max level 85 curves).
  - All Web GUI and integration unit tests passing cleanly via `.\tools\pyclean.exe`.


### Item 63 - Web GUI PTS Environment Switching and Level 80 vs 85 Curve Scaling Resolution - [DONE]
- **Root Cause 1 (Web UI Environment Decoupling)**:
  - In `tools/simulator_ui.html`, `buildPayloadFromForm()` did not pass `environment` or `env` in the request body. When `/api/simulate` or `/api/preview_stats` were called, the backend fell back to `env = "live"`.
  - In `tools/simulator_ui.html`, `setEnvironment(env)` invoked `loadCatalog(true)` which rebuilt `classSelect` but omitted repopulating `specSelect` or updating `specSelect.value` to PTS paths (`data/extractor/pts/disciplines/...`).
  - In `src/swtorsim/web_gui.py::load_run_config_bundle`, `raw_rc["spec_path"]` was not updated when PTS candidates were found, resulting in the returned configuration still containing Live discipline paths.
- **Root Cause 2 (Combat Curves LRU Cache Trap)**:
  - In `src/swtorsim/combat_curves.py`, `_curves(env: str | None = None)` was decorated with `@lru_cache(maxsize=4)`. When called with `env=None` (as done by `player_standard_health`, `derived_stat`, and `armor_constants`), Python cached `_curves(None)` pointing to Live curves. When `set_data_environment("pts")` was toggled, subsequent calls with `None` continued returning the cached Live table!
  - Because Live curves clamp at level 80, any simulation or stat preview at level 85 clamped to level 80 values (Standard Health remained 19,335, and rating divisors remained level 80).
- **Implementation**:
  - Split `combat_curves.py` into internal `@lru_cache(maxsize=4) def _load_curves(env: str)` and external `_curves(env: str | None = None)` that resolves `env = env or get_data_environment()` before cache lookup, ensuring distinct cache slots for `'live'` and `'pts'`.
  - In `simulator_ui.html`:
    - Updated `buildPayloadFromForm()` to include `environment: currentEnvironment`, `env: currentEnvironment`, and `pts: currentEnvironment === "pts"`.
    - Updated `setEnvironment(env)` to automatically adjust level default (80 for Live, 85 for PTS) and re-link active discipline paths between `data/extractor/` and `data/extractor/pts/`.
    - Added change listener on `levelInput` to dynamically refresh the mini-sheet in real time via `/api/preview_stats`.
  - In `src/swtorsim/web_gui.py`:
    - Normalized path separators (`\` to `/`) and ensured `load_run_config_bundle` returns updated `spec_path` matching the active environment.
    - Explicitly set `set_data_environment(env)` and passed `environment` in simulation responses.
- **Verification**:
  - `Live (level 80)`: Player standard health is `19,335`.
  - `PTS (level 85)`: Player standard health is `21,810` (+12.8% base damage scaling). Ratings suffer diminishing returns (3400 Alacrity rating yields 10.88% at level 80 vs 10.36% at level 85; 2500 Crit rating yields 10.67% at level 80 vs 10.16% at level 85).
  - All unit tests in `tests/test_web_gui.py` passing (6/6).


### 10. Standalone In-Browser Pyodide WebAssembly Release Pipeline - [DONE]
- Implemented dual-mode backend architecture in 	ools/web/pyodide_client.js preserving 100% native desktop CPython speed and multiprocessing.Pool while transparently intercepting /api/* fetch requests when running as a static web app.
- Created 	ools/bundle_pyodide_assets.py to compress engine code, discipline trees, and parsed blueprints into a compact 4.83 MB runtime zip (dist/swtorsim_assets.zip), excluding ~560 MB of raw extraction binaries and caches.
- Created 	ools/web/sim_worker.js and src/swtorsim/pyodide_bridge.py to run the simulation engine inside a Web Worker with Pyodide 0.27.2, providing asynchronous, unblocked 60 FPS simulations and progress streaming.
- Made matplotlib lazy/optional in src/swtorsim/tester.py to eliminate heavy graphical dependencies in headless/web mode.
- Added Emscripten runtime detection in src/swtorsim/web_gui.py to gracefully run sequential worker batches in WASM while retaining multi-core OS process pooling on desktop.
- Implemented 	ools/build_web_release.py producing a self-contained static dist/ directory ready for deployment on GitHub Pages or local preview via python -m http.server 8080 -d dist.


### 11. In-Browser Multi-Core Web Worker Pool & Live/PTS Robustness Fixes - [DONE]
- **Multi-Worker Pyodide Pool (`tools/web/pyodide_client.js`)**:
  - Implemented multi-core hardware scaling via `navigator.hardwareConcurrency` (up to 16 Web Workers), overcoming WebAssembly's single-thread GIL restriction by running independent Pyodide workers in parallel.
  - Added primary worker hydration (`Worker 0`) with request-queuing `readyPromise` to eliminate initial blank catalog / race conditions on cold launch.
  - Spawns secondary background workers dynamically upon primary readiness, updating the UI badge to `[BACKEND: Pyodide [WASM Multi-Core: N/N Cores]]`.
- **Parallel Batch Slicing & Merging (`src/swtorsim/web_gui.py`, `src/swtorsim/pyodide_bridge.py`)**:
  - Added `execute_simulation_slice` and `SIMULATE_SLICE` action to execute discrete chunked iteration slices across independent worker threads.
  - Added `aggregate_batch_slices` and `AGGREGATE_BATCH` action allowing `Worker 0` to combine harvested batch runs across all workers into unified statistical metrics, DPS histograms, and damage breakdowns.
  - Aggregates live progress counters across all worker threads for real-time progress bar streaming in the browser UI.
- **Cross-Environment & Filesystem Robustness (`config_load.py`, `web_gui.py`, `simulator_ui.html`)**:
  - Added case-insensitive file and directory fallback in `load_json_file` and `_resolve_workspace_path` to resolve Emscripten MEMFS case-sensitivity differences.
  - Added tactical and legendary dropdown fallback in `simulator_ui.html` when switching between Live (41 tacticals) and PTS (35 tacticals).
  - Sanitized empty and whitespace FQN strings in `config_load.py::load_complete_loadout` preventing `ValueError: WindowsPath('.') has an empty name`.
  - Upgraded `pyodide_client.js` fetch interceptor to return HTTP 400 with full stack trace on errors instead of masking them as HTTP 200.


### 12. Batch Verbosity String Suppression & Multi-Worker Pool Warm-up Gating - [DONE]
- **Worker Pool Warm-up Gating (`tools/web/pyodide_client.js`)**:
  - Implemented `ensureAllWorkersReady()` in `pyodide_client.js` to prevent race conditions where batch runs launched before secondary Web Workers finished booting.
  - Capped `targetPoolSize` to `Math.max(2, Math.min(hardwareCores, 8))` to prevent browser WebAssembly memory thrashing across excessive parallel runtimes.
  - Added live status updates to the Run button (`⏳ Warming Cores (N/8)...`) and header badge so batch iterations never start on a single worker while background instances are initializing.
- **Combat String Formatting Suppression in Batch Mode (`engine.py`, `setup.py`, `events.py`, `abilities.py`, `web_gui.py`, `tester.py`)**:
  - Added `verbose: bool = True` to `Simulation.__init__` and `prepare_simulation`.
  - Added `if getattr(sim, "verbose", True):` guards around all combat hit, cast, channel, tick, and buff expire `print()` formatting calls across `events.py` and `abilities.py`.
  - Passed `verbose=False` in `web_gui.py::_batch_worker_task` and `tester.py`, completely eliminating thousands of f-string allocations and virtual `/dev/null` file writes per simulation run in both CPython and WebAssembly.


### 13. Dynamic Unconstrained Core Scaling & In-Browser Core Selector - [DONE]
- **Unconstrained Core Detection**: Removed the arbitrary 8-core ceiling in `tools/web/pyodide_client.js`, allowing `navigator.hardwareConcurrency` to automatically provision all available physical/logical cores (e.g. 16, 24, 32) on high-end hardware.
- **In-Browser Core Selector UI (`pyodide_client.js`)**:
  - Added a `Cores: [ N (Max) ▾ ]` dropdown in the web dashboard header next to the backend badge.
  - Dynamically builds choices (`1`, `2`, `4`, `8`, `12`, `16`, `24`, `32`, `Max`) tailored to the user's specific CPU architecture.
  - Dynamically resizes the worker pool on demand: terminating surplus Web Workers to instantly reclaim browser RAM if reduced, or provisioning additional workers if increased.
  - Persists user preferences to `localStorage["swtor_wasm_cores"]` across browser sessions.
  - Enforces `ensureAllWorkersReady()` on whatever core count is currently selected before executing any Monte Carlo batch slices.


### 14. Minimal Backend Indicator Redesign (Option 5) - [DONE]
- Replaced the verbose `[BACKEND: Pyodide [WASM Multi-Core: N/N Cores]]` header badge with an ultra-compact status pill:
  - Desktop Native: `<span style="color:#3fb950;">●</span> Native` (green dot).
  - Browser WASM: `<span style="color:#58a6ff;">●</span> Web` (blue dot).
  - Background Warming: `<span style="color:#d29922;">●</span> Warming (N/Total)` (amber dot).
- Reduced badge padding (`2px 7px`), font size (`11px`), and letter spacing to cleanly match the header controls.
- Preserved full operational telemetry (thread count, execution model, OS process details) inside the mouseover `title` tooltip.


### 15. Custom File Importers & Dynamic In-Browser Storage - [DONE]
- **Custom File Import System (`simulator_ui.html`, `pyodide_client.js`, `sim_worker.js`, `web_gui.py`)**:
  - Added `📁 Import` buttons next to **Combat Rotation**, **Skill Tree Choices**, **Build Stat Preset**, and **Preset Config** (Header).
  - Client-side JSON schema validation on upload ensures only syntactically sound rotations, skill tree choices, and stat dictionaries are accepted.
  - Automatically groups dropdown items using distinct `<optgroup label="★ My Custom Files">` so custom uploads stand out from built-in presets.
  - Contextual `🗑️ Delete` button dynamically appears whenever a custom file is selected, allowing instant deletion.
- **Dual-Mode Persistence Architecture**:
  - **In-Browser WebAssembly**: Stores custom files in browser `localStorage["swtor_custom_files"]` and syncs them directly into Pyodide virtual MEMFS (`pyodide.FS.writeFile`) across all Web Workers upon initialization.
  - **Native Desktop Python**: Endpoints `/api/custom_file/import` and `/api/custom_file/delete` persist custom JSON files to disk in `data/rotations/custom/`, `data/Choices/custom/`, `data/builds/custom/`, and `data/run_config/custom/`.
  - Python's catalog recursive scanner (`base.rglob("*.json")`) automatically discovers and exposes custom subdirectories with zero changes to core engine loading logic.


### 16. Rotation Builder WebAssembly Connection & Dual-Mode Unification - [DONE]
- **WebAssembly Bridge Integration (`pyodide_bridge.py`)**:
  - Implemented dispatcher actions `GET_BUILDER_CATALOG`, `LOAD_BUILDER_RUN_CONFIG`, `LOAD_ROTATION`, `DISCOVER_LOADOUT`, `RUN_ROTATION_PREVIEW`, and `SAVE_ROTATION`.
  - Directly imported and invoked `data.rotation_builder` functions (`get_workspace_catalog`, `discover_loadout_catalog`, `normalize_rotation_steps`, `run_dry_run_preview`) within the Pyodide WebAssembly runtime.
- **Client-Side Interceptor Routing (`pyodide_client.js`)**:
  - Added fetch interceptors for `/api/launch_rotation_builder` (routes to `rotation_builder.html` in Web mode), `/api/catalog`, `/api/run_config`, `/api/rotation`, `/api/loadout`, and `/api/preview`.
  - Integrated `/api/rotation/save` with Pyodide virtual MEMFS and browser `localStorage["swtor_custom_files"]`, broadcasting saved rotations via `WRITE_VIRTUAL_FILE` across the entire Web Worker pool.
  - Automatically saves custom rotations to both `data/rotations/<class>/<spec>/<filename>` and `data/rotations/custom/<filename>`, ensuring newly created rotations immediately appear under `* My Custom Files` in the Combat Simulator dropdown.
- **Rotation Builder UI & Navigation (`rotation_builder_ui.html`, `simulator_ui.html`)**:
  - Added a `[ Combat Simulator ]` button in the Rotation Builder header to seamlessly switch back or focus the simulator tab.
  - Updated `populateExistingRotationsSelect()` to group custom rotations under `* My Custom Files`.
  - Added `data/__init__.py` to Pyodide asset packaging to support direct modular imports in browser WASM.


### 17. Named Window Pairing & Builder Single-Worker Optimization - [DONE]
- **Option A Named Window Pairing (`simulator_ui.html`, `rotation_builder_ui.html`, `pyodide_client.js`)**:
  - Assigned deterministic target names: `window.name = "swtor_sim"` for the Combat Simulator and `window.name = "swtor_builder"` for the Rotation Builder.
  - In `simulator_ui.html`, clicking "Rotation Builder" now targets `"swtor_builder"` via `window.open(url, "swtor_builder")`, reusing the existing tab rather than spawning duplicate tabs.
  - In `rotation_builder_ui.html`, clicking "Combat Simulator" now explicitly targets `"swtor_sim"` (`window.open(url, "swtor_sim")` / `target="swtor_sim"`), eliminating reliance on `window.opener.focus()` and preventing blocked navigation.
- **Dedicated Single-Worker Builder Acceleration (`pyodide_client.js`)**:
  - Detected `isBuilderPage` and clamped `targetPoolSize = 1` for the Rotation Builder, suppressing secondary worker initialization.
  - Eliminates the previous bottleneck where 16-32 Web Workers simultaneously downloaded and unpacked asset archives in parallel, resolving memory starvation on Worker 0 and allowing loadouts, gear, and abilities to load in 1-2 seconds.


### 18. New-Tab Window Navigation (`_blank`) - [DONE]
- **Removed Named-Window Targeting Reloads**:
  - Removed named window target pairing (`swtor_sim` / `swtor_builder`), which forced existing tabs to navigate and reload their entire document on click.
  - In `simulator_ui.html`, clicking "Rotation Builder" now opens a new tab via standard `window.open(data.url, "_blank")`.
  - In `rotation_builder_ui.html`, clicking "Combat Simulator" now opens a new tab via standard `target="_blank"`.
  - Existing tabs now keep their active state and memory intact without unwanted reloads.


### 19. Class Swap & Skill-Tree Choices Validation Fix - [DONE]
- **Robust Choices Decoding (`rotation_builder.py`)**:
  - Fixed `AttributeError: 'list' object has no attribute 'get'` triggered when switching classes.
  - Root cause: An old rotation file mistakenly located in `data/Choices/Specs/Hatred/Rotations/BasicMaliPS.json` was being indexed as a choices preset and loaded as a `list` instead of a `dict`.
  - Added strict dictionary type-checking in `discover_loadout_catalog`: if loaded choices content is a `list`, non-dictionary, or empty, it automatically defaults to an empty mapping `{}` and defaults skill-tree slots safely to `1`.
  - Filtered `get_workspace_catalog()` choices scanning to verify that indexed choice files are actual skill-tree mappings (excluding legacy rotations or stat builds).
- **Client Class Swap Reset (`rotation_builder_ui.html`)**:
  - In `onSpecChange()`, if no specific choice file matches the new class/spec, `choicesFileSelect` cleanly resets to empty `(Default Class Choices)` instead of retaining another class's choices.
  - Automatically clears old class-specific tacticals and legendary implants upon changing class/spec to prevent cross-class gear carryover.


### 20. Rotation Builder Save & PC Download Unification - [DONE]
- **Automatic Browser Download on Save (`rotation_builder_ui.html`)**:
  - In Web/WASM mode, clicking "Save Rotation" now both saves the rotation into the simulator catalog (`localStorage` and virtual MEMFS) AND immediately triggers an automatic browser download of the `.json` file to the user's PC (`Downloads` folder).
  - Clarified the button label to `💾 Save Rotation` and updated toast messages to state: `[OK] Saved to My Custom Files & downloaded <filename>`.
  - In desktop/native Python mode, continues writing directly to the repository's workspace disk (`data/rotations/<class>/<spec>/<filename>`).

### 21. Rotation Builder Download-Only Simplification - [DONE]
- **Removed In-App Rotation Saving (`rotation_builder_ui.html`)**:
  - Deprecated and removed in-app saving (`saveRotationToDisk`) and internal folder inputs (Class Folder / Spec Folder).
  - Streamlined the interface to a single, dedicated `⬇️ Download JSON` button that downloads the formatted rotation `.json` directly to the user's local PC.
  - Users can load downloaded rotations into the Combat Simulator anytime via the simulator's `📁 Import` button, or re-open them in the Rotation Builder via `Import File...`.
  - Rebuilt the complete Web WASM release in `dist/`.

### 22. Rotation Builder Save & Download Restoration - [DONE]
- **Restored In-App Saving Alongside Direct Download (`rotation_builder_ui.html`)**:
  - Re-enabled `💾 Save Rotation` to allow users to register custom rotations directly into `data/rotations/custom/` and browser storage for instant use in the simulator.
  - Retained `⬇️ Download` so users can also download `.json` files to disk whenever desired.
  - Verified cross-tab synchronization and Pyodide virtual memory hydration.
  - Rebuilt production bundle in `dist/`.

### 23. Worker Pool Ready-State Gating for File Deletions & Mutations - [DONE]
- **Fixed Unready Worker Rejection on Delete (`pyodide_client.js`)**:
  - In `/api/custom_file/delete`, `/api/custom_file/import`, and `/api/rotation/save`, virtual file mutations previously broadcasted to `state.workers` indiscriminately.
  - If secondary workers were still booting in the background, attempting to send `DELETE_VIRTUAL_FILE` to unready workers caused `Error: Pyodide Web Worker is not ready yet.` and triggered an alert popup even though the file was deleted from storage.
  - Filtered live worker mutations strictly to `state.workers.filter(w => w.isReady)`. Any secondary worker booting in the background automatically syncs current storage upon ready.
  - Cleaned up any legacy duplicate entries for the deleted file across persistent storage.
  - Rebuilt production bundle in `dist/`.

### 24. Save & Download Button UI Simplification - [DONE]
- **Independent Save & Download Actions (`rotation_builder_ui.html`)**:
  - Decoupled `saveRotationToDisk()` from downloading: clicking **Save** strictly saves into browser presets and virtual files without triggering an automatic file download.
  - Clicking **Download** strictly downloads the formatted `.json` file to the user's PC without modifying simulator presets.
  - Cleaned up button aesthetics: applied compact `.btn-sm` sizing, removed emoji icons, and simplified label to **Save** and **Download**.
  - Rebuilt production bundle in `dist/`.

### 25. Rotation Builder PTS (8.0) Environment Support - [DONE]
- **Added Dual Environment Toggle in Rotation Builder (`Live 7.9` vs `PTS 8.0`)**:
  - Added header environment toggle buttons in `tools/rotation_builder_ui.html` matching the Combat Simulator styling.
  - When PTS is selected, the Rotation Builder points to `data/extractor/pts/` (PTS disciplines, Level 85 enhanced blueprints such as `Assassinate+`, PTS gear, and PTS combat curves).
  - Updated `get_workspace_catalog`, `discover_loadout_catalog`, and `run_dry_run_preview` in `data/rotation_builder.py` and `pyodide_bridge.py` to accept `env` query/payload parameters.
  - In Web WASM mode, forwarded `env` in Pyodide client dispatch.
  - Rebuilt production bundle in `dist/`.

### 26. Web WASM Build Preset Selection Interceptor - [DONE]
- **Fixed `/api/build_stats` 404 in Browser WASM Mode (`pyodide_client.js`, `simulator_ui.html`)**:
  - In Section 3 ("Character Stats & Sheet"), selecting a preset from `Build Stat Preset` (`#buildSelect`) previously triggered a network fetch to `/api/build_stats` that was missing in Pyodide client request interception, resulting in a 404 failure and preventing inputs/sheet from updating.
  - Added `GET_BUILD_STATS` bridge action and intercepted `/api/build_stats` in `pyodide_client.js` with virtual memory and storage resolution.
  - Added instant catalog cache lookup directly in `simulator_ui.html` so selecting any preset build immediately updates the stat inputs and recalculates the live character sheet without latency.
  - Rebuilt production bundle in `dist/`.


### 27. Suppressed Multi-Core UI in Rotation Builder - [DONE]
- **Removed Cores Selector & Cleaned Header Badge (`tools/web/pyodide_client.js`)**:
  - In `updateCoreSelectorUI()`, added early return and cleanup when `isBuilderPage` is true: removes `#swtor-core-selector-container` so the multi-core dropdown is never shown in the Rotation Builder.
  - In `updateBackendBadge()`, adjusted tooltips and warming labels on the Rotation Builder to avoid referencing multi-core worker pool counts, keeping the discreet `Web` status badge clean.
  - Rebuilt production bundle in `dist/`.


### 28. Interactive Skill Tree Drawer in Combat Simulator - [DONE]
- **Added Visual 1/2/3 Choice Drawer to Simulator (`simulator_ui.html`, `web_gui.py`)**:
  - Upgraded `get_class_gear_options` in `web_gui.py` to compile human-readable `skill_tree` tier data (level, slot names, and ability types) matching the discipline.
  - Added an interactive `[Skill Tree]` toggle button and drawer inside Box 2 ("Discipline, Gear & Choices") on `simulator_ui.html`.
  - Clicking any tier option (Option 1, 2, or 3 across all 8 tiers) dynamically updates active talent selections, highlights choices in the drawer, syncs `#choicesPreviewBadge`, and passes `choices_override` directly to simulation batches.
  - Rebuilt production bundle in `dist/`.


### 29. Comprehensive Project Documentation & Inline Docstrings Suite - [DONE]
- **Multi-File Documentation Suite (`README.md`, `docs/`)**:
  - Rewrote root `README.md` with an accessible overview, quickstart workflows (Web GUI, CLI, Rotation Builder, Extractor, Pyodide Web Release), repository structure map, and documentation index.
  - Created `docs/user_guide.md` covering Web GUI usage, CLI flags, `run_config.json` schema, character stats (`data/builds/`), skill-tree choices (`data/choices/`), visual Rotation Builder & rotation JSON condition syntax, and auxiliary tools.
  - Rewrote `docs/architecture.md` with end-to-end Mermaid diagrams and detailed phase breakdowns (blueprint hydration, `prepare_simulation`, 7 raid dummy debuffs, `SimulationEngine` event loop, 11 discrete event types, action handlers, `ActiveEffect` stacking, `TriggerManager` proc bus, resource pools, and dual-runtime execution).
  - Created `docs/combat_math.md` documenting `Player.recalculate_stats`, class buffs & companion bonuses, diminishing returns (`calc_dr`), Alacrity/GCD rounding, `accuracy_roll`, `calculate_base_damage`, `handle_mitigation`, the 6 multiplicative damage buckets, and `calculate_crit`.
  - Created `docs/extractor_and_schemas.md` documenting the `.tor` MYP / GOM `.bkt` / `.stb` / FNV-1a 64-bit tag hash extraction pipeline and annotated JSON schemas for disciplines, abilities, talents, and combat curves.
  - Created `docs/developer_guide.md` covering `AGENTS.md` invariants, architectural routing, step-by-step extension workflows (stat IDs, action handlers, conditions, proc triggers, new disciplines), and testing protocols.
  - Updated `docs/rewrite.md` to archive the completed blueprint migration and link to the current documentation suite.
- **Inline Codebase Docstrings (`src/swtorsim/`, `src/extractor/`, `data/rotation_builder.py`)**:
  - Added module, class, and function/method docstrings across all 18 `src/swtorsim/` modules, all 30 `src/extractor/` modules, and `data/rotation_builder.py` while preserving strict CRLF (`\r\n`) line endings.

### 30. Mudkip Blue & Gill Orange Web UI Color Scheme - [DONE]
- **Updated Web UI Color Palette (`tools/simulator_ui.html`, `tools/rotation_builder_ui.html`, `tools/web/pyodide_client.js`)**:
  - Updated CSS custom properties (`:root`) and component color rules without altering any HTML structure, DOM elements, or layout geometry.
  - Applied Mudkip Body Blue (`--bg-panel: #58abdf`) to outer chrome (Header, Sidebar, and Navigation Tab Bars), Soft Blue (`--bg-base: #c2e4f6`) to the main workspace canvas, Crisp White (`--bg-card: #ffffff`) to inner metric/table/config boxes, and Mudkip Gill Orange (`--accent: #ff7818`, `#e65c00`) to primary CTAs, badges, active states, and DPS highlights.
  - Added `[data-theme="dark"]` Matte Mudkip Night CSS variable overrides (`--bg-base: #0e121a`, `--bg-panel: #141a24`, `--bg-card: #1c2331`, `--border: #263144`, `--accent: #ff7818`, `--cyan: #58abdf`) and a header theme toggle button (`#themeToggleBtn`) with `localStorage` persistence (`swtorsim_theme`) and cross-tab `storage` synchronization.
  - Rebuilt standalone web release bundle in `dist/` via `tools/build_web_release.py`.

### 31. Authoritative Loadout Proc Registry & Phantom Stride Activation Fix - [DONE]
- **Root Cause**:
  - In `BasicMaliPS.json`, `phantom_stride` steps are gated by `"proc_cooldown_above": {"name": "Bloodletting", "value": ...}`.
  - In extracted SWTOR GOM data, the internal lockout sub-effect for Bloodletting is named `"Bloodletting_3"` (`tag.abl.sith_inquisitor.bloodletting_lockout`), while the Rotation Builder UI normalizes it to `"Bloodletting"`.
  - Previously, `requirements.py :: check_proc_cooldown_above` only checked `eff.name == name`, which evaluated `"Bloodletting_3" == "Bloodletting"` as `False`, causing `remaining_cooldown` to always equal `0.0s` and preventing Phantom Stride from ever being cast.
- **Implementation**:
  - Added `build_proc_registry(loadout_blueprints)` in `src/swtorsim/setup.py` and `player.proc_registry` on `Player` (`src/swtorsim/entities.py`), using the exact blueprint proc classification logic from `data/rotation_builder.py` (`lockout_effect`, `trigger_icd`, `proc_buff`).
  - Added `TriggerManager.get_remaining_icd(source_fqn, current_time, caster)` in `src/swtorsim/triggers.py` to query active `interval_61` rate-limit lockouts on event-bus triggers.
  - Updated `check_proc_cooldown_above` in `src/swtorsim/requirements.py` to resolve canonical proc names against `caster.proc_registry` (looking up the exact mapped lockout effect `effect_name` or querying `sim.triggers.get_remaining_icd`), while preserving fallback lookup on `caster.procs` and `caster.effects` for custom fixtures.
  - Updated `ARCHITECTURE.md`, `docs/architecture.md`, `docs/user_guide.md`, and `docs/developer_guide.md`.
  - Rebuilt standalone web release bundle in `dist/` via `tools/build_web_release.py`.
- **Verification**:
  - BasicMaliPS simulations now cast Phantom Stride on cooldown when Bloodletting is on lockout (`1` cast in 1M HP runs at `9.80s`/`9.10s`; `4` casts in 6M HP 14gcd runs; `3` casts in 6M HP 13gcd runs).
  - Enhanced `tests/test_simulation_integration.py` (`test_06` and `test_07`) to assert `player.proc_registry` hydration, `Bloodletting_3` lockout evaluation, and end-to-end `Phantom Stride` execution; 15/15 integration and ability execution unit tests passing.


### 32. Trigger Re-entrancy Guard & Pre-Execution ICD Lockout (`src/swtorsim/triggers.py`) - [DONE]
- **Root Cause**:
  - When a triggered branch executed an instant damage action (e.g. Volatile Substance detonation triggered by Acid Blade periodic damage), `handle_damage_action` immediately called `hit_event.resolve(sim)`.
  - In `DamageHit.resolve`, `sim.triggers.dispatch('on_damage_taken')` fired synchronously during the hit.
  - In `TriggerManager.dispatch`, `sub['next_allowed_time']` was previously updated *after* `sub['ability'].execute_branch(...)` returned.
  - Because the re-entrant dispatch call occurred while the outer `execute_branch` was still resolving, `sub['next_allowed_time']` remained `0.0`. If the damage inherited a matching tag (e.g. `tag.abl.debuff.poison`), the subscriber immediately matched and executed itself again recursively, causing `RecursionError: maximum recursion depth exceeded`.
- **Implementation**:
  - In `src/swtorsim/triggers.py`, updated `TriggerManager.dispatch` to assign `sub['next_allowed_time'] = sim.current_time + effective_interval` immediately *before* executing the branch, locking the ICD against synchronous child actions. If the branch does not run (`not ran`), the lockout is rolled back.
  - Added an active execution flag `sub['is_executing'] = True` inside a `try...finally` block to protect subscribers against any zero-ICD re-entrancy.
  - Rebuilt standalone web release bundle via `tools/build_web_release.py`.
- **Verification**:
  - Verified Concealment Operative rotation with Level 39 Choice 2 (Best Defense / Crippling Slice) and `Recursion.json` runs cleanly without recursion errors, successfully detonating Volatile Substance once at `t = 1.86s` and casting Crippling Slice on GCD at `t = 2.70s`.
  - 15/15 integration and ability execution unit tests passing in `tests/test_simulation_integration.py` and `tests/test_ability_execution.py`.

## [Spec-Aware Rotations & Custom Hierarchy Refactor] - 2026-11-06

### Summary of Changes
- **Backend Catalog Discovery (`src/swtorsim/web_gui.py` & `data/rotation_builder.py`)**:
  - Implemented `_scan_rotations()` to extract authoritative `class`, `spec`, and `is_custom` properties for all discovered rotation files.
  - Discerned preset files (`data/rotations/<class>/<spec>/<name>.json`) from user custom files (`data/rotations/custom/<class>/<spec>/<name>.json`).
  - Added spec-aware folder targeting in `/api/custom_file/import` (`data/rotations/custom/<class>/<spec>/`).
  - Hardened `/api/custom_file/delete` to strictly reject paths outside `/custom/`.
- **Eliminated Dual-Write in Rotation Builder (`data/rotation_builder.py`)**:
  - Saving custom rotations via `/api/rotation/save` now saves strictly to `data/rotations/custom/<class_folder>/<spec_folder>/<filename>.json`.
  - Removed write operation into preset `data/rotations/<class_folder>/<spec_folder>/` folder, preventing duplicate entries and ghost presets.
- **Dynamic Spec-Aware WebUI Filtering (`tools/simulator_ui.html` & `tools/rotation_builder_ui.html`)**:
  - Added `getActiveSpecInfo()` to reliably parse class and discipline slugs from the active discipline selection.
  - Implemented `updateRotationOptionsForCurrentSpec()` to dynamically filter the Rotation dropdown on `#classSelect` and `#specSelect` changes:
    - Primary optgroups: `★ My Custom Files` (matching active spec) and `Preset Rotations` (matching active spec).
    - Secondary optgroups: Other disciplines placed at the bottom to avoid dropdown pollution while maintaining access.
    - Automatic fallback/selection of the active spec's standard preset when available.
  - Updated `setupFileImporter` to pass active `class_folder` and `spec_folder` on rotation import.
  - Preserved strict CRLF line endings across all files per Rule #6.
- **Web Release Bundler Isolation (`tools/bundle_pyodide_assets.py`)**:
  - Added `"custom"` to `EXCLUDE_PATTERNS` so that user/developer scratch files in `data/rotations/custom/`, `data/Choices/custom/`, `data/builds/custom/`, and `data/run_config/custom/` are strictly excluded from `dist/swtorsim_assets.zip`.
  - Promoted `BasicMaliPS PTS.json` to `data/rotations/assassin/hatred/` as an official built-in preset.

## [Unreleased] - 2026-11-06: Empirical Modifier Bucketing — Test 8 (Assailable Elemental & Susceptible Tech)
### Added / Verified
- **Test 8 Empirically Proven (`docs/modifier_bucketing_log.md`)**:
  - Tested **Target Elemental Type Vulnerability (*Assailable Elemental* `+7%` / GOM `370`)** and **Target Tech Channel Vulnerability (*Susceptible* `+5%` / GOM `388`)** using Innovative Ordnance Mercenary `Incendiary Missile` (`Burning` DoT tick).
  - Target: Operations Training Dummy with All Debuffs Module active.
  - Calculated exact additive prediction in `BUCKET_1`: $3,411.3242 \times (1.0 + 0.07 + 0.05) = \mathbf{3,820.68} \implies \mathbf{3,821}$.
  - Calculated multiplicative prediction: $3,411.3242 \times 1.07 \times 1.05 = \mathbf{3,832.62} \implies \mathbf{3,833}$.
  - Observed in-game hit: **`3,821`** (exact match to Option A).
  - Definitively established that `370` (*Assailable Elemental*) and `388` (*Susceptible Tech*) are **ADDITIVE in `BUCKET_1`** alongside Attacker Damage Done (`79`), Force Vulnerability (`386`), Melee Vulnerability (`384`), and Internal Vulnerability (`376`).
- **Codebase & Master Checklist Sync**:
  - Updated `_TARGET_DEBUFF_BUCKETS` in `src/swtorsim/combat_math_unbucketed.py` with `"channel_tech": BUCKET_1` and `"type_elemental": BUCKET_1`.
  - Checked off IDs `370` and `388` in `docs/modifier_bucketing_master_checklist.md`.
  - Enforced strict Windows CRLF line endings across all files per Rule 6.

## [Unreleased] - 2026-11-06: Empirical Modifier Bucketing — Test 9 (Marked Ranged Vulnerability)
### Added / Verified
- **Test 9 Empirically Proven (`docs/modifier_bucketing_log.md`)**:
  - Tested **Target Ranged Channel Vulnerability (*Marked* `+5%` / GOM `382`)** on Arsenal Mercenary using `Priming Shot` (`abl.bounty_hunter.skill.arsenal.priming_shot`) against the Operations Training Dummy with All Debuffs Module active (*Sundered* `-20%` armor, *Marked* `+5%` ranged vulnerability).
  - Verified Energy armor mitigation with *High Velocity Gas Cylinder* (`+35%` armor penetration $\implies 21.8697\%$ effective DR), *Target Tracking* (`+35%` ranged crit damage), *Advanced Targeting* (`+10%` crit damage proc on crit), and *Supercharge* stacks (`+0.1%` damage done per stack, `+1.0%` at 10 stacks).
  - At 10 stacks of *Supercharge* (`+11%` total caster `BUCKET_1` from *Ironsights* `+10%` + *Supercharge* `+1%`), Option A (Additive in `BUCKET_1`, $1.160	imes$) predicted **`18,245 – 20,153`** non-crit and **`36,480 – 40,294`** crit, whereas Option B (Multiplicative, $1.11 	imes 1.05 = 1.1655	imes$) predicted a strict minimum floor of **`18,331`** non-crit and **`36,653`** crit.
  - Observed in-game hits of **`18,261`** (non-crit) and **`36,604`** (crit) sit strictly below Option B's mathematical floor, definitively proving that **`382` (*Marked*) is ADDITIVE in `BUCKET_1`**.
- **Codebase & Master Checklist Sync**:
  - Locked `"channel_ranged": BUCKET_1` and `"382": (BUCKET_1, None)` in `src/swtorsim/combat_math_unbucketed.py`.
  - Checked off ID `382` in `docs/modifier_bucketing_master_checklist.md`.
  - Enforced strict Windows CRLF line endings across all modified files per Rule 6.


## [Unreleased] - 2026-11-06: Stack Modification Targeting & Tag Resolution Fix (`abilities.py`)
### Fixed
- **`handle_modify_stack_charge` Targeting Priority (`src/swtorsim/abilities.py`)**:
  - Fixed a critical precedence bug where an active `owner_effect_key` in the trigger context caused `(eff is None or getattr(eff, "is_expired", False)) and search_tags` to evaluate to `False`, silently bypassing explicit action `tags` (such as `tag.abl.sith_warrior.fury_stacks`).
  - Re-architected `handle_modify_stack_charge` to strictly follow 3-tier targeting priority:
    1. **Explicit Tag Search**: Searches `owner_entity`, `caster`, and `target` for active effects matching `search_tags`.
    2. **Explicit Ability Spec Search**: Resolves active effects matching `ints.ability_spec` (respecting `is_stem_matching_enabled()` per Rule #7).
    3. **Trigger Origin Fallback**: Defaults to `owner_key` on `owner_entity` only when no explicit tags or specs are defined.
  - Verified that Marauder **Frenzy** now immediately grants the full 30/30 stacks of `Fury`, enabling **Berserk** to pass requirements and successfully activate Ataru Berserk buff while properly dispelling the Fury stacks.
  - Enforced strict Windows CRLF line endings across all files per Rule #6.

- **Stack-Building Effect Accumulation (`src/swtorsim/entities.py`)**:
  - Fixed stack accumulation in `Entity.apply_effect` where effects without scaling stat modifiers (`scales_with_stack_charge == False`) were permanently clamped at 1 stack.
  - Added `can_accumulate_stacks = effect_instance.max_stacks > 1 and (effect_instance.scales_with_stacks or effect_instance.initial_stacks < effect_instance.max_stacks)` to properly distinguish stack-building buffs (`initial < max`) from charge-consuming buffs (`initial == max`).
  - Verified natural Fury accumulation on Marauder through rage spenders: gains +4 Fury per attack (+2 base + +2 from Short Fuse), cleanly accumulating to 30 stacks and enabling Berserk.

## [Unreleased] - 2026-11-06: WebUI Export / Import Config Class & Spec Preservation (simulator_ui.html, web_gui.py, pyodide_client.js, rotation_builder_ui.html)
### Added / Fixed
- **Class & Spec Preservation on Config Export / Save (tools/simulator_ui.html)**:
  - buildPayloadFromForm() and buildExportRunConfigObject() now explicitly capture class, class_name, spec, and spec_name from active dropdown selections or getActiveSpecInfo().
  - Added dedicated Export Config action button in the simulator header and Export .JSON in the Save/Export modal for immediate direct JSON download.
  - Automatically suggests clean, spec-aware filenames (e.g. assassin_hatred_config.json) when saving or exporting.
- **Robust Class & Discipline Resolution on Import (tools/simulator_ui.html, src/swtorsim/web_gui.py, tools/web/pyodide_client.js)**:
  - populateSpecsForClass(clsName, targetSpecPath, targetSpecName) now intelligently matches by targetSpecPath or falls back to targetSpecName, resolving discipline selections across different environments (Live vs PTS) or file paths.
  - setupFileImporter now unwraps nested { run_config: ... } / { config: ... } structures and permits schemas with class, class_name, spec, or spec_name.
  - load_run_config_bundle in src/swtorsim/web_gui.py extracts class_name and spec_name directly from the imported run config JSON and populates them into both bundle and raw_rc.
  - Endpoints /api/run_config/save and /api/custom_file/import ensure class and spec metadata are permanently persisted into saved/imported JSON files on disk.
  - In tools/web/pyodide_client.js, fixed /api/run_config/save to export payload.run_config directly without extraneous outer payload wrapper.
- **Standalone Web Release (dist/)**:
  - Rebuilt standalone Web release via build_web_release.py keeping dist/index.html and dist/pyodide_client.js in complete sync.
  - All unit tests and integration tests passing cleanly.
- **Case-Insensitive Class & Spec Select Matching on Import**:
  - Implemented setSelectValueCaseInsensitive() to ensure lowercase values from JSON configs (e.g. 'marauder', 'carnage') properly select uppercase DOM option elements (e.g. 'Marauder', 'Carnage').
  - Updated populateSpecsForClass() to perform case-insensitive key lookup in CATALOG.disciplines and match discipline filenames/slugs case-insensitively.
  - load_run_config_bundle now prefers canonical capitalized discipline blueprint names from gear_opts.
  - Rebuilt dist/ web release.

## [Unreleased] - 2026-11-06: Additive Alacrity Scaling for Stat 274 (`entities.py`)
### Fixed
- **Additive Alacrity Scaling for Stat 274 (`src/swtorsim/entities.py`)**:
  - Implemented `stat_cbt_instant_reduction_percentage` (`274`) as an additive Alacrity percentage buff across both `Player.calculate_gcd` and `Player.calculate_cooldown`.
  - Replaced the flawed multiplicative percentage reduction (`pct_mod -= val`) with `total_alacrity = gear_alacrity + alacrity_bonus`, aligning with SWTOR engine mechanics `time = base / (1.0 + total_alacrity)`.
  - Aligns simulated execution under Berserk with live StarParse combat logs (1.1s GCD and ~8.7s Ferocity cooldown) without artificial DPS inflation.
  - Rebuilt standalone web distribution (`dist/`).

## [Unreleased] - 2026-11-06: Off-Hand Scope Correction for Dual Wield Mastery (Stat 127) (`combat_math.py`, `combat_math_unbucketed.py`)
### Fixed
- **Off-Hand Attack Scoping for Stat 127 (`src/swtorsim/combat_math.py`, `src/swtorsim/combat_math_unbucketed.py`)**:
  - Corrected `STAT_cbt_dual_wield_damage_done_modifier_percentage` (`127`) from erroneously applying a universal x1.25 (+25%) damage multiplier across all hits (including main-hand melee and Force attacks like *Devastating Blast* and *Gore* whenever an off-hand was equipped).
  - Wired `hand = action_data.get("hand", "main")` into `handle_modifiers` and `handle_caster_buffs`, scoping Stat 127 strictly to attacks executed with the off-hand weapon (`hand == "off"`).
  - Scoped `STAT_cbt_dual_wield_accuracy_modifier_fixed` (`126`) in `accuracy_roll` strictly to off-hand attacks (`hand == "off"`).
  - Benchmarked simulated peak hits against live StarParse combat logs on 10M Operations Dummy, showing near 1:1 match across all abilities:
    - *Gore*: 53,123 dmg (Sim) vs 53,013 dmg (Live, 99.8% match)
    - *Dual Saber Throw*: 20,468 dmg (Sim) vs 20,283 dmg (Live, 99.1% match)
    - *Ravage*: 17,029 dmg (Sim) vs 17,264 dmg (Live, 98.6% match)
    - *Vicious Throw*: 91,101 dmg (Sim) vs 95,311 dmg (Live peak crit / 85,128 avg crit)
    - *Devastating Blast*: 79,498 dmg (Sim) vs 86,370 dmg (Live peak crit / 70,641 avg crit)

## [Unreleased] - 2026-11-07: Empirical Verification of Dual Wield Mastery Stat 127 as Additive Offhand Scalar (Test 10)
### Added / Verified
- **Empirical Proof: Dual Wield Mastery Stat 127 Modifies Base Offhand Weapon Scalar (`src/swtorsim/combat_math_unbucketed.py`, `docs/modifier_bucketing_log.md`)**:
  - Empirically verified `STAT_cbt_dual_wield_damage_done_modifier_percentage` (`127`) on Level 80 Carnage Marauder using `Assault` (`abl.flurry.sith_warrior.assault_optimize`) against Operations Training Dummy with Sundered (-20% armor) and Beat Down (+5% melee channel vuln).
  - Observed live in-game offhand hit of **`965`** (alongside MH Strike 1 of `2,208`, MH Flurry 1 crit of `*4,033`, and MH Flurry 2 of `2,215`).
  - Disproved Option A (additive in `BUCKET_1` on 30% base, max possible `857`) and Option B (multiplicative on 30% base, max possible `865`).
  - Proved Option C: Stat 127 is an additive increase directly to the base offhand weapon scalar: `offhand_ratio = 0.30 + val = 0.30 + 0.25 = 0.55` (55%), yielding expected post-mitigation range of `846 – 1,269` which perfectly contains observed hit `965` at an ~28% weapon roll.
  - Implemented in `src/swtorsim/combat_math_unbucketed.py` (`dual_wield_damage_modifier` in `calculate_base_damage` and `handle_caster_buffs`).
  - Logged Test 10 in `docs/modifier_bucketing_log.md` and marked `127` in `docs/modifier_bucketing_master_checklist.md`.

## [Unreleased] - 2026-11-07: Empirical Verification of Target State Bleeding Stat 221 as BUCKET_5 (Test 11)
### Added / Verified
- **Empirical Proof: Target State Bleeding Stat 221 Forms Multiplicative Layer BUCKET_5 (`src/swtorsim/combat_math_unbucketed.py`, `docs/modifier_bucketing_log.md`)**:
  - Empirically verified `STAT_cbt_damage_done_if_target_bleeding_modifier_percentage` (`221`) via *Bloodbath* (+25% damage to *Sweeping Slash* while target is bleeding) on Level 80 Vengeance Juggernaut against Operations Training Dummy with Sundered (-20% armor), Beat Down (+5% melee channel vuln), and Overwhelmed (+10% AoE vuln).
  - Observed clean baseline hit of `8,205` with no bleed active (matching theoretical floor `8,201 – 8,806`).
  - Observed hits while `Bleeding (Shatter)` was active: `10,892` non-crit and `17,757` / `18,102` crits.
  - Disproved Option A (additive in `BUCKET_1`), whose theoretical non-crit ceiling is strictly `10,704` and crit ceiling is strictly `17,700` (`10,892 > 10,704` by 188 points; `18,102 > 17,700` by 402 points).
  - Proved Option B: Stat 221 forms an independent multiplicative conditional bucket (**`BUCKET_5`**), multiplying against `BUCKET_1` (Damage Done/Vulnerabilities) and `BUCKET_2` (AoE Vulnerability) by exactly `1.250000x` (`1.59500x` total multiplier).
  - Locked `BUCKET_5 = "bucket_5"` and routed `221` and `STAT_cbt_damage_done_if_target_bleeding_modifier_percentage` to `BUCKET_5` in `src/swtorsim/combat_math_unbucketed.py`.
  - Logged Test 11 in `docs/modifier_bucketing_log.md` and marked `221` in `docs/modifier_bucketing_master_checklist.md`.
## [Unreleased] - 2026-11-07: Empirical Verification of Caster Type Dealt Scale Energy / Kinetic Stat 395/397 in BUCKET_1 (Test 12)
### Added / Verified
- **Empirical Proof: Caster Type Dealt Scale Energy/Kinetic Pools Additively in BUCKET_1 (`src/swtorsim/combat_math_unbucketed.py`, `docs/modifier_bucketing_log.md`)**:
  - Empirically verified `stat_cbt_damage_dealt_scale_type_energy_modifier_percentage` (`395`) and `kinetic` (`397`) via *High Energy Gas Cylinder* (+7% Energy/Kinetic damage dealt) on Level 80 Advanced Prototype Powertech using `Magnetic Blast` against Operations Training Dummy with all debuffs module active.
  - Active modifiers in BUCKET_1: Power Bracer (+10%), Shock Trooper (+10%), Susceptible Tech (+5%), and HEGC (+7%).
  - Observed live StarParse combat logs: Non-crits `14,783`, `14,921`, `15,014`, `15,107`, `15,118`, `15,217`, `15,271`; Crits `*26,895`, `*27,096`, `*27,423`, `*27,538`.
  - Disproved Option B (separate multiplicative bucket): Option B's theoretical floor is strictly `15,079.0`. Hits `14,783`, `14,921`, and `15,014` are mathematically impossible under Option B.
  - Proved Option A: Stat 395 and 397 pool additively in `BUCKET_1` (`1.3200x` multiplier), perfectly encompassing all crits within expected range `26,788 – 28,072`.
  - Routed `395` and `397` to `BUCKET_1` in `src/swtorsim/combat_math_unbucketed.py`.

## [Unreleased] - 2026-11-07: Empirical Re-Verification of Target State Bleeding Stat 221 on Advanced Prototype Powertech (Test 13)
### Added / Verified
- **Empirical Proof: Target State Bleeding Stat 221 Multiplies as BUCKET_5 with 100.00% Exact Integer Precision (`docs/modifier_bucketing_log.md`, `docs/modifier_bucketing_master_checklist.md`)**:
  - Empirically tested `STAT_cbt_damage_done_if_target_bleeding_modifier_percentage` (`221`) via *Blood Tracker* (+3% damage to bleeding targets) on Level 80 Advanced Prototype Powertech using `Bleeding (Retractable Blade)` (zero variance, Internal damage bypassing armor).
  - Pre-test predictions for single bleed tick: Option A (additive +30%) = `3,578` non-crit / `6,441` crit; Option B (multiplicative BUCKET_5, 1.27 * 1.03 = 1.3081x) = `3,601` (`3,600.8`) non-crit / `6,482` (`6,481.7`) crit.
  - Observed in-game hits: Non-crit tick **`3,601`**, Crit tick **`6,482`** — achieving 100.00% exact integer match to the single unit.
  - Formally locked `221` as verified independent multiplicative layer `BUCKET_5` across both Sith Warrior (Test 11) and Bounty Hunter (Test 13).


## 2026-11-07 — Remove Redundant `TRAINING_DUMMY_ARMOR_DEBUFF_PATH` Constant
- **`src/swtorsim/run_config.py`**: Removed the redundant hardcoded `TRAINING_DUMMY_ARMOR_DEBUFF_PATH` constant in favor of the environment-aware helper `get_training_dummy_armor_debuff_path(env)`.
- **`src/swtorsim/config_load.py`**: Updated top-level imports and `load_training_dummy_armor_debuff()` fallback to call `get_training_dummy_armor_debuff_path()` directly, eliminating duplicate inner imports and ensuring default debuff loading respects the active environment (`live` vs. `pts`).
- **Legacy DebuffModule Cleanup (`data/DebuffModule.json`, `src/swtorsim/config_load.py`, `tools/bundle_pyodide_assets.py`)**: Removed the unused legacy `data/DebuffModule.json` file, dead `load_permanent_effects_from_dict` / `load_permanent_effects_from_json` loaders in `config_load.py`, and its entry in `bundle_pyodide_assets.py`.


## 2026-11-07 — Symmetric `data/extractor/live/` and `data/extractor/pts/` Directory Layout
- **Filesystem Layout (`data/extractor/`)**: Moved Live extracted game data (`parsed/`, `disciplines/`, `extracted/`, `combat_curves.json`, `adrenals.json`, `gear_abilities_talents.json`, `relics.json`) into `data/extractor/live/` as a symmetric peer to `data/extractor/pts/`, while keeping shared Jedipedia caches (`hashes.bin`, `gom.js`, `fnv1a64.js`) at `data/extractor/`.
- **Extractor & Engine Routing (`src/extractor/config.py`, `src/swtorsim/settings.py`, `src/swtorsim/run_config.py`, `src/swtorsim/combat_curves.py`, `src/swtorsim/class_buffs.py`)**:
  - Updated `get_extractor_data_dir()` to return `Path("data/extractor/live")` for `"live"` and `Path("data/extractor/pts")` for `"pts"`.
  - Added `resolve_env_extractor_path(path_str, env)` in `run_config.py` to cleanly map between `data/extractor/live/` and `data/extractor/pts/` (while maintaining backwards compatibility with legacy `data/extractor/disciplines/` paths).
- **Web GUI, Rotation Builder, & WebAssembly Release (`src/swtorsim/web_gui.py`, `data/rotation_builder.py`, `tools/bundle_pyodide_assets.py`, `tools/simulator_ui.html`, `tools/rotation_builder_ui.html`)**: Replaced asymmetric ternary path branches with `get_extractor_data_dir(env)`, `get_disciplines_dir(env)`, `get_gear_path(env)`, `get_relics_path(env)`, and `resolve_env_extractor_path()`, and rebuilt `dist/swtorsim_assets.zip`.
