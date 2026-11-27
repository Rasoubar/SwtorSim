r"""Save and compare deterministic DPS baselines across saved run_config files.

Usage:
    .\tools\pyclean.exe tools\dps_baseline.py --save %TEMP%\swtorsim_dps_baseline.json
    .\tools\pyclean.exe tools\dps_baseline.py --compare %TEMP%\swtorsim_dps_baseline.json
"""

from __future__ import annotations

import argparse
import contextlib
import glob
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.run_config import load_run_config
from src.swtorsim.setup import prepare_simulation


def _discover_configs(include_custom: bool) -> list[str]:
    patterns = ["data/run_config/*.json"]
    if include_custom:
        patterns.append("data/run_config/custom/*.json")
    paths: list[str] = []
    for pat in patterns:
        paths.extend(sorted(glob.glob(str(ROOT / pat))))
    return paths


def _run_config_dps(config_path: str) -> dict[str, Any]:
    cfg = load_run_config(config_path)
    with contextlib.redirect_stdout(io.StringIO()):
        inputs = load_from_run_config(cfg)
        sim, _player, _target = prepare_simulation(
            inputs.rotation_config,
            inputs.stats_config,
            inputs.loadout_blueprints,
            cfg.dummy_hp,
            inputs.debuff_module,
            seed=cfg.seed,
        )
        sim.verbose = False
        duration = float(getattr(cfg, "duration", 300.0) or 300.0)
        sim.run_until(duration)
    eff_dur = max(0.001, sim.relative_time())
    total_dmg = float(sim.tracker.total_damage)
    return {
        "dps": total_dmg / eff_dur,
        "total_damage": total_dmg,
        "duration": eff_dur,
        "seed": cfg.seed,
    }


def _collect_baselines(include_custom: bool) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for abs_path in _discover_configs(include_custom):
        rel = os.path.relpath(abs_path, ROOT).replace("\\", "/")
        try:
            results[rel] = _run_config_dps(abs_path)
        except Exception as exc:
            print(f"[SKIP] {rel}: {exc}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Save or compare deterministic DPS baselines.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--save", metavar="PATH", help="Save baseline JSON to PATH.")
    group.add_argument("--compare", metavar="PATH", help="Compare current code against baseline JSON at PATH.")
    parser.add_argument("--include-custom", action="store_true", help="Also include data/run_config/custom/*.json.")
    parser.add_argument("--fail-on-diff", action="store_true", help="Exit 1 if any config DPS differs by > 0.01.")
    args = parser.parse_args()

    os.chdir(ROOT)

    if args.save:
        data = _collect_baselines(args.include_custom)
        out_path = Path(args.save)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"[OK] Saved {len(data)} DPS baselines to {out_path}")
        for rel, entry in data.items():
            print(f"  {rel:44s} | DPS={entry['dps']:9.2f} | seed={entry['seed']}")
        return 0

    in_path = Path(args.compare)
    if not in_path.is_file():
        print(f"[FAIL] Baseline file not found: {in_path}")
        return 2

    old_data: dict[str, dict[str, Any]] = json.loads(in_path.read_text(encoding="utf-8"))
    new_data = _collect_baselines(args.include_custom)

    any_diff = False
    print(f"{'Config':44s} | {'Old DPS':>9s} | {'New DPS':>9s} | {'Diff':>9s} | {'Pct':>7s}")
    print("-" * 88)
    for rel in sorted(set(old_data) | set(new_data)):
        if rel not in old_data:
            print(f"[NEW]  {rel:37s} | {'-':>9s} | {new_data[rel]['dps']:9.2f} | {'-':>9s} | {'-':>7s}")
            continue
        if rel not in new_data:
            print(f"[MISS] {rel:37s} | {old_data[rel]['dps']:9.2f} | {'-':>9s} | {'-':>9s} | {'-':>7s}")
            continue
        od = old_data[rel]["dps"]
        nd = new_data[rel]["dps"]
        diff = nd - od
        pct = (100.0 * diff / od) if od else 0.0
        tag = "[DIFF]" if abs(diff) > 0.01 else "[OK]  "
        if abs(diff) > 0.01:
            any_diff = True
        print(f"{tag} {rel:37s} | {od:9.2f} | {nd:9.2f} | {diff:+9.2f} | {pct:+6.2f}%")

    return 1 if (args.fail_on_diff and any_diff) else 0


if __name__ == "__main__":
    raise SystemExit(main())
