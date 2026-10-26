from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

from extractor.config import (
    COMBAT_SYSTEMS_PER_LEVEL_FQN,
    DERIVED_STAT_MAPPING_FQN,
    DERIVED_STAT_MODIFIERS_FQN,
    STANDARD_DAMAGE_FQN,
    STANDARD_HEALING_FQN,
)
from extractor.gom.gom import GomLookup
from extractor.graph import BucketStore
from extractor.node import ParsedField, ParsedNode

DIVISOR_FIELD = "modDerivedStatMappingPercentageDivisor"
CAP_FIELD = "modDerivedStatMappingPercentageCap"
SPEC_FIELD = "modDerivedStatMappingModifierSpec"
TARGET_STAT_FIELD = "modDerivedStatMappingTargetStat"
MODIFIERS_FIELD = "modDerivedStatModifiersList"
MAPPING_FIELD = "modDerivedStatMappingListData"
ARMOR_ADDITIVE_FIELD = "dcvArmorDamageReductionAdditive"
ARMOR_MULTIPLIER_FIELD = "dcvArmorDamageReductionLevelMultiplier"
STANDARD_TABLE_FIELD = "cbtStandardDamageHealing"
TOUGHNESS_PREFIX = "cbtToughness_"
STANDARD_CURVES = ("player", "boss_raid")


def build_combat_curves(
    store: BucketStore,
    gom: GomLookup,
    output_path: Path,
) -> None:
    """Write per-level divisor/cap, armor, and standard damage/healing curves."""
    payload = {
        "modDerivedStatModifiers": _derived_stat_modifiers(store, gom),
        "dcvCombatSystemsPerLevel": _armor_by_level(store, gom),
        "cbtStandardDamage": _standard_curve(store, gom, STANDARD_DAMAGE_FQN),
        "cbtStandardHealing": _standard_curve(store, gom, STANDARD_HEALING_FQN),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _derived_stat_modifiers(
    store: BucketStore,
    gom: GomLookup,
) -> dict[str, list[dict[str, Any]]]:
    curves, known_specs = _divisor_curves(store, gom)
    mapping = _parse_fqn(store, gom, DERIVED_STAT_MAPPING_FQN)
    field = _require_field(mapping, MAPPING_FIELD)
    key_enum, _value_enum = gom.lookup_list_enum_refs(field.id)
    grouped: dict[str, OrderedDict[str, list[str]]] = {}

    for entry in _lookup_entries(field.value, MAPPING_FIELD):
        source = _enum_member(gom, key_enum, _enum_index(entry["key"]))
        if source in grouped:
            raise RuntimeError(f"Duplicate derived-stat mapping for {source}")
        spec_targets: OrderedDict[str, list[str]] = OrderedDict()
        for context in _lookup_entries(entry["value"], MAPPING_FIELD):
            for row in _class_rows(context["value"]):
                named = _named_fields(gom, row)
                spec = _decimal_id(named[SPEC_FIELD][1])
                if spec not in known_specs:
                    raise RuntimeError(
                        f"Modifier spec {spec} for {source} is missing from "
                        f"{DERIVED_STAT_MODIFIERS_FQN}"
                    )
                if spec not in curves:
                    continue
                _target_id, target_value = named[TARGET_STAT_FIELD]
                target = _enum_member(
                    gom,
                    gom.field_enum_ref(_target_id),
                    _enum_index(target_value),
                )
                targets = spec_targets.setdefault(spec, [])
                if target not in targets:
                    targets.append(target)
        if spec_targets:
            grouped[source] = spec_targets

    if not grouped:
        raise RuntimeError(
            f"No divisor/cap stats found in {DERIVED_STAT_MODIFIERS_FQN}"
        )

    return {
        source: [
            {"targets": targets, "levels": curves[spec]}
            for spec, targets in spec_targets.items()
        ]
        for source, spec_targets in grouped.items()
    }


def _divisor_curves(
    store: BucketStore,
    gom: GomLookup,
) -> tuple[dict[str, dict[str, dict[str, float]]], set[str]]:
    parsed = _parse_fqn(store, gom, DERIVED_STAT_MODIFIERS_FQN)
    field = _require_field(parsed, MODIFIERS_FIELD)
    curves: dict[str, dict[str, dict[str, float]]] = {}
    known_specs: set[str] = set()
    for entry in _lookup_entries(field.value, MODIFIERS_FIELD):
        spec = _decimal_id(entry["key"])
        known_specs.add(spec)
        levels: dict[str, dict[str, float]] = {}
        for level_entry in _lookup_entries(entry["value"], MODIFIERS_FIELD):
            named = _named_fields(gom, level_entry["value"])
            if DIVISOR_FIELD not in named or CAP_FIELD not in named:
                continue
            level = _level_key(level_entry["key"])
            levels[level] = {
                "divisor": _as_float(named[DIVISOR_FIELD][1]),
                "cap": _as_float(named[CAP_FIELD][1]),
            }
        if levels:
            curves[spec] = _sorted_levels(levels)
    return curves, known_specs


def _armor_by_level(store: BucketStore, gom: GomLookup) -> dict[str, dict[str, float]]:
    parsed = _parse_fqn(store, gom, COMBAT_SYSTEMS_PER_LEVEL_FQN)
    additive = _float_levels(parsed, ARMOR_ADDITIVE_FIELD)
    multiplier = _float_levels(parsed, ARMOR_MULTIPLIER_FIELD)
    if set(additive) != set(multiplier):
        raise RuntimeError(
            f"{COMBAT_SYSTEMS_PER_LEVEL_FQN} armor fields do not cover the same levels"
        )
    return _sorted_levels(
        {
            level: {
                ARMOR_ADDITIVE_FIELD: additive[level],
                ARMOR_MULTIPLIER_FIELD: multiplier[level],
            }
            for level in additive
        }
    )


def _standard_curve(
    store: BucketStore,
    gom: GomLookup,
    fqn: str,
) -> dict[str, dict[str, int]]:
    parsed = _parse_fqn(store, gom, fqn)
    field = _require_field(parsed, STANDARD_TABLE_FIELD)
    key_enum, _value_enum = gom.lookup_list_enum_refs(field.id)
    found: dict[str, dict[str, int]] = {}
    for entry in _lookup_entries(field.value, STANDARD_TABLE_FIELD):
        name = _enum_member(gom, key_enum, _enum_index(entry["key"]))
        if not name.startswith(TOUGHNESS_PREFIX):
            raise RuntimeError(f"Unexpected toughness key {name} on {fqn}")
        curve = name[len(TOUGHNESS_PREFIX) :]
        if curve not in STANDARD_CURVES:
            continue
        levels = {
            _level_key(level_entry["key"]): _as_int(level_entry["value"])
            for level_entry in _lookup_entries(entry["value"], STANDARD_TABLE_FIELD)
        }
        found[curve] = _sorted_levels(levels)
    missing = [curve for curve in STANDARD_CURVES if curve not in found]
    if missing:
        raise RuntimeError(f"{fqn} is missing curves: {', '.join(missing)}")
    return {curve: found[curve] for curve in STANDARD_CURVES}


def _float_levels(parsed: ParsedNode, field_name: str) -> dict[str, float]:
    field = _require_field(parsed, field_name)
    levels = {
        _level_key(entry["key"]): _as_float(entry["value"])
        for entry in _lookup_entries(field.value, field_name)
    }
    if not levels:
        raise RuntimeError(f"{field_name} has no levels")
    return levels


def _parse_fqn(store: BucketStore, gom: GomLookup, fqn: str) -> ParsedNode:
    node_id = store.fqn_to_id.get(fqn)
    if node_id is None:
        raise RuntimeError(f"Failed to load {fqn}")
    return store.parse_node(node_id, gom)


def _require_field(parsed: ParsedNode, name: str) -> ParsedField:
    for field in parsed.fields:
        if field.name == name:
            return field
    raise RuntimeError(f"Missing field {name}")


def _lookup_entries(value: Any, field_name: str) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or "key_type" not in value or "list" not in value:
        raise RuntimeError(f"{field_name} is not a lookup list")
    entries = value["list"]
    if not isinstance(entries, list):
        raise RuntimeError(f"{field_name} lookup list is empty or invalid")
    return entries


def _class_rows(value: Any) -> list[list[dict[str, Any]]]:
    if not isinstance(value, dict) or "list" not in value:
        raise RuntimeError("Expected a list of modifier mapping rows")
    rows: list[list[dict[str, Any]]] = []
    for item in value["list"]:
        if not isinstance(item, list):
            raise RuntimeError("Expected class fields on a modifier mapping row")
        rows.append(item)
    return rows


def _named_fields(gom: GomLookup, children: Any) -> dict[str, tuple[str, Any]]:
    if not isinstance(children, list):
        raise RuntimeError("Expected class fields")
    named: dict[str, tuple[str, Any]] = {}
    for child in children:
        field_id = str(child["id"])
        named[gom.field_name(field_id)] = (field_id, child["value"])
    return named


def _enum_index(value: Any) -> int:
    if isinstance(value, dict) and "index" in value:
        return int(value["index"])
    raise RuntimeError(f"Expected an enum index, got {value!r}")


def _enum_member(gom: GomLookup, enum_id: str | None, index: int) -> str:
    if not enum_id:
        raise RuntimeError("Missing enum type for a combat curve field")
    name = gom.enum_member(enum_id, index)
    if name == str(index) or name.endswith(f"[{index}]"):
        raise RuntimeError(f"Failed to resolve enum {enum_id} index {index}")
    return name


def _level_key(value: Any) -> str:
    return _decimal_id(value)


def _decimal_id(value: Any) -> str:
    if isinstance(value, bool):
        raise RuntimeError(f"Expected an integer id, got {value!r}")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.isdigit():
        return str(int(value))
    raise RuntimeError(f"Expected an integer id, got {value!r}")


def _as_float(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"Expected a float, got {value!r}")
    return float(value)


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        raise RuntimeError(f"Expected an integer, got {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    raise RuntimeError(f"Expected an integer, got {value!r}")


def _sorted_levels(levels: dict[str, Any]) -> dict[str, Any]:
    return {level: levels[level] for level in sorted(levels, key=int)}
