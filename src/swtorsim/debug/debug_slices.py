"""The replay jobs of the debugger split into slices, for the browser build's pool of workers.

Measuring (Measure proc, the exact check, damage checks) replays the fight many times. In the browser there are no
processes, only Web Workers that cannot call each other, so the page splits the work: each worker runs a slice of
trials and returns its raw records, and one worker then aggregates them with the same functions the native API uses.
Trial ``i`` is seeded the same wherever it runs, so the result equals the serial one.

All functions take the fight as ``config`` (a saved run config) or ``setup`` (the simulator page's payload) plus
``environment``, ``seed``, ``duration`` and ``dummy_hp``, like ``debug_api``.
"""

from __future__ import annotations

from typing import Any

from src.swtorsim.debug import debug_api
from src.swtorsim.debug.damage_check import measure_damage, reference_stats, run_damage_trial
from src.swtorsim.debug.proc_measure import (
    measure_proc,
    run_trial,
    sweep_extra,
    sweep_grid,
    sweep_proc,
    _rolled,
)

PROC_SEED_BASE = 1_000_003
DAMAGE_SEED_BASE = 2_000_003


class _NeedMoreTrials(Exception):
    """Raised inside an aggregation when it wants trials that have not been run yet."""


def _fight(config, setup, environment, seed, duration, dummy_hp, with_tracer: bool):
    what, _label, _kind = debug_api.fight_source(config, setup)
    return debug_api.get_builder(what, environment, seed, with_tracer=with_tracer, dummy_hp=dummy_hp, duration=duration)


# --- Measure proc ------------------------------------------------------------------------------------------------------

def trials_slice(*, key: list, anchor: float, first: int, count: int, window: float = 0.0, config: str | None = None,
                 setup: dict | None = None, environment: str = "live", seed: int | None = None,
                 duration: float | None = None, dummy_hp: int | None = None,
                 seed_base: int = PROC_SEED_BASE) -> list[list[dict]]:
    """Trials ``first`` .. ``first + count - 1`` of a proc measurement; one record list per trial."""
    start = float(anchor) - max(0.0, float(window))
    with debug_api._LOCK:
        build_sim, _seed, _duration = _fight(config, setup, environment, seed, duration, dummy_hp, False)
        return [run_trial(build_sim, tuple(key), start, float(window), seed_base + i)
                for i in range(int(first), int(first) + int(count))]


def measure_aggregate(*, key: list, anchor: float, trials: list, window: float = 0.0, max_trials: int = 500,
                      min_trials: int = 100, precision: float = 0.02, source: str = "",
                      seconds: float | None = None) -> dict[str, Any]:
    """Applies the stop rule to the trials run so far: ``{"done": True, "result": ...}`` or ``{"done": False}``.

    The rule is checked after every trial in order, so the result is identical to a serial run. ``done`` is False when
    the rule wants a trial that is not in ``trials`` yet.
    """
    start = float(anchor) - max(0.0, float(window))

    def run_batch(first, count):
        if first >= len(trials):
            raise _NeedMoreTrials
        return trials[first:first + count]

    try:
        result = measure_proc(None, tuple(key), start, window=float(window), max_trials=int(max_trials),
                              min_trials=int(min_trials), precision=float(precision), source=source,
                              run_batch=run_batch, batch_size=16)
    except _NeedMoreTrials:
        return {"done": False, "trials": len(trials)}
    data = debug_api.measure_result_dict(result)
    if seconds is not None:
        data["seconds"] = float(seconds)
    return {"done": True, "result": data}


# --- the exact check ---------------------------------------------------------------------------------------------------

def _clamp_step(step) -> float:
    return min(10.0, max(0.1, float(step)))


def sweep_plan(*, key: list, anchor: float, step: float = 1.0, config: str | None = None, setup: dict | None = None,
               environment: str = "live", seed: int | None = None, duration: float | None = None,
               dummy_hp: int | None = None) -> dict[str, Any]:
    """One probe replay: the chance at that roll and which forced draws the sweep must run (none without a chance)."""
    with debug_api._LOCK:
        build_sim, _seed, _duration = _fight(config, setup, environment, seed, duration, dummy_hp, False)
        probe = run_trial(build_sim, tuple(key), float(anchor), 0.0, PROC_SEED_BASE)
    rolled = _rolled(probe)
    chance = rolled[0].get("chance") if rolled else None
    if not rolled or chance is None or chance >= 100.0:
        return {"chance": None, "values": [], "probe": probe}
    return {"chance": float(chance), "values": sweep_grid(_clamp_step(step)) + sweep_extra(float(chance)), "probe": probe}


def forced_slice(*, key: list, anchor: float, values: list, config: str | None = None, setup: dict | None = None,
                 environment: str = "live", seed: int | None = None, duration: float | None = None,
                 dummy_hp: int | None = None) -> list[list[dict]]:
    """One replay per forced draw value; one record list per value, in order."""
    with debug_api._LOCK:
        build_sim, _seed, _duration = _fight(config, setup, environment, seed, duration, dummy_hp, False)
        return [run_trial(build_sim, tuple(key), float(anchor), 0.0, PROC_SEED_BASE, float(v)) for v in values]


def sweep_aggregate(*, key: list, anchor: float, probe: list, values: list, results: list, step: float = 1.0,
                    source: str = "", seconds: float | None = None) -> dict[str, Any]:
    """The exact-check result from the probe and the forced replays (``results[i]`` belongs to ``values[i]``)."""
    table = {float(v): records for v, records in zip(values, results)}

    def lookup(forced):
        return [probe if v is None else table[float(v)] for v in forced]

    step = _clamp_step(step)
    result = sweep_proc(None, tuple(key), float(anchor), step, source, run_forced=lookup)
    data = debug_api.sweep_result_dict(result, step)
    if seconds is not None:
        data["seconds"] = float(seconds)
    return data


# --- damage checks -----------------------------------------------------------------------------------------------------

def damage_slice(*, ability: str, anchor: float, first: int, count: int, window: float = 0.0,
                 want_reference: bool = False, config: str | None = None, setup: dict | None = None,
                 environment: str = "live", seed: int | None = None, duration: float | None = None,
                 dummy_hp: int | None = None, seed_base: int = DAMAGE_SEED_BASE) -> dict[str, Any]:
    """Damage trials ``first`` .. ``first + count - 1`` (the hits of ``ability`` in each), and optionally the stat reference."""
    start = float(anchor) - max(0.0, float(window))
    with debug_api._LOCK:
        build_sim, _seed, _duration = _fight(config, setup, environment, seed, duration, dummy_hp, True)
        hits = [run_damage_trial(build_sim, ability, start, float(window), seed_base + i)
                for i in range(int(first), int(first) + int(count))]
        reference = reference_stats(build_sim, start) if want_reference else None
    return {"hits": hits, "reference": reference}


def damage_aggregate(*, ability: str, anchor: float, trials: list, reference: dict | None, window: float = 0.0,
                     seconds: float | None = None) -> dict[str, Any]:
    """The damage check result from the trials run (one hit list per trial, in order)."""
    start = float(anchor) - max(0.0, float(window))

    def run_batch(first, count):
        return trials[first:first + count]

    result = measure_damage(None, ability, start, float(window), len(trials), run_batch=run_batch, reference=reference or {})
    data = result.to_dict()
    if seconds is not None:
        data["seconds"] = float(seconds)
    return data
