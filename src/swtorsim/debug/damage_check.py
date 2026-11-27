"""Damage checks: replays one ability's hit many times and summarizes crit rate and damage spread.

Like ``proc_measure`` this only drives the real engine (built with a tracer so hits are recorded) and compares what
happened with the character's stat values at that moment. The combat formulas are not re-derived: the stat values
are shown as a reference, so a gap points at inputs (stats, buffs, bonuses) rather than at the math.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Callable

from src.swtorsim.debug.proc_measure import wilson_interval

_EPS = 1e-4  # the tracer rounds event times to 4 decimals, so anchor a hair before the hit


def _hits_in_window(sim, ability: str, anchor: float, window: float) -> list[dict]:
    return [
        e for e in sim.tracer.events
        if e.get("type") == "damage_hit" and e.get("ability") == ability
        and anchor - _EPS <= e["t"] <= anchor + window + _EPS
    ]


def run_damage_trial(build_sim: Callable, ability: str, anchor: float, window: float, trial_seed: int) -> list[dict]:
    """One replay (same state up to ``anchor``, then a fresh random stream); returns that ability's hits in the window."""
    sim = build_sim()
    sim.run_until(anchor - _EPS)
    random.seed(trial_seed)
    sim.run_until(anchor + window)
    return [
        {"damage": e["damage"], "crit": bool(e["is_crit"]), "bonus_crit": (e.get("math") or {}).get("bonus_crit_chance")}
        for e in _hits_in_window(sim, ability, anchor, window)
    ]


def reference_stats(build_sim: Callable, anchor: float) -> dict:
    """The crit chance / multiplier the character has just before ``anchor`` (read from its stats, nothing re-derived)."""
    sim = build_sim()
    sim.run_until(anchor - _EPS)
    stats = sim.incoming_attack_victim.stats
    return {
        "crit_chance": float(stats.get("Critical Chance", 0.0)),
        "crit_modifier": float(stats.get("Critical Modifier", 0.0)),
    }


@dataclass
class DamageMeasurement:
    ability: str
    anchor: float
    window: float
    trials: int = 0
    hits: int = 0
    crits: int = 0
    normal: list = field(default_factory=list)
    crit_damage: list = field(default_factory=list)
    bonus_crit: list = field(default_factory=list)
    reference: dict = field(default_factory=dict)
    seconds: float = 0.0

    @staticmethod
    def _summary(values):
        if not values:
            return None
        return {"n": len(values), "min": min(values), "mean": sum(values) / len(values), "max": max(values)}

    @property
    def crit_rate(self) -> float:
        return self.crits / self.hits if self.hits else 0.0

    @property
    def interval(self) -> tuple[float, float]:
        return wilson_interval(self.crits, self.hits)

    @property
    def expected_crit(self) -> float | None:
        """Stat crit chance plus the hit's own bonus (from the hit audit), as a fraction; None without a reference."""
        if "crit_chance" not in self.reference:
            return None
        bonus = sum(self.bonus_crit) / len(self.bonus_crit) if self.bonus_crit else 0.0
        return min(1.0, max(0.0, self.reference["crit_chance"] + bonus))

    @property
    def verdict(self) -> str:
        expected = self.expected_crit
        if self.hits == 0:
            return "no hits in the window"
        if expected is None:
            return "no reference"
        low, high = self.interval
        return "consistent" if low <= expected <= high else "differs from the stats"

    @property
    def crit_ratio(self) -> float | None:
        normal, crit = self._summary(self.normal), self._summary(self.crit_damage)
        return crit["mean"] / normal["mean"] if normal and crit and normal["mean"] else None

    def to_dict(self) -> dict:
        low, high = self.interval
        return {
            "ability": self.ability, "anchor": self.anchor, "window": self.window, "trials": self.trials,
            "hits": self.hits, "crits": self.crits, "crit_rate": self.crit_rate, "interval": [low, high],
            "expected_crit": self.expected_crit, "reference": self.reference,
            "bonus_crit": (sum(self.bonus_crit) / len(self.bonus_crit)) if self.bonus_crit else None,
            "normal": self._summary(self.normal), "crit_damage": self._summary(self.crit_damage),
            "crit_ratio": self.crit_ratio,
            "expected_ratio": (1.0 + self.reference["crit_modifier"]) if "crit_modifier" in self.reference else None,
            "verdict": self.verdict, "seconds": self.seconds,
        }


def measure_damage(
    build_sim: Callable | None,
    ability: str,
    anchor: float,
    window: float = 0.0,
    trials: int = 300,
    seed_base: int = 2_000_003,
    run_batch: Callable | None = None,
    batch_size: int = 1,
    reference: dict | None = None,
) -> DamageMeasurement:
    """Replays ``trials`` times and collects every hit of ``ability`` in [anchor, anchor + window].

    ``run_batch(first, count)`` may replace the serial loop (worker processes); trial ``i`` is seeded
    ``seed_base + i`` either way, so the result does not depend on scheduling.
    """
    if run_batch is None:
        def run_batch(first, count):
            return [run_damage_trial(build_sim, ability, anchor, window, seed_base + i) for i in range(first, first + count)]

    result = DamageMeasurement(ability=ability, anchor=anchor, window=window)
    started = time.perf_counter()
    while result.trials < trials:
        for hits in run_batch(result.trials, min(max(1, batch_size), trials - result.trials)):
            result.trials += 1
            for hit in hits:
                result.hits += 1
                if hit["crit"]:
                    result.crits += 1
                    result.crit_damage.append(hit["damage"])
                else:
                    result.normal.append(hit["damage"])
                if hit["bonus_crit"] is not None:
                    result.bonus_crit.append(float(hit["bonus_crit"]))
    if reference is None and build_sim is not None:
        reference = reference_stats(build_sim, anchor)
    result.reference = reference or {}
    result.seconds = time.perf_counter() - started
    return result

def _worker_damage(args: tuple):
    from src.swtorsim.debug import proc_measure

    ability, anchor, window, trial_seed = args
    return run_damage_trial(proc_measure._worker_build_sim, ability, anchor, window, trial_seed)


class ParallelDamageTrials:
    """Damage trials on worker processes (each builds the fight with a tracer once). Use as a context manager."""

    def __init__(self, config_path: str, environment: str, seed: int | None, ability: str, anchor: float,
                 window: float, workers: int, seed_base: int = 2_000_003):
        self._args = (config_path, environment, seed, True)
        self._ability, self._anchor, self._window, self._seed_base = ability, anchor, window, seed_base
        self.workers = max(1, int(workers))
        self.batch_size = self.workers * 4
        self._pool = None

    def __enter__(self):
        from concurrent.futures import ProcessPoolExecutor
        from src.swtorsim.debug import proc_measure

        self._pool = ProcessPoolExecutor(self.workers, initializer=proc_measure._init_worker, initargs=self._args)
        return self

    def __exit__(self, *exc):
        self._pool.shutdown(wait=True, cancel_futures=True)
        self._pool = None

    def run_batch(self, first: int, count: int):
        jobs = [(self._ability, self._anchor, self._window, self._seed_base + i) for i in range(first, first + count)]
        return list(self._pool.map(_worker_damage, jobs))
