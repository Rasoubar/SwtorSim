"""Run the sim over a crit sweep and fit the diminishing-return slopes."""

import os
import random
import sys
import time
from dataclasses import dataclass
from multiprocessing import Pool, cpu_count

import numpy as np

from src.diminishing_returns.config import (
    PAIR_COLORS,
    PAIR_LABELS,
    VARIANT_ORDER,
    DrConfig,
    SpecEntry,
    with_relics,
)
from src.diminishing_returns.fit import CritCurves, fit_surface
from src.diminishing_returns.raw import RawRun, load_raw, raw_results_path, save_raw
from src.swtorsim.combat_curves import (
    CRITICAL_CHANCE_TARGET,
    CRITICAL_DAMAGE_TARGET,
    CRITICAL_RATING,
    derived_stat,
)
from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.settings import set_stem_matching
from src.swtorsim.setup import prepare_simulation

MASTERY_STEP = 1000.0
MASTERY_TOLERANCE = 1e-3
GRID_POINTS = 201

_STATE: dict = {}


@dataclass
class SpecResult:
    """Curves for one spec, ready to plot."""

    name: str
    crit: np.ndarray
    mastery_slope: np.ndarray
    power_slope: np.ndarray
    crit_slope: np.ndarray
    mastery_sigma: np.ndarray
    power_sigma: np.ndarray
    crit_sigma: np.ndarray
    sweep_label: str
    xlabel: str
    relic_gains: list[tuple[str, str, np.ndarray]]
    gear_label: str
    game_version: str
    author: str
    build_dps: float | None


def run_specs(dr: DrConfig, debug: bool = False) -> list[SpecResult]:
    """Runs every spec in the config and returns its fitted curves."""
    if not dr.specs:
        raise ValueError("DR config has no specs.")
    set_stem_matching(dr.specs[0].run_config.enable_stem_matching)
    return [run_spec(dr, spec, index, debug=debug) for index, spec in enumerate(dr.specs)]


def run_spec(dr: DrConfig, spec: SpecEntry, spec_index: int, debug: bool = False) -> SpecResult:
    """Samples one spec under four relic setups, then fits the slopes."""
    started = time.perf_counter()
    print(f"\n{spec.name}: {dr.samples_per_variant} samples x {len(VARIANT_ORDER)} relic variants")
    reference = _load_quietly(spec.run_config)
    ratio = _assert_mastery_multiplier(
        reference, spec.run_config.dummy_hp, dr.expected_mastery_multiplier
    )
    print(f"Mastery bonus: {ratio:.4f} per base point (expected {dr.expected_mastery_multiplier:g})")

    build_stats = reference.stats_config["stats"]
    crit, mastery, power, seeds = _sample_design(dr, build_stats, spec_index)
    dps = _run_variants(dr, spec, crit, mastery, power, seeds)

    mastery0 = float(build_stats["Mastery"])
    power0 = float(build_stats["Power"])
    build_crit = float(build_stats[dr.sweep_stat])
    if debug:
        path = save_raw(RawRun(
            spec_name=spec.name,
            pair_key=spec.pair_key,
            sweep_stat=dr.sweep_stat,
            crit=crit,
            mastery=mastery,
            power=power,
            seeds=seeds,
            dps=dps,
            mastery0=mastery0,
            power0=power0,
            build_crit=build_crit,
            sweep_min=dr.sweep_min,
            sweep_max=dr.sweep_max,
        ), raw_results_path(spec.name))
        print(f"Saved raw results to {path}")
    return _fit_result(
        dr, spec.name, spec.pair_key, crit, mastery, power, dps,
        mastery0, power0, build_crit, dr.sweep_stat, dr.sweep_min, dr.sweep_max, started,
    )


def refit_raw(path: str, dr: DrConfig) -> SpecResult:
    """Fits and returns curves from a debug archive, without simulating."""
    raw = load_raw(path)
    print(
        f"\nRefitting {raw.spec_name} from {path} ({len(raw.crit)} samples)"
    )
    if raw.sweep_min != dr.sweep_min or raw.sweep_max != dr.sweep_max:
        print(
            f"  saved sweep is {raw.sweep_min:g}..{raw.sweep_max:g}; "
            "the plot uses that range"
        )
    return _fit_result(
        dr, raw.spec_name, raw.pair_key, raw.crit, raw.mastery, raw.power, raw.dps,
        raw.mastery0, raw.power0, raw.build_crit, raw.sweep_stat,
        raw.sweep_min, raw.sweep_max, time.perf_counter(),
    )


def _fit_result(
    dr: DrConfig,
    spec_name: str,
    pair_key: str,
    crit,
    mastery,
    power,
    dps,
    mastery0: float,
    power0: float,
    build_crit: float,
    sweep_stat: str,
    sweep_min: float,
    sweep_max: float,
    started: float,
) -> SpecResult:
    """Fits each relic variant and packages the curves for plotting."""
    curves = _crit_curves(dr.level)
    fits = {
        key: fit_surface(crit, mastery, power, dps[key], mastery0, power0, curves)
        for key in VARIANT_ORDER
    }
    for key in VARIANT_ORDER:
        fit = fits[key]
        print(f"  {key}: game crit curves, residual std {fit.residual_std:,.0f} DPS")

    grid = np.linspace(sweep_min, sweep_max, GRID_POINTS)
    chosen = fits[pair_key].evaluate(grid)
    relic_gains = []
    for key in VARIANT_ORDER:
        if key == "none":
            continue
        # The four variants share seeds, so the relic gain is fit on the paired
        # DPS difference. Its standard error then leaves out noise that cancels.
        gain = fit_surface(
            crit, mastery, power, dps[key] - dps["none"], mastery0, power0, curves
        ).evaluate(grid)
        relic_gains.append((PAIR_LABELS[key], PAIR_COLORS[key], gain.dps, gain.dps_sigma))

    if sweep_min <= build_crit <= sweep_max:
        at_build = fits[pair_key].evaluate(np.array([build_crit]))
        build_dps = float(at_build.dps[0])
        print(f"DPS {(spec_name + ':').ljust(22)}{round(build_dps)}")
        print(
            f"  at {sweep_stat} {build_crit:g}: "
            f"Mastery {at_build.dps_per_mastery[0]:.3f} ± {at_build.dps_per_mastery_sigma[0]:.3f}, "
            f"Power {at_build.dps_per_power[0]:.3f} ± {at_build.dps_per_power_sigma[0]:.3f}, "
            f"Crit {at_build.dps_per_crit[0]:.3f} ± {at_build.dps_per_crit_sigma[0]:.3f} DPS per point"
        )
    else:
        build_dps = None
        print(
            f"Build {sweep_stat} {build_crit:g} is outside "
            f"{sweep_min:g}..{sweep_max:g}, so fitted DPS at the build is omitted."
        )
    print(f"Finished {spec_name} in {time.perf_counter() - started:.1f}s")

    xlabel = "Crit Rating" if sweep_stat == "Critical Rating" else sweep_stat
    sweep_label = "Crit" if sweep_stat == "Critical Rating" else sweep_stat
    return SpecResult(
        name=spec_name,
        crit=chosen.crit,
        mastery_slope=chosen.dps_per_mastery,
        power_slope=chosen.dps_per_power,
        crit_slope=chosen.dps_per_crit,
        mastery_sigma=chosen.dps_per_mastery_sigma,
        power_sigma=chosen.dps_per_power_sigma,
        crit_sigma=chosen.dps_per_crit_sigma,
        sweep_label=sweep_label,
        xlabel=xlabel,
        relic_gains=relic_gains,
        gear_label=dr.gear_label,
        game_version=dr.game_version,
        author=dr.author,
        build_dps=build_dps,
    )


def _crit_curves(level: int) -> CritCurves:
    chance_divisor, chance_cap = derived_stat(CRITICAL_RATING, level, CRITICAL_CHANCE_TARGET)
    damage_divisor, damage_cap = derived_stat(CRITICAL_RATING, level, CRITICAL_DAMAGE_TARGET)
    return CritCurves(
        level=level,
        chance_cap=chance_cap,
        chance_divisor=chance_divisor,
        damage_cap=damage_cap,
        damage_divisor=damage_divisor,
    )


def _sample_design(dr: DrConfig, build_stats: dict, spec_index: int):
    rng = np.random.default_rng([dr.seed, spec_index])
    n = dr.samples_per_variant
    crit = np.linspace(dr.sweep_min, dr.sweep_max, n)
    mastery = float(build_stats["Mastery"]) + rng.uniform(-dr.jitter_mastery, dr.jitter_mastery, n)
    power = float(build_stats["Power"]) + rng.uniform(-dr.jitter_power, dr.jitter_power, n)
    seeds = rng.integers(0, 2**31, size=n)
    return crit, mastery, power, seeds


def _run_variants(dr: DrConfig, spec: SpecEntry, crit, mastery, power, seeds) -> dict[str, np.ndarray]:
    n = len(crit)
    variants = dr.variant_relics()
    payload = {
        "enable_stem_matching": spec.run_config.enable_stem_matching,
        "duration": spec.run_config.duration,
        "dummy_hp": spec.run_config.dummy_hp,
        "sweep_stat": dr.sweep_stat,
        "variants": [
            (key, with_relics(spec.run_config, variants[key]))
            for key in VARIANT_ORDER
        ],
    }
    tasks = [
        (key, float(crit[i]), float(mastery[i]), float(power[i]), int(seeds[i]))
        for key in VARIANT_ORDER
        for i in range(n)
    ]
    cores = cpu_count() or 1
    chunksize = max(1, len(tasks) // (cores * 8))
    print(f"Using {cores} CPU cores")
    harvested = np.empty(len(tasks))
    started = time.perf_counter()
    report_every = max(1, len(tasks) // 20)
    with Pool(processes=cores, initializer=_initializer, initargs=(payload,)) as pool:
        for index, value in enumerate(pool.imap(_worker, tasks, chunksize=chunksize)):
            harvested[index] = value
            done = index + 1
            if done % report_every == 0 or done == len(tasks):
                elapsed = time.perf_counter() - started
                print(f"  {done}/{len(tasks)} fights  {done / elapsed:,.0f} fights/s", flush=True)

    return {
        key: harvested[index * n:(index + 1) * n]
        for index, key in enumerate(VARIANT_ORDER)
    }


def _initializer(payload: dict) -> None:
    old = sys.stdout
    sys.stdout = open(os.devnull, "w")
    try:
        set_stem_matching(payload["enable_stem_matching"])
        _STATE["duration"] = payload["duration"]
        _STATE["dummy_hp"] = payload["dummy_hp"]
        _STATE["sweep_stat"] = payload["sweep_stat"]
        _STATE["variants"] = {
            key: load_from_run_config(run_config)
            for key, run_config in payload["variants"]
        }
    finally:
        sys.stdout.close()
        sys.stdout = old


def _worker(task) -> float:
    variant_key, sweep_value, mastery, power, seed = task
    old = sys.stdout
    sys.stdout = open(os.devnull, "w")
    try:
        random.seed(seed)
        inputs = _STATE["variants"][variant_key]
        base = inputs.stats_config
        stats_config = {
            "class_name": base["class_name"],
            "level": base["level"],
            "stats": {
                **base["stats"],
                _STATE["sweep_stat"]: sweep_value,
                "Mastery": mastery,
                "Power": power,
            },
        }
        sim, _player, target = prepare_simulation(
            inputs.rotation_config,
            stats_config,
            inputs.loadout_blueprints,
            _STATE["dummy_hp"],
            inputs.debuff_module,
        )
        sim.run_timed(_STATE["duration"], target)
        elapsed = sim.current_time
        if elapsed <= 0.0:
            raise RuntimeError(f"Simulation for seed {seed} ended at time 0.")
        return sim.tracker.total_damage / elapsed
    finally:
        sys.stdout.close()
        sys.stdout = old


def _assert_mastery_multiplier(inputs, dummy_hp: int, expected: float) -> float:
    base_mastery = float(inputs.stats_config["stats"]["Mastery"])
    low = _effective_mastery(inputs, dummy_hp, base_mastery)
    high = _effective_mastery(inputs, dummy_hp, base_mastery + MASTERY_STEP)
    ratio = (high - low) / MASTERY_STEP
    if abs(ratio - expected) > MASTERY_TOLERANCE:
        raise RuntimeError(
            "Mastery bonus check failed: raising base Mastery by "
            f"{MASTERY_STEP:g} changed effective Mastery by {ratio:.4f} per point, "
            f"expected {expected:g}. The class buff passive should apply this."
        )
    return ratio


def _effective_mastery(inputs, dummy_hp: int, mastery: float) -> float:
    base = inputs.stats_config
    stats_config = {
        "class_name": base["class_name"],
        "level": base["level"],
        "stats": {**base["stats"], "Mastery": mastery},
    }
    old = sys.stdout
    sys.stdout = open(os.devnull, "w")
    try:
        _sim, player, _target = prepare_simulation(
            inputs.rotation_config,
            stats_config,
            inputs.loadout_blueprints,
            dummy_hp,
            inputs.debuff_module,
        )
    finally:
        sys.stdout.close()
        sys.stdout = old
    return float(player.stats["Mastery"])


def _load_quietly(run_config):
    old = sys.stdout
    sys.stdout = open(os.devnull, "w")
    try:
        return load_from_run_config(run_config)
    finally:
        sys.stdout.close()
        sys.stdout = old
