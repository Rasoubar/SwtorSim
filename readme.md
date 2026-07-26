# SWTOR Combat Simulator

A multithreaded, event-driven combat simulator for *Star Wars: The Old Republic* (SWTOR). This tool simulates rotation loops, ability usage, passive procs, damage mitigation, and resource pools to analyze character performance through single test runs or parallelized Monte Carlo simulations.

---

## 🛠️ Execution Pipeline & Architecture

### Section 1: Data Ingestion & In-Memory Loading

* **1. Prompt for chosen spec to get file locations.**
  * **Top-Level Handler:** `cli.select_loadout_paths()`
  * **Functions Called:** 
    * `cli.prompt_menu_choice()`

* **2. Prompt & Extract Optional Choices**
  * **Top-Level Handler:** `cli.prompt_optional_choices()`
  * **Functions Called:** 
    * `cli.draft_choices()`
      * `config_load.load_json_file()`
      * `cli._process_item_additions()`

* **3. Load Character Stats**
  * **Top-Level Handler:** `config_load.load_character_stats_from_json()`
  * **Functions Called:** 
    * `config_load.load_json_file()`

* **4. Load Rotation Sequence**
  * **Top-Level Handler:** `config_load.load_rotation_from_json()`
  * **Functions Called:** 
    * `config_load.load_json_file()`

* **5. Load Abilities, Procs, and Effects**
  * **Top-Level Handler:** `config_load.build_complete_loadout()`
  * **Functions Called:** 
    * **5.1 - Load Base Files:**
      * `config_load.load_abilities_from_json()` $\rightarrow$ `config_load.load_abilities_from_dict()`
      * `config_load.load_procs_from_json()` $\rightarrow$ `config_load.load_procs_from_dict()`
      * `config_load.load_permanent_effects_from_json()` $\rightarrow$ `config_load.load_permanent_effects_from_dict()`
    * **5.2 - Merge Choices with Base Loadout:**
      * `config_load.load_abilities_from_dict()`
      * `config_load.load_procs_from_dict()`
      * `config_load.load_permanent_effects_from_dict()`

---

### Section 2: Post-Data Simulation Preparation

* **1. Instantiate Core Simulation Entities**
  * **Top-Level Handler:** `setup.prepare_simulation()`
  * **Actions:**
    * Deep-copies `abilities_db` to isolate ability state per simulation.
    * Instantiates `Player` entity with class name and abilities.
    * Instantiates `Dummy` target entity with specified HP (`dummy_hp`).
    * Merges custom stat dictionary into `player.base_stats`.
    * Instantiates the core `Simulation` event engine.

* **2. Bind Databases and Recalculate Player State**
  * **Top-Level Handler:** `setup.prepare_simulation()`
  * **Actions:**
    * Deep-copies and assigns `procs_db` to `player.procs`.
    * Deep-copies and assigns `buffs_db` to `player.effects`.
    * Calls `player.recalculate_stats()` to compute final baseline attributes.

* **3. Apply Pre-Simulation Static Modifications**
  * **Top-Level Handler:** `setup.prepare_simulation()`
  * **Functions Called:** 
    * `setup.pre_sim_effects()`
  * **Actions:**
    * Scans player passive effects for cooldown modifications (e.g., CDR) and applies adjustments directly to matching abilities in `ability_db`.
    * Scans for max charge modification effects and increases ability max/current charges.

* **4. Attach Rotation Engine**
  * **Top-Level Handler:** `setup.prepare_simulation()`
  * **Actions:**
    * Instantiates `Rotation` using `rotation_config` steps and attaches it to `player.rotation`.

* **5. Schedule Initial Simulation Events**
  * **Top-Level Handler:** `setup.prepare_simulation()`
  * **Functions Called:**
    * `setup.schedule_periodic()`
  * **Actions:**
    * Schedules `PlayerReady` event at `t = 0.0`.
    * Finds all `periodic` trigger procs and schedules their initial `PeriodicProcTick` at a randomized offset between `0.0` and `ICD`.
    * Schedules initial `ResourceTick` event at a randomized offset between `0.0` and `1.0`.

* **6. Execute Simulation Run**
  * **Top-Level Handler:** `Tester.run_test()` or `Tester.run_monte_carlo()`
  * **Functions Called:**
    * `sim.run_timed()`
    * `Tester.execute_single_worker_task()` (for parallel Monte Carlo execution)

---

### Section 3: Core Event Engine Loop

* **1. Initialize Event Engine Loop**
  * **Main Handler:** `Simulation.run_timed()`
  * **Functions Called:** 
    * `heapq.heappop()`
    * `Event.resolve()`
  * **Actions:**
    * Pops priority events ordered by absolute timestamp and sequence ID from the priority queue.
    * Advances `sim.current_time` to match the event's timestamp.
    * Calls `event.resolve(sim)` for execution.
    * Terminates loop when the queue empties, the configured fight duration is reached, or target HP drops to $\le 0$.

* **2. Evaluate Rotation & Decision State**
  * **Main Handler:** `PlayerReady.resolve()`
  * **Functions Called:** 
    * `Rotation.evaluate()`
      * `FixedAbilityStep.evaluate()` / `PriorityBlockStep.evaluate()` / `OptionalAbilityStep.evaluate()`
        * `Ability.cast()`
    * `Simulation.schedule_absolute()` / `Simulation.schedule_relative()`
  * **Actions:**
    * Evaluates active step in the rotation sequence against character state, energy, GCD lockouts, and target conditions.
    * **If Cast Succeeds:** Advances rotation step pointer and schedules the next `PlayerReady` event at `max(current_time, player.next_gcd)`.
    * **If Blocked/Waiting:** Re-schedules `PlayerReady` to retry $0.1\text{s}$ later.

* **3. Cast & Ability Execution Processing**
  * **Main Handler:** `Ability.cast()`
  * **Functions Called:** 
    * `Ability.can_cast()`
    * `ResourcePool.spend()`
    * `Ability.apply_cooldown_locks()`
    * `Ability.evaluate_on_cast_procs()`
    * `abilities.execute_single_action()`
  * **Actions:**
    * Validates ability GCD, resource cost, cooldown, charges, and conditions.
    * Interrupts active channel if a new ability is cast during channeling.
    * Spends resource cost, updates player's `next_gcd`, applies cooldown/charge consumption, and triggers `cast` procs.
    * Loops over defined actions (`damage`, `dot`, `channel`, `buff`, `debuff`, etc.) and executes them.

* **4. Action Handling & Sub-Event Dispatching**
  * **Main Handler:** `abilities.execute_single_action()`
  * **Functions Called:**
    * `abilities.handle_damage_action()` $\rightarrow$ `combat_math.accuracy_roll()` $\rightarrow$ schedules `DamageHit`
    * `abilities.handle_dot_action()` $\rightarrow$ instantiates `ActiveDot` $\rightarrow$ schedules `DotTick`
    * `abilities.handle_channel_action()` $\rightarrow$ instantiates `ActiveChannel` $\rightarrow$ schedules `ChannelTickEvent`
    * `abilities.handle_buff_action()` / `handle_debuff_action()` $\rightarrow$ `Entity.apply_effect()` $\rightarrow$ schedules `EffectExpire`
    * `abilities.handle_resource_gain_action()` $\rightarrow$ schedules or resolves `ResourceGainEvent`
    * `abilities.handle_cooldown_modification()` $\rightarrow$ modifies active cooldowns
    * `abilities.handle_restore_charge()` $\rightarrow$ `Ability.restore_charge()`

  * **4.A. Combat Math & Damage Resolution**
    * **Main Handler:** `DamageHit.resolve()`
    * **Functions Called:** 
      * `combat_math.calculate_hit()`
        * `combat_math.handle_modifiers()` $\rightarrow$ `handle_caster_buffs()`, `handle_target_debuffs()`, `consume_charges()`
        * `combat_math.calculate_base_damage()`
        * `combat_math.handle_mitigation()`
        * `combat_math.calculate_crit()`
      * `ApplyDamageLand.resolve()` (scheduled or instant)
        * `Metrics.log_damage()`
      * `DamageHit.evaluate_on_hit_procs()`
    * **Actions:**
      * Computes raw base damage, applies buff/debuff buckets, armor mitigation/penetration, and crit rolls.
      * Schedules `ApplyDamageLand` after `impact_delay` (or resolves immediately).
      * Deducts target HP and logs hit/damage/crit metrics to `Metrics` tracker.
      * Evaluates eligible `hit` or `crit` procs and executes their associated actions.

  * **4.B. Recurring & Ticking Event Execution**
    * **Main Handlers:**
      * `DotTick.resolve()`: Processes DoT tick actions, reduces `ticks_remaining`, and schedules next tick or deletes DoT on expiration.
      * `ChannelTickEvent.resolve()`: Processes channel tick actions, spends resource tick costs, and schedules next tick or clears channel state and queues `PlayerReady` on completion/clip.
      * `PeriodicProcTick.resolve()`: Runs periodic proc actions and schedules the next interval tick.
      * `ResourceTick.resolve()`: Executes passive energy/heat/force regeneration scaled by Alacrity and schedules the next tick.
      * `EffectExpire.resolve()`: Cleans up expired buff/debuff instances and triggers entity stat recalculation if necessary.
      * `ChargeRestoreEvent.resolve()`: Restores charges to multi-charge abilities and chains timer events.

---

## 🏛️ Codebase Module Overview

| Module            | Purpose / Responsibility                                                                                     |
|:------------------|:-------------------------------------------------------------------------------------------------------------|
| `cli.py`          | Interactive terminal UI for selecting paths, skills, tacticals, implants, and relics.                        |
| `config_load.py`  | JSON parser for character statistics, rotation step configurations, abilities, and effects.                  |
| `engine.py`       | Core event-driven execution loop (`Simulation`) using Python's `heapq` priority queue.                       |
| `setup.py`        | Environment bootstrapper (`prepare_simulation`) that sets up player/target entities and initial events.      |
| `tester.py`       | Test orchestrator running single iterations or multi-core parallelized Monte Carlo simulations.              |
| `events.py`       | Discrete engine event definitions (`PlayerReady`, `DamageHit`, `DotTick`, `ResourceTick`, etc.).             |
| `abilities.py`    | Ability usage rules, cooldown locking, charge management, and action execution dispatching.                  |
| `combat_math.py`  | Accuracy rolls, modifier bucketing, diminishing returns curves, mitigation, and crits/supercrits.            |
| `entities.py`     | `Entity`, `Player`, and `Dummy` state management, effect tracking, and dynamic stat updates.                 |
| `effects.py`      | Data structures for DoTs (`ActiveDot`), channels (`ActiveChannel`), and passive procs (`ProcData`).          |
| `resources.py`    | Class resource pool logic (`Force`, `Energy`, `Heat`, `Rage`/`Focus`).                                       |
| `rotation.py`     | Rotation step engine supporting fixed actions, priority blocks, optional steps, and anchors(discern opener). |
| `metrics.py`      | Damage logger tracking total DPS, ability hit breakdowns, and execute phase ($<30\%$ Target HP) stats.       |
| `requirements.py` | Conditional validator (`CONDITION_REGISTRY`) evaluating resource thresholds, buffs, and HP percentages.      |

---

## 🗺️ Roadmap & Next Steps

The simulator is transitioning from handwritten JSON blueprints to raw extracted game data to achieve 100% data fidelity with live SWTOR servers. With the **Extracted Data Parser Engine** already completed—resolving internal SWTOR node hashes, 64-bit integer IDs, and effect references into clean blueprint structures—the next phase focuses on integrating the new file format directly into the engine runtime:

### 1. Ingestion & Load Routine Refactor
* **Data Loader Overhaul (`config_load.py`):** Rewrite loading routines to parse the new extracted file schemas and databases, mapping nida-resolved node hashes directly to runtime entity models.
* **Load-Time Key & Tag Sanitization:** Shift key normalization (`snake_case`) and tag processing (`frozenset`) into the data loading layer to maximize runtime event queue performance.

### 2. Ability Execution Engine Adaptation
* **Node-Based Ability Resolution (`abilities.py`):** Refactor `Ability.cast()` and `execute_single_action()` to execute abilities directly from the extracted node trees (action sequences, child effect links, conditional branches).
* **Dynamic Condition Matching:** Map extracted condition IDs (tho id's might be gone) and target criteria into `requirements.py`.

### 3. Mechanics & State Resolution Overhaul
* **Native Stack & Charge Consumption:** Align buff/debuff stack handling, refresh logic, and stack-draining triggers in `combat_math.py` and `entities.py` with extracted node rules.
* **Proc & Trigger Mechanics:** Re-architect proc listeners (`cast`, `hit`, `crit`, `periodic`) to subscribe dynamically to extracted effect trigger IDs.
* **Advanced Resource & Event Features:** Finalize passive resource decay timers for builder pools (`Rage` / `Focus`) and properly implement channel clipping and partial channel tick resolution.


readme written with Gemini assistance because author is clueless but can review shit