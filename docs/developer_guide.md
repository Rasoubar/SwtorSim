# SwtorSim Developer & Contributor Guide

This handbook covers the core architectural invariants, file routing, and step-by-step workflows for extending **SwtorSim** with new mechanics, stat modifiers, action handlers, conditions, and class disciplines.

---

## 1. Core Simulation Invariants (`AGENTS.md`)

All contributions must strictly adhere to the project's architectural rules defined in [`AGENTS.md`](../AGENTS.md). This section is a summary; if it ever disagrees with `AGENTS.md`, `AGENTS.md` wins.

1. **Combat Math Formulas Are Frozen**:
   - **NEVER** modify, "fix", or replace any combat math formula (damage, buckets, mitigation, accuracy, crit chance, crit multiplier / supercrit, DR curves, alacrity/timing scaling). They have passed extensive testing against live SWTOR combat logs. See `AGENTS.md` §1 for the exact scope.
2. **No Magnitude Heuristics (`mod.is_percent`)**:
   - Strictly honor `mod.is_percent` and the parsed blueprint structure.
   - All percentage values in parsed blueprints are canonical decimal fractions (`0.05` = `5%`). Never write magnitude heuristics such as `val / 100.0 if abs(val) > 1.0 else val`.
3. **Authoritative GOM Stat IDs**:
   - Always cross-reference stat IDs against [`src/extractor/mod_stats.py`](../src/extractor/mod_stats.py) and the maintainer's `Stat_IDs.xlsx` sheet (not stored in the repo). Never invent or guess unverified stat IDs.
4. **Ability Stem Matching Toggle**:
   - Any FQN stem matching (such as matching `assassinate` to `assassinate_plus`) must respect [`is_stem_matching_enabled()`](../src/swtorsim/settings.py#L40-L42).
5. **Terminal Codepage & Line Endings**:
   - Use ASCII status tags (`[OK]`, `[WARN]`, `[FAIL]`) in console output instead of Unicode emojis so Windows `cp1252` terminals never crash.
   - Preserve Windows CRLF (`\r\n`) line endings across all repository files.
6. **Catalog & State Hygiene**:
   - Whenever new actions, conditions, triggers, or stats are modeled, update `tools/catalog_game_data.py` and re-run it to regenerate `data/catalog_summary.md`. **Note:** that tool is currently missing from the repo; skip this step until it is restored.

---

## 2. Architectural Routing Quick-Reference

Before searching across multiple files, use this routing table (see [`ARCHITECTURE.md`](../ARCHITECTURE.md) for the full map):

| Subsystem | Target File | Key Symbols |
| :--- | :--- | :--- |
| **Event Queue & Clock** | [`src/swtorsim/engine.py`](../src/swtorsim/engine.py) | `SimulationEngine`, `schedule_relative`, `schedule_absolute`, `run_timed` |
| **Simulation Hydration** | [`src/swtorsim/setup.py`](../src/swtorsim/setup.py) | `prepare_simulation`, `build_proc_registry`, `schedule_periodic` |
| **Loadout & Raid Debuffs** | [`src/swtorsim/config_load.py`](../src/swtorsim/config_load.py) | `load_from_run_config`, `load_training_dummy_armor_debuffs`, `_DUMMY_DEBUFF_ROUTING` |
| **Character Stats & Time Scaling** | [`src/swtorsim/entities.py`](../src/swtorsim/entities.py) | `Entity`, `Player`, `Dummy`, `recalculate_stats`, `scale_time_modifier`, `apply_effect`, `proc_registry` |
| **Combat Math & 6 Buckets** | [`src/swtorsim/combat_math.py`](../src/swtorsim/combat_math.py) | `calculate_hit`, `handle_modifiers`, `handle_caster_buffs`, `handle_target_debuffs`, `calculate_base_damage`, `handle_mitigation`, `calculate_crit`, `accuracy_roll` |
| **Stat Modifier Normalization** | [`src/swtorsim/modifiers.py`](../src/swtorsim/modifiers.py) | `Modifier`, `normalize_stat_name`, `applies_to`, `_ability_stem` |
| **Abilities, Effects & Actions** | [`src/swtorsim/abilities.py`](../src/swtorsim/abilities.py) | `AbilityBlueprint`, `Effect`, `Branch`, `Ability`, `execute_single_action`, `handle_*` |
| **Runtime Buffs, DoTs, Channels** | [`src/swtorsim/effects.py`](../src/swtorsim/effects.py) | `ActiveEffect`, `ActiveDot`, `ActiveChannel` |
| **Timeline Events** | [`src/swtorsim/events.py`](../src/swtorsim/events.py) | `PlayerReady`, `DamageHit`, `DotTick`, `ChannelTickEvent`, `CastFinishEvent`, `EffectExpire`, `ProjectileImpactEvent`, `DelayedBranchEvent` |
| **Conditions & Requirements** | [`src/swtorsim/requirements.py`](../src/swtorsim/requirements.py) | `validate_all`, `CONDITION_REGISTRY`, `check_proc_cooldown_above`, `check_*` |
| **Reactive Proc Event Bus** | [`src/swtorsim/triggers.py`](../src/swtorsim/triggers.py) | `TriggerManager`, `subscribe`, `get_remaining_icd`, `dispatch` |
| **Primary Resource Pools** | [`src/swtorsim/resources.py`](../src/swtorsim/resources.py) | `ResourcePool`, `StandardPool`, `HeatPool`, `EnergyPool`, `BuilderPool` |
| **Rotation Evaluator** | [`src/swtorsim/rotation.py`](../src/swtorsim/rotation.py) | `Rotation`, `FixedAbilityStep`, `PriorityBlockStep`, `OptionalAbilityStep` |

---

## 3. Step-by-Step Developer Workflows

### 3.1 Adding or Routing a GOM Stat Modifier

When a talent, buff, debuff, or implant modifies a stat (`stat_changes` or `initializers`):

1. **Verify the GOM Stat ID**:
   - Look up the numeric ID and enum name in [`src/extractor/mod_stats.py :: EMBEDDED_STAT_LABELS`](../src/extractor/mod_stats.py#L12-L490) and `Stat_IDs.xlsx`.
2. **Determine Where the Stat Applies**:
   - **Global Character Sheet Stat** (e.g., Mastery, Power, Alacrity, Accuracy, Base Crit, Bonus Damage):
     - Add alias mapping in [`src/swtorsim/modifiers.py :: STAT_ALIASES`](../src/swtorsim/modifiers.py#L8-L55) if it maps to a sheet stat, and ensure [`Player.recalculate_stats()`](../src/swtorsim/entities.py#L220-L335) accumulates it when `not mod.targets`.
     - Add the raw stat name to `_SKIP_BASE_STATS` in [`combat_math.py`](../src/swtorsim/combat_math.py#L183-L201) so untargeted sheet stats aren't double-counted on each hit.
   - **Ability Timing / Resource Cost Stat** (e.g., Cooldown, Cast Time, Channel Duration, Tick Interval, Resource Cost, Resource Regen):
     - Route in the corresponding `Player.calculate_*` method in [`src/swtorsim/entities.py`](../src/swtorsim/entities.py#L350-L535) (`calculate_cooldown`, `calculate_cast_time`, `calculate_channel_duration`, `calculate_effect_duration`, `calculate_effect_tick`, `calculate_resource_cost`, `calculate_resource_regen`).
   - **Per-Hit Damage / Crit / Surge / Armor Pen Modifier**:
     - If it is a caster buff, add it to `_CASTER_DAMAGE_DISPATCH`, `_CRIT_CHANCE_DISPATCH`, or `_CRIT_DAMAGE_DISPATCH` in [`src/swtorsim/combat_math.py`](../src/swtorsim/combat_math.py#L74-L181) under the appropriate bucket (`BUCKET_NORMAL`, `BUCKET_EXECUTE`, `BUCKET_CHANNEL`, `BUCKET_DAMAGE_TYPE`, `BUCKET_TAG`, or `BUCKET_TARGET_STATE`).
     - If it is a target debuff, route it in [`handle_target_debuffs()`](../src/swtorsim/combat_math.py#L334-L645).
3. **Update the Catalog & Add a Unit Test**:
   - Register the stat in `tools/catalog_game_data.py` (currently missing from the repo) and add a unit test under [`tests/`](../tests/).

---

### 3.2 Adding a New Action Handler

When a parsed ability branch contains an `action_type` not yet handled in [`abilities.py :: execute_single_action`](../src/swtorsim/abilities.py#L459-L535):

1. Write a dedicated `handle_<action_name>(sim, caster, target, action, ...)` function in [`src/swtorsim/abilities.py`](../src/swtorsim/abilities.py).
2. Add the `elif action_type == "<action_name>":` branch in `execute_single_action()`.
   - If the action is a visual/positional/PVP-only effect that has no impact on PvE dummy DPS, add it to `NOOP_ACTION_TYPES` (`abilities.py` lines 423–456).
3. Update `HANDLED_ACTIONS` / `NOOP_ACTIONS` in `tools/catalog_game_data.py` (currently missing from the repo) and add a test in [`tests/test_ability_execution.py`](../tests/test_ability_execution.py).

---

### 3.3 Adding a New Condition Evaluator

All blueprint and rotation conditions are dispatched through [`src/swtorsim/requirements.py :: CONDITION_DISPATCH`](../src/swtorsim/requirements.py#L540-L605):

1. Implement a `check_<condition_name>(data, caster, target, sim=None, context=None, **_kwargs) -> bool` function in [`src/swtorsim/requirements.py`](../src/swtorsim/requirements.py).
   - Note that blueprint conditions (`cbtRequirement*` / `effRequirement*`) may include `"negated": True` inside `data`; `validate_all()` automatically inverts the return value when `data.get("negated")` is `True` (unless the handler is listed in `_SELF_NEGATING_HANDLERS`).
2. Register the condition key in `CONDITION_DISPATCH`.
3. Add a unit test in [`tests/requirements_test.py`](../tests/requirements_test.py) and update `tools/catalog_game_data.py` (currently missing from the repo).

---

### 3.4 Onboarding a New Class Discipline

Because all disciplines, abilities, talents, tacticals, and legendary implants are already extracted into `data/extractor/`, onboarding a new playable spec requires only:

1. **Verify Class Resource Pool Mapping** ([`src/swtorsim/resources.py`](../src/swtorsim/resources.py#L154-L172)):
   - Check `CLASS_RESOURCE_MAP` in `resources.py` and `prepare_simulation` in `setup.py` to ensure the class maps to the right pool (`Force`, `Energy`, `Heat`, or `Rage`/`Focus`) and max resource (`500`/`600` Force for Sorcerer/Sage, `100` Force for Assassin/Shadow, `100` Energy/Heat, `12` Rage/Focus).
2. **Create a Character Stats Profile (`data/builds/<spec>_stats.json`)**:
   - Add sheet ratings (`Mastery`, `Power`, `Critical Rating`, `Alacrity Rating`, `Accuracy Rating`, `Weapon Damage Min`, `Weapon Damage Max`, `Force/Tech Bonus`, and `Offhand Damage Min`/`Max` for dual-wield specs).
3. **Create a Skill Tree Choices File (`data/choices/<spec>_choices.json`)**:
   - Specify `"option_1"`, `"option_2"`, or `"option_3"` for each tier (`level_23` through `level_73`).
4. **Build a Rotation (`data/rotations/<spec>_rotation.json`)**:
   - Launch `.\.venv\Scripts\python.exe data/rotation_builder.py --ui`, select the new discipline and choices, and construct the opener and priority list.
5. **Validate Against a Live Combat Log**:
   - Run a single `TEST` simulation (`run_sim.py --config ...`) and compare hit sizes, tick counts, and buff uptimes against a live StarParse log. (The log tools `tools/parse_combat_log.py` and `tools/validate_modifiers_vs_log.py` are currently missing from the repo.)

---

## 4. Testing & Verification Protocol

Run the full test suite before finalizing any change:

```powershell
# Run all unit and integration tests (unittest; pytest is not installed)
.\tools\pyclean.exe -m unittest discover -s tests -p "*test*.py"
```

The coverage catalog tool (`tools/catalog_game_data.py`) is currently missing from the repo.

### Test Suite Overview (`tests/`)

| Test File | Coverage |
| :--- | :--- |
| [`tests/test_ability_execution.py`](../tests/test_ability_execution.py) | Blueprint hydration, instant/cast/channel execution, projectiles, stack charges, cooldown reductions, immunities, and action handlers. |
| [`tests/requirements_test.py`](../tests/requirements_test.py) | All 36 condition evaluators (`CONDITION_DISPATCH`), negation handling, stack comparisons, and rotation rules. |
| [`tests/test_simulation_integration.py`](../tests/test_simulation_integration.py) | Full-fight deterministic and Monte Carlo integration tests across disciplines (Hatred, Madness, Annihilation, etc.). |