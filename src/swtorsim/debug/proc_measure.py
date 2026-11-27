"""Measures a proc's real chance by replaying the same fight state many times.

Each trial rebuilds the simulation with the original seed and runs it up to just before the anchor time, so the
state (stats, effects, ICDs, cooldowns) is identical to the traced run. The random generator is then reseeded with
the trial's own seed, the fight runs through the window, and the proc's evaluations in that window are counted.

Window 0 measures the roll at the anchor instant (does the effective chance produce that rate). A window that
starts earlier, at the triggering action (``lead`` seconds before the evaluation), also exercises everything between
the action and the roll: crit gating, once-per-hit-group dedupe, how many evaluations one action causes.

The real engine is only driven, never changed. Simulations come from a caller-supplied builder that returns a
traced simulation (see ``make_sim_builder``).
"""

from __future__ import annotations

import contextlib
import io
import math
import random
import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Callable

# Outcomes where the evaluation reached the roll stage (the proc chance was computed).
_ROLLED = ("fired", "branch_did_not_run", "roll_failed")
_Z = 2.576  # 99% interval: keeps false alarms rare when many procs are measured
_EPS = 1e-6


def proc_key(rec: dict) -> tuple:
    """Identity of one trigger rule across runs (ids of Python objects are not stable, indices are)."""
    return (rec.get("fqn"), rec.get("effect_key"), rec.get("branch_index"), rec.get("trigger_index"))


def wilson_interval(successes: int, trials: int, z: float = _Z) -> tuple[float, float]:
    """Wilson score interval for a proportion; (0, 1) when there are no trials."""
    if trials <= 0:
        return 0.0, 1.0
    p = successes / trials
    denom = 1.0 + z * z / trials
    center = (p + z * z / (2 * trials)) / denom
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denom
    return max(0.0, center - half), min(1.0, center + half)


@dataclass
class ProcMeasurement:
    key: tuple
    source: str
    anchor: float
    window: float
    trials: int = 0
    rolls: int = 0
    roll_passes: int = 0
    fires: int = 0
    expected_passes: float = 0.0
    variance: float = 0.0
    seconds: float = 0.0
    stopped_because: str = ""
    per_trial_rolls: list = field(default_factory=list)

    @property
    def observed(self) -> float:
        return self.roll_passes / self.rolls if self.rolls else 0.0

    @property
    def expected(self) -> float:
        return self.expected_passes / self.rolls if self.rolls else 0.0

    @property
    def interval(self) -> tuple[float, float]:
        return wilson_interval(self.roll_passes, self.rolls)

    @property
    def z_score(self) -> float:
        return (self.roll_passes - self.expected_passes) / math.sqrt(self.variance) if self.variance > 0 else 0.0

    @property
    def verdict(self) -> str:
        if self.rolls == 0:
            return "no evaluations reached the roll in the window"
        if self.variance == 0:  # chance 0 or 100: any deviation is a bug, not noise
            return "consistent" if self.roll_passes == round(self.expected_passes) else "MISMATCH"
        return "consistent" if abs(self.z_score) < _Z else "MISMATCH"

    def describe(self) -> str:
        lo, hi = self.interval
        return (
            f"{self.source}: observed {self.observed * 100:.2f}% "
            f"(99% interval {lo * 100:.2f}-{hi * 100:.2f}%) vs expected {self.expected * 100:.2f}% "
            f"over {self.rolls} rolls in {self.trials} trials, {self.fires / max(1, self.trials):.3f} fires/trial "
            f"-> {self.verdict}"
        )


def run_trial(build_sim: Callable, key: tuple, anchor: float, window: float, trial_seed: int, forced: float | None = None):
    """One replay. Returns the matching evaluation records inside [anchor, anchor + window].

    ``forced`` (0-100) replaces the rule's roll draw from the anchor on (see ``sweep_proc``); the engine still
    consumes its normal random number, so nothing else in the fight shifts.
    """
    sim = build_sim()
    sim.run_until(anchor - _EPS)
    if forced is not None:
        sim.triggers.forced_draws = {key: float(forced)}
    random.seed(trial_seed)
    sim.run_until(anchor + window)
    records = [
        rec for rec in sim.triggers.proc_log
        if proc_key(rec) == key and anchor - _EPS <= rec["t"] <= anchor + window + _EPS
    ]
    return records


def measure_proc(
    build_sim: Callable | None,
    key: tuple,
    anchor: float,
    window: float = 0.0,
    max_trials: int = 500,
    min_trials: int = 100,
    precision: float = 0.02,
    seed_base: int = 1_000_003,
    source: str = "",
    run_batch: Callable | None = None,
    batch_size: int = 1,
) -> ProcMeasurement:
    """Runs trials until the interval is tight (``precision`` half-width), the result is decisive, or the cap.

    ``build_sim`` must return a fresh traced simulation seeded like the run being investigated, with its random
    generator at the seed's start (``prepare_simulation(seed=...)`` does that).

    ``run_batch(first_index, count)`` may replace the serial replay loop (see ``ParallelTrials``): it returns one
    record list per trial, trial ``i`` seeded ``seed_base + i``. Results are consumed in trial order and the stop
    rule is applied after every trial, so the outcome is identical however the trials were scheduled.
    """
    if run_batch is None:
        def run_batch(first, count):
            return [run_trial(build_sim, key, anchor, window, seed_base + i) for i in range(first, first + count)]

    result = ProcMeasurement(key=key, source=source or str(key[0]), anchor=anchor, window=window)
    started = time.perf_counter()
    stopped = ""
    while result.trials < max_trials and not stopped:
        batch = run_batch(result.trials, min(max(1, batch_size), max_trials - result.trials))
        for records in batch:
            result.trials += 1
            rolled = [r for r in records if r["outcome"] in _ROLLED]
            result.per_trial_rolls.append(len(rolled))
            for rec in rolled:
                chance = rec.get("chance")
                p = (chance if chance is not None else 100.0) / 100.0
                result.rolls += 1
                result.expected_passes += p
                result.variance += p * (1.0 - p)
                if rec["outcome"] != "roll_failed":
                    result.roll_passes += 1
                if rec["outcome"] == "fired":
                    result.fires += 1
            if result.trials >= min_trials and result.rolls:
                lo, hi = result.interval
                if abs(result.z_score) >= 4.0 and result.variance > 0:
                    stopped = "decisive mismatch"
                    break
                if (hi - lo) / 2.0 <= precision:
                    stopped = "precision reached"
                    break
    result.stopped_because = stopped or "trial cap"
    result.seconds = time.perf_counter() - started
    return result


# --- parallel trials -------------------------------------------------------------------------------------------

_worker_build_sim = None


def _init_worker(config_path: str, environment: str, seed: int | None, with_tracer: bool = False) -> None:
    global _worker_build_sim
    _worker_build_sim, _seed, _duration = make_sim_builder(config_path, environment, seed, with_tracer=with_tracer)


def _worker_trial(args: tuple):
    key, anchor, window, trial_seed, forced = args
    return run_trial(_worker_build_sim, key, anchor, window, trial_seed, forced)


class ParallelTrials:
    """Runs trials on worker processes; each loads the run config once. Use as a context manager.

    ``measure_proc(None, key, anchor, ..., run_batch=pool.run_batch, batch_size=pool.batch_size)`` gives exactly
    the serial result (same per-trial seeds, same stop rule), only sooner.
    """

    def __init__(self, config_path: str, environment: str, seed: int | None, key: tuple, anchor: float,
                 window: float, workers: int, seed_base: int = 1_000_003):
        self._args = (config_path, environment, seed)
        self._key, self._anchor, self._window, self._seed_base = key, anchor, window, seed_base
        self.workers = max(1, int(workers))
        self.batch_size = self.workers * 4
        self._pool = None

    def __enter__(self):
        from concurrent.futures import ProcessPoolExecutor

        self._pool = ProcessPoolExecutor(self.workers, initializer=_init_worker, initargs=self._args)
        return self

    def __exit__(self, *exc):
        self._pool.shutdown(wait=True, cancel_futures=True)
        self._pool = None

    def run_batch(self, first: int, count: int):
        jobs = [(self._key, self._anchor, self._window, self._seed_base + i, None) for i in range(first, first + count)]
        return list(self._pool.map(_worker_trial, jobs))

    def run_forced(self, values: list):
        """One replay per forced draw value (see ``sweep_proc``); results in the order of ``values``."""
        jobs = [(self._key, self._anchor, self._window, self._seed_base, v) for v in values]
        return list(self._pool.map(_worker_trial, jobs))


@dataclass
class SweepResult:
    key: tuple
    source: str
    anchor: float
    chance: float | None = None
    values: list = field(default_factory=list)
    passes: list = field(default_factory=list)
    expected_count: int = 0
    boundary_at_chance_passes: bool | None = None
    boundary_above_chance_fails: bool | None = None
    problems: list = field(default_factory=list)
    seconds: float = 0.0

    @property
    def observed_count(self) -> int:
        return sum(1 for p in self.passes if p)

    @property
    def verdict(self) -> str:
        if self.chance is None:
            return "no roll"
        return "exact" if not self.problems else "MISMATCH"

    def describe(self) -> str:
        if self.chance is None:
            return f"{self.source}: no chance roll at this moment (it passes whenever its conditions pass)"
        return (
            f"{self.source}: {self.observed_count} of {len(self.values)} forced draws passed; the recorded chance "
            f"{self.chance:.4f}% allows {self.expected_count} -> {self.verdict}"
            + ("" if not self.problems else " (" + "; ".join(self.problems) + ")")
        )


def sweep_grid(step: float = 1.0) -> list:
    """The forced draw values of a sweep: ``step``, 2*``step``, ... up to 100."""
    count = int(round(100.0 / step))
    return [round(step * i, 6) for i in range(1, count + 1)]


def sweep_extra(chance: float) -> list:
    """The two edge draws tested around a chance: the chance itself (passes) and just above it (fails)."""
    return [chance, chance + 1e-6] if 0.0 < chance < 100.0 else []


def _rolled(records: list) -> list:
    return [r for r in records if r["outcome"] in _ROLLED]


def sweep_proc(
    build_sim: Callable | None,
    key: tuple,
    anchor: float,
    step: float = 1.0,
    source: str = "",
    run_forced: Callable | None = None,
    seed: int = 1_000_003,
) -> SweepResult:
    """Exact check of one proc roll: forces the draw to every value ``step``..100 and sees which pass.

    A roll passes when ``draw <= chance``, so with a chance of 30 the draws 1..30 pass and 31..100 fail. The sweep
    counts the passes, checks they form one block (all pass up to a threshold, none above), and tests the two draws
    right at the chance (``chance`` passes, ``chance + 0.000001`` fails). No sampling error: the result is exact.

    Each replay is identical up to the anchor, so the chance is the same in all of them; only the roll changes.
    Rolls at that single instant are covered; use ``measure_proc`` with a lead for an action's several rolls.
    ``run_forced(values)`` may replace the serial loop (``ParallelTrials.run_forced``).
    """
    result = SweepResult(key=key, source=source or str(key[0]), anchor=anchor)
    started = time.perf_counter()
    if run_forced is None:
        def run_forced(values):
            return [run_trial(build_sim, key, anchor, 0.0, seed, v) for v in values]

    probe = _rolled(run_trial(build_sim, key, anchor, 0.0, seed) if build_sim else run_forced([None])[0])
    chances = [r.get("chance") for r in probe]
    if not probe or chances[0] is None or chances[0] >= 100.0:
        result.seconds = time.perf_counter() - started
        return result
    result.chance = float(chances[0])

    grid = sweep_grid(step)
    extra = sweep_extra(result.chance)
    outcomes = run_forced(grid + extra)

    def passed(records):
        rolled = _rolled(records)
        return None if not rolled else rolled[0]["outcome"] != "roll_failed"

    result.values = grid
    result.passes = [passed(r) for r in outcomes[:len(grid)]]
    if any(p is None for p in result.passes):
        result.problems.append("some replays reached no roll")
        result.passes = [bool(p) for p in result.passes]
    result.expected_count = sum(1 for v in grid if v <= result.chance + 1e-9)
    if result.observed_count != result.expected_count:
        result.problems.append(f"{result.observed_count} passed, expected {result.expected_count}")
    if result.passes != sorted(result.passes, reverse=True):
        result.problems.append("passes are not one block (not monotonic in the draw)")
    if extra:
        at, above = (passed(r) for r in outcomes[len(grid):])
        result.boundary_at_chance_passes, result.boundary_above_chance_fails = bool(at), above is False
        if not at:
            result.problems.append("a draw equal to the chance did not pass")
        if above is not False:
            result.problems.append("a draw just above the chance did not fail")
    chances_seen = {r.get("chance") for rs in outcomes for r in _rolled(rs)}
    if len(chances_seen) > 1:
        result.problems.append("the chance differed between replays")
    result.seconds = time.perf_counter() - started
    return result

def _run_inside_traced_engine(sim) -> None:
    """Makes this simulation's own run calls execute with the traced engine installed.

    The traced engine is swapped in process-wide only for the duration of a ``with`` block, and the events of a
    fight resolve long after the simulation is built, so the run methods of this one simulation re-enter it.
    """
    from src.swtorsim.debug.traced_run import traced_engine

    run_until, run_timed = sim.run_until, sim.run_timed

    def traced_run_until(*args, **kwargs):
        with traced_engine():
            return run_until(*args, **kwargs)

    def traced_run_timed(*args, **kwargs):
        with traced_engine():
            return run_timed(*args, **kwargs)

    sim.run_until, sim.run_timed = traced_run_until, traced_run_timed


def _resolve_setup(setup: dict, dummy_hp: int | None):
    """Resolves the simulator's own request payload (the form of the Combat Simulator page) like a TEST run does."""
    from src.swtorsim.web_gui import _resolve_simulation_inputs_from_payload

    payload = dict(setup)
    payload["mode"] = "TEST"
    with contextlib.redirect_stdout(io.StringIO()):
        cfg, resolved = _resolve_simulation_inputs_from_payload(payload)
    if dummy_hp is not None:
        cfg.dummy_hp = int(dummy_hp)
    inputs = SimpleNamespace(
        rotation_config=resolved["rotation_config"], stats_config=resolved["stats_config"],
        loadout_blueprints=resolved["loadout_blueprints"], debuff_module=resolved["debuff_module"],
    )
    return cfg, inputs


def make_sim_builder(config_path, environment: str = "live", seed: int | None = None,
                     with_tracer: bool = False, dummy_hp: int | None = None, duration: float | None = None):
    """Loads a run config once and returns ``(build_sim, seed, duration)``.

    ``config_path`` is a run config file, or a dict: the setup of the Combat Simulator page (its request payload), which
    is resolved exactly like a TEST run and also sets the combat distance like it does.

    The simulation is built like a real single run (run config, tactical, GCD stall, incoming attacks), so a traced run and
    its replays are the same fight. With ``with_tracer`` each simulation carries a fresh ``CombatTracer`` (``sim.tracer``).

    ``build_sim()`` builds a fresh simulation with the traced ``TriggerManager`` installed (the real engine files
    are untouched; see ``traced_run.traced_engine``) and the random generator seeded.
    """
    from src.swtorsim.config_load import load_from_run_config
    from src.swtorsim.debug.traced_run import traced_engine
    from src.swtorsim.run_config import load_run_config
    from src.swtorsim.setup import prepare_simulation

    from_setup = isinstance(config_path, dict)
    if from_setup:
        cfg, inputs = _resolve_setup(config_path, dummy_hp)
    else:
        cfg = load_run_config(config_path, environment=environment)
        with contextlib.redirect_stdout(io.StringIO()):
            inputs = load_from_run_config(cfg)
        if dummy_hp is not None:
            cfg.dummy_hp = int(dummy_hp)
    run_seed = cfg.seed if seed is None else seed
    if duration is None:
        duration = float(getattr(cfg, "duration", 300.0) or 300.0)
    gcd_stall = float(getattr(cfg, "gcd_stall", 0.0) or 0.0)
    incoming = float(getattr(cfg, "incoming_attack_interval", 0.0) or 0.0)

    def build_sim():
        tracer = None
        if with_tracer:
            from src.swtorsim.debug.tracer import CombatTracer
            tracer = CombatTracer()
        with contextlib.redirect_stdout(io.StringIO()), traced_engine():
            sim, player, target = prepare_simulation(
                inputs.rotation_config, inputs.stats_config, inputs.loadout_blueprints,
                cfg.dummy_hp, inputs.debuff_module, seed=run_seed, tracer=tracer, config=cfg,
                gcd_stall=gcd_stall, incoming_attack_interval=incoming,
            )
            if from_setup:  # what the simulator's own TEST run does after preparing
                player.combat_distance = cfg.combat_distance
                target.combat_distance = cfg.combat_distance
        sim.verbose = False
        _run_inside_traced_engine(sim)
        return sim

    build_sim.inputs = inputs  # the loaded loadout, for read-only lookups (icons, names)
    build_sim.config = cfg
    return build_sim, run_seed, duration


def summarize_proc_log(proc_log: list) -> list[dict]:
    """One row per trigger rule: evaluation counts by outcome, first rolled time, mean effective chance."""
    rows: dict[tuple, dict] = {}
    for rec in proc_log:
        row = rows.setdefault(proc_key(rec), {
            "key": proc_key(rec), "source": rec.get("source"), "kind": rec.get("kind"), "outcomes": {}, "first_roll": None,
            "chance_sum": 0.0, "chance_n": 0,
        })
        row["outcomes"][rec["outcome"]] = row["outcomes"].get(rec["outcome"], 0) + 1
        if rec["outcome"] in _ROLLED:
            if row["first_roll"] is None:
                row["first_roll"] = rec["t"]
            if rec.get("chance") is not None:
                row["chance_sum"] += rec["chance"]
                row["chance_n"] += 1
    for row in rows.values():
        row["mean_chance"] = row["chance_sum"] / row["chance_n"] if row["chance_n"] else None
    return sorted(rows.values(), key=lambda r: (r["first_roll"] is None, r["first_roll"] or 0.0))
