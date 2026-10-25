import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Set, Union

STAT_ID_MAP: Dict[int, str] = {}


def load_stat_map(csv_path: Union[str, Path]) -> None:
    """Populates STAT_ID_MAP from the modifier_id_mapping CSV file."""
    path = Path(csv_path)
    if not path.is_file():
        return

    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                STAT_ID_MAP[int(row["Global ID"])] = row["Column1"]
            except (KeyError, ValueError):
                continue


def _auto_load_stat_map() -> None:
    """Searches upward from this file and cwd to find and load data/modifier_id_mapping.csv."""
    search_roots = [Path(__file__).resolve(), Path.cwd()]
    for root in search_roots:
        for parent in [root, *root.parents]:
            candidate = parent / "data" / "modifier_id_mapping.csv"
            if candidate.is_file():
                load_stat_map(candidate)
                return


_auto_load_stat_map()


def _modify_stat_amount(action: Dict[str, Any]) -> float:
    """Uses the percent when it is set, otherwise the flat minimum."""
    percent = float(action.get("amount_percent") or 0.0)
    if percent:
        return percent
    return float(action.get("amount_min") or 0.0)


def resolve_stat(raw_stat: Union[str, int]) -> str:
    """Translates integer Global IDs to canonical strings, or returns existing strings."""
    if isinstance(raw_stat, int):
        return STAT_ID_MAP.get(raw_stat, str(raw_stat))
    if isinstance(raw_stat, str) and raw_stat.isdigit():
        return STAT_ID_MAP.get(int(raw_stat), raw_stat)
    return str(raw_stat)


def extract_targets(data: Dict[str, Any]) -> frozenset:
    """Extracts ability FQNs and category tags across impact, tags, and strings blocks."""
    targets: Set[str] = set()

    # 1. Action / effect tags list
    raw_tags = data.get("tags")
    if isinstance(raw_tags, list):
        targets.update(t for t in raw_tags if isinstance(t, str))

    # 2. Talent impact block (dict or raw string)
    impact = data.get("impact")
    if isinstance(impact, dict):
        fqn = impact.get("fqn")
        if fqn:
            targets.add(fqn)
    elif isinstance(impact, str) and impact:
        targets.add(impact)

    # 3. Action strings fallback
    strings = data.get("strings")
    if isinstance(strings, dict):
        tag = strings.get("tag")
        if tag:
            targets.add(tag)

    return frozenset(targets)


@dataclass(frozen=True)
class Modifier:
    """A concrete stat adjustment applied by an effect or talent."""

    stat: str
    value: float
    targets: frozenset = frozenset()
    conditional_tag: Optional[str] = None
    is_percent: bool = False

    def applies_to(
            self,
            ability_fqn: Optional[str] = None,
            ability_tags: frozenset = frozenset(),
    ) -> bool:
        """Returns True if the modifier applies globally or matches the ability's FQN or tags."""
        if not self.targets:
            return True
        if ability_fqn and ability_fqn in self.targets:
            return True
        if ability_tags and not self.targets.isdisjoint(set(ability_tags)):
            return True
        if ability_fqn:
            from src.swtorsim.settings import is_stem_matching_enabled
            if is_stem_matching_enabled():
                for t in self.targets:
                    stem = str(t).split(".")[-1]
                    if stem and ability_fqn.endswith(f".{stem}_plus"):
                        return True
        return False

    @classmethod
    def from_stat_change(cls, data: Dict[str, Any]) -> "Modifier":
        """Builds a Modifier from a root-level talent stat_changes entry."""
        raw_stat = data.get("name") or data.get("stat", "")
        resolved = resolve_stat(raw_stat)
        raw_val = data.get("value", 0.0)
        try:
            val = float(raw_val)
        except (ValueError, TypeError):
            val = 0.0

        if "percentage" in resolved.lower() or "_pct" in resolved.lower():
            is_pct = True
        elif resolved in ("64", "STAT_abl_time_cooldown"):
            is_pct = False
        elif resolved in ("68", "STAT_abl_cost_force"):
            # Bioware overloaded STAT_abl_cost_force: -0.10 is -10%, while -3.0 to -25.0 are flat Force
            is_pct = (-1.0 < val < 1.0 and val != 0.0)
        else:
            is_pct = False
        return cls(
            stat=resolved,
            value=val,
            targets=extract_targets(data),
            is_percent=is_pct,
        )

    @classmethod
    def from_modify_stat(cls, action: Dict[str, Any]) -> "Modifier":
        """Builds a Modifier from a flat modify_stat action node."""
        raw_stat = action.get("stat") or action.get("name", "")
        resolved = resolve_stat(raw_stat)
        percent = float(action.get("amount_percent") or 0.0)
        min_amt = float(action.get("amount_min") or 0.0)
        if percent != 0.0:
            is_pct = True
            val = percent
        elif "percentage" in resolved.lower() or "_pct" in resolved.lower():
            is_pct = True
            val = min_amt
        else:
            is_pct = False
            val = min_amt
        return cls(
            stat=resolved,
            value=val,
            targets=extract_targets(action),
            is_percent=is_pct,
        )

    @classmethod
    def from_modify_meta_stat(cls, action: Dict[str, Any]) -> "Modifier":
        """Builds a Modifier from a nested modify_meta_stat action node."""
        floats = action.get("floats") or {}
        ints = action.get("ints") or {}
        bools = action.get("bools") or {}
        raw_stat = ints.get("stat", action.get("stat", ""))
        resolved = resolve_stat(raw_stat)
        stat_mod_type = ints.get("stat_mod_type")
        # In SWTOR GOM: stat_mod_type 1 = flat, 2 = percentage
        is_pct = (stat_mod_type == 2) or bool(bools.get("is_percentage", False)) or "percentage" in resolved.lower()
        return cls(
            stat=resolved,
            value=float(floats.get("amount", 0.0)),
            targets=extract_targets(action),
            is_percent=is_pct,
        )

    @classmethod
    def from_conditional_stat_mod(cls, action: Dict[str, Any]) -> "Modifier":
        """Builds a Modifier from apply_conditional_meta_stat_mod or apply_conditional_stat_mod."""
        floats = action.get("floats") or {}
        ints = action.get("ints") or {}
        bools = action.get("bools") or {}
        strings = action.get("strings") or {}
        raw_stat = ints.get("stat", action.get("stat", ""))
        resolved = resolve_stat(raw_stat)
        percent = float(floats.get("amount_percent") or 0.0)
        min_amt = float(floats.get("amount_min") or 0.0)
        amt = floats.get("amount")
        stat_mod_type = ints.get("stat_mod_type")
        if percent != 0.0:
            is_pct = True
            val = percent
        elif stat_mod_type == 2:
            is_pct = True
            val = float(amt) if amt is not None else min_amt
        elif amt is not None:
            val = float(amt)
            is_pct = bool(bools.get("is_percentage", False)) or "percentage" in resolved.lower()
        else:
            val = min_amt
            is_pct = bool(bools.get("is_percentage", False)) or "percentage" in resolved.lower()
        cond_tag = strings.get("conditional_tag") or action.get("conditional_tag")
        return cls(
            stat=resolved,
            value=val,
            targets=extract_targets(action),
            conditional_tag=cond_tag if cond_tag else None,
            is_percent=is_pct,
        )
