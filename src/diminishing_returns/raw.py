"""Saved fight results, so a fit can be redone without simulating again."""

import json
import os
from dataclasses import dataclass

import numpy as np

from src.diminishing_returns.config import VARIANT_ORDER

RAW_DIR = os.path.join("figures", "dr")


@dataclass
class RawRun:
    """One spec's samples and the DPS of each relic variant."""

    spec_name: str
    pair_key: str
    sweep_stat: str
    crit: np.ndarray
    mastery: np.ndarray
    power: np.ndarray
    seeds: np.ndarray
    dps: dict[str, np.ndarray]
    mastery0: float
    power0: float
    build_crit: float
    sweep_min: float
    sweep_max: float


def raw_results_path(spec_name: str, out_dir: str = RAW_DIR) -> str:
    """Path of the debug file for a spec."""
    stem = spec_name.replace("/", "_").replace(os.sep, "_")
    return os.path.join(out_dir, f"raw_{stem}.npz")


def save_raw(run: RawRun, path: str) -> str:
    """Writes a compressed archive of the fight inputs and DPS."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    missing = [key for key in VARIANT_ORDER if key not in run.dps]
    if missing:
        raise ValueError(f"Raw results are missing relic variants: {', '.join(missing)}.")
    meta = json.dumps({
        "spec_name": run.spec_name,
        "pair_key": run.pair_key,
        "sweep_stat": run.sweep_stat,
    })
    np.savez_compressed(
        path,
        meta=np.array(meta),
        crit=np.asarray(run.crit, dtype=float),
        mastery=np.asarray(run.mastery, dtype=float),
        power=np.asarray(run.power, dtype=float),
        seeds=np.asarray(run.seeds),
        dps=np.vstack([np.asarray(run.dps[key], dtype=float) for key in VARIANT_ORDER]),
        mastery0=np.float64(run.mastery0),
        power0=np.float64(run.power0),
        build_crit=np.float64(run.build_crit),
        sweep_min=np.float64(run.sweep_min),
        sweep_max=np.float64(run.sweep_max),
    )
    return path


def load_raw(path: str) -> RawRun:
    """Loads an archive written by save_raw."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Raw results not found: {path}")
    with np.load(path) as data:
        meta = json.loads(data["meta"].item())
        stacked = np.asarray(data["dps"], dtype=float)
        if stacked.shape[0] != len(VARIANT_ORDER):
            raise ValueError(
                f"Raw results in '{path}' have {stacked.shape[0]} relic variants, "
                f"expected {len(VARIANT_ORDER)}."
            )
        dps = {key: stacked[index] for index, key in enumerate(VARIANT_ORDER)}
        return RawRun(
            spec_name=meta["spec_name"],
            pair_key=meta["pair_key"],
            sweep_stat=meta["sweep_stat"],
            crit=np.asarray(data["crit"], dtype=float),
            mastery=np.asarray(data["mastery"], dtype=float),
            power=np.asarray(data["power"], dtype=float),
            seeds=np.asarray(data["seeds"]),
            dps=dps,
            mastery0=float(data["mastery0"]),
            power0=float(data["power0"]),
            build_crit=float(data["build_crit"]),
            sweep_min=float(data["sweep_min"]),
            sweep_max=float(data["sweep_max"]),
        )
