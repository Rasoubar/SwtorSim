# SwtorSim Architectural Routing Map

## 1. Module Directory & Responsibility Map (`src/swtorsim/`, `src/extractor/`, `tools/`)

| Module | Responsibility | Primary Classes & Functions |
|---|---|---|
| `swtorsim/engine.py` | Event heap & simulation clock (fight duration counts from first damage; pre-combat excluded) | `Simulation :: schedule_relative, schedule_absolute, run_timed, run_until, _stop_time, time_origin, relative_time, log, flush_log`; `sim_log` (all verbose console lines; fight-relative times) |
| `swtorsim/setup.py` | Loadout wiring, passive init, proc registry & tactical swaps | `prepare_simulation, build_proc_registry, schedule_periodic, swap_tactical, prepare_tactical_swaps, validate_tactical_for_class, validate_pre_combat_rules` |
| `swtorsim/entities.py` | Actors, stats, timers, immunities | `Entity :: apply_effect, cleanup_expired_effects, has_immunity`; `Player :: recalculate_stats, calculate_gcd, calculate_cast_time, calculate_channel_duration, calculate_cooldown, calculate_resource_cost, calculate_resource_regen, calculate_effect_duration, calculate_effect_tick, break_stealth, proc_registry`; `Dummy :: recalculate_stats, hp_ratio` |
| `swtorsim/class_buffs.py` | Universal class buffs & hidden permanent bonus (+1% acc/crit chance/crit mult) | `apply_class_buffs, load_class_buff_effects, HIDDEN_BONUSES` |
| `swtorsim/abilities.py` | Cast lifecycle, targeting, actions | `Ability :: can_cast, cast, _start_channel, apply_cooldown_locks, schedule_recharge`; `Effect :: execute, execute_triggered_branches`; `Branch :: execute`; `execute_single_action, handle_*` |
| `swtorsim/effects.py` | Buff, DoT, and channel state | `ActiveEffect :: from_effect, from_effect_node, _resolve_branch_modifiers, get_effective_modifiers, modify_stacks, set_stacks`; `ActiveChannel, ActiveDot` |
| `swtorsim/events.py` | Queued event resolution & pre-combat sequencing | `AbilityCast, CastFinishEvent, ChannelTickEvent, ProjectileImpactEvent, DamageHit, ApplyDamageLand, DotTick, EffectExpire, ResourceTick, PlayerReady, PreCombatEvent :: resolve`; `PreCombatRunner :: run, request, finish, _pull_gate_open`; `schedule_next_decision, is_pre_combat_active, PullConditionsNotMetError` |
| `swtorsim/combat_math.py` | Hit math, DR curves, buckets, crits (formulas FROZEN, see `AGENTS.md` §1) | `calculate_hit, calculate_base_damage, handle_modifiers, handle_caster_buffs, handle_target_debuffs, handle_mitigation, calculate_crit, accuracy_roll, calc_dr` |
| `swtorsim/combat_curves.py` | Level 80 curves & armor constants | `player_standard_health, derived_stat, armor_constants` |
| `swtorsim/modifiers.py` | Stat ID mapping & target filters | `Modifier :: applies_to, from_stat_change, from_modify_stat, from_modify_meta_stat, from_conditional_stat_mod`; `resolve_stat` |
| `swtorsim/requirements.py` | Condition evaluation (36/36 types) | `validate_all, evaluate_extracted_conditions, evaluate_logic, evaluate_single_extracted_condition, check_proc_cooldown_above, entity_has_effect, get_entity_effect_stacks` |
| `swtorsim/triggers.py` | Proc subscriptions, ICDs, dispatch | `TriggerManager :: subscribe, unsubscribe, get_remaining_icd, dispatch` |
| `swtorsim/resources.py` | Resource pools & passive regen | `ResourcePool, StandardPool, HeatPool, EnergyPool, BuilderPool :: can_afford, spend, generate, tick_passive_regen` |
| `swtorsim/rotation.py` | Priority list & step evaluation; loop-only `weave` list (entries tried like optional steps before every step after `loop_anchor`) | `Rotation :: evaluate, get_next_lead_time, build_weave, pending_weave_step`; `PriorityBlockStep, FixedAbilityStep, OptionalAbilityStep :: evaluate` |
| `swtorsim/config_load.py` | Loadout & JSON hydration | `load_from_run_config, load_complete_loadout` |
| `swtorsim/run_config.py` | Run config schema & validation | `RunConfig, load_run_config, validate_run_config, normalize_pre_combat` |
| `swtorsim/settings.py` | Global simulation toggles | `is_stem_matching_enabled, is_projectile_flight_time_enabled, is_in_flashpoint_operation` |
| `swtorsim/metrics.py` | Telemetry & damage breakdown | `Metrics :: log_damage, log_effect_applied, print_metrics` |
| `swtorsim/tester.py` | Single-run & Monte Carlo runner | `Tester :: run_test, run_monte_carlo` |
| `extractor/abilities.py` | GOM ability/effect/action decoder | `build_abilities, _decode_effect, _decode_branch, _decode_action, _decode_condition, _decode_trigger` |
| `extractor/talents.py` | Talent stat change extractor | `build_talents, _parse_stat_change` |
| `extractor/disciplines.py` | Discipline APC tree builder | `build_disciplines, _apply_replacements` |
| `extractor/mod_stats.py` | GOM stat ID enum decoder | `load_stat_labels, decode_stat_name` |
| `extractor/eff_triggers.py` | GOM trigger enum decoder | `load_trigger_labels, decode_trigger_name` |
| `tools/catalog_game_data.py` (MISSING from repo) | Blueprint coverage auditor | `run_catalog, format_report` |
| `tools/parse_combat_log.py` (MISSING from repo) | Live combat log parser | `parse_log_file, analyze_fight` |
| `data/rotation_builder.py` | Local Web UI & CLI rotation builder | `discover_loadout_catalog, normalize_rotation_steps, normalize_pre_combat_steps, normalize_weave_steps, normalize_pull_gate, build_rotation_file_data, class_tactical_fqns, run_dry_run_preview, launch_web_builder` (serves `/` = builder UI, `/timeline[.html]` = Cast Timeline) |
| `tools/rotation_builder_ui.html` | Rotation Builder page (incl. Visual Map tab) | `renderTimeline` (step editor), `renderPreCombat`, `renderWeave` (Always Weave panel), `renderRightPanel`, `renderVisualMapHtml, vizSelectStep, vizStatePayload, openCastTimelineWindow` (BroadcastChannel `swtorsim-cast-timeline`) |
| `tools/rotation_timeline_ui.html` | Pop-out Cast Timeline window (builder dry-run, or simulator single run with `?source=sim`) | `buildModel, draw, renderDetail, setSelected` (channel `swtorsim-cast-timeline[-sim]`; messages: `hello`/`select` out; `state`/`stale`/`select` in) |
| `tools/rotation_map_ui.html` | Pop-out Rotation Map window for the builder (horizontal; Opener / Loop lanes; off-GCD steps hang below the arrow where they fire; weave list as a strip above the Loop lane) | `render, laneHtml, weaveHtml, stepHtml, applySelection` (channel `swtorsim-rotation-map`; messages: `hello`/`goto` out; `state`/`select` in; builder side `vizMapPayload, openVisualMapWindow`) |
| `swtorsim/cast_timeline.py` | Display-only per-cast recorder for the Cast Timeline (step, phase `pre_combat` / `rotation` / `weave`, buffs, cast/channel timing) | `CastTimelineRecorder.install/finalize/ability_maps, rotation_steps_of, ability_name_to_slug` |
| `swtorsim/web_gui.py` | Local Web GUI simulator dashboard & REST API | `get_simulator_catalog, preview_character_stats, execute_simulation_from_payload, launch_web_simulator, execute_simulation_slice, aggregate_batch_slices, request_simulation_cancel` (cancel: `POST /api/simulate_cancel`; TEST result carries `cast_timeline`; serves `/timeline[.html]`) |
| `swtorsim/pyodide_bridge.py` | Pyodide WASM in-memory action dispatcher | `dispatch :: GET_CATALOG, GET_CLASS_GEAR, LOAD_RUN_CONFIG, PREVIEW_STATS, SIMULATE, SIMULATE_SLICE, AGGREGATE_BATCH` |
| `tools/web/pyodide_client.js` | Multi-core Web Worker pool & fetch interceptor | `executeBatchMultiCore, cancelActiveSimulation, ensureAllWorkersReady, setTargetPoolSize, updateCoreSelectorUI, updateBackendBadge` |
| `tools/web/sim_worker.js` | Dedicated Pyodide 0.27.2 Web Worker runner | Web Worker bootstrapping, virtual MEMFS unpack, progress dispatch |
| `tools/bundle_pyodide_assets.py` | Asset bundler for browser distribution | `build_bundle` (compresses engine & blueprints into `dist/swtorsim_assets.zip`) |
| `tools/build_web_release.py` | One-command static web release compiler | Bundles assets, copies worker scripts, injects client bridge into `dist/` |

## 2. End-to-End Execution Lifecycle (Call Flow)

0. **Pre-combat (optional)**: `setup.py :: prepare_simulation` builds `events.py :: PreCombatRunner` from `normalize_pre_combat` steps (`ability` / `swap_tactical` / `wait` / `wait_until`) plus optional `pull_conditions` (fight-start gate; unmet after `pull_max_wait` raises `PullConditionsNotMetError`). Every cast/channel completion calls `events.py :: schedule_next_decision`, which resumes the runner (channels finish, rotation blocked) until `PreCombatRunner.finish` schedules the first `PlayerReady`. Tracer/report times are relative to T0 = first damage (pre-combat negative).
1. `abilities.py :: Ability.can_cast` -> Checks cast/channel lockouts, GCD/cooldowns, charges, cost (`Player.calculate_resource_cost`), and conditions (`requirements.py :: validate_all`).
2. `abilities.py :: Ability.cast` -> Spends resources/charges, locks timers (`Ability.apply_cooldown_locks`), breaks stealth (`Player.break_stealth`), dispatches `on_ability_activate` (`TriggerManager.dispatch`), and routes:
   - **Instant**: Calls `Ability.execute_effect` and dispatches `on_ability_post_activate`.
   - **Cast**: Sets `caster.active_cast`, schedules `events.py :: CastFinishEvent.resolve`.
   - **Channel**: Calls `Ability._start_channel`, sets `ActiveChannel`, runs `on_apply`, schedules `events.py :: ChannelTickEvent.resolve`.
3. `abilities.py :: Effect.execute` -> Validates conditions (`validate_all`) and immunity (`Entity.is_immune_to_effect`); routes persistent effects to `entities.py :: Entity.apply_effect` or instant effects to `Branch.execute`.
4. `abilities.py :: execute_single_action` -> Dispatches branch actions to `handle_*` functions (`handle_damage_action, handle_invoke_projectile, handle_ability_cancel, handle_grant_immunity, handle_set_effect_stack_charge, handle_custom_action`).
5. `events.py :: ProjectileImpactEvent.resolve` -> Delays impact by `distance / (speed * 10.0)` when enabled, then runs `Effect.execute_triggered_branches("on_travel_complete")`.
6. `events.py :: DamageHit.resolve` -> Rolls `combat_math.py :: accuracy_roll` (misses abort branch), computes damage via `combat_math.py :: calculate_hit`, dispatches `on_pre_damage_dealt` / `on_pre_damage_taken`, schedules `ApplyDamageLand`.
7. `events.py :: ApplyDamageLand.resolve` -> Deducts `target.hp`, logs `Metrics.log_damage`, and dispatches `on_damage_dealt, on_damage_taken, on_pre_death, on_death, on_kill` via `triggers.py :: TriggerManager.dispatch`.

## 3. Combat Math & Modifier Routing (`combat_math.py`, `modifiers.py`, `entities.py`)

- **Base Stat Recalculation**: `entities.py :: Player.recalculate_stats` aggregates untargeted `Modifier` records and DR curves (`combat_math.py :: calc_dr`).
- **Hit-Time Modifiers**: `combat_math.py :: calculate_hit` runs `handle_modifiers` (`handle_caster_buffs`, `handle_target_debuffs`), `calculate_base_damage`, `handle_mitigation`, `calculate_crit`, and `accuracy_roll`.
- **Dispatch Tables**: `_CASTER_DAMAGE_DISPATCH` (61 stat keys), `_CRIT_CHANCE_DISPATCH` (9 keys), `_CRIT_DAMAGE_DISPATCH` (9 keys), `_SKIP_BASE_STATS`.
- **6 Damage Buckets**: `normal_percentage`, `channel_scaling`, `damage_type_scaling`, `tag_scaling`, `target_state`, `sub_30`.

## 4. State, Effects, & Triggers (`effects.py`, `triggers.py`, `requirements.py`, `resources.py`)

- **Effects**: `entities.py :: Entity.apply_effect` builds `effects.py :: ActiveEffect.from_effect`, scales stacks (`60`/`61`), duration (`44`), and tick rate (`45`), subscribes triggers (`TriggerManager.subscribe`), runs `on_apply`/`on_refresh`, and schedules `events.py :: DotTick` & `EffectExpire`.
- **Stacks & Immunities**: `ActiveEffect.modify_stacks` (dispatches `on_stack_charge_increased/decreased`) vs `ActiveEffect.set_stacks` (silent cap); `Entity.immunities` unions `_base_immunities` and effect `immunities`.
- **Conditions & Triggers**: `requirements.py :: evaluate_single_extracted_condition` & `evaluate_logic` evaluate 36 conditions; `check_proc_cooldown_above` queries `Player.proc_registry` (built by `setup.py :: build_proc_registry`) for authoritative `lockout_effect` and `trigger_icd` mappings; `triggers.py :: TriggerManager.dispatch` filters `spell_type, attack_type, weapon_mode`, tags, ICD (`229`), and proc chance (`228`).

## 5. "Where to Look" Quick-Reference Routing Table

| Task | Target `file.py :: Class.method` |
|---|---|
| Adding a new stat ID | `combat_math.py :: _CASTER_DAMAGE_DISPATCH, _CRIT_CHANCE_DISPATCH, _CRIT_DAMAGE_DISPATCH, handle_target_debuffs` |
| Adding a base / rating stat | `entities.py :: Player.recalculate_stats` & `combat_math.py :: _SKIP_BASE_STATS` |
| Debugging cooldown / GCD / Alacrity scaling | `entities.py :: Player.calculate_cooldown, calculate_gcd, calculate_cast_time, calculate_channel_duration` |
| Debugging DoT duration / tick / charge scaling | `entities.py :: Player.calculate_effect_duration, calculate_effect_tick, calculate_ability_max_charges` |
| Adding / fixing an action handler | `abilities.py :: execute_single_action, handle_<action>` |
| Fixing a condition check | `requirements.py :: evaluate_single_extracted_condition, evaluate_logic` |
| Debugging proc triggers / ICDs | `triggers.py :: TriggerManager.dispatch` & `events.py :: DamageHit.resolve` |
| Updating blueprint extraction | `extractor/abilities.py :: _decode_action, _decode_branch, _is_redundant_self_aoe_branch` |
| Updating catalog coverage (tool MISSING from repo) | `tools/catalog_game_data.py :: IMPLEMENTED_ACTIONS, IMPLEMENTED_CONDITIONS, IMPLEMENTED_STATS, IMPLEMENTED_TRIGGERS` |
| Debugging pre-combat order / tactical swaps | `events.py :: PreCombatRunner.run, schedule_next_decision` & `setup.py :: swap_tactical` |
| Debugging in-browser WASM simulation / worker slices | `tools/web/pyodide_client.js :: executeBatchMultiCore` & `src/swtorsim/pyodide_bridge.py :: dispatch` |
| Updating Pyodide runtime assets or web release build | `tools/bundle_pyodide_assets.py :: build_bundle` & `tools/build_web_release.py` |
