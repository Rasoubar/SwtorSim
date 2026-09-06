from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from extractor.bkt import fqn_to_relative_path
from extractor.config import OUTPUT_DIR
from extractor.eff_triggers import (
    EFFECT_DURATION_TRIGGERS,
    decode_trigger_name,
    load_trigger_labels,
)
from extractor.mod_stats import decode_stat_name, get_stat_labels
from extractor.graph import NodeRecord
from extractor.naming import normalize_stack_charge

DEFAULT_BASE_GCD = 1.5

CRIT_RESULT_NAME = "effResultCrit"
CRIT_RESULT_TOKENS = frozenset({CRIT_RESULT_NAME, "32"})

ACTOR_LABELS: dict[str, str] = {
    "2": "caster",
    "3": "target",
}

# cbtComparisonEnum members, each confirmed against Jedipedia's rendering of the
# matching condition: 2/3/5 from abl.sith_warrior.endure_pain/14/1 ("< 100%",
# "> 33%", "<= 33%"), 4 from abl.sith_inquisitor.severing_slash/43/4 ("is not =
# Champion", negated), 6 from abl.sith_inquisitor.whirlwind/41/3 (">= Strong").
# Values 0 and 1 never occur in the extracted data, so they stay unmapped.
COMPARISON_LABELS: dict[str, str] = {
    "2": "lt",
    "3": "gt",
    "4": "eq",
    "5": "lte",
    "6": "gte",
}

LOGIC_OP_LABELS: dict[str, str] = {
    "effLogicOpOr": "or",
    "effLogicOpAnd": "and",
}

# effTargetOverrideEnum members from client.gom (1-based index → snake_case).
TARGET_OVERRIDE_LABELS: dict[str, str] = {
    "1": "invalid",
    "2": "caster",
    "3": "aoe_sphere",
    "4": "primary_target",
    "5": "aoe_cone",
    "6": "pet",
    "7": "master",
    "8": "companion",
    "9": "all_aura_occupants",
    "10": "attacker",
    "11": "defender",
    "12": "enemies_list",
    "13": "owner",
    "14": "aura_occupant",
    "15": "aoe_cylinder",
    "16": "attackers_list",
    "17": "projectile_hit_target",
    "18": "random_enemy",
    "19": "trigger_target",
    "20": "trigger_caster",
    "21": "party_members",
    "22": "raid_members",
    "23": "space_sphere",
    "24": "warzone_team",
    "25": "containing_control_point",
}

# SortType int values on target overrides. Only 1 and 6 appear in extracted
# data; labels confirmed against Jedipedia / in-game behavior (e.g. ion_pulse
# SortType=1 → Closest, volt_rush effect 5 SortType=6 → Least Health).
# These do not match 1-based ordinals of aoeTargetSortTypeEnum in client.gom.
AOE_TARGET_SORT_LABELS: dict[str, str] = {
    "1": "closest",
    "6": "least_health",
}


def _field_value(record: NodeRecord, name: str) -> Any:
    for field in record.resolved_fields:
        if field.get("name") == name:
            return field["value"]
    return None


def _has_field(record: NodeRecord, name: str) -> bool:
    return any(field.get("name") == name for field in record.resolved_fields)


def _ignore_alacrity(record: NodeRecord, name: str, *, default: bool) -> bool:
    if _has_field(record, name):
        return bool(_field_value(record, name))
    return default


def _float_field(record: NodeRecord, name: str) -> float | None:
    value = _field_value(record, name)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _icon_png_name(spec: Any) -> str | None:
    if not isinstance(spec, str):
        return None
    spec = spec.strip()
    if not spec:
        return None
    lower = spec.lower()
    if lower.endswith(".png") or lower.endswith(".dds"):
        spec = spec[: spec.rfind(".")]
        if not spec:
            return None
    return f"{spec}.png"


def icon_stems_from_payload(payload: dict[str, Any]) -> set[str]:
    stems: set[str] = set()

    def _add(name: Any) -> None:
        png = _icon_png_name(name)
        if png is not None:
            stems.add(png[:-4])

    _add(payload.get("icon"))
    for effect in payload.get("effects") or []:
        if isinstance(effect, dict):
            _add(effect.get("icon"))
    return stems


def _snake_case(name: str) -> str:
    for prefix in (
        "effParam_",
        "effCondition_",
        "effAction_",
        "effTrigger_",
        "effTargetOverride_",
    ):
        if name.startswith(prefix):
            name = name[len(prefix) :]
            break
    if name.startswith("_UNUSED_"):
        name = name[len("_UNUSED_") :]
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
    return normalize_stack_charge(s2.lower())


MS_PER_SECOND = 1000.0

DROPPED_ACTION_PARAMS: frozenset[str] = frozenset(
    {
        "effParam_IsSpecialAbility",
        "effParam_DisableCritRoll",
        "effParam_ThreatPercent",
        "effParam_FailureMessageId",
        "effParam_FailureMessage",
        "effParam_Name",
        "effParam_LevelCap",
        "effParam_IgnoreRedirectedDamage",
    }
)

TRIGGER_LABELS: dict[str, str] = load_trigger_labels()

DROPPED_ACTION_TYPES: frozenset[str] = frozenset(
    {
        "effAction_PlayAppearance",
        "effAction_ModifyThreat",
        "effAction_Immobilize",
        "effAction_ModifyMovementSpeed",
    }
)

DROPPED_INITIALIZER_TYPES: frozenset[str] = frozenset(
    {
        "effInitializer_SetName",
        "effInitializer_SetDescription",
        "effInitializer_SetIcon",
        "effInitializer_SetDuration",
        "effInitializer_SetTags",
        "effInitializer_SetType",
        "effInitializer_SetHidden",
    }
)

DROPPED_CONDITION_TYPES: frozenset[str] = frozenset(
    {
        "effCondition_IfCalledByEffect",
        "effCondition_IsAlive",
        "effCondition_IsEnemy",
        "effCondition_IfWeaponType",
        "effCondition_IsChanneling",
        "effCondition_InRange",
    }
)

ELSE_CONDITION_TYPES: frozenset[str] = frozenset(
    {
        "effCondition_Else",
        "effCondition_IfElseBlock",
    }
)


def build_id_to_fqn(records: dict[str, NodeRecord]) -> dict[str, str]:
    return {record.entry.node_id: record.entry.fqn for record in records.values()}


def load_extracted_id_to_fqn(extracted_dir: Path = OUTPUT_DIR) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not extracted_dir.exists():
        return mapping
    for path in extracted_dir.rglob("*.json"):
        if path.name == "index.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        node_id = data.get("id")
        fqn = data.get("fqn")
        if isinstance(node_id, str) and isinstance(fqn, str):
            mapping[node_id] = fqn
    return mapping


def _resolve_ability_spec(
    raw: Any,
    id_to_fqn: dict[str, str] | None,
) -> str | None:
    key = str(raw)
    if key == "0":
        return None
    if id_to_fqn and key in id_to_fqn:
        return id_to_fqn[key]
    return key


def _decode_generic_ints(
    int_params: dict[str, Any],
    *,
    id_to_fqn: dict[str, str] | None = None,
    exclude_keys: frozenset[str] = frozenset(),
    skip_zero: bool = False,
) -> dict[str, Any]:
    ints: dict[str, Any] = {}
    for key, value in int_params.items():
        if key in DROPPED_ACTION_PARAMS or key in exclude_keys:
            continue
        if key == "effParam_AbilitySpec":
            if str(value) == "0":
                ints["ability_spec"] = 0
            else:
                resolved = _resolve_ability_spec(value, id_to_fqn)
                if resolved is not None:
                    ints["ability_spec"] = resolved
            continue
        if str(value).isdigit():
            int_value = int(value)
            if skip_zero and int_value == 0:
                continue
            ints[_snake_case(key)] = int_value
    return ints


def _resolved_conditional_tag(int_params: dict[str, Any]) -> str | None:
    """Return a resolved tag string stored in the int-param ConditionalTag slot."""
    raw = int_params.get("effParam_ConditionalTag")
    if raw is None:
        return None
    value = str(raw).strip()
    if not value or value.isdigit():
        return None
    return value


def _should_drop_condition(condition_name: Any) -> bool:
    return isinstance(condition_name, str) and condition_name in DROPPED_CONDITION_TYPES


def _is_else_condition(condition_name: Any) -> bool:
    return isinstance(condition_name, str) and condition_name in ELSE_CONDITION_TYPES


# ("else", None) for effCondition_Else, ("block", block_id) for IfElseBlock.
ElseMarker = tuple[str, str | None]


def _else_marker_from_fields(fields: dict[str, Any]) -> ElseMarker | None:
    """Read an if/else gating marker from a single condition's fields."""
    condition_name = fields.get("effConditionName")
    if condition_name == "effCondition_Else":
        return ("else", None)
    if condition_name == "effCondition_IfElseBlock":
        int_params = _lookup_list_to_dict(fields.get("effIntParams"))
        block_id = int_params.get("effParam_BlockIdentifier")
        return ("block", str(block_id) if block_id is not None else "1")
    return None


def _branch_else_markers(branch: list[dict[str, Any]]) -> list[ElseMarker]:
    """Collect every Else / IfElseBlock marker on a raw sub-effect."""
    conditions_raw = _sub_effect_field(branch, "effConditions")
    if not isinstance(conditions_raw, list):
        return []
    markers: list[ElseMarker] = []
    for entry in conditions_raw:
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        if not isinstance(value, list):
            continue
        marker = _else_marker_from_fields(_condition_fields(value))
        if marker is not None:
            markers.append(marker)
    return markers


def _resolve_run_if_none_ran(
    markers_by_index: dict[int, list[ElseMarker]],
) -> dict[int, list[int]]:
    """Resolve each marked branch's gate to a list of earlier raw indices.

    Literal reading: Else gates on the immediately previous raw index;
    IfElseBlock gates on every earlier member of the same block. Both markers
    on one sub-effect (currently unused) produce the union.
    """
    gates: dict[int, list[int]] = {}
    for index, markers in sorted(markers_by_index.items()):
        gate: set[int] = set()
        for kind, block_id in markers:
            if kind == "else":
                if index > 1:
                    gate.add(index - 1)
            elif kind == "block":
                for earlier, earlier_markers in markers_by_index.items():
                    if earlier >= index:
                        continue
                    if any(
                        m[0] == "block" and m[1] == block_id for m in earlier_markers
                    ):
                        gate.add(earlier)
        if gate:
            gates[index] = sorted(gate)
    return gates


def _simplify_condition_logic(logic: dict[str, Any] | None) -> dict[str, Any] | None:
    if logic is None:
        return None
    if "condition" in logic:
        return logic
    if "op" not in logic or "operands" not in logic:
        return logic

    op = logic["op"]
    simplified_operands: list[dict[str, Any]] = []
    for operand in logic["operands"]:
        simplified = _simplify_condition_logic(operand)
        if simplified is None:
            continue
        if simplified.get("op") == op and "operands" in simplified:
            simplified_operands.extend(simplified["operands"])
        else:
            simplified_operands.append(simplified)

    if not simplified_operands:
        return None
    if len(simplified_operands) == 1:
        return simplified_operands[0]
    return {"op": op, "operands": simplified_operands}


def _finalize_conditions(
    conditions: dict[str, Any] | None,
    *,
    context: str | None = None,
) -> dict[str, Any] | None:
    if conditions is None:
        return None
    if not conditions.get("list"):
        return None
    logic = _simplify_condition_logic(conditions.get("logic"))
    if logic is None and len(conditions["list"]) == 1:
        logic = {"condition": conditions["list"][0]["id"]}
    if logic is None:
        ids = ", ".join(item["id"] for item in conditions["list"])
        print(
            f"Warning: dropping {len(conditions['list'])} conditions without a "
            f"logic tree on {context or 'unknown node'}: {ids}",
            file=sys.stderr,
        )
        return None
    return {"list": conditions["list"], "logic": logic}


def _lookup_list_to_dict(entries: Any) -> dict[str, Any]:
    if not isinstance(entries, list):
        return {}
    result: dict[str, Any] = {}
    for entry in entries:
        if isinstance(entry, dict) and "key" in entry:
            result[str(entry["key"])] = entry["value"]
    return result


def _decode_actor(raw: Any) -> str:
    key = str(raw)
    return ACTOR_LABELS.get(key, f"actor_{key}")


_warned_comparisons: set[str] = set()


def _decode_comparison(raw: Any, *, context: str | None = None) -> str:
    key = str(raw)
    label = COMPARISON_LABELS.get(key)
    if label is not None:
        return label
    if key not in _warned_comparisons:
        _warned_comparisons.add(key)
        print(
            f"Warning: unmapped comparison value {key} on "
            f"{context or 'unknown node'}; emitting cmp_{key}",
            file=sys.stderr,
        )
    return f"cmp_{key}"


def _ability_name(record: NodeRecord) -> str | None:
    loc_text = _field_value(record, "locTextRetrieverMap")
    if isinstance(loc_text, dict):
        resolved = loc_text.get("resolved_text")
        if isinstance(resolved, str):
            return resolved
    return None


def _cooldown(record: NodeRecord) -> float:
    value = _float_field(record, "ablCooldownTime")
    if value is None:
        return 0.0
    return value


def _effect_ids(record: NodeRecord) -> list[str]:
    effect_ids = _field_value(record, "ablEffectIDs")
    if isinstance(effect_ids, dict) and isinstance(effect_ids.get("list"), list):
        return [str(fqn) for fqn in effect_ids["list"]]
    return []


def _ability_type(record: NodeRecord) -> str:
    is_passive = _field_value(record, "ablIsPassive")
    if is_passive is True:
        return "passive"
    return "active"


def _activation(record: NodeRecord) -> dict[str, Any]:
    channel_time = _float_field(record, "ablChannelingTime")
    if channel_time is not None:
        return {"type": "channel", "duration": channel_time}
    cast_time = _float_field(record, "ablCastingTime")
    if cast_time is not None:
        return {"type": "cast", "duration": cast_time}
    return {"type": "instant", "duration": 0.0}


def _energy_cost(record: NodeRecord) -> float | None:
    force_cost = _float_field(record, "ablForceCost")
    if force_cost is not None:
        return force_cost
    return _float_field(record, "ablEnergyCost")


def _gcd_fields(record: NodeRecord) -> tuple[bool, float]:
    if not _has_field(record, "ablGlobalCooldownTime"):
        return False, 0.0
    gcd_time = _float_field(record, "ablGlobalCooldownTime")
    if gcd_time == -1.0:
        return True, DEFAULT_BASE_GCD
    if gcd_time is not None:
        return True, gcd_time
    return True, DEFAULT_BASE_GCD


def _zero_effect_fqn(record: NodeRecord) -> str | None:
    effect_zero = _field_value(record, "ablEffectZero")
    if isinstance(effect_zero, dict):
        fqn = effect_zero.get("fqn")
        if isinstance(fqn, str):
            return fqn
    return None


def _zero_effect_record(
    record: NodeRecord,
    records_by_fqn: dict[str, NodeRecord],
) -> NodeRecord | None:
    fqn = _zero_effect_fqn(record)
    if fqn is None:
        return None
    return records_by_fqn.get(fqn)


def _sub_effects(effect_record: NodeRecord) -> list[list[dict[str, Any]]]:
    sub_effects = _field_value(effect_record, "effSubEffects")
    if not isinstance(sub_effects, dict):
        return []
    raw_list = sub_effects.get("list")
    if not isinstance(raw_list, list):
        return []
    return [entry for entry in raw_list if isinstance(entry, list)]


def _sub_effect_field(sub_effect: list[dict[str, Any]], name: str) -> Any:
    for field in sub_effect:
        if field.get("name") == name:
            return field.get("value")
    return None


def _collect_tags(effect_record: NodeRecord) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for sub_effect in _sub_effects(effect_record):
        initializers = _sub_effect_field(sub_effect, "effInitializers")
        if not isinstance(initializers, dict):
            continue
        init_list = initializers.get("list")
        if not isinstance(init_list, list):
            continue
        for initializer in init_list:
            if not isinstance(initializer, list):
                continue
            init_name = None
            function_tags: Any = None
            for field in initializer:
                if field.get("name") == "effInitializerName":
                    init_name = field.get("value")
                elif field.get("name") == "effFunctionTags":
                    function_tags = field.get("value")
            if init_name != "effInitializer_SetTags":
                continue
            if not isinstance(function_tags, list):
                continue
            for entry in function_tags:
                if not isinstance(entry, dict):
                    continue
                key = entry.get("key")
                if isinstance(key, str) and key not in seen:
                    seen.add(key)
                    tags.append(key)
    return tags


def _condition_fields(condition_entry: list[dict[str, Any]]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for field in condition_entry:
        name = field.get("name")
        if isinstance(name, str):
            fields[name] = field.get("value")
    return fields


def _decode_condition(
    condition_id: str,
    condition_entry: list[dict[str, Any]],
    *,
    id_to_fqn: dict[str, str] | None = None,
    context: str | None = None,
) -> dict[str, Any] | None:
    fields = _condition_fields(condition_entry)
    condition_name = fields.get("effConditionName")
    if _should_drop_condition(condition_name):
        return None

    condition_type = (
        _snake_case(str(condition_name))
        if isinstance(condition_name, str)
        else "unknown"
    )

    bool_params = _lookup_list_to_dict(fields.get("effBoolParams"))
    int_params = _lookup_list_to_dict(fields.get("effIntParams"))
    float_params = _lookup_list_to_dict(fields.get("effFloatParams"))
    string_params = _lookup_list_to_dict(fields.get("effStringParams"))
    function_tags = _lookup_list_to_dict(fields.get("effFunctionTags"))

    decoded: dict[str, Any] = {
        "id": condition_id,
        "type": condition_type,
        "negated": bool(bool_params.get("effParam_Negated", False)),
    }

    if "effParam_Actor" in int_params:
        decoded["actor"] = _decode_actor(int_params["effParam_Actor"])
    if "effParam_FromActor" in int_params:
        decoded["from_actor"] = _decode_actor(int_params["effParam_FromActor"])
    if "effParam_Comparison" in int_params:
        decoded["comparison"] = _decode_comparison(
            int_params["effParam_Comparison"],
            context=f"{context or 'unknown node'} condition {condition_id}",
        )
    if "effParam_Count" in int_params:
        decoded["count"] = int(int_params["effParam_Count"])
    if "effParam_AbilitySpec" in int_params:
        ability_spec = _resolve_ability_spec(int_params["effParam_AbilitySpec"], id_to_fqn)
        if ability_spec is not None:
            decoded["ability_spec"] = ability_spec

    floats: dict[str, float] = {}
    for key, value in float_params.items():
        if isinstance(value, (int, float)):
            floats[_snake_case(str(key))] = float(value)
    if floats:
        decoded["floats"] = floats

    tag_keys = [key for key, enabled in function_tags.items() if enabled is True]
    if tag_keys:
        decoded["tags"] = tag_keys

    extra_ints = {
        _snake_case(key): int(value)
        for key, value in int_params.items()
        if key
        not in {
            "effParam_Actor",
            "effParam_FromActor",
            "effParam_Comparison",
            "effParam_Count",
            "effParam_FailureMessageId",
            "effParam_AbilitySpec",
        }
        and str(value).isdigit()
    }
    if extra_ints:
        decoded["ints"] = extra_ints

    extra_strings = {
        _snake_case(key): value
        for key, value in string_params.items()
        if key not in {"effParam_Name", "effParam_FailureMessage"}
        and isinstance(value, str)
    }
    if extra_strings:
        decoded["strings"] = extra_strings

    return decoded


def _logic_entry_fields(entry: list[dict[str, Any]]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for field in entry:
        name = field.get("name")
        if isinstance(name, str):
            fields[name] = field.get("value")
    return fields


def _decode_condition_logic(logic_list: list[Any]) -> dict[str, Any] | None:
    stack: list[dict[str, Any]] = []
    for entry in logic_list:
        if not isinstance(entry, list):
            continue
        fields = _logic_entry_fields(entry)
        # Extracted nodes store postfix RPN as effPostfixElement*; keep the
        # legacy effConditionLogic* names as a fallback for older dumps.
        logic_type = fields.get("effPostfixElementType") or fields.get(
            "effConditionLogicType"
        )
        logic_value = fields.get("effPostfixElementId")
        if logic_value is None:
            logic_value = fields.get("effConditionLogicValue")
        if logic_type in LOGIC_OP_LABELS:
            if len(stack) < 2:
                continue
            right = stack.pop()
            left = stack.pop()
            stack.append(
                {
                    "op": LOGIC_OP_LABELS[logic_type],
                    "operands": [left, right],
                }
            )
        elif logic_value is not None:
            stack.append({"condition": str(logic_value)})
    if not stack:
        return None
    if len(stack) != 1:
        return stack[-1]
    return stack[0]


def _collect_conditions(
    effect_record: NodeRecord,
    *,
    id_to_fqn: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    all_conditions: dict[str, list[dict[str, Any]]] = {}
    logic_lists: list[list[Any]] = []

    for sub_effect in _sub_effects(effect_record):
        conditions = _sub_effect_field(sub_effect, "effConditions")
        if isinstance(conditions, list):
            for entry in conditions:
                if isinstance(entry, dict) and "key" in entry and "value" in entry:
                    key = str(entry["key"])
                    value = entry.get("value")
                    if not isinstance(value, list):
                        continue
                    fields = _condition_fields(value)
                    condition_name = fields.get("effConditionName")
                    if _should_drop_condition(condition_name):
                        continue
                    if _is_else_condition(condition_name):
                        continue
                    all_conditions[key] = value

        postfix = _sub_effect_field(sub_effect, "effPostfixElements")
        if isinstance(postfix, dict):
            postfix_list = postfix.get("list")
            if isinstance(postfix_list, list) and postfix_list:
                logic_lists.append(postfix_list)

    if not all_conditions:
        return None

    decoded_list = [
        decoded
        for condition_id, entry in sorted(all_conditions.items())
        if (
            decoded := _decode_condition(
                condition_id,
                entry,
                id_to_fqn=id_to_fqn,
                context=effect_record.entry.fqn,
            )
        )
        is not None
    ]
    if not decoded_list:
        return None

    valid_ids = {item["id"] for item in decoded_list}

    logic: dict[str, Any] | None = None
    for logic_list in logic_lists:
        candidate = _filter_condition_logic(
            _decode_condition_logic(logic_list),
            valid_ids,
        )
        if candidate is not None:
            logic = candidate
            break

    return _finalize_conditions(
        {"list": decoded_list, "logic": logic},
        context=effect_record.entry.fqn,
    )


def _entry_fields(entry: list[dict[str, Any]]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for field in entry:
        name = field.get("name")
        if isinstance(name, str):
            fields[name] = field.get("value")
    return fields


def _action_param_dicts(entry: list[dict[str, Any]]) -> dict[str, Any]:
    fields = _entry_fields(entry)
    return {
        "bool": _lookup_list_to_dict(fields.get("effBoolParams")),
        "int": _lookup_list_to_dict(fields.get("effIntParams")),
        "float": _lookup_list_to_dict(fields.get("effFloatParams")),
        "string": _lookup_list_to_dict(fields.get("effStringParams")),
        "tags": _lookup_list_to_dict(fields.get("effFunctionTags")),
        "time_interval": _lookup_list_to_dict(fields.get("effTimeIntervalParams")),
        "int_list": _lookup_list_to_dict(fields.get("effIntListParams")),
    }


def _int_list_items(value: Any) -> list[str]:
    if isinstance(value, dict):
        items = value.get("list")
    elif isinstance(value, list):
        items = value
    else:
        return []
    if not isinstance(items, list):
        return []
    return [str(item) for item in items]


def _decode_eff_results(int_list_params: dict[str, Any]) -> list[str]:
    tokens = _int_list_items(int_list_params.get("effParam_Results"))
    if any(token in CRIT_RESULT_TOKENS for token in tokens):
        return [CRIT_RESULT_NAME]
    return []


def _raw_time_interval_seconds(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return int(str(value)) / MS_PER_SECOND
    except (TypeError, ValueError):
        return None


def _float_param(params: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = params.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _int_param(params: dict[str, Any], key: str, default: int = 0) -> int:
    value = params.get(key)
    if value is not None and str(value).isdigit():
        return int(value)
    return default


def _effect_number(fqn: str) -> int | None:
    if "/" not in fqn:
        return None
    suffix = fqn.rsplit("/", 1)[-1]
    if suffix.isdigit():
        return int(suffix)
    return None


def _effect_records(
    record: NodeRecord,
    records_by_fqn: dict[str, NodeRecord],
) -> list[NodeRecord]:
    resolved: list[tuple[int, NodeRecord]] = []
    for fqn in _effect_ids(record):
        number = _effect_number(fqn)
        if number is None or number == 0:
            continue
        effect = records_by_fqn.get(fqn)
        if effect is not None:
            resolved.append((number, effect))
    resolved.sort(key=lambda item: item[0])
    return [effect for _, effect in resolved]


def _effect_field_interval_seconds(record: NodeRecord, name: str) -> float | None:
    value = _field_value(record, name)
    if value is None:
        return None
    try:
        return int(str(value)) / MS_PER_SECOND
    except (TypeError, ValueError):
        return None


def _effect_int_field(effect_record: NodeRecord, name: str) -> int | None:
    value = _field_value(effect_record, name)
    if value is None:
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _effect_stack_charge(effect_record: NodeRecord) -> dict[str, Any] | None:
    stack_charge: dict[str, Any] = {}

    initial = _effect_int_field(effect_record, "effInitialCharges")
    if initial is not None:
        stack_charge["initial"] = initial

    maximum = _effect_int_field(effect_record, "effMaxCharges")
    if maximum is not None:
        stack_charge["max"] = maximum

    nr_occurances = _effect_int_field(effect_record, "effStackLimit")
    if nr_occurances is not None:
        stack_charge["nr_occurances"] = nr_occurances

    if _has_field(effect_record, "effScalesWithCharges"):
        stack_charge["scales_with_stack_charge"] = bool(
            _field_value(effect_record, "effScalesWithCharges")
        )

    if _has_field(effect_record, "effStackLimitIsByTag"):
        stack_charge["is_by_tag"] = bool(
            _field_value(effect_record, "effStackLimitIsByTag")
        )
    if _has_field(effect_record, "effStackLimitIsByCaster"):
        stack_charge["is_per_caster"] = bool(
            _field_value(effect_record, "effStackLimitIsByCaster")
        )

    relevant_tags_raw = _field_value(effect_record, "effStackLimitRelevantTags")
    if isinstance(relevant_tags_raw, list):
        tag_keys = [
            str(entry["key"])
            for entry in relevant_tags_raw
            if isinstance(entry, dict) and entry.get("value")
        ]
        if len(tag_keys) == 1:
            stack_charge["relevant_tags"] = tag_keys[0]
        elif tag_keys:
            stack_charge["relevant_tags"] = tag_keys

    return stack_charge or None


def _effect_has_meaningful_metadata(
    *,
    tags: list[str] | None = None,
    duration: float | None = None,
    tick_interval: float | None = None,
    stack_charge: dict[str, Any] | None = None,
    conditions: dict[str, Any] | None = None,
    target_overrides: list[dict[str, Any]] | None = None,
    initializers: list[dict[str, Any]] | None = None,
) -> bool:
    return (
        bool(tags)
        or duration is not None
        or tick_interval is not None
        or bool(stack_charge)
        or conditions is not None
        or bool(target_overrides)
        or bool(initializers)
    )


def _merge_stack_charge_from_initializers(
    stack_charge: dict[str, Any] | None,
    initializers: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for initializer in initializers:
        if initializer.get("initializer_type") != "set_stack_charge_limit":
            continue
        merged = dict(stack_charge or {})
        for key in (
            "nr_occurances",
            "is_by_tag",
            "is_per_caster",
            "is_multi_target",
            "relevant_tags",
        ):
            if key in initializer:
                merged[key] = initializer[key]
        return merged
    return stack_charge


def _effect_timing(effect_record: NodeRecord) -> tuple[float | None, float | None]:
    return (
        _effect_field_interval_seconds(effect_record, "effDuration"),
        _effect_field_interval_seconds(effect_record, "effInterval"),
    )


def _effect_tags(effect_record: NodeRecord) -> list[str]:
    tags = _collect_tags(effect_record)
    seen = set(tags)
    eff_tags = _field_value(effect_record, "effTags")
    if isinstance(eff_tags, list):
        for entry in eff_tags:
            if not isinstance(entry, dict):
                continue
            key = entry.get("key")
            if isinstance(key, str) and key not in seen:
                seen.add(key)
                tags.append(key)
    return tags


def _effect_has_if_called_by_effect(effect_record: NodeRecord) -> bool:
    for branch in _sub_effects(effect_record):
        conditions = _sub_effect_field(branch, "effConditions")
        if not isinstance(conditions, list):
            continue
        for entry in conditions:
            if not isinstance(entry, dict):
                continue
            value = entry.get("value")
            if not isinstance(value, list):
                continue
            fields = _condition_fields(value)
            if fields.get("effConditionName") == "effCondition_IfCalledByEffect":
                return True
    return False


def _filter_condition_logic(
    logic: dict[str, Any] | None,
    valid_ids: set[str],
) -> dict[str, Any] | None:
    if logic is None:
        return None
    if "condition" in logic:
        if logic["condition"] in valid_ids:
            return logic
        return None
    if "op" in logic and "operands" in logic:
        filtered = [
            child
            for child in (_filter_condition_logic(op, valid_ids) for op in logic["operands"])
            if child is not None
        ]
        if not filtered:
            return None
        if len(filtered) == 1:
            return filtered[0]
        return {"op": logic["op"], "operands": filtered}
    return logic


def _branch_conditions(
    branch: list[dict[str, Any]],
    *,
    id_to_fqn: dict[str, str] | None = None,
    context: str | None = None,
) -> tuple[ElseMarker | None, dict[str, Any] | None]:
    conditions_raw = _sub_effect_field(branch, "effConditions")
    postfix_raw = _sub_effect_field(branch, "effPostfixElements")

    if not isinstance(conditions_raw, list):
        conditions_raw = []

    kept_conditions: dict[str, list[dict[str, Any]]] = {}
    marker: ElseMarker | None = None
    for entry in conditions_raw:
        if not isinstance(entry, dict):
            continue
        key = str(entry["key"])
        value = entry.get("value")
        if not isinstance(value, list):
            continue
        fields = _condition_fields(value)
        condition_marker = _else_marker_from_fields(fields)
        if condition_marker is not None:
            marker = condition_marker
            continue
        if _should_drop_condition(fields.get("effConditionName")):
            continue
        kept_conditions[key] = value

    if not kept_conditions:
        return marker, None

    decoded_list = [
        decoded
        for condition_id, entry in sorted(kept_conditions.items())
        if (
            decoded := _decode_condition(
                condition_id,
                entry,
                id_to_fqn=id_to_fqn,
                context=context,
            )
        )
        is not None
    ]
    if not decoded_list:
        return marker, None

    valid_ids = {item["id"] for item in decoded_list}

    logic: dict[str, Any] | None = None
    if isinstance(postfix_raw, dict):
        postfix_list = postfix_raw.get("list")
        if isinstance(postfix_list, list) and postfix_list:
            logic = _filter_condition_logic(
                _decode_condition_logic(postfix_list),
                valid_ids,
            )

    return marker, _finalize_conditions(
        {"list": decoded_list, "logic": logic},
        context=context,
    )


def _decode_action(
    entry: list[dict[str, Any]],
    *,
    id_to_fqn: dict[str, str] | None = None,
    standard_rating: float | None = None,
) -> dict[str, Any] | None:
    fields = _entry_fields(entry)
    action_name = fields.get("effActionName")
    if not isinstance(action_name, str):
        return None

    if action_name in DROPPED_ACTION_TYPES:
        return None

    params = _action_param_dicts(entry)
    bool_params = params["bool"]
    int_params = params["int"]
    float_params = params["float"]

    if action_name == "effAction_WeaponDamage":
        decoded: dict[str, Any] = {
            "action_type": "damage",
            "attack_type": 1,
            "hand": "main"
            if bool_params.get("effParam_IgnoreDualWieldModifier")
            else "off",
            "coeff": _float_param(float_params, "effParam_Coefficient"),
            "amp": _float_param(float_params, "effParam_AmountModifierPercent"),
            "shp_min": _float_param(float_params, "effParam_StandardHealthPercentMin"),
            "shp_max": _float_param(float_params, "effParam_StandardHealthPercentMax"),
        }
        if "effParam_FlurryBlowsMin" in int_params:
            decoded["flurry_min"] = _int_param(int_params, "effParam_FlurryBlowsMin")
        if "effParam_FlurryBlowsMax" in int_params:
            decoded["flurry_max"] = _int_param(int_params, "effParam_FlurryBlowsMax")
        if "effParam_HealthStealPercentage" in float_params:
            decoded["health_steal_percent"] = _float_param(
                float_params, "effParam_HealthStealPercentage"
            )
        return decoded

    if action_name == "effAction_SpellDamage":
        decoded = {
            "action_type": "damage",
            "attack_type": 3,
            "damage_type": _int_param(int_params, "effParam_DamageType"),
            "coeff": _float_param(float_params, "effParam_Coefficient"),
            "amp": _float_param(float_params, "effParam_AmountModifierPercent"),
            "shp_min": _float_param(float_params, "effParam_StandardHealthPercentMin"),
            "shp_max": _float_param(float_params, "effParam_StandardHealthPercentMax"),
        }
        if "effParam_HealthStealPercentage" in float_params:
            decoded["health_steal_percent"] = _float_param(
                float_params, "effParam_HealthStealPercentage"
            )
        return decoded

    if action_name == "effAction_ModifyStat":
        decoded = {
            "action_type": "modify_stat",
            "stat": decode_stat_name(
                _int_param(int_params, "effParam_Stat"),
                get_stat_labels(),
            ),
            "amount_percent": _float_param(float_params, "effParam_AmountPercent"),
            "amount_min": _float_param(float_params, "effParam_AmountMin"),
            "amount_max": _float_param(float_params, "effParam_AmountMax"),
        }
        # Schema always includes StandardRatingPercent keys (often 0). Only
        # rating-scaled actions (relics/adrenals) have a non-zero percent.
        sr_min = _float_param(float_params, "effParam_StandardRatingPercentMin")
        sr_max = _float_param(float_params, "effParam_StandardRatingPercentMax")
        if standard_rating is not None and (sr_min != 0.0 or sr_max != 0.0):
            decoded["amount_min"] = sr_min * standard_rating
            decoded["amount_max"] = sr_max * standard_rating
        return decoded

    if action_name in {"effAction_RestoreForce", "effAction_RestoreEnergy"}:
        return {
            "action_type": "energy_recovery",
            "min": _float_param(float_params, "effParam_AmountMin"),
            "max": _float_param(float_params, "effParam_AmountMax"),
            "percent": _float_param(float_params, "effParam_AmountPercent"),
        }

    if action_name == "effAction_CallEffect":
        decoded = {
            "action_type": "call_effect",
            "effect": _int_param(int_params, "effParam_EffectNumber"),
        }
        if "effParam_FromActor" in int_params:
            decoded["from_actor"] = _decode_actor(int_params["effParam_FromActor"])
        if "effParam_ToActor" in int_params:
            decoded["to_actor"] = _decode_actor(int_params["effParam_ToActor"])
        return decoded

    generic: dict[str, Any] = {"action_type": _snake_case(action_name)}
    tag_keys = [key for key, enabled in params["tags"].items() if enabled is True]
    if tag_keys:
        generic["tags"] = tag_keys

    floats = {
        _snake_case(key): float(value)
        for key, value in float_params.items()
        if key not in DROPPED_ACTION_PARAMS and isinstance(value, (int, float))
    }
    if floats:
        generic["floats"] = floats

    ints = _decode_generic_ints(int_params, id_to_fqn=id_to_fqn)
    if ints:
        generic["ints"] = ints

    bools = {
        _snake_case(key): bool(value)
        for key, value in bool_params.items()
        if key not in DROPPED_ACTION_PARAMS
    }
    if bools:
        generic["bools"] = bools

    strings = {
        _snake_case(key): value
        for key, value in params["string"].items()
        if key not in DROPPED_ACTION_PARAMS and isinstance(value, str)
    }
    resolved_tag = _resolved_conditional_tag(int_params)
    if resolved_tag and not strings.get("conditional_tag"):
        strings["conditional_tag"] = resolved_tag
    if strings:
        generic["strings"] = strings

    return generic


def _decode_trigger(
    entry: list[dict[str, Any]],
    *,
    id_to_fqn: dict[str, str] | None = None,
) -> dict[str, Any]:
    fields = _entry_fields(entry)
    trigger_name = fields.get("effTriggerName")
    label, _index = decode_trigger_name(trigger_name, TRIGGER_LABELS)
    decoded: dict[str, Any] = {"trigger": label}

    params = _action_param_dicts(entry)
    tag_keys = [key for key, enabled in params["tags"].items() if enabled is True]
    if tag_keys:
        decoded["tags"] = tag_keys

    exclusion_map = _lookup_list_to_dict(fields.get("effTagExclusions"))
    excluded_tags = [key for key, enabled in exclusion_map.items() if enabled is True]
    if excluded_tags:
        decoded["excluded_tags"] = excluded_tags

    if "effParam_TickNumber" in params["int"]:
        decoded["tick_number"] = _int_param(params["int"], "effParam_TickNumber")

    intervals: dict[str, float] = {}
    for key, value in params["time_interval"].items():
        seconds = _raw_time_interval_seconds(value)
        if seconds is not None and seconds != 0.0:
            intervals[f"interval_{key}"] = seconds
    if intervals:
        decoded["intervals"] = intervals

    bools = {
        _snake_case(key): bool(value)
        for key, value in params["bool"].items()
        if key not in DROPPED_ACTION_PARAMS
    }
    if bools:
        decoded["bools"] = bools

    ints = _decode_generic_ints(
        params["int"],
        id_to_fqn=id_to_fqn,
        exclude_keys=frozenset({"effParam_TickNumber"}),
        skip_zero=True,
    )
    if ints:
        decoded["ints"] = ints

    floats = {
        _snake_case(key): float(value)
        for key, value in params["float"].items()
        if key not in DROPPED_ACTION_PARAMS
        and isinstance(value, (int, float))
        and not (key == "effParam_ProcChancePercent" and float(value) == 0.0)
    }
    if floats:
        decoded["floats"] = floats

    eff_results = _decode_eff_results(params["int_list"])
    if eff_results:
        decoded["effResults"] = eff_results

    return decoded


def _raw_branch_action_names(branch: list[dict[str, Any]]) -> set[str]:
    actions_raw = _sub_effect_field(branch, "effActions")
    if not isinstance(actions_raw, dict):
        return set()
    action_list = actions_raw.get("list")
    if not isinstance(action_list, list):
        return set()

    names: set[str] = set()
    for entry in action_list:
        if not isinstance(entry, list):
            continue
        action_name = _entry_fields(entry).get("effActionName")
        if isinstance(action_name, str):
            names.add(action_name)
    return names


def _effect_raw_action_names(effect_record: NodeRecord) -> set[str]:
    names: set[str] = set()
    for branch in _sub_effects(effect_record):
        names |= _raw_branch_action_names(branch)
    return names


def _should_drop_effect_entirely(effect_record: NodeRecord) -> bool:
    action_names = _effect_raw_action_names(effect_record)
    return bool(action_names) and action_names <= DROPPED_ACTION_TYPES


def _call_effect_targets(effects: list[dict[str, Any]]) -> set[int]:
    targets: set[int] = set()
    for effect in effects:
        for branch in effect.get("branches", []):
            for action in branch.get("actions", []):
                if action.get("action_type") == "call_effect":
                    target = action.get("effect")
                    if isinstance(target, int):
                        targets.add(target)
    return targets


def _unreferenced_call_only_numbers(effects: list[dict[str, Any]]) -> set[int]:
    called = _call_effect_targets(effects)
    return {
        effect["number"]
        for effect in effects
        if not effect.get("entry") and effect["number"] not in called
    }


def _prune_unreferenced_call_only_effects(
    effects: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    unreferenced = _unreferenced_call_only_numbers(effects)
    if not unreferenced:
        return effects
    effects = [effect for effect in effects if effect["number"] not in unreferenced]
    return _prune_dropped_effect_references(effects, unreferenced)


def _prune_dropped_effect_references(
    effects: list[dict[str, Any]],
    dropped_effect_numbers: set[int],
) -> list[dict[str, Any]]:
    if not dropped_effect_numbers:
        return effects

    pruned: list[dict[str, Any]] = []
    for effect in effects:
        branches: list[dict[str, Any]] = []
        for branch in effect.get("branches", []):
            updated_branch = dict(branch)
            actions = updated_branch.get("actions")
            if actions:
                updated_branch["actions"] = [
                    action
                    for action in actions
                    if not (
                        action.get("action_type") == "call_effect"
                        and action.get("effect") in dropped_effect_numbers
                    )
                ]
            if (
                updated_branch.get("actions")
                or updated_branch.get("conditions")
                or updated_branch.get("initializers")
                or updated_branch.get("triggers")
            ):
                branches.append(updated_branch)
        if not branches:
            if _effect_has_meaningful_metadata(
                tags=effect.get("tags"),
                duration=effect.get("duration"),
                tick_interval=effect.get("tick_interval"),
                stack_charge=effect.get("stack_charge"),
                conditions=effect.get("conditions"),
                target_overrides=effect.get("target_overrides"),
                initializers=effect.get("initializers"),
            ):
                updated_effect = dict(effect)
                updated_effect["branches"] = []
                pruned.append(updated_effect)
            continue
        updated_effect = dict(effect)
        updated_effect["branches"] = branches
        pruned.append(updated_effect)
    return pruned


def _branch_actions(
    branch: list[dict[str, Any]],
    *,
    id_to_fqn: dict[str, str] | None = None,
    standard_rating: float | None = None,
) -> list[dict[str, Any]]:
    actions_raw = _sub_effect_field(branch, "effActions")
    if not isinstance(actions_raw, dict):
        return []
    action_list = actions_raw.get("list")
    if not isinstance(action_list, list):
        return []

    actions: list[dict[str, Any]] = []
    for entry in action_list:
        if not isinstance(entry, list):
            continue
        decoded = _decode_action(
            entry,
            id_to_fqn=id_to_fqn,
            standard_rating=standard_rating,
        )
        if decoded is not None:
            actions.append(decoded)
    return actions


def _branch_triggers(
    branch: list[dict[str, Any]],
    *,
    id_to_fqn: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    triggers_raw = _sub_effect_field(branch, "effTriggers")
    if not isinstance(triggers_raw, dict):
        return []
    trigger_list = triggers_raw.get("list")
    if not isinstance(trigger_list, list):
        return []

    triggers: list[dict[str, Any]] = []
    for entry in trigger_list:
        if isinstance(entry, list):
            triggers.append(_decode_trigger(entry, id_to_fqn=id_to_fqn))
    return triggers


def _set_icon_spec_from_initializers(effect_record: NodeRecord) -> str | None:
    for branch in _sub_effects(effect_record):
        initializers_raw = _sub_effect_field(branch, "effInitializers")
        if not isinstance(initializers_raw, dict):
            continue
        initializer_list = initializers_raw.get("list")
        if not isinstance(initializer_list, list):
            continue
        for entry in initializer_list:
            if not isinstance(entry, list):
                continue
            fields = _entry_fields(entry)
            if fields.get("effInitializerName") != "effInitializer_SetIcon":
                continue
            string_params = _action_param_dicts(entry)["string"]
            spec = string_params.get("effParam_IconSpec")
            if not isinstance(spec, str) or not spec.strip():
                raw = fields.get("effStringParams")
                entries = raw.get("list") if isinstance(raw, dict) else raw
                spec = _lookup_list_to_dict(entries).get("effParam_IconSpec")
            if isinstance(spec, str) and spec.strip():
                return spec.strip()
    return None


def _effect_icon_png(effect_record: NodeRecord) -> str | None:
    png = _icon_png_name(_field_value(effect_record, "effIcon"))
    if png is not None:
        return png
    return _icon_png_name(_set_icon_spec_from_initializers(effect_record))


def _decode_initializer(entry: list[dict[str, Any]]) -> dict[str, Any] | None:
    fields = _entry_fields(entry)
    initializer_name = fields.get("effInitializerName")
    if not isinstance(initializer_name, str):
        return None
    if initializer_name in DROPPED_INITIALIZER_TYPES:
        return None

    params = _action_param_dicts(entry)
    bool_params = params["bool"]
    int_params = params["int"]
    string_params = params["string"]

    if initializer_name == "effInitializer_SetStackLimit":
        decoded: dict[str, Any] = {
            "initializer_type": "set_stack_charge_limit",
            "is_by_tag": bool(bool_params.get("effParam_IsByTag", False)),
            "is_per_caster": bool(bool_params.get("effParam_IsPerCaster", False)),
            "is_multi_target": bool(bool_params.get("effParam_IsMultiTarget", False)),
        }
        if "effParam_MaxStackCount" in int_params:
            decoded["nr_occurances"] = _int_param(int_params, "effParam_MaxStackCount")
        relevant_tags = string_params.get("effParam_RelevantTags")
        if isinstance(relevant_tags, str) and relevant_tags:
            decoded["relevant_tags"] = relevant_tags
        return decoded

    generic: dict[str, Any] = {"initializer_type": _snake_case(initializer_name)}
    bools = {
        _snake_case(key): bool(value)
        for key, value in bool_params.items()
        if key not in DROPPED_ACTION_PARAMS
    }
    ints = {
        _snake_case(key): int(value)
        for key, value in int_params.items()
        if key not in DROPPED_ACTION_PARAMS and str(value).isdigit()
    }
    strings = {
        _snake_case(key): value
        for key, value in string_params.items()
        if key not in DROPPED_ACTION_PARAMS and isinstance(value, str)
    }
    if bools:
        generic["bools"] = bools
    if ints:
        generic["ints"] = ints
    if strings:
        generic["strings"] = strings
    return generic


def _branch_initializers(branch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    initializers_raw = _sub_effect_field(branch, "effInitializers")
    if not isinstance(initializers_raw, dict):
        return []
    initializer_list = initializers_raw.get("list")
    if not isinstance(initializer_list, list):
        return []

    initializers: list[dict[str, Any]] = []
    for entry in initializer_list:
        if not isinstance(entry, list):
            continue
        decoded = _decode_initializer(entry)
        if decoded is not None:
            initializers.append({k: v for k, v in decoded.items() if v is not None})
    return initializers


def _decode_aoe_target_sort(raw: Any) -> str:
    key = str(raw)
    label = AOE_TARGET_SORT_LABELS.get(key)
    if label is not None:
        return label
    if key.startswith("aoeTargetSort_"):
        return _snake_case(key[len("aoeTargetSort_") :])
    return f"sort_{key}"


def _decode_target_override_type(raw: Any) -> str:
    key = str(raw)
    label = TARGET_OVERRIDE_LABELS.get(key)
    if label is not None:
        return label
    if key.startswith("effTargetOverride_"):
        return _snake_case(key)
    return f"override_{key}"


def _decode_target_override(entry: list[dict[str, Any]]) -> dict[str, Any] | None:
    fields = _entry_fields(entry)
    override_name = fields.get("effTargetOverrideName")
    if override_name is None:
        return None

    params = _action_param_dicts(entry)
    decoded: dict[str, Any] = {"type": _decode_target_override_type(override_name)}

    for key, value in params["bool"].items():
        decoded[_snake_case(str(key))] = bool(value)
    for key, value in params["int"].items():
        param_key = _snake_case(str(key))
        if param_key == "sort_type":
            decoded[param_key] = _decode_aoe_target_sort(value)
        elif str(value).lstrip("-").isdigit():
            decoded[param_key] = int(value)
    for key, value in params["float"].items():
        if isinstance(value, (int, float)):
            decoded[_snake_case(str(key))] = float(value)
    for key, value in params["string"].items():
        if isinstance(value, str) and value:
            decoded[_snake_case(str(key))] = value

    return decoded


def _branch_target_overrides(branch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    overrides_raw = _sub_effect_field(branch, "effTargetOverrides")
    if not isinstance(overrides_raw, dict):
        return []
    override_list = overrides_raw.get("list")
    if not isinstance(override_list, list):
        return []

    decoded: list[dict[str, Any]] = []
    for entry in override_list:
        if not isinstance(entry, list):
            continue
        override = _decode_target_override(entry)
        if override is not None:
            decoded.append(override)
    return decoded


def _non_stack_initializers(
    initializers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        initializer
        for initializer in initializers
        if initializer.get("initializer_type") != "set_stack_charge_limit"
    ]


def _hoist_effect_header(
    header: list[dict[str, Any]],
    *,
    id_to_fqn: dict[str, str] | None = None,
    standard_rating: float | None = None,
    context: str,
) -> tuple[
    dict[str, Any] | None,
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Lift sub-effect 1 (effect gate / targeting) out of the branch list."""
    actions = _branch_actions(
        header,
        id_to_fqn=id_to_fqn,
        standard_rating=standard_rating,
    )
    if actions:
        print(
            f"Warning: {context} sub-effect 1 has {len(actions)} action(s); "
            f"expected effect header with no actions",
            file=sys.stderr,
        )

    triggers = _branch_triggers(header, id_to_fqn=id_to_fqn)
    if triggers:
        print(
            f"Warning: {context} sub-effect 1 has {len(triggers)} trigger(s); "
            f"expected effect header with no triggers",
            file=sys.stderr,
        )

    _marker, conditions = _branch_conditions(
        header,
        id_to_fqn=id_to_fqn,
        context=f"{context} sub-effect 1",
    )
    target_overrides = _branch_target_overrides(header)
    initializers = _branch_initializers(header)
    return conditions, target_overrides, initializers


def _is_redundant_self_aoe_branch(
    branch: list[dict[str, Any]],
    effect_tags: set[str],
) -> bool:
    conditions_raw = _sub_effect_field(branch, "effConditions")
    if not isinstance(conditions_raw, list):
        return False

    for entry in conditions_raw:
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        if not isinstance(value, list):
            continue
        fields = _condition_fields(value)
        if fields.get("effConditionName") != "effCondition_HasEffect":
            continue

        bool_params = _lookup_list_to_dict(fields.get("effBoolParams"))
        int_params = _lookup_list_to_dict(fields.get("effIntParams"))
        function_tags = _lookup_list_to_dict(fields.get("effFunctionTags"))

        if not bool_params.get("effParam_Negated"):
            continue
        if int_params.get("effParam_Actor") != "3":
            continue

        tag_keys = [key for key, enabled in function_tags.items() if enabled is True]
        if any(tag in effect_tags for tag in tag_keys):
            return True
    return False


def _enrich_trigger_timing(
    triggers: list[dict[str, Any]],
    effect_duration: float | None,
    effect_tick_interval: float | None,
) -> None:
    for trigger in triggers:
        name = trigger.get("trigger")
        if name in EFFECT_DURATION_TRIGGERS and effect_duration is not None:
            trigger["delay"] = effect_duration
        elif name == "on_tick" and effect_tick_interval is not None:
            tick_number = trigger.get("tick_number")
            if tick_number is not None:
                trigger["delay"] = tick_number * effect_tick_interval


def _decode_branch(
    branch: list[dict[str, Any]],
    effect_tags: set[str],
    *,
    index: int,
    gate: list[int] | None = None,
    effect_duration: float | None = None,
    effect_tick_interval: float | None = None,
    id_to_fqn: dict[str, str] | None = None,
    standard_rating: float | None = None,
    context: str | None = None,
) -> dict[str, Any] | None:
    if _is_redundant_self_aoe_branch(branch, effect_tags):
        return None

    _marker, conditions = _branch_conditions(
        branch,
        id_to_fqn=id_to_fqn,
        context=context,
    )
    actions = _branch_actions(
        branch,
        id_to_fqn=id_to_fqn,
        standard_rating=standard_rating,
    )
    triggers = _branch_triggers(branch, id_to_fqn=id_to_fqn)
    initializers = _branch_initializers(branch)
    target_overrides = _branch_target_overrides(branch)

    if not actions and conditions is None and not target_overrides:
        return None

    decoded: dict[str, Any] = {"index": index}
    if gate:
        decoded["run_if_none_ran"] = gate
    if conditions is not None:
        decoded["conditions"] = conditions
    if target_overrides:
        decoded["target_overrides"] = target_overrides
    if initializers:
        decoded["initializers"] = initializers
    if actions:
        decoded["actions"] = actions
    if triggers:
        _enrich_trigger_timing(triggers, effect_duration, effect_tick_interval)
        decoded["triggers"] = triggers
    else:
        decoded["triggers"] = [{"trigger": "on_apply"}]
    return decoded


def _decode_effect(
    effect_record: NodeRecord,
    *,
    id_to_fqn: dict[str, str] | None = None,
    standard_rating: float | None = None,
) -> dict[str, Any] | None:
    number = _effect_number(effect_record.entry.fqn)
    if number is None or number == 0:
        return None

    tags = _effect_tags(effect_record)
    tag_set = set(tags)
    duration, tick_interval = _effect_timing(effect_record)
    stack_charge = _effect_stack_charge(effect_record)

    sub_effects = _sub_effects(effect_record)
    effect_conditions: dict[str, Any] | None = None
    effect_target_overrides: list[dict[str, Any]] = []
    header_initializers: list[dict[str, Any]] = []
    if sub_effects:
        effect_conditions, effect_target_overrides, header_initializers = (
            _hoist_effect_header(
                sub_effects[0],
                id_to_fqn=id_to_fqn,
                standard_rating=standard_rating,
                context=effect_record.entry.fqn,
            )
        )

    markers_by_index: dict[int, list[ElseMarker]] = {}
    for raw_index, branch in enumerate(sub_effects, start=1):
        if raw_index == 1:
            continue
        markers = _branch_else_markers(branch)
        if markers:
            markers_by_index[raw_index] = markers
    gates = _resolve_run_if_none_ran(markers_by_index)

    branches: list[dict[str, Any]] = []
    branch_initializers: list[dict[str, Any]] = []
    for raw_index, branch in enumerate(sub_effects, start=1):
        if raw_index == 1:
            continue
        decoded_branch = _decode_branch(
            branch,
            tag_set,
            index=raw_index,
            gate=gates.get(raw_index),
            effect_duration=duration,
            effect_tick_interval=tick_interval,
            id_to_fqn=id_to_fqn,
            standard_rating=standard_rating,
            context=f"{effect_record.entry.fqn} sub-effect {raw_index}",
        )
        if decoded_branch is not None:
            branches.append(decoded_branch)
            branch_initializers.extend(decoded_branch.get("initializers", []))

    effect_initializers = _non_stack_initializers(header_initializers)
    stack_charge = _merge_stack_charge_from_initializers(
        stack_charge,
        header_initializers + branch_initializers,
    )

    if not branches and not _effect_has_meaningful_metadata(
        tags=tags,
        duration=duration,
        tick_interval=tick_interval,
        stack_charge=stack_charge,
        conditions=effect_conditions,
        target_overrides=effect_target_overrides,
        initializers=effect_initializers,
    ):
        return None

    decoded: dict[str, Any] = {
        "number": number,
        "entry": not _effect_has_if_called_by_effect(effect_record),
    }
    icon = _effect_icon_png(effect_record)
    if icon:
        decoded["icon"] = icon
    decoded["branches"] = branches
    if effect_conditions is not None:
        decoded["conditions"] = effect_conditions
    if effect_target_overrides:
        decoded["target_overrides"] = effect_target_overrides
    if effect_initializers:
        decoded["initializers"] = effect_initializers
    if tags:
        decoded["tags"] = tags
    if stack_charge:
        decoded["stack_charge"] = stack_charge
    if duration is not None:
        decoded["duration"] = duration
    if tick_interval is not None:
        decoded["tick_interval"] = tick_interval
    if duration is not None or tick_interval is not None:
        decoded["effIgnoreAlacrity"] = _ignore_alacrity(
            effect_record,
            "effIgnoreAlacrity",
            default=False if tick_interval is not None else True,
        )
    return decoded


def _build_effects(
    record: NodeRecord,
    records_by_fqn: dict[str, NodeRecord],
    *,
    id_to_fqn: dict[str, str] | None = None,
    standard_rating: float | None = None,
) -> list[dict[str, Any]]:
    effect_records = _effect_records(record, records_by_fqn)
    dropped_effect_numbers: set[int] = set()
    for effect_record in effect_records:
        number = _effect_number(effect_record.entry.fqn)
        if number is None or number == 0:
            continue
        if _should_drop_effect_entirely(effect_record):
            dropped_effect_numbers.add(number)

    effects: list[dict[str, Any]] = []
    for effect_record in effect_records:
        number = _effect_number(effect_record.entry.fqn)
        if number in dropped_effect_numbers:
            continue
        decoded = _decode_effect(
            effect_record,
            id_to_fqn=id_to_fqn,
            standard_rating=standard_rating,
        )
        if decoded is not None:
            effects.append(decoded)

    effects = _prune_dropped_effect_references(effects, dropped_effect_numbers)
    return _prune_unreferenced_call_only_effects(effects)


def _build_ability_payload(
    record: NodeRecord,
    records_by_fqn: dict[str, NodeRecord],
    *,
    id_to_fqn: dict[str, str] | None = None,
    standard_rating: float | None = None,
) -> dict[str, Any]:
    ability_type = _ability_type(record)
    payload: dict[str, Any] = {
        "fqn": record.entry.fqn,
        "name": _ability_name(record),
    }
    icon = _icon_png_name(_field_value(record, "ablIconSpec"))
    if icon:
        payload["icon"] = icon
    payload["type"] = ability_type
    payload["cooldown"] = _cooldown(record)
    payload["ablIgnoreAlacrity"] = _ignore_alacrity(
        record, "ablIgnoreAlacrity", default=False
    )
    payload["energy_cost"] = _energy_cost(record)

    if ability_type == "active":
        triggers_gcd, base_gcd = _gcd_fields(record)
        payload["triggers_gcd"] = triggers_gcd
        payload["base_gcd"] = base_gcd
        payload["activation"] = _activation(record)

    zero_effect = _zero_effect_record(record, records_by_fqn)
    if zero_effect is not None:
        payload["tags"] = _collect_tags(zero_effect)
        payload["conditions"] = _collect_conditions(zero_effect, id_to_fqn=id_to_fqn)
    else:
        payload["tags"] = []
        payload["conditions"] = None

    payload["effects"] = _build_effects(
        record,
        records_by_fqn,
        id_to_fqn=id_to_fqn,
        standard_rating=standard_rating,
    )

    return payload


def build_abilities(
    records: dict[str, NodeRecord],
    output_dir: Path,
    *,
    standard_rating: float | None = None,
) -> tuple[int, set[str]]:
    """Build trimmed root-ability JSON files from extracted node records."""
    output_dir.mkdir(parents=True, exist_ok=True)
    records_by_fqn = {record.entry.fqn: record for record in records.values()}
    id_to_fqn = build_id_to_fqn(records)

    count = 0
    icon_stems: set[str] = set()
    for record in records.values():
        if not record.entry.fqn.startswith("abl."):
            continue
        if record.entry.base_class_name != "ablAbility":
            continue
        payload = _build_ability_payload(
            record,
            records_by_fqn,
            id_to_fqn=id_to_fqn,
            standard_rating=standard_rating,
        )
        icon_stems |= icon_stems_from_payload(payload)
        dest = output_dir / fqn_to_relative_path(record.entry.fqn)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        count += 1
    return count, icon_stems
