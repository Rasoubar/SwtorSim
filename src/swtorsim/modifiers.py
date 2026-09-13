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
        if ability_tags and not self.targets.isdisjoint(ability_tags):
            return True
        return False

    @classmethod
    def from_stat_change(cls, data: Dict[str, Any]) -> "Modifier":
        """Builds a Modifier from a root-level talent stat_changes entry."""
        raw_stat = data.get("name") or data.get("stat", "")
        return cls(
            stat=resolve_stat(raw_stat),
            value=float(data.get("value", 0.0)),
            targets=extract_targets(data),
        )

    @classmethod
    def from_modify_stat(cls, action: Dict[str, Any]) -> "Modifier":
        """Builds a Modifier from a flat modify_stat action node."""
        value = action.get("amount_min", action.get("amount_percent", 0.0))
        raw_stat = action.get("stat") or action.get("name", "")
        return cls(
            stat=resolve_stat(raw_stat),
            value=float(value),
            targets=extract_targets(action),
        )

    @classmethod
    def from_modify_meta_stat(cls, action: Dict[str, Any]) -> "Modifier":
        """Builds a Modifier from a nested modify_meta_stat action node."""
        floats = action.get("floats") or {}
        ints = action.get("ints") or {}
        raw_stat = ints.get("stat", action.get("stat", ""))
        return cls(
            stat=resolve_stat(raw_stat),
            value=float(floats.get("amount", 0.0)),
            targets=extract_targets(action),
        )