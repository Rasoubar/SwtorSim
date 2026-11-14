# SwtorSim User Guide

This guide covers how to configure, run, and customize simulations in **SwtorSim**, how to build character loadouts and priority rotations, and how to use the included analysis tools.

---

## 1. Running Simulations

SwtorSim provides three ways to run simulations:

### A. Local Web GUI Dashboard (Recommended)

Launch the interactive browser interface:

```powershell
.\.venv\Scripts\python.exe main.py --web
```

- Starts a local multi-threaded HTTP server on `http://127.0.0.1:8787` (automatically increments the port if `8787` is busy) and opens your default web browser.
- **Features**:
  - **Environment Switcher**: Toggle between **Live (Level 80)** and **PTS (Level 85)** datasets on the fly.
  - **Loadout Configuration**: Pick Origin Story / Class, Discipline, Skill Tree Choices (with tier-by-tier visual icon cards), Tactical item, two Legendary Implants, and two Relics.
  - **Character Stats Editor**: Load or customize character stat profiles (`Mastery`, `Power`, `Critical Rating`, `Alacrity Rating`, `Accuracy Rating`, `Mainhand` / `Offhand` weapon damage).
  - **Simulation Settings**: Choose `TEST` (single verbose run with combat log and buff/debuff uptime table) or `MONTE_CARLO` (multi-core statistical run with DPS histogram and execute-phase breakdown), fight duration, dummy HP, combat distance, and engine toggles.
  - **Integrated Rotation Builder**: Switch directly to the visual Rotation Builder tab to inspect, reorder, or create priority rotation steps and conditions.

### B. Command-Line Config Mode (`run_config.json`)

To run headlessly using a JSON configuration file:

```powershell
# Runs using run_config.json in the project root
.\.venv\Scripts\python.exe run_sim.py

# Or pass a custom run configuration path to main.py
.\.venv\Scripts\python.exe main.py --config path/to/my_run_config.json
```

- In **`TEST`** mode, the terminal prints every ability cast, damage hit, DoT tick, and buff expiration, followed by an overall DPS summary, execute-phase (`<30% HP`) DPS summary, and an active buff/debuff uptime report.
- In **`MONTE_CARLO`** mode, SwtorSim distributes `iterations` fights across all CPU cores using `multiprocessing.Pool`, prints average/median/min/max/std-dev DPS, prints ability breakdowns for the full fight and the execute phase, and saves a DPS distribution histogram to `figures/dps_distribution_histogram.png`.

### C. Interactive CLI Wizard

If you prefer a guided terminal menu that prompts you step-by-step for discipline, stats, rotation, choices, tactical, legendaries, and relics:

```powershell
.\.venv\Scripts\python.exe main.py --interactive
```

At the end of the prompts, you can optionally save your selections back to `run_config.json`.

---

## 2. Configuration Files Reference

### 2.1 `run_config.json`

`run_config.json` defines the complete simulation loadout and runtime parameters.

```json
{
  "spec_path": "data/extractor/disciplines/sith_inquisitor/hatred.json",
  "class_name": "Assassin",
  "spec": "Hatred",
  "stats_path": "data/builds/hatred_stats.json",
  "rotation_path": "data/rotations/hatred_Priority_Test.json",
  "choices": {"23": 1, "27": 1, "39": 1, "43": 1, "51": 1, "64": 1, "68": 1, "73": 1},
  "main_hand": {"min": 3161, "max": 4741},
  "off_hand": null,
  "tactical_fqn": "abl.itm.tactical.sith_inquisitor.assassin.hatred.two_time_trouble",
  "legendary_fqns": [
    "abl.itm.legendary.sith_inquisitor.assassin.force_training",
    "abl.itm.legendary.sith_inquisitor.assassin.vampiric_blades"
  ],
  "relic_fqns": [
    "abl.itm.relic.scales_with_item_rating.serendipitous_assault.pve.blue.stat_burst",
    "abl.itm.relic.scales_with_item_rating.focused_retribution.pve.blue.stat_burst"
  ],
  "mode": "TEST",
  "iterations": 1000,
  "duration": 1000,
  "dummy_hp": 10000000,
  "training_dummy_armor_debuff": true,
  "enable_stem_matching": true,
  "enable_projectile_flight_time": true,
  "default_combat_distance": 4.0,
  "in_flashpoint_operation": true,
  "environment": "live",
  "level": 80
}
```

#### Field Reference

| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `spec_path` | `string` | *(Required)* | Path to the discipline JSON file in `data/extractor/disciplines/` (or `data/extractor/pts/disciplines/`). |
| `class_name` | `string` | *(Auto-inferred)* | Combat style / class tab name (e.g. `"Assassin"`, `"Marauder"`). Inferred from `spec_path` if omitted. |
| `spec` | `string` | *(Auto-inferred)* | Discipline display name (e.g. `"Hatred"`, `"Annihilation"`). Inferred from `spec_path` if omitted. |
| `stats_path` | `string` | *(Required)* | Path to the character stats JSON file in `data/builds/`. |
| `rotation_path` | `string` | *(Required)* | Path to the rotation JSON file in `data/rotations/`. |
| `choices` | `object` | *(Required)* | Skill-tree picks for this spec. Keys are level strings (`"23"` … `"73"`), values are `1`, `2`, or `3`. |
| `main_hand` | `object` | `{"min": 0, "max": 0}` | Main-hand weapon damage range for this spec: `{"min": 3161, "max": 4741}`. |
| `off_hand` | `object` or `null` | `null` | Off-hand weapon damage range. `null` means no off-hand weapon (shield, focus, or generator). |
| `tactical_fqn` | `string` | *(Required)* | FQN (`abl.itm.tactical.*`) of the equipped Tactical item. |
| `legendary_fqns` | `list[str]` | *(Required)* | List of exactly **2** distinct Legendary Implant FQNs (`abl.itm.legendary.*`). |
| `relic_fqns` | `list[str]` | `[]` | List of up to **2** distinct Relic FQNs (`abl.itm.relic.*`). |
| `mode` | `string` | `"TEST"` | `"TEST"` for a single verbose run, or `"MONTE_CARLO"` for a multi-core statistical batch. |
| `iterations` | `int` | `1000` | Number of fights to simulate when `mode` is `"MONTE_CARLO"`. |
| `duration` | `int` | `1000` | Maximum fight duration in seconds (simulation stops early if the target dummy reaches `0` HP). |
| `dummy_hp` | `int` | `10000000` | Starting HP of the Operations Training Dummy (`10,000,000` = standard parsing dummy). |
| `training_dummy_armor_debuff` | `bool` | `true` | Applies the 7 standard Operations Training Dummy raid debuffs (*Sundered*, *Beat Down*, *Marked*, *Vulnerable*, *Susceptible*, *Assailable*, *Overwhelmed*). |
| `enable_stem_matching` | `bool` | `false` | Enables ability stem matching (so modifiers targeting a base ability FQN also match upgraded `_plus` variants). |
| `enable_projectile_flight_time` | `bool` | `false` | Enables distance-based projectile travel time (`distance / (travel_speed * 10.0)`). Timed projectiles (`interval "41"`) always use their fixed flight time. |
| `default_combat_distance` | `float` | `4.0` | Distance from player to target in meters (`0.0` to `35.0`). Used for distance-based projectiles and range checks. |
| `in_flashpoint_operation` | `bool` | `true` | Marks the player as inside a Flashpoint/Operation (required by certain relic/implant conditions). |
| `environment` | `string` | `"live"` | `"live"` (uses `data/extractor/`, Level 80) or `"pts"` (uses `data/extractor/pts/`, Level 85). |
| `level` | `int` | `80` (`85` on PTS) | Character level used to index `combat_curves.json`. |

---

### 2.2 Character Stats (`data/builds/*.json`)

Character stat files store unbuffed gear ratings shared across specs. Main-hand and off-hand damage live on the run config, because they depend on the spec's weapons.

```json
{
  "Mastery": 19749,
  "Power": 11524,
  "Critical Rating": 4214,
  "Alacrity Rating": 2250,
  "Accuracy Rating": 2694,
  "Force Power": 9332,
  "Tech Power": 0
}
```

- **How Stats Are Hydrated**:
  - During `prepare_simulation()`, `Player.recalculate_stats()` automatically applies all 4 raid Class Buffs (*Mark of Power*, *Force Valor*, *Coordination*, *Unnatural Might*), the 5 hidden +1% Companion bonuses (+1% Accuracy, +1% Crit Chance, +1% Surge, +1% Alacrity, +1% Endurance), and any passive stat modifiers from your discipline tree and legendary implants.
  - Ratings (`Critical Rating`, `Alacrity Rating`, `Accuracy Rating`) are converted into percentages using the level-indexed diminishing returns formulas in `combat_curves.json`.
  - A dual-wield spec sets `off_hand` to a `{"min", "max"}` range on the run config. `off_hand: null` means that spec has no off-hand weapon.

---

### 2.3 Skill Tree Choices

Skill-tree picks are stored on the run config. Each talent tier (`"23"`, `"27"`, ..., `"73"`) maps to option `1`, `2`, or `3`:

```json
{
  "23": 1,
  "27": 2,
  "39": 1,
  "43": 1,
  "51": 1,
  "64": 1,
  "68": 3,
  "73": 1
}
```

At runtime, `resolve_skill_tree_fqns()` resolves these selections against the discipline's `skill_tree` dictionary:
- Selected `abl.*` / `tal.*` nodes are added to your active loadout.
- If a selected option specifies a `"replaces"` ability (e.g. `Demolish` replacing `Crushing Darkness`, or `Assassinate+` replacing `Assassinate`), the base ability is automatically swapped out for the replacement.

---

## 3. Rotation Format & Visual Rotation Builder

### 3.1 Using the Rotation Builder (`data/rotation_builder.py`)

You can create and edit rotations visually in your browser:

```powershell
.\.venv\Scripts\python.exe data/rotation_builder.py --ui
```

The Rotation Builder automatically inspects your selected Discipline, Skill Tree Choices, Tactical, Legendaries, and Relics to discover:
- Every castable active ability in your loadout (distinguishing GCD abilities from off-GCD abilities).
- Every buff, debuff, DoT, proc, and stack counter referenced by those abilities, pre-populating condition dropdowns so you never have to type raw FQN strings manually.

### 3.2 Rotation JSON Structure (`data/rotations/*.json`)

A rotation file contains a `"name"`, a boolean `"loop"`, and an ordered `"steps"` array:

```json
{
  "name": "Hatred Priority Rotation",
  "loop": true,
  "steps": [
    {
      "type": "optional",
      "ability_id": "recklessness",
      "rules": {}
    },
    {
      "type": "fixed",
      "ability_id": "creeping_terror"
    },
    {
      "type": "loop_anchor"
    },
    {
      "type": "priority_block",
      "name": "Main Priority",
      "pool": [
        {
          "priority": 1,
          "ability_id": "assassinate+",
          "rules": {
            "target_hp_below": {
              "pct": 0.3,
              "bypass_if_buff_active": ["Reaper's Rush", "reapers_rush"]
            }
          }
        },
        {
          "priority": 2,
          "ability_id": "demolish",
          "rules": {
            "caster_has_buff": ["Raze"]
          }
        },
        {
          "priority": 3,
          "ability_id": "creeping_terror",
          "rules": {
            "target_missing_debuff": ["Creeping Terror"]
          }
        }
      ]
    }
  ]
}
```

#### Step Types

| Step Type | Blocks GCD / Advances When? | Description |
| :--- | :--- | :--- |
| `"fixed"` | **Blocking** | Waits until `ability_id` is off cooldown, affordable, and meets its ability conditions, then casts it and advances to the next step. |
| `"priority_block"` | **Blocking** | Evaluates `pool` options in order from top to bottom. Casts the **first** option whose `rules` pass and whose ability can be cast, then advances. |
| `"optional"` | **Non-Blocking** | Evaluates `rules` and attempts to cast `ability_id` if valid (ideal for off-GCD buffs like *Recklessness*, *Polarity Shift*, or *Bloodthirst*). **Always advances** the rotation pointer even if the ability is on cooldown. |
| `"loop_anchor"` | **Marker** | Marks the start of the repeating loop. Everything before `"loop_anchor"` executes once as the **Opener**; when the rotation reaches the end of `"steps"` and `"loop": true`, it jumps back to `"loop_anchor"`. |

#### Supported Rotation Rule Conditions (`"rules"`)

All conditions inside a `"rules"` dictionary must evaluate to `True` (logical `AND`) for the step/option to fire:

| Rule Key | Example Value | Description |
| :--- | :--- | :--- |
| `caster_has_buff` | `["Raze"]` or `"Raze"` | True if the caster has any of the listed buffs active. |
| `caster_does_not_have_buff` | `[" recklessness "]` | True if the caster does **not** have any of the listed buffs active. |
| `caster_buff_stacks` | `{"name": "Voltage", "comparison": "gte", "value": 2}` | Compares the stack count of a caster buff (`eq`, `lt`, `lte`, `gt`, `gte`). |
| `target_has_debuff` | `["Discharge", "Creeping Terror"]` | True if the target has any of the listed debuffs/DoTs active. |
| `target_missing_debuff` | `["Creeping Terror"]` | True if the target is missing the listed debuff/DoT. |
| `target_debuff_stacks` | `{"name": "Sundered", "comparison": "gte", "value": 5}` | Compares the stack count of a target debuff/DoT. |
| `target_hp_below` | `0.3` or `{"pct": 0.3, "bypass_if_buff_active": ["Reaper's Rush"]}` | True if target HP ratio `<= pct`, or if any bypass buff is active on the caster. |
| `target_hp_above` | `0.3` | True if target HP ratio `> threshold`. |
| `caster_energy_above` | `60` | True if caster primary resource `>= threshold`. |
| `caster_energy_below` | `40` | True if caster primary resource `< threshold`. |
| `ability_cooldown_under` | `{"name": "eradicate", "value": 1.5}` | True if the remaining cooldown of `name` is `< value` seconds. |
| `ability_cooldown_above` | `{"name": "eradicate", "value": 1.5}` | True if the remaining cooldown of `name` is `> value` seconds. |
| `proc_cooldown_above` | `{"name": "Bloodletting", "value": 1.5}` | True if the named proc is not active and its remaining ICD/lockout (resolved via `player.proc_registry`) is `> value` seconds. |

---

## 4. Auxiliary Tools & Utilities

### 4.1 Diminishing Returns Curve Fitter (`src/diminishing_returns/runner.py`)

Fits theoretical SWTOR diminishing returns parameters (`Cap` and `Divisor`) against empirical `(rating, percentage)` pairs observed on the in-game character sheet:

```powershell
.\.venv\Scripts\python.exe src/diminishing_returns/runner.py
```

### 4.2 Combat Log Parser (`tools/parse_combat_log.py`)

Parses live SWTOR combat logs (StarParse format) to inspect ability hit counts, crit rates, tick intervals, and average hit sizes:

```powershell
.\.venv\Scripts\python.exe tools/parse_combat_log.py
```

### 4.3 Live Log vs. Simulator Modifier Validator (`tools/validate_modifiers_vs_log.py`)

Compares simulated ability damage, critical hit multipliers, and active buff/debuff buckets directly against a live SWTOR combat log to verify mathematical parity:

```powershell
.\.venv\Scripts\python.exe tools/validate_modifiers_vs_log.py
```
