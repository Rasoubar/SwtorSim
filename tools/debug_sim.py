"""SwtorSim Interactive Combat Debugger & Visual Replay Runner.

Executes a simulation with full diagnostic telemetry and compiles an
interactive standalone HTML dashboard covering initial loadout, passives,
combat timeline, rotation candidate trees, and hit math equations.

Usage:
    .\\tools\\pyclean.exe tools/debug_sim.py Hatred
    .\\tools\\pyclean.exe tools/debug_sim.py Hatred --hp 100k
    .\\tools\\pyclean.exe tools/debug_sim.py hatred_13gcd --output report.html --no-browser
"""

import argparse
import os
import sys
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from main import discover_configs, parse_hp_value, resolve_config_path
from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.debug.html_reporter import generate_debug_html
from src.swtorsim.debug.tracer import CombatTracer
from src.swtorsim.run_config import load_run_config
from src.swtorsim.tester import Tester


def run_debug_simulation(
    config_identifier: str | Path,
    dummy_hp: int | None = None,
    duration: float | None = None,
    output_path: str | Path | None = None,
    open_browser: bool = True,
    export_json: bool = False,
    environment: str = "live",
) -> str:
    """Executes a traced simulation run and writes the interactive debug HTML report."""
    resolved_path = resolve_config_path(str(config_identifier))
    config = load_run_config(str(resolved_path), environment=environment)

    if dummy_hp is not None:
        config.dummy_hp = dummy_hp
    if duration is not None:
        config.duration = int(duration)

    print(f"\n[OK] Loaded config for debugging: {resolved_path.name}")
    print(f"[OK] Character: {config.class_name} | Spec: {config.spec} | Dummy HP: {config.dummy_hp:,}")

    inputs = load_from_run_config(config)
    tracer = CombatTracer()

    tester = Tester(
        rotation_config=inputs.rotation_config,
        stats_config=inputs.stats_config,
        loadout_blueprints=inputs.loadout_blueprints,
        duration=getattr(config, "duration", 1000.0),
        dummy_hp=config.dummy_hp,
        debuff_module=inputs.debuff_module,
        enable_stem_matching=getattr(config, "enable_stem_matching", True),
        gcd_stall=getattr(config, "gcd_stall", 0.0),
    )

    print("\n--- Running Simulation with Diagnostic Telemetry ---")
    sim, player, target = tester.run_test(show_buffs=True, tracer=tracer, config=config)

    # Determine output HTML location
    if output_path:
        out_file = Path(output_path).resolve()
    else:
        out_file = (PROJECT_ROOT / f"debug_{resolved_path.stem}.html").resolve()

    trace_data = tracer.to_dict()
    html_path = generate_debug_html(trace_data, out_file)
    print(f"\n[OK] Generated interactive debug dashboard: {html_path}")

    if export_json:
        import json
        json_path = out_file.with_suffix(".json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(trace_data, f, indent=2, ensure_ascii=False)
        print(f"[OK] Exported trace JSON: {json_path}")

    if open_browser:
        print("[OK] Opening report in default browser...")
        webbrowser.open(out_file.as_uri())

    return html_path


def main():
    parser = argparse.ArgumentParser(
        description="SwtorSim Interactive Debugger & Visual Replay Generator."
    )
    parser.add_argument(
        "config",
        nargs="?",
        default=None,
        help="Config name (e.g. 'Hatred') or file path to run_config.json.",
    )
    parser.add_argument(
        "--hp",
        "-hp",
        default=None,
        help="Target dummy HP (e.g. '100k', '1m', '2.5m', '6.5m').",
    )
    parser.add_argument(
        "--duration",
        "-d",
        type=float,
        default=None,
        help="Max fight duration cutoff in seconds.",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output HTML file path (default: debug_<config_name>.html).",
    )
    parser.add_argument(
        "--pts",
        action="store_true",
        help="Use PTS extracted data instead of Live.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not automatically launch web browser after generation.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Also export full trace telemetry as a .json file.",
    )

    args = parser.parse_args()

    cfg_name = args.config
    if not cfg_name:
        configs = discover_configs()
        if not configs:
            print("[FAIL] No configurations found in data/run_config/.")
            sys.exit(1)
        print("\nAvailable Configurations:")
        for idx, c in enumerate(configs, 1):
            print(f"  [{idx}] {c.stem}")
        raw_choice = input(f"\nSelect configuration [1-{len(configs)}] (default 1): ").strip()
        if raw_choice.isdigit() and 1 <= int(raw_choice) <= len(configs):
            cfg_name = str(configs[int(raw_choice) - 1])
        else:
            cfg_name = str(configs[0])

    hp_val = parse_hp_value(args.hp) if args.hp else None
    env = "pts" if args.pts else "live"

    run_debug_simulation(
        config_identifier=cfg_name,
        dummy_hp=hp_val,
        duration=args.duration,
        output_path=args.output,
        open_browser=not args.no_browser,
        export_json=args.json,
        environment=env,
    )


if __name__ == "__main__":
    main()
