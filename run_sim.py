"""SwtorSim Unified Simulation Runner.

Quickly run combat simulations by selecting a run configuration and dummy HP
either interactively or via command-line arguments.

Usage Examples:
    .\\tools\\pyclean.exe run_sim.py
    .\\tools\\pyclean.exe run_sim.py hatred_14gcd --hp 1m
    .\\tools\\pyclean.exe run_sim.py hatred_14gcd --hp 6.5m --mode TEST
    .\\tools\\pyclean.exe run_sim.py hatred_13gcd --hp 6m --mode BATCH --iterations 50
"""

import argparse
import os
import random
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.run_config import load_run_config
from src.swtorsim.tester import Tester

CONFIG_DIR = PROJECT_ROOT / "data" / "run_config"

COMMON_HP_PRESETS = [
    ("1.0M (1,000,000)  - Quick test", 1_000_000),
    ("2.5M (2,500,000)  - Small dummy", 2_500_000),
    ("6.0M (6,000,000)  - Standard dummy", 6_000_000),
    ("6.5M (6,500,000)  - Operation dummy", 6_500_000),
    ("10.0M (10,000,000) - Extended dummy", 10_000_000),
]


def parse_hp_value(val: str | int | float) -> int:
    """Parses strings like '1m', '2.5m', '500k', or '1000000' into integer HP."""
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).strip().lower().replace(",", "").replace("_", "")
    if s.endswith("m"):
        return int(float(s[:-1]) * 1_000_000)
    elif s.endswith("k"):
        return int(float(s[:-1]) * 1_000)
    return int(float(s))


def discover_configs() -> list[Path]:
    """Finds all JSON files in data/run_config."""
    if not CONFIG_DIR.exists():
        return []
    return sorted(CONFIG_DIR.glob("*.json"))


def resolve_config_path(identifier: str) -> Path:
    """Resolves a config argument to a Path (supports basename or full path)."""
    p = Path(identifier)
    if p.exists() and p.is_file():
        return p.resolve()
    # Check in CONFIG_DIR with and without .json
    candidate = CONFIG_DIR / identifier
    if candidate.exists() and candidate.is_file():
        return candidate.resolve()
    candidate_json = CONFIG_DIR / f"{identifier}.json"
    if candidate_json.exists() and candidate_json.is_file():
        return candidate_json.resolve()
    raise FileNotFoundError(f"Configuration file not found: {identifier}")


def prompt_config_interactive() -> Path | None:
    """Interactively prompts the user to select an available configuration or launch the Web GUI."""
    configs = discover_configs()
    print("\nAvailable Configurations:")
    print("  [0] Launch Web GUI Dashboard (Browser)")
    for idx, cfg in enumerate(configs, 1):
        print(f"  [{idx}] {cfg.name}")
    print(f"  [{len(configs) + 1}] Custom path...")

    while True:
        choice = input(f"\nSelect option [0-{len(configs) + 1}] (default 0 for Web GUI, 1 for {configs[0].name if configs else 'config'}): ").strip()
        if not choice:
            return None
        if choice.isdigit():
            i = int(choice)
            if i == 0:
                return None
            if 1 <= i <= len(configs):
                return configs[i - 1]
            elif i == len(configs) + 1:
                custom = input("Enter path to custom run_config JSON: ").strip()
                path = resolve_config_path(custom)
                return path
        print(f"[WARN] Invalid selection: '{choice}'. Please enter 0-{len(configs) + 1}.")


def prompt_hp_interactive(default_hp: int) -> int:
    """Interactively prompts the user to choose target dummy HP."""
    print("\nTarget Dummy HP:")
    for idx, (label, val) in enumerate(COMMON_HP_PRESETS, 1):
        default_tag = " [Config Default]" if val == default_hp else ""
        print(f"  [{idx}] {label}{default_tag}")
    custom_idx = len(COMMON_HP_PRESETS) + 1
    print(f"  [{custom_idx}] Custom value (e.g. 1.5m, 750k, 3000000)")

    # Find if default matches a preset
    default_preset_idx = 1
    for idx, (_, val) in enumerate(COMMON_HP_PRESETS, 1):
        if val == default_hp:
            default_preset_idx = idx
            break

    while True:
        choice = input(f"\nSelect HP [1-{custom_idx}] (default {default_preset_idx}): ").strip()
        if not choice:
            return COMMON_HP_PRESETS[default_preset_idx - 1][1]
        if choice.isdigit():
            i = int(choice)
            if 1 <= i <= len(COMMON_HP_PRESETS):
                return COMMON_HP_PRESETS[i - 1][1]
            elif i == custom_idx:
                raw_val = input("Enter custom HP: ").strip()
                try:
                    return parse_hp_value(raw_val)
                except Exception:
                    print(f"[WARN] Could not parse HP value: '{raw_val}'.")
                    continue
        else:
            # User might have typed '1m' or '2.5m' directly
            try:
                return parse_hp_value(choice)
            except Exception:
                pass
        print(f"[WARN] Invalid selection: '{choice}'.")


def prompt_mode_interactive(default_mode: str) -> tuple[str, int]:
    """Interactively prompts for TEST (single run) or BATCH (Monte Carlo)."""
    print("\nSimulation Mode:")
    print("  [1] TEST  (Single run with real-time combat log & damage breakdown)")
    print("  [2] BATCH (Multi-iteration Monte Carlo)")

    default_choice = "2" if default_mode == "BATCH" else "1"
    choice = input(f"\nSelect mode [1-2] (default {default_choice}): ").strip() or default_choice

    if choice == "2":
        raw_iters = input("Enter number of iterations (default 50): ").strip()
        iterations = int(raw_iters) if raw_iters.isdigit() and int(raw_iters) > 0 else 50
        return "BATCH", iterations
    return "TEST", 1


def main():
    parser = argparse.ArgumentParser(
        description="Quickly run SWTOR combat simulations with selectable config and dummy HP."
    )
    parser.add_argument(
        "config",
        nargs="?",
        default=None,
        help="Config name (e.g. 'hatred_14gcd') or file path to run_config.json.",
    )
    parser.add_argument(
        "--hp",
        "-hp",
        default=None,
        help="Target dummy HP (supports numbers or shorthands like '1m', '2.5m', '6.5m').",
    )
    parser.add_argument(
        "--mode",
        "-m",
        choices=["TEST", "BATCH", "test", "batch"],
        default=None,
        help="Simulation mode: 'TEST' (single parse) or 'BATCH' (Monte Carlo).",
    )
    parser.add_argument(
        "--iterations",
        "-i",
        type=int,
        default=None,
        help="Iterations for BATCH mode (default 50).",
    )
    parser.add_argument(
        "--duration",
        "-d",
        type=float,
        default=None,
        help="Max duration cutoff in seconds (default 1000s or until dummy dies).",
    )
    parser.add_argument(
        "--web",
        "-w",
        action="store_true",
        help="Launch the local Web GUI Dashboard in the browser.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8766,
        help="Port for the local Web GUI server (default: 8766).",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the Web GUI server without automatically opening a browser tab.",
    )

    args = parser.parse_args()

    if args.web:
        from src.swtorsim.web_gui import launch_web_simulator

        launch_web_simulator(port=args.port, open_browser=not args.no_browser)
        return

    # 1. Resolve configuration
    if args.config:
        config_path = resolve_config_path(args.config)
    else:
        print("=== SwtorSim Simulation Runner ===")
        config_path = prompt_config_interactive()
        if config_path is None:
            from src.swtorsim.web_gui import launch_web_simulator

            launch_web_simulator(port=args.port, open_browser=not args.no_browser)
            return

    config = load_run_config(str(config_path))
    print(f"\n[OK] Loaded config: {config_path.name}")

    # 2. Resolve Dummy HP
    if args.hp is not None:
        dummy_hp = parse_hp_value(args.hp)
    elif not args.config:
        dummy_hp = prompt_hp_interactive(getattr(config, "dummy_hp", 6_000_000))
    else:
        dummy_hp = getattr(config, "dummy_hp", 6_000_000)

    config.dummy_hp = dummy_hp

    # 3. Resolve Mode & Iterations
    if args.mode is not None:
        config.mode = args.mode.upper()
    elif not args.config:
        mode, iters = prompt_mode_interactive(getattr(config, "mode", "TEST"))
        config.mode = mode
        if mode == "BATCH":
            config.iterations = iters
    else:
        # If config specifies mode, keep it; default to TEST for direct quick runs
        if not hasattr(config, "mode") or not config.mode:
            config.mode = "TEST"

    if args.iterations is not None:
        config.iterations = args.iterations

    if args.duration is not None:
        config.duration = args.duration

    print(f"[OK] Target Dummy HP: {config.dummy_hp:,}")
    print(f"[OK] Mode: {config.mode}" + (f" ({config.iterations} iterations)" if config.mode == "BATCH" else ""))
    print("-" * 60)

    # 4. Prepare and execute simulation
    random.seed(getattr(config, "seed", None))
    inputs = load_from_run_config(config)

    tester = Tester(
        rotation_config=inputs.rotation_config,
        stats_config=inputs.stats_config,
        loadout_blueprints=inputs.loadout_blueprints,
        duration=getattr(config, "duration", 1000.0),
        dummy_hp=config.dummy_hp,
        debuff_module=inputs.debuff_module,
        enable_stem_matching=getattr(config, "enable_stem_matching", True),
    )

    if config.mode == "TEST":
        tester.run_test()
    elif config.mode == "BATCH":
        tester.run_monte_carlo(iterations=getattr(config, "iterations", 50))


if __name__ == "__main__":
    main()
