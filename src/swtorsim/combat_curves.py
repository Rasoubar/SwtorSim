"""Level-dependent combat rating curves, standard health tables, and armor constants."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.swtorsim.settings import get_extractor_data_dir, get_data_environment

CURVES_PATH = Path("data/extractor/live/combat_curves.json")

ALACRITY_RATING = "STAT_rtg_spell_haste"
ACCURACY_RATING = "STAT_rtg_accuracy"
CRITICAL_RATING = "STAT_rtg_critical_chance"
CRITICAL_CHANCE_TARGET = "STAT_cbt_force_critical_chance"
CRITICAL_DAMAGE_TARGET = "STAT_cbt_force_critical_damage"
MASTERY = "STAT_att_mastery"

_ARMOR_ADDITIVE = "dcvArmorDamageReductionAdditive"
_ARMOR_MULTIPLIER = "dcvArmorDamageReductionLevelMultiplier"


@lru_cache(maxsize=4)
def _load_curves(env: str) -> dict[str, Any]:
    """Loads and caches combat_curves.json for the specified data environment."""
    curves_path = get_extractor_data_dir(env) / "combat_curves.json"
    if not curves_path.exists():
        curves_path = CURVES_PATH
    with curves_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _curves(env: str | None = None) -> dict[str, Any]:
    """Returns the loaded combat curves dictionary for the requested or active environment."""
    active_env = env or get_data_environment()
    return _load_curves(active_env)


def player_standard_health(level: int, env: str | None = None) -> int:
    """Player standard health from cbtStandardDamage at this level."""
    table = _curves(env)["cbtStandardDamage"]["player"]
    return int(_level_row(table, level, "player standard health"))


def derived_stat(source: str, level: int, target: str | None = None, env: str | None = None) -> tuple[float, float]:
    """Returns (divisor, cap) for a derived-stat source at this level."""
    groups = _curves(env)["modDerivedStatModifiers"].get(source)
    if not groups:
        raise KeyError(f"No derived-stat curve for '{source}'.")

    if target is None:
        if len(groups) != 1:
            raise KeyError(f"'{source}' has multiple curves; pass a target stat.")
        group = groups[0]
    else:
        matches = [group for group in groups if target in group["targets"]]
        if len(matches) != 1:
            raise KeyError(f"No unique '{source}' curve targets '{target}'.")
        group = matches[0]

    row = _level_row(group["levels"], level, f"{source} curve")
    return float(row["divisor"]), float(row["cap"])


def armor_constants(level: int, env: str | None = None) -> tuple[float, float]:
    """Returns (level multiplier, additive) for armor damage reduction."""
    row = _level_row(
        _curves(env)["dcvCombatSystemsPerLevel"],
        level,
        "armor constants",
    )
    return float(row[_ARMOR_MULTIPLIER]), float(row[_ARMOR_ADDITIVE])


def _level_row(table: dict, level: int, label: str) -> Any:
    """Looks up the curve row for ``level``, clamping to the nearest available level bound if needed."""
    key = str(level)
    if key in table:
        return table[key]
    numeric_keys = [int(k) for k in table.keys() if k.isdigit()]
    if numeric_keys:
        max_lvl = max(numeric_keys)
        if level > max_lvl:
            return table[str(max_lvl)]
        min_lvl = min(numeric_keys)
        if level < min_lvl:
            return table[str(min_lvl)]
    raise KeyError(f"No {label} for level {level}.")
