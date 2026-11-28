# SwtorSim — SWTOR Discrete-Event Combat Simulation Engine

**SwtorSim** is a deterministic/Monte Carlo discrete-event combat simulator and game-data extraction suite for *Star Wars: The Old Republic* (SWTOR).

Unlike spreadsheet calculators or hardcoded rotation scripts, SwtorSim extracts ability, talent, discipline, gear, relic, and combat-curve blueprints directly from SWTOR's `.tor` (MYP) client archives and executes them inside a priority-queue discrete-event engine (`heapq`). It runs both natively on multi-core CPython 3.13+ and entirely in the browser via a zero-backend **Pyodide (WebAssembly)** Web Worker pool.

> **Run in Your Browser (No Install):** [Launch SwtorSim Web App](https://swtorsim.pages.dev)
>
> <!-- Add 1-2 screenshots of the Simulator Dashboard and Rotation Builder here before publishing -->

---

## Key Features

- **Data-Driven Blueprint Engine**: Abilities (`abl.*`), talents (`tal.*`), disciplines (`dis.*`), tacticals, legendary implants, relics, adrenals, and combat curves are parsed directly from SWTOR's Game Object Model (GOM) `.bkt` buckets and `.stb` string tables.
- **High-Fidelity SWTOR Combat Math**:
  - Exact Level 80 (Live) and Level 85 (PTS) diminishing returns curves (`combat_curves.json`).
  - Calibrated **6-bucket multiplicative damage model** (`normal_percentage`, `sub_30`, `channel_scaling`, `damage_type_scaling`, `tag_scaling`, `target_state`).
  - Full support for dual-wield off-hand weapon penalties, flurry hit splitting, armor mitigation & armor penetration, alacrity time-scaling, and supercrit overflow (`crit_chance > 1.0`).
- **Complete Reactive Event Bus**: Supports 22+ GOM trigger types (`on_damage_dealt`, `on_ability_activate`, `on_tick`, `on_travel_complete`, `on_stack_charge_increased`, `on_enter_combat`, etc.) with internal cooldown (`interval_61`) rate-limiting and 36 condition evaluators.
- **Dual-Mode Execution**:
  - **Native Mode**: Fast CLI and local web dashboard powered by Python `multiprocessing.Pool`.
  - **Browser-Only WebAssembly Mode**: Standalone static build (`dist/`) running parallel Pyodide Web Workers in the user's browser—deployable to GitHub Pages, Cloudflare Pages, or Netlify with zero server cost.
- **Visual Rotation Builder**: Interactive browser-based rotation editor (`src/swtorsim/rotation_builder.py`) with a visual Rotation Map and Cast Timeline.

---

## Documentation Index

| Guide | Description |
| :--- | :--- |
| **[User Guide](docs/user_guide.md)** | Installing, running simulations (Web GUI & CLI), configuring `run_config.json`, character builds, skill-tree choices, and using the Rotation Builder. |
| **[Architecture Guide](docs/architecture.md)** | Deep dive into the discrete-event loop, entity hydration, ability/effect/branch execution, active effect stacking, proc triggers, and resource pools. |
| **[Combat Math Reference](docs/combat_math.md)** | Complete mathematical formulas for bonus damage, diminishing returns, accuracy, base damage, armor mitigation, the 6 multiplicative damage buckets, and critical hits. |
| **[Extractor & JSON Schemas](docs/extractor_and_schemas.md)** | How the `.tor` MYP / GOM binary extractor works, plus annotated schemas for discipline, ability, talent, gear, relic, and combat curve JSON files. |
| **[Developer & Contributor Guide](docs/developer_guide.md)** | Engine invariants, architectural routing, how to add new stat IDs, action handlers, condition checks, proc triggers, and new class disciplines, plus testing protocols. |
| **[Pyodide Web Release Guide](docs/pyodide_web_release.md)** | Building, testing, and deploying the standalone browser-only WebAssembly release (`dist/`). |

---

## Quickstart

### Prerequisites

- **Python 3.13+**
- Install dependencies inside a virtual environment:
  ```powershell
  python -m venv .venv
  .\.venv\Scripts\pip install -r requirements.txt
  ```

### 1. Launch the Web GUI Dashboard (Recommended)

Start the local web application (automatically opens `http://127.0.0.1:8787` in your browser):

```powershell
.\.venv\Scripts\python.exe main.py --web
```

From the Web GUI you can:
- Switch between **Live (Level 80)** and **PTS (Level 85)** game data environments.
- Select your **Class Discipline**, **Skill Tree Choices**, **Tactical**, **Legendary Implants**, **Relics**, and **Character Stats**.
- Run a **Single Test** (with a full timestamped combat log and buff/debuff uptime report) or a **Monte Carlo Batch** (with DPS distribution histogram, overall & sub-30% execute phase breakdowns).
- Open the integrated **Visual Rotation Builder** to create or edit priority rotations.

### 2. Run from the Command Line (CLI)

Run a simulation directly from `run_config.json`:

```powershell
# Run using the default run_config.json
.\.venv\Scripts\python.exe run_sim.py

# Or specify a custom config file
.\.venv\Scripts\python.exe main.py --config run_config.json

# Or launch the interactive terminal wizard
.\.venv\Scripts\python.exe main.py --interactive
```

### 3. Open the Standalone Rotation Builder

Launch the browser-based Rotation Builder directly:

```powershell
.\.venv\Scripts\python.exe src/swtorsim/rotation_builder.py
```

`--port` changes the listen port (default 8765). `--no-browser` starts the server without opening a tab.

### 4. Extract Game Data from a SWTOR Installation

`data/extractor/` is excluded from git by default. To extract or refresh blueprints from a local SWTOR client or PTS build:

```powershell
# Interactive extractor menu
.\.venv\Scripts\python.exe run_extractor.py

# Direct CLI extraction from SWTOR Assets folder
.\.venv\Scripts\python.exe src/extractor/main.py "C:\Program Files (x86)\Steam\steamapps\common\Star Wars - The Old Republic\Assets"

# Extract PTS data to data/extractor/pts/ (Level 85)
.\.venv\Scripts\python.exe src/extractor/main.py "C:\Path\To\PTS\Assets" --pts
```

### 5. Build the Standalone Browser (Pyodide) Release

To package the simulator and all game data into a static `dist/` folder that runs entirely in the browser via WebAssembly:

```powershell
.\.venv\Scripts\python.exe tools/build_web_release.py
.\.venv\Scripts\python.exe -m http.server 8080 --directory dist
```

---

## Repository Structure

```text
SwtorSim/
├── run_sim.py                   # Primary CLI & Web GUI simulation runner (--web, --config, --hp, interactive menu)
├── main.py                      # Standalone CLI runner & interactive wizard entry point (--web, --config, --interactive)
├── run_extractor.py             # Interactive CLI wrapper for the SWTOR game data extractor
├── run_config.json              # Default simulation run configuration
├── ARCHITECTURE.md              # Fast file/symbol routing table for developers
├── AGENTS.md                    # Core simulation invariants and contributor rules
├── data/
│   ├── builds/                  # Character stat profiles (Mastery, Power, Crit, Alacrity, Accuracy, Weapon dmg)
│   ├── choices/                 # Discipline skill-tree tier selections
│   ├── rotations/               # Priority & sequential ability rotation JSON files
│   └── extractor/               # Extracted & parsed game data blueprints
│       ├── combat_curves.json   # Level-indexed DR curves, armor constants, standard damage tables
│       ├── disciplines/         # Class discipline definitions & skill tree layouts
│       ├── gear_abilities_talents.json # Tactical & Legendary implant catalog
│       ├── relics.json          # Item-rating-scaled relic FQN catalog
│       ├── adrenals.json        # Adrenal FQN catalog
│       ├── icons/               # Extracted ability/talent icons (.png)
│       ├── parsed/              # Parsed Live (Lvl 80) ability (abl/) & talent (tal/) blueprints
│       └── pts/                 # Parsed PTS (Lvl 85) blueprints, curves, and disciplines
├── src/
│   ├── swtorsim/                # Core Discrete-Event Simulation Engine
│   │   ├── engine.py            # SimulationEngine priority queue (heapq)
│   │   ├── setup.py             # Simulation hydration, passive activation, dummy debuffs
│   │   ├── entities.py          # Entity, Player (stat recalculation, DR, time scaling), Dummy
│   │   ├── abilities.py         # AbilityBlueprint, Effect, Branch, Ability, and action handlers
│   │   ├── effects.py           # ActiveEffect, ActiveDot, ActiveChannel runtime instances
│   │   ├── events.py            # Discrete timeline events (DamageHit, DotTick, PlayerReady, etc.)
│   │   ├── combat_math.py       # Base damage, mitigation, 6 damage buckets, accuracy, crits
│   │   ├── combat_curves.py     # Rating-to-percentage DR equations and curve lookups
│   │   ├── modifiers.py         # Stat Modifier normalization, FQN/tag targeting, stem matching
│   │   ├── requirements.py      # 36 condition & requirement evaluators
│   │   ├── triggers.py          # TriggerManager reactive proc event bus & ICD tracking
│   │   ├── resources.py         # Force, Energy, Heat, and Rage/Focus resource pools
│   │   ├── rotation.py          # Rotation, FixedAbilityStep, PriorityBlockStep, OptionalAbilityStep
│   │   ├── class_buffs.py       # Raid class buffs (+5% Mastery/Endurance/Damage/Crit) & companion bonuses
│   │   ├── config_load.py       # Loadout blueprint resolver & 7 raid dummy debuff splitter
│   │   ├── run_config.py        # RunConfig dataclass & validator
│   │   ├── settings.py          # Global toggles (environment, stem matching, projectile flight time)
│   │   ├── metrics.py           # Damage breakdown, execute phase (<30% HP), and buff uptime tracker
│   │   ├── tester.py            # Single-run and multiprocessing Monte Carlo runner
│   │   ├── web_gui.py           # Local Web GUI server & UI
│   │   ├── rotation_builder.py  # Rotation Builder HTTP backend and dry-run
│   │   └── pyodide_bridge.py    # WebAssembly bridge for in-browser execution
│   ├── extractor/               # Binary .tor (MYP) & GOM (.bkt / .stb) Game Data Extractor
│   └── diminishing_returns/     # Empirical DR curve-fitting utility
├── tests/                       # Unit and full-fight integration test suite
└── tools/                       # Web UI pages, release bundler, and Pyodide worker runtime (`tools/web/`)
```

---

## Running the Test Suite

Execute the unit and integration test suite via `unittest`:

```powershell
.\tools\pyclean.exe -m unittest discover -s tests -p "*test*.py"
```

---

## Contributing & Bug Reports

- Read [ARCHITECTURE.md](ARCHITECTURE.md) and the [Developer & Contributor Guide](docs/developer_guide.md) before modifying engine or extractor code, and make sure the full `unittest` suite passes.
- When reporting a simulation bug, please include your exported `run_config.json`, rotation JSON, and whether you are running on `live` or `pts`.

---

## License & Disclaimer

### Source Code License
The original source code in this repository is licensed under the **GNU General Public License v3.0 (GPL-3.0)** — see [LICENSE](LICENSE) for the full text.

This license applies **only** to original code authored for SwtorSim and does **not** grant any rights or license to extracted game data, strings, or icons from *Star Wars: The Old Republic*.

### Fan Project & IP Disclaimer
SwtorSim is an unofficial, non-commercial fan project and is not affiliated with, endorsed by, or sponsored by **Lucasfilm Ltd.**, **Electronic Arts Inc.**, or **Broadsword Online Games**.

*Star Wars*, *Star Wars: The Old Republic*, and all related logos, character/ability names, icons, and game data are trademarks and copyrights of their respective owners. If you are a rights holder and have any concerns, please open an issue on the repository.
