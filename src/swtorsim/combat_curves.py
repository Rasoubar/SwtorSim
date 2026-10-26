import json
from functools import lru_cache
from pathlib import Path
from typing import Any

CURVES_PATH = Path("data/extractor/combat_curves.json")

ALACRITY_RATING = "STAT_rtg_spell_haste"
ACCURACY_RATING = "STAT_rtg_accuracy"
CRITICAL_RATING = "STAT_rtg_critical_chance"
CRITICAL_CHANCE_TARGET = "STAT_cbt_force_critical_chance"
CRITICAL_DAMAGE_TARGET = "STAT_cbt_force_critical_damage"
MASTERY = "STAT_att_mastery"

_ARMOR_ADDITIVE = "dcvArmorDamageReductionAdditive"
_ARMOR_MULTIPLIER = "dcvArmorDamageReductionLevelMultiplier"


@lru_cache(maxsize=1)
def _curves() -> dict[str, Any]:
    with CURVES_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def player_standard_health(level: int) -> int:
    """Player standard health from cbtStandardDamage at this level."""
    table = _curves()["cbtStandardDamage"]["player"]
    return int(_level_row(table, level, "player standard health"))


def derived_stat(source: str, level: int, target: str | None = None) -> tuple[float, float]:
    """Returns (divisor, cap) for a derived-stat source at this level."""
    groups = _curves()["modDerivedStatModifiers"].get(source)
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


def armor_constants(level: int) -> tuple[float, float]:
    """Returns (level multiplier, additive) for armor damage reduction."""
    row = _level_row(
        _curves()["dcvCombatSystemsPerLevel"],
        level,
        "armor constants",
    )
    return float(row[_ARMOR_MULTIPLIER]), float(row[_ARMOR_ADDITIVE])


def _level_row(table: dict, level: int, label: str) -> Any:
    key = str(level)
    if key not in table:
        raise KeyError(f"No {label} for level {level}.")
    return table[key]
