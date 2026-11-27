r"""Measure a proc's real chance by replaying the fight state many times (see src/swtorsim/debug/proc_measure.py).

Usage:
    .\tools\pyclean.exe tools\measure_proc.py Hatred --list
    .\tools\pyclean.exe tools\measure_proc.py Hatred --proc "Forked Darkness" --trials 500
    .\tools\pyclean.exe tools\measure_proc.py Hatred --proc "Forked Darkness" --lead 1.5   # include the action that leads to it
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from main import resolve_config_path
from src.swtorsim.debug.proc_measure import ParallelTrials, make_sim_builder, measure_proc, summarize_proc_log, sweep_proc


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure a proc's chance by replaying the same state.")
    parser.add_argument("config", help="Config name (e.g. 'Hatred') or run_config path.")
    parser.add_argument("--pts", action="store_true", help="Use PTS data instead of Live.")
    parser.add_argument("--seed", type=int, default=None, help="Fight seed (default: the config's seed).")
    parser.add_argument("--list", action="store_true", help="List the procs evaluated in the traced run and exit.")
    parser.add_argument("--proc", default=None, help="Substring of the proc's source ability name to measure.")
    parser.add_argument("--at", type=float, default=None, help="Raw sim time to anchor at (default: first roll).")
    parser.add_argument("--lead", type=float, default=0.0,
                        help="Start this many seconds before the anchor, so the actions leading to the roll run too.")
    parser.add_argument("--trials", type=int, default=500, help="Trial cap (default 500).")
    parser.add_argument("--sweep", action="store_true",
                        help="Exact check: force every draw 1..100 at the anchor instead of sampling (ignores --lead).")
    parser.add_argument("--step", type=float, default=1.0, help="Draw step for --sweep (default 1).")
    parser.add_argument("--workers", type=int, default=1, help="Worker processes for trials (default 1; same result, sooner).")
    args = parser.parse_args()

    path = str(resolve_config_path(args.config))
    build_sim, seed, duration = make_sim_builder(path, "pts" if args.pts else "live", args.seed)

    sim = build_sim()
    sim.run_until(duration + (sim.pre_combat_end_time or 0.0))
    rows = summarize_proc_log(sim.triggers.proc_log)

    if args.list or not args.proc:
        print(f"[OK] {len(rows)} procs evaluated (seed {seed}):")
        for row in rows:
            chance = "-" if row["mean_chance"] is None else f"{row['mean_chance']:.1f}%"
            first = "-" if row["first_roll"] is None else f"{row['first_roll']:.2f}s"
            print(f"  {str(row['source']):36s} {str(row['kind']):9s} chance {chance:>7s}  first roll {first:>8s}  {row['outcomes']}")
        return 0

    matches = [r for r in rows if r["first_roll"] is not None and args.proc.lower() in str(r["source"]).lower()]
    if not matches:
        print(f"[FAIL] No rolled proc matches '{args.proc}'. Use --list.")
        return 1
    row = matches[0]
    if len(matches) > 1:
        print(f"[WARN] {len(matches)} rules match; measuring the first ({row['source']}).")
    anchor = (args.at if args.at is not None else row["first_roll"]) - args.lead
    env = "pts" if args.pts else "live"
    if args.sweep:
        sweep_anchor = args.at if args.at is not None else row["first_roll"]
        if args.workers > 1:
            with ParallelTrials(path, env, args.seed, row["key"], sweep_anchor, 0.0, args.workers) as pool:
                swept = sweep_proc(None, row["key"], sweep_anchor, args.step, str(row["source"]), run_forced=pool.run_forced)
        else:
            swept = sweep_proc(build_sim, row["key"], sweep_anchor, args.step, str(row["source"]))
        print(f"[OK] {swept.describe()}")
        print(f"     {swept.seconds:.1f}s; anchor {sweep_anchor:.4f}s")
        return 0 if swept.verdict != "MISMATCH" else 2
    if args.workers > 1:
        with ParallelTrials(path, env, args.seed, row["key"], anchor, args.lead, args.workers) as pool:
            result = measure_proc(None, row["key"], anchor, window=args.lead, max_trials=args.trials,
                                  source=str(row["source"]), run_batch=pool.run_batch, batch_size=pool.batch_size)
    else:
        result = measure_proc(build_sim, row["key"], anchor, window=args.lead, max_trials=args.trials, source=str(row["source"]))
    print(f"[OK] {result.describe()}")
    print(f"     stopped: {result.stopped_because}; {result.seconds:.1f}s; anchor {anchor:.2f}s window {args.lead:.2f}s")
    return 0 if result.verdict != "MISMATCH" else 2


if __name__ == "__main__":
    raise SystemExit(main())
