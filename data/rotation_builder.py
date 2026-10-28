import argparse
import copy
import json
import os
import re
import sys
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

SWTORSIM_ROOT = Path(__file__).resolve().parents[1]
if str(SWTORSIM_ROOT) not in sys.path:
    sys.path.insert(0, str(SWTORSIM_ROOT))

from src.swtorsim.cli import index_disciplines, select_choices_path, select_discipline_path
from src.swtorsim.config_load import fqn_to_relative_path, load_json_file
from src.swtorsim.run_config import (
    BUILDS_DIR,
    CHOICES_DIR,
    DISCIPLINES_DIR,
    GEAR_PATH,
    LEGENDARY_PREFIX,
    RELICS_PATH,
    ROTATIONS_DIR,
    TACTICAL_PREFIX,
    discipline_names,
    filter_gear_for_class,
    relic_menu_label,
    resolve_skill_tree_fqns,
)

PARSED_DIR = SWTORSIM_ROOT / "data" / "extractor" / "parsed"
UI_HTML_PATH = SWTORSIM_ROOT / "tools" / "rotation_builder_ui.html"


# ---------------------------------------------------------------------------
# Data Structures & Catalog Discovery
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CastableAbility:
    fqn: str
    name: str
    triggers_gcd: bool
    slug: str = ""
    cooldown: float = 0.0
    energy_cost: float = 0.0
    max_charges: int | None = None
    activation_type: str = "instant"
    activation_duration: float = 0.0


def ability_name_to_slug(name: str, fqn: str = "") -> str:
    """Converts an ability display name (e.g. 'Assassinate+') into its canonical rotation slug ('assassinate+')."""
    raw = (name or "").strip()
    if not raw:
        raw = fqn.split(".")[-1] if fqn else "unknown"
    return raw.lower().replace(" ", "_")


def _resolve_workspace_path(rel_or_abs: str | Path) -> Path:
    """Resolves a path relative to SWTORSIM_ROOT if it is not already absolute/existing."""
    p = Path(rel_or_abs)
    if p.exists():
        return p.resolve()
    candidate = SWTORSIM_ROOT / p
    if candidate.exists():
        return candidate.resolve()
    return candidate


def loadout_fqns(
    spec_data: dict,
    choices: dict,
    tactical_fqn: str = "",
    legendary_fqns: list[str] | None = None,
    relic_fqns: list[str] | None = None,
) -> list[str]:
    """Baseline discipline abilities plus chosen skill-tree slots and optional gear/relics."""
    baseline = spec_data.get("active_abilities", [])
    if not isinstance(baseline, list):
        raise ValueError("Discipline file active_abilities must be a list.")

    tree_fqns = resolve_skill_tree_fqns(spec_data.get("skill_tree", {}), choices)
    extra: list[str] = []
    if tactical_fqn:
        extra.append(tactical_fqn)
    if legendary_fqns:
        extra.extend(f for f in legendary_fqns if f)
    if relic_fqns:
        extra.extend(f for f in relic_fqns if f)

    ordered: list[str] = []
    seen: set[str] = set()
    for fqn in [*baseline, *tree_fqns, *extra]:
        if not isinstance(fqn, str) or not fqn.strip():
            print(f"[WARN] Skipping invalid ability id: {fqn!r}")
            continue
        if fqn in seen:
            continue
        seen.add(fqn)
        ordered.append(fqn)
    return ordered


def build_castable_catalog(
    spec_path: str,
    choices_path: str | dict,
    parsed_dir: Path = PARSED_DIR,
) -> list[CastableAbility]:
    """Returns active abilities for a discipline and skill-tree selection, sorted by name."""
    resolved_spec = _resolve_workspace_path(spec_path)
    spec_data = load_json_file(str(resolved_spec))
    if isinstance(choices_path, dict):
        choices = choices_path
    else:
        resolved_choices = _resolve_workspace_path(choices_path)
        choices = load_json_file(str(resolved_choices))

    actives: list[CastableAbility] = []
    passive_count = 0
    talent_count = 0

    for fqn in loadout_fqns(spec_data, choices):
        if fqn.startswith("tal."):
            talent_count += 1
            continue

        full_path = parsed_dir / fqn_to_relative_path(fqn)
        if not full_path.is_file():
            print(f"[WARN] Blueprint file not found for FQN '{fqn}': {full_path}")
            continue

        data = load_json_file(str(full_path))
        ability_type = data.get("type")
        if ability_type == "passive":
            passive_count += 1
            continue
        if ability_type != "active":
            print(
                f"[WARN] Skipping '{fqn}': type is {ability_type!r}, "
                "expected 'active' or 'passive'."
            )
            continue

        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            name = fqn
        activation = data.get("activation") or {}
        actives.append(
            CastableAbility(
                fqn=fqn,
                name=name,
                triggers_gcd=data.get("triggers_gcd") is not False,
                slug=ability_name_to_slug(name, fqn),
                cooldown=float(data.get("cooldown") or 0.0),
                energy_cost=float(data.get("energy_cost") or 0.0),
                max_charges=int(data["max_charges"]) if data.get("max_charges") is not None else None,
                activation_type=str(activation.get("type") or "instant"),
                activation_duration=float(activation.get("duration") or 0.0),
            )
        )

    actives.sort(key=lambda ability: (ability.name.lower(), ability.fqn))
    on_gcd = sum(ability.triggers_gcd for ability in actives)
    off_gcd = len(actives) - on_gcd
    print(
        f"[OK] Castable abilities: {len(actives)} "
        f"({on_gcd} on GCD, {off_gcd} off-GCD). "
        f"Omitted {passive_count} passives and {talent_count} talents."
    )
    return actives


def _strip_effect_number_suffix(effect_name: str, parent_name: str) -> str:
    """Normalizes internal effect names like 'Bloodletting_3' back to 'Bloodletting' when appropriate."""
    if not effect_name:
        return parent_name
    m = re.match(r"^(.+)_\d+$", effect_name)
    if m:
        prefix = m.group(1)
        if not parent_name or prefix.lower() == parent_name.lower():
            return parent_name or prefix
        return prefix
    return effect_name


def discover_loadout_catalog(
    spec_path: str,
    choices: dict | str,
    tactical_fqn: str = "",
    legendary_fqns: list[str] | None = None,
    relic_fqns: list[str] | None = None,
    parsed_dir: Path = PARSED_DIR,
) -> dict[str, Any]:
    """
    Inspects all blueprints in a loadout (discipline + skill tree + tactical + legendaries + relics)
    and auto-discovers:
      - Castable active abilities (with slug, FQN, cooldown, cost, GCD, cast/channel info)
      - Caster buffs & proc buffs (with max stacks, duration, source)
      - Target debuffs & DoTs (with max stacks, duration, tick info, source)
      - Procs & ICD lockouts (for proc_cooldown_above)
      - Skill tree choice metadata (level -> slot -> ability/talent names)
    """
    resolved_spec = _resolve_workspace_path(spec_path)
    spec_data = load_json_file(str(resolved_spec))
    class_name, spec_name = discipline_names(spec_data, str(resolved_spec))
    default_class_folder, default_spec_folder = rotation_folder_defaults(str(resolved_spec))

    if isinstance(choices, str):
        resolved_choices = _resolve_workspace_path(choices)
        choices_dict = load_json_file(str(resolved_choices))
    else:
        choices_dict = dict(choices)

    # Normalize skill tree choices to default to 1 if any level is missing
    skill_tree_raw = spec_data.get("skill_tree", {})
    normalized_choices: dict[str, int] = {}
    for lvl in skill_tree_raw:
        val = choices_dict.get(str(lvl), choices_dict.get(int(lvl) if str(lvl).isdigit() else lvl, 1))
        try:
            slot_int = int(val)
            if slot_int not in (1, 2, 3):
                slot_int = 1
        except (ValueError, TypeError):
            slot_int = 1
        normalized_choices[str(lvl)] = slot_int

    # Build human-readable skill tree metadata
    skill_tree_info: dict[str, dict[str, list[dict[str, str]]]] = {}
    for lvl, slots in sorted(skill_tree_raw.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else 999):
        lvl_str = str(lvl)
        skill_tree_info[lvl_str] = {}
        if isinstance(slots, dict):
            for slot_key, fqns in slots.items():
                entries = []
                for fqn in fqns or []:
                    bp_path = parsed_dir / fqn_to_relative_path(fqn)
                    bp_name = fqn.split(".")[-1].replace("_", " ").title()
                    bp_type = "talent" if fqn.startswith("tal.") else "ability"
                    if bp_path.is_file():
                        try:
                            bp_doc = load_json_file(str(bp_path))
                            bp_name = bp_doc.get("name") or bp_name
                            bp_type = bp_doc.get("type") or bp_type
                        except Exception:
                            pass
                    entries.append({"fqn": fqn, "name": bp_name, "type": bp_type})
                skill_tree_info[lvl_str][str(slot_key)] = entries

    initial_fqns = loadout_fqns(
        spec_data,
        normalized_choices,
        tactical_fqn=tactical_fqn,
        legendary_fqns=legendary_fqns,
        relic_fqns=relic_fqns,
    )

    # Expand sub-abilities referenced by execute_ability or custom actions
    all_fqns: list[str] = []
    seen_fqns: set[str] = set()
    queue = list(initial_fqns)
    loaded_docs: dict[str, dict] = {}

    while queue:
        fqn = queue.pop(0)
        if not fqn or fqn in seen_fqns:
            continue
        seen_fqns.add(fqn)
        all_fqns.append(fqn)

        bp_path = parsed_dir / fqn_to_relative_path(fqn)
        if not bp_path.is_file():
            continue
        try:
            doc = load_json_file(str(bp_path))
        except Exception:
            continue
        loaded_docs[fqn] = doc

        for eff in doc.get("effects") or []:
            for branch in eff.get("branches") or []:
                for act in branch.get("actions") or []:
                    if not isinstance(act, dict):
                        continue
                    a_type = act.get("action_type")
                    ints = act.get("ints") or {}
                    if a_type == "execute_ability":
                        sub_spec = ints.get("ability_spec") or act.get("ability_spec")
                        if isinstance(sub_spec, str) and sub_spec and sub_spec not in seen_fqns:
                            queue.append(sub_spec)
                    elif a_type == "custom" and str(ints.get("param1", "")) == "6855115466292073041":
                        sub_spec = ints.get("param2")
                        if isinstance(sub_spec, str) and sub_spec and sub_spec not in seen_fqns:
                            queue.append(sub_spec)

    abilities_list: list[dict[str, Any]] = []
    caster_buffs_map: dict[str, dict[str, Any]] = {}
    target_debuffs_map: dict[str, dict[str, Any]] = {}
    procs_map: dict[str, dict[str, Any]] = {}

    initial_fqn_set = set(initial_fqns)

    for fqn in all_fqns:
        doc = loaded_docs.get(fqn)
        if not doc:
            continue

        parent_name = str(doc.get("name") or fqn).strip()
        ability_type = doc.get("type") or "passive"

        # 1. Castable active abilities (only those directly in the loadout)
        if fqn in initial_fqn_set and ability_type == "active" and not fqn.startswith("tal."):
            activation = doc.get("activation") or {}
            abilities_list.append(
                {
                    "fqn": fqn,
                    "name": parent_name,
                    "slug": ability_name_to_slug(parent_name, fqn),
                    "triggers_gcd": doc.get("triggers_gcd") is not False,
                    "cooldown": float(doc.get("cooldown") or 0.0),
                    "energy_cost": float(doc.get("energy_cost") or 0.0),
                    "max_charges": int(doc["max_charges"]) if doc.get("max_charges") is not None else None,
                    "activation_type": str(activation.get("type") or "instant"),
                    "activation_duration": float(activation.get("duration") or 0.0),
                }
            )

        if fqn.startswith("tal."):
            continue

        effects = doc.get("effects") or []
        is_aggressive_ability = "tag.abl.utility.aggressive_action" in (doc.get("tags") or [])

        # Map call_effect targets within this blueprint: effect_number -> set of to_actor strings
        called_to_actors: dict[int, set[str]] = {}
        called_with_enemy_override: set[int] = set()
        for eff in effects:
            for branch in eff.get("branches") or []:
                b_overrides = {
                    o.get("type")
                    for o in (branch.get("target_overrides") or [])
                    if isinstance(o, dict)
                }
                is_enemy_branch = bool(
                    b_overrides & {"trigger_target", "aoe_sphere", "aoe_cone", "enemies_list", "primary_target"}
                )
                for act in branch.get("actions") or []:
                    if isinstance(act, dict) and act.get("action_type") == "call_effect":
                        target_eff_num = act.get("effect")
                        to_actor = str(act.get("to_actor") or "")
                        if isinstance(target_eff_num, int):
                            called_to_actors.setdefault(target_eff_num, set()).add(to_actor)
                            if is_enemy_branch:
                                called_with_enemy_override.add(target_eff_num)

        for eff in effects:
            eff_num = eff.get("number", 1)
            raw_eff_name = str(eff.get("name") or parent_name).strip()
            eff_tags = [str(t) for t in (eff.get("tags") or [])]
            eff_tags_lower = " ".join(eff_tags).lower()
            initializers = eff.get("initializers") or []
            init_types = {
                init.get("initializer_type")
                for init in initializers
                if isinstance(init, dict)
            }
            is_passive_init = any(
                init.get("initializer_type") == "eff_initializer__set_passive"
                and (init.get("bools") or {}).get("is_passive", False)
                for init in initializers
                if isinstance(init, dict)
            )
            is_proc_init = "eff_initializer__set_effect_procs" in init_types
            is_hidden = bool(eff.get("is_hidden", False))
            duration = float(eff.get("duration") or 0.0)
            tick_interval = float(eff.get("tick_interval") or 0.0)
            stack_charge = eff.get("stack_charge") or {}
            max_stacks = int(stack_charge.get("max", stack_charge.get("nr_occurances", 1)) or 1)

            # Check lockout tags (e.g. tag.abl.sith_inquisitor.bloodletting_lockout)
            if any("lockout" in t.lower() for t in eff_tags):
                proc_label = _strip_effect_number_suffix(raw_eff_name, parent_name)
                procs_map[proc_label] = {
                    "name": proc_label,
                    "effect_name": raw_eff_name,
                    "source_name": parent_name,
                    "source_fqn": fqn,
                    "icd": duration,
                    "kind": "lockout_effect",
                }
                continue

            # Check branch triggers for ICD (interval_61) on passive/proc abilities
            if ability_type == "passive":
                for branch in eff.get("branches") or []:
                    for trig in branch.get("triggers") or []:
                        intervals = trig.get("intervals") or {}
                        icd_val = float(intervals.get("interval_61") or 0.0)
                        if icd_val > 0.0:
                            proc_label = _strip_effect_number_suffix(raw_eff_name, parent_name)
                            procs_map[proc_label] = {
                                "name": proc_label,
                                "source_name": parent_name,
                                "source_fqn": fqn,
                                "icd": icd_val,
                                "kind": "trigger_icd",
                            }

            # Skip passive container effects that don't expire
            if is_passive_init and duration <= 0.0:
                continue

            # Skip instant/transient delivery wrappers (duration <= 0.5s with is_hidden=True)
            if duration <= 0.0 and not is_proc_init and max_stacks <= 1:
                continue
            if is_hidden and duration <= 0.5 and not is_proc_init and max_stacks <= 1:
                continue

            # Inspect actions & triggers inside this effect
            has_damage_action = False
            has_negative_stat_mod = False
            has_positive_stat_mod = False
            has_target_damage_taken_trigger = False
            for branch in eff.get("branches") or []:
                for trig in branch.get("triggers") or []:
                    if trig.get("trigger") in ("on_damage_taken", "on_pre_damage_taken") and (trig.get("ints") or {}).get("actor") == 2:
                        has_target_damage_taken_trigger = True
                for act in branch.get("actions") or []:
                    if not isinstance(act, dict):
                        continue
                    a_type = act.get("action_type")
                    if a_type == "damage":
                        has_damage_action = True
                    elif a_type in ("modify_stat", "modify_meta_stat", "apply_conditional_stat_mod", "apply_conditional_meta_stat_mod"):
                        amt = act.get("amount_min")
                        if amt is None:
                            amt = (act.get("floats") or {}).get("amount", 0.0)
                        amt = float(amt or 0.0)
                        stat_str = str(act.get("stat") or (act.get("ints") or {}).get("stat") or "")
                        # Cost/cooldown reductions have negative amounts but are caster buffs
                        if stat_str in ("64", "67", "68", "69", "229") or "cost" in stat_str.lower() or "cooldown" in stat_str.lower():
                            has_positive_stat_mod = True
                        elif amt < 0:
                            has_negative_stat_mod = True
                        elif amt > 0:
                            has_positive_stat_mod = True

            # Classify as Target Debuff / DoT vs Caster Buff
            is_debuff_tag = any(
                kw in eff_tags_lower
                for kw in (
                    "debuff",
                    "damage_over_time",
                    "periodic_damage",
                    "accuracy_reduced",
                    "armor_reduced",
                    "vulnerable",
                    "marked",
                    "deathmark",
                    "slowed",
                    "stunned",
                )
            )
            is_dot = (tick_interval > 0.0 and has_damage_action) or "damage_over_time" in eff_tags_lower or "periodic_damage" in eff_tags_lower

            to_actors = called_to_actors.get(eff_num, set())
            targeted_at_enemy = (
                is_debuff_tag
                or is_dot
                or has_target_damage_taken_trigger
                or (eff_num in called_with_enemy_override and not is_proc_init)
                or (not is_proc_init and has_negative_stat_mod and not has_positive_stat_mod)
                or (not is_proc_init and is_aggressive_ability and eff.get("entry") and has_damage_action and duration > 0.0)
                or (not is_proc_init and ("actor_1" in to_actors) and has_negative_stat_mod)
            )

            clean_name = raw_eff_name
            if is_hidden and re.match(r"^.+_\d+$", raw_eff_name):
                clean_name = _strip_effect_number_suffix(raw_eff_name, parent_name)

            if targeted_at_enemy and not is_proc_init:
                existing = target_debuffs_map.get(clean_name)
                if not existing or max_stacks > existing["max_stacks"] or duration > existing["duration"]:
                    target_debuffs_map[clean_name] = {
                        "name": clean_name,
                        "source_name": parent_name,
                        "source_fqn": fqn,
                        "duration": duration,
                        "max_stacks": max_stacks,
                        "is_dot": is_dot,
                    }
            else:
                existing = caster_buffs_map.get(clean_name)
                if not existing or max_stacks > existing["max_stacks"] or duration > existing["duration"]:
                    caster_buffs_map[clean_name] = {
                        "name": clean_name,
                        "source_name": parent_name,
                        "source_fqn": fqn,
                        "duration": duration,
                        "max_stacks": max_stacks,
                        "is_proc": is_proc_init or ability_type == "passive",
                    }
                if is_proc_init and clean_name not in procs_map:
                    procs_map[clean_name] = {
                        "name": clean_name,
                        "source_name": parent_name,
                        "source_fqn": fqn,
                        "icd": duration,
                        "kind": "proc_buff",
                    }

    abilities_list.sort(key=lambda a: (a["name"].lower(), a["fqn"]))
    caster_buffs_list = sorted(caster_buffs_map.values(), key=lambda b: b["name"].lower())
    target_debuffs_list = sorted(target_debuffs_map.values(), key=lambda d: d["name"].lower())
    procs_list = sorted(procs_map.values(), key=lambda p: p["name"].lower())

    # Class-filtered gear options
    gear_path = _resolve_workspace_path(GEAR_PATH)
    gear_data = load_json_file(str(gear_path)) if gear_path.is_file() else {}
    try:
        tacticals_map = filter_gear_for_class(gear_data, TACTICAL_PREFIX, class_name)
        legendaries_map = filter_gear_for_class(gear_data, LEGENDARY_PREFIX, class_name)
    except ValueError:
        tacticals_map = {}
        legendaries_map = {}

    tacticals_list = [{"name": k, "fqn": v} for k, v in sorted(tacticals_map.items())]
    legendaries_list = [{"name": k, "fqn": v} for k, v in sorted(legendaries_map.items())]

    return {
        "class_name": class_name,
        "spec_name": spec_name,
        "spec_path": spec_path,
        "default_class_folder": default_class_folder,
        "default_spec_folder": default_spec_folder,
        "choices": normalized_choices,
        "skill_tree": skill_tree_info,
        "tacticals": tacticals_list,
        "legendaries": legendaries_list,
        "abilities": abilities_list,
        "caster_buffs": caster_buffs_list,
        "target_debuffs": target_debuffs_list,
        "procs": procs_list,
    }


# ---------------------------------------------------------------------------
# Rotation Normalization & Validation
# ---------------------------------------------------------------------------

CONDITION_METADATA = [
    {
        "key": "caster_has_buff",
        "label": "Caster Has Buff",
        "category": "Caster Buffs",
        "value_type": "buff_name",
        "description": "True if the caster currently has the specified buff (or any buff in a list).",
    },
    {
        "key": "caster_does_not_have_buff",
        "label": "Caster Does NOT Have Buff",
        "category": "Caster Buffs",
        "value_type": "buff_name",
        "description": "True if the caster does NOT currently have the specified buff.",
    },
    {
        "key": "caster_buff_stacks",
        "label": "Caster Buff Stacks",
        "category": "Caster Buffs",
        "value_type": "buff_stacks",
        "description": "Checks stack/charge count on a caster buff (e.g. Harnessed Darkness >= 3).",
    },
    {
        "key": "target_has_debuff",
        "label": "Target Has Debuff / DoT",
        "category": "Target Debuffs",
        "value_type": "debuff_name",
        "description": "True if the target currently has the specified debuff or DoT.",
    },
    {
        "key": "target_doesnt_have_debuff",
        "label": "Target Does NOT Have Debuff / DoT",
        "category": "Target Debuffs",
        "value_type": "debuff_name",
        "description": "True if the target does NOT currently have the specified debuff or DoT.",
    },
    {
        "key": "target_debuff_stacks",
        "label": "Target Debuff Stacks",
        "category": "Target Debuffs",
        "value_type": "debuff_stacks",
        "description": "Checks stack count on a target debuff or DoT.",
    },
    {
        "key": "target_hp_below_pct",
        "label": "Target HP Below % (Execute)",
        "category": "Target Health",
        "value_type": "hp_below",
        "description": "True when target HP ratio <= decimal fraction (e.g. 0.4 for 40%). Supports optional bypass buff.",
    },
    {
        "key": "target_hp_above_pct",
        "label": "Target HP Above %",
        "category": "Target Health",
        "value_type": "hp_above",
        "description": "True when target HP ratio > decimal fraction (e.g. 0.4 for 40%).",
    },
    {
        "key": "caster_energy_above",
        "label": "Caster Force / Energy Above (>=",
        "category": "Caster Resource",
        "value_type": "resource_number",
        "description": "True when caster resource (Force/Energy/Heat) >= threshold.",
    },
    {
        "key": "caster_energy_below",
        "label": "Caster Force / Energy Below (<)",
        "category": "Caster Resource",
        "value_type": "resource_number",
        "description": "True when caster resource (Force/Energy/Heat) < threshold.",
    },
    {
        "key": "proc_cooldown_above",
        "label": "Proc Lockout / ICD Above (sec)",
        "category": "Cooldowns & Procs",
        "value_type": "proc_cooldown",
        "description": "True if the proc buff is NOT active and its internal cooldown / lockout remaining is > value seconds.",
    },
    {
        "key": "ability_cooldown_under",
        "label": "Ability Cooldown Under (sec)",
        "category": "Cooldowns & Procs",
        "value_type": "ability_cooldown",
        "description": "True if the specified ability's remaining cooldown is < value seconds.",
    },
]

KNOWN_RULE_KEYS = {item["key"] for item in CONDITION_METADATA} | {
    "caster_has_buff_stacks",
    "caster_buff_charges",
    "target_has_debuff_stacks",
}


def normalize_rotation_steps(raw_steps: list[Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Normalizes loaded rotation steps and repairs common hand-authored JSON issues
    (such as rule keys accidentally placed on the pool entry dict outside 'rules').
    """
    if not isinstance(raw_steps, list):
        raise ValueError("Rotation file must be a JSON array of steps.")

    normalized: list[dict[str, Any]] = []
    warnings: list[str] = []

    for idx, step in enumerate(raw_steps):
        if not isinstance(step, dict):
            warnings.append(f"Step #{idx + 1} was not an object and was skipped.")
            continue

        step_type = step.get("type", "fixed")
        if step_type == "loop_anchor":
            normalized.append({"type": "loop_anchor"})
        elif step_type == "fixed":
            normalized.append(
                {
                    "type": "fixed",
                    "ability_id": str(step.get("ability_id") or ""),
                }
            )
        elif step_type == "optional":
            rules = dict(step.get("rules") or {})
            for k, v in step.items():
                if k not in ("type", "ability_id", "rules") and k in KNOWN_RULE_KEYS:
                    rules[k] = v
                    warnings.append(
                        f"Step #{idx + 1} (Optional '{step.get('ability_id')}'): moved misplaced rule '{k}' into 'rules'."
                    )
            normalized.append(
                {
                    "type": "optional",
                    "ability_id": str(step.get("ability_id") or ""),
                    "rules": rules,
                }
            )
        elif step_type == "priority_block":
            block_name = str(step.get("name") or f"Priority Block {idx + 1}")
            raw_pool = step.get("pool") or []
            clean_pool: list[dict[str, Any]] = []
            for row_idx, item in enumerate(raw_pool):
                if not isinstance(item, dict):
                    continue
                rules = dict(item.get("rules") or {})
                for k, v in item.items():
                    if k not in ("ability_id", "rules") and k in KNOWN_RULE_KEYS:
                        rules[k] = v
                        warnings.append(
                            f"Block '{block_name}' row #{row_idx + 1} ('{item.get('ability_id')}'): "
                            f"moved misplaced rule '{k}' into 'rules'."
                        )
                clean_pool.append(
                    {
                        "ability_id": str(item.get("ability_id") or ""),
                        "rules": rules,
                    }
                )
            normalized.append(
                {
                    "type": "priority_block",
                    "name": block_name,
                    "pool": clean_pool,
                }
            )
        else:
            warnings.append(f"Step #{idx + 1}: unknown step type '{step_type}'.")

    return normalized, warnings


def get_workspace_catalog() -> dict[str, Any]:
    """Returns available disciplines, choices files, run configs, existing rotations, and relics."""
    disc_dir = _resolve_workspace_path(DISCIPLINES_DIR)
    disciplines = index_disciplines(str(disc_dir))
    # Convert absolute discipline paths back to workspace-relative POSIX paths
    rel_disciplines: dict[str, dict[str, str]] = {}
    for cls_name, specs in disciplines.items():
        rel_disciplines[cls_name] = {}
        for sp_name, sp_path in specs.items():
            try:
                rel_p = Path(sp_path).resolve().relative_to(SWTORSIM_ROOT).as_posix()
            except ValueError:
                rel_p = str(sp_path)
            rel_disciplines[cls_name][sp_name] = rel_p

    def _scan_json_dir(dir_rel: str) -> list[dict[str, str]]:
        base = _resolve_workspace_path(dir_rel)
        items: list[dict[str, str]] = []
        if not base.is_dir():
            return items
        for path in sorted(base.rglob("*.json")):
            if not path.is_file():
                continue
            label = path.relative_to(base).with_suffix("").as_posix()
            try:
                rel_path = path.resolve().relative_to(SWTORSIM_ROOT).as_posix()
            except ValueError:
                rel_path = str(path)
            items.append({"label": label, "path": rel_path})
        return items

    choices_files = _scan_json_dir(CHOICES_DIR)
    rotations_files = _scan_json_dir(ROTATIONS_DIR)
    run_configs = _scan_json_dir("data/run_config")
    builds_files = _scan_json_dir(BUILDS_DIR)

    relics_path = _resolve_workspace_path(RELICS_PATH)
    relics_raw = load_json_file(str(relics_path)) if relics_path.is_file() else []
    relics_list = [
        {"label": relic_menu_label(fqn), "fqn": fqn}
        for fqn in relics_raw
        if isinstance(fqn, str)
    ]

    return {
        "disciplines": rel_disciplines,
        "choices_files": choices_files,
        "rotations": rotations_files,
        "run_configs": run_configs,
        "builds": builds_files,
        "relics": relics_list,
        "conditions": CONDITION_METADATA,
    }


def run_dry_run_preview(payload: dict[str, Any]) -> dict[str, Any]:
    """Runs a quick single-iteration simulation preview for the current rotation and loadout."""
    import random
    from src.swtorsim.config_load import (
        load_character_stats_from_json,
        load_complete_loadout,
        load_training_dummy_armor_debuff,
    )
    from src.swtorsim.events import PlayerReady, ResourceTick
    from src.swtorsim.rotation import Rotation
    from src.swtorsim.settings import set_stem_matching
    from src.swtorsim.setup import prepare_simulation, schedule_periodic

    spec_path = str(_resolve_workspace_path(payload["spec_path"]))
    spec_data = load_json_file(spec_path)
    class_name, _spec_name = discipline_names(spec_data, spec_path)
    choices = payload.get("choices") or {}
    tactical_fqn = payload.get("tactical_fqn") or ""
    legendary_fqns = payload.get("legendary_fqns") or []
    relic_fqns = payload.get("relic_fqns") or []
    rotation_steps = payload.get("rotation") or []
    duration = min(120.0, max(5.0, float(payload.get("duration") or 30.0)))

    builds = _resolve_workspace_path(BUILDS_DIR)
    build_files = sorted(builds.glob("*.json")) if builds.is_dir() else []
    stats_path = str(build_files[0]) if build_files else ""
    if not stats_path:
        raise ValueError("No build stats JSON found in data/builds.")

    set_stem_matching(True)
    random.seed(42)

    fqns = loadout_fqns(
        spec_data,
        choices,
        tactical_fqn=tactical_fqn,
        legendary_fqns=legendary_fqns,
        relic_fqns=relic_fqns,
    )
    loadout_bps = load_complete_loadout(fqns, parsed_dir=str(PARSED_DIR))
    stats_cfg = load_character_stats_from_json(class_name, stats_path, 85)
    debuff_mod = {}
    try:
        debuff = load_training_dummy_armor_debuff()
        debuff_mod[debuff.name] = debuff
    except Exception:
        pass

    sim, player, target = prepare_simulation(
        rotation_steps, stats_cfg, loadout_bps, 10_000_000, debuff_mod
    )
    player.rotation = Rotation("PreviewRotation", rotation_steps)

    cast_log: list[dict[str, Any]] = []
    orig_cast = None

    # Wrap ability casts to record exact timeline events
    for abl in set(player.ability_db.values()):
        orig_fn = abl.cast

        def _make_wrapper(a, fn):
            def _wrapped(caster, tgt, s):
                step_idx = getattr(caster.rotation, "current_step", 0)
                step_obj = (
                    caster.rotation.sequence[step_idx]
                    if caster.rotation and 0 <= step_idx < len(caster.rotation.sequence)
                    else None
                )
                step_label = getattr(step_obj, "name", None) or type(step_obj).__name__
                ok = fn(caster, tgt, s)
                if ok:
                    active_buffs = [
                        eff.name
                        for eff in caster.effects.values()
                        if not getattr(eff, "is_expired", False)
                        and not getattr(eff, "is_passive", False)
                        and not any("lockout" in t for t in getattr(eff, "tags", ()))
                    ]
                    cast_log.append(
                        {
                            "time": round(s.current_time, 2),
                            "ability": a.name,
                            "slug": ability_name_to_slug(a.name, a.fqn),
                            "triggers_gcd": a.triggers_gcd,
                            "resource": round(caster.resource.current_value, 1),
                            "step_index": step_idx + 1,
                            "step_label": step_label,
                            "buffs": active_buffs[:6],
                        }
                    )
                return ok

            return _wrapped

        abl.cast = _make_wrapper(abl, orig_fn)

    sim.schedule_absolute(0.0, PlayerReady(player, target))
    sim.schedule_relative(1.0, ResourceTick(player))
    schedule_periodic(player, target, sim)
    sim.run_timed(duration=duration)

    total_dmg = getattr(sim.tracker, "total_damage", 0.0) if hasattr(sim, "tracker") and sim.tracker else (target.max_hp - target.hp)
    dps = total_dmg / duration if duration > 0 else 0.0

    return {
        "duration": duration,
        "total_damage": round(total_dmg, 0),
        "dps": round(dps, 1),
        "casts": cast_log,
    }


# ---------------------------------------------------------------------------
# Local Web Server Handler
# ---------------------------------------------------------------------------


class RotationBuilderRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        # Keep console output clean
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path

        try:
            if route in ("/", "/index.html"):
                if not UI_HTML_PATH.is_file():
                    self._send_json({"error": f"UI file not found at {UI_HTML_PATH}"}, status=500)
                    return
                html_bytes = UI_HTML_PATH.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(html_bytes)
                return

            if route == "/api/catalog":
                self._send_json(get_workspace_catalog())
                return

            if route == "/api/rotation":
                qs = parse_qs(parsed.query)
                rel_path = (qs.get("path") or [""])[0]
                if not rel_path:
                    self._send_json({"error": "Missing 'path' query parameter."}, status=400)
                    return
                target_file = _resolve_workspace_path(rel_path)
                if not target_file.is_file():
                    self._send_json({"error": f"Rotation file not found: {rel_path}"}, status=404)
                    return
                raw_data = load_json_file(str(target_file))
                steps, warnings = normalize_rotation_steps(raw_data)
                self._send_json(
                    {
                        "path": rel_path,
                        "filename": target_file.name,
                        "steps": steps,
                        "warnings": warnings,
                    }
                )
                return

            if route == "/api/run_config":
                qs = parse_qs(parsed.query)
                rel_path = (qs.get("path") or [""])[0]
                target_file = _resolve_workspace_path(rel_path)
                if not target_file.is_file():
                    self._send_json({"error": f"Run config not found: {rel_path}"}, status=404)
                    return
                rc_data = load_json_file(str(target_file))
                choices_data = {}
                if rc_data.get("choices_path"):
                    c_file = _resolve_workspace_path(rc_data["choices_path"])
                    if c_file.is_file():
                        choices_data = load_json_file(str(c_file))
                self._send_json(
                    {
                        "run_config": rc_data,
                        "choices": choices_data,
                    }
                )
                return

            self._send_json({"error": f"Not found: {route}"}, status=404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path

        try:
            payload = self._read_json_body()

            if route == "/api/loadout":
                spec_path = payload.get("spec_path")
                choices = payload.get("choices") or payload.get("choices_path") or {}
                tactical_fqn = payload.get("tactical_fqn") or ""
                legendary_fqns = payload.get("legendary_fqns") or []
                relic_fqns = payload.get("relic_fqns") or []
                if not spec_path:
                    self._send_json({"error": "spec_path is required."}, status=400)
                    return
                result = discover_loadout_catalog(
                    spec_path=spec_path,
                    choices=choices,
                    tactical_fqn=tactical_fqn,
                    legendary_fqns=legendary_fqns,
                    relic_fqns=relic_fqns,
                )
                self._send_json(result)
                return

            if route == "/api/rotation/save":
                class_folder = str(payload.get("class_folder") or "assassin").strip().lower()
                spec_folder = str(payload.get("spec_folder") or "hatred").strip().lower()
                filename = str(payload.get("filename") or "StandardRotation.json").strip()
                steps = payload.get("steps")
                if not isinstance(steps, list):
                    self._send_json({"error": "steps must be a list."}, status=400)
                    return
                if not filename.endswith(".json"):
                    filename += ".json"
                # Sanitize filename
                filename = Path(filename).name
                target_dir = SWTORSIM_ROOT / "data" / "rotations" / class_folder / spec_folder
                target_dir.mkdir(parents=True, exist_ok=True)
                full_path = target_dir / filename

                formatted = json.dumps(steps, indent=4, ensure_ascii=False)
                # Write with Windows CRLF line endings per Rule #6
                formatted_crlf = formatted.replace("\r\n", "\n").replace("\n", "\r\n") + "\r\n"
                full_path.write_bytes(formatted_crlf.encode("utf-8"))

                rel_saved = full_path.relative_to(SWTORSIM_ROOT).as_posix()
                print(f"[OK] Saved rotation to {rel_saved}")
                self._send_json({"ok": True, "path": rel_saved, "filename": filename})
                return

            if route == "/api/preview":
                result = run_dry_run_preview(payload)
                self._send_json(result)
                return

            self._send_json({"error": f"Unknown endpoint: {route}"}, status=404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)


def launch_web_builder(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    """Starts the local Rotation Builder web server."""
    os.chdir(SWTORSIM_ROOT)
    server = None
    actual_port = port
    for candidate_port in range(port, port + 20):
        try:
            server = ThreadingHTTPServer((host, candidate_port), RotationBuilderRequestHandler)
            actual_port = candidate_port
            break
        except OSError:
            continue

    if server is None:
        raise RuntimeError(f"[FAIL] Could not bind local HTTP server on ports {port}-{port + 19}.")

    url = f"http://{host}:{actual_port}"
    print("=========================================")
    print("   SWTOR SIM - WEB ROTATION BUILDER      ")
    print("=========================================")
    print(f"[OK] Server running at: {url}")
    print("[OK] Press Ctrl+C in the terminal to stop the server.")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[OK] Shutting down Rotation Builder server.")
    finally:
        server.server_close()


# ---------------------------------------------------------------------------
# Legacy Terminal CLI Builder (preserved for --cli mode and existing callers)
# ---------------------------------------------------------------------------


def get_input(prompt, type_func=str, default=None):
    """Helper function to safely capture and format terminal input."""
    default_str = f" [Default: {default}]" if default is not None else " [Required]"
    while True:
        user_input = input(f"{prompt}{default_str}: ").strip()
        if not user_input:
            if default is not None:
                return default
            print("[FAIL] This field is required. Please try again.")
            continue
        try:
            if type_func == bool:
                if user_input.lower() in ["y", "yes", "t", "true", "1"]:
                    return True
                elif user_input.lower() in ["n", "no", "f", "false", "0"]:
                    return False
                else:
                    print("[FAIL] Please enter 'y' or 'n'.")
                    continue

            return type_func(user_input)
        except ValueError:
            print(f"[FAIL] Invalid format. Expected {type_func.__name__}. Try again.")


def build_rules(indent="  "):
    """Interactively builds a dictionary of conditional rules for a rotation step."""
    rules = {}
    print(f"\n{indent}--- Adding Rules (Conditions) ---")
    print(f"{indent}Examples: caster_energy_below, caster_has_buff, target_hp_below_pct")

    while get_input(f"{indent}Add a rule? (y/n)", bool, False):
        key = get_input(f"{indent}Rule Key", str)
        is_nested = get_input(f"{indent}Is the value for '{key}' a nested dictionary? (y/n)", bool, False)

        if is_nested:
            nested_dict = {}
            print(f"{indent}  [Building Nested Dictionary for '{key}']")
            while True:
                sub_key = get_input(f"{indent}  Sub-key (e.g., 'name' or 'value')", str)
                sub_val_str = get_input(f"{indent}  Value for '{sub_key}'", str)

                if sub_val_str.lower() in ["true", "false"]:
                    sub_val = sub_val_str.lower() == "true"
                else:
                    try:
                        sub_val = float(sub_val_str) if "." in sub_val_str else int(sub_val_str)
                    except ValueError:
                        sub_val = sub_val_str

                nested_dict[sub_key] = sub_val

                if not get_input(f"{indent}  Add another sub-key to '{key}'? (y/n)", bool, False):
                    break

            rules[key] = nested_dict
            print(f"{indent}[OK] Added nested rule: '{key}': {nested_dict}")

        else:
            val_str = get_input(f"{indent}Value for '{key}'", str)

            if val_str.lower() in ["true", "false"]:
                val = val_str.lower() == "true"
            else:
                try:
                    val = float(val_str) if "." in val_str else int(val_str)
                except ValueError:
                    val = val_str

            rules[key] = val
            print(f"{indent}[OK] Added rule: '{key}': {val}")

    return rules


def pick_ability(catalog: list[CastableAbility], prompt: str = "Select ability number: ") -> str:
    """Shows the castable list and returns the chosen ability FQN."""
    if not catalog:
        raise ValueError("No castable abilities to choose from.")

    for idx, ability in enumerate(catalog, 1):
        suffix = "" if ability.triggers_gcd else " (off-GCD)"
        print(f"  [{idx}] {ability.name}{suffix}")

    while True:
        try:
            choice_idx = int(input(prompt).strip()) - 1
            if 0 <= choice_idx < len(catalog):
                return catalog[choice_idx].fqn
            print(f"  [FAIL] Invalid selection. Please enter a number between 1 and {len(catalog)}.")
        except ValueError:
            print(f"  [FAIL] Invalid selection. Please enter a number between 1 and {len(catalog)}.")


def rotation_folder_defaults(spec_path: str) -> tuple[str, str]:
    """Class and spec folder names from a discipline path, not its display names."""
    path = Path(spec_path)
    return path.parent.name, path.stem


def cli_main():
    os.chdir(SWTORSIM_ROOT)
    print("=========================================")
    print("      SWTOR SIM - ROTATION BUILDER       ")
    print("=========================================")

    _class_name, _spec, spec_path = select_discipline_path()
    choices_path = select_choices_path()
    catalog = build_castable_catalog(spec_path, choices_path)
    if not catalog:
        print("[WARN] No castable abilities found. Exiting without saving.")
        return

    default_class, default_spec = rotation_folder_defaults(spec_path)
    rotation = []
    saved_templates = {}

    while True:
        print("\nWhat kind of step do you want to add to the timeline?")
        print("  1. Fixed Cast (No rules. Engine waits until ability is ready)")
        print("  2. Optional Cast (Has rules. Engine skips it if rules fail)")
        print("  3. Priority Block (A pool of abilities evaluated top-to-bottom)")
        print("  4. Loop Anchor (Marks where the rotation restarts after an opener)")
        print("  5. Insert Saved Template (Paste a previously saved block/cast)")
        print("  0. Finish & Save Rotation")

        choice = get_input("Select an option", int)

        if choice == 0:
            break

        elif choice == 1:
            print("\n--- Adding FIXED Step ---")
            ability_id = pick_ability(catalog)
            rotation.append({"type": "fixed", "ability_id": ability_id})
            print(f"[OK] Fixed step '{ability_id}' added.")

        elif choice == 2:
            print("\n--- Adding OPTIONAL Step ---")
            ability_id = pick_ability(catalog)
            rules = build_rules()

            step_dict = {"type": "optional", "ability_id": ability_id, "rules": rules}
            rotation.append(step_dict)
            print(f"[OK] Optional step '{ability_id}' added.")

            if get_input("  Save this Optional Step as a template for reuse? (y/n)", bool, False):
                t_name = get_input("  Enter a short template name (e.g., 'reck_opt')", str)
                saved_templates[t_name] = step_dict
                print(f"  [OK] Template '{t_name}' saved to clipboard.")

        elif choice == 3:
            print("\n--- Adding PRIORITY BLOCK ---")
            block_name = get_input("Block Name (e.g., Main Priority Window)", str)
            pool = []

            while True:
                print(f"\n  [Pool: {block_name}] Current size: {len(pool)}")
                add_ability = get_input("  Add an ability to this priority pool? (y/n)", bool, True)
                if not add_ability:
                    break

                ab_id = pick_ability(catalog, prompt="  Select ability number: ")
                ab_rules = build_rules(indent="    ")
                pool.append({"ability_id": ab_id, "rules": ab_rules})
                print(f"  [OK] Added '{ab_id}' to pool.")

            step_dict = {"type": "priority_block", "name": block_name, "pool": pool}
            rotation.append(step_dict)
            print(f"[OK] Priority Block '{block_name}' added.")

            if get_input("  Save this Priority Block as a template for reuse? (y/n)", bool, False):
                t_name = get_input("  Enter a short template name (e.g., 'main_filler')", str)
                saved_templates[t_name] = step_dict
                print(f"  [OK] Template '{t_name}' saved to clipboard.")

        elif choice == 4:
            print("\n--- Adding LOOP ANCHOR ---")
            rotation.append({"type": "loop_anchor"})
            print("[OK] Loop Anchor added. Everything below this will repeat indefinitely.")

        elif choice == 5:
            print("\n--- INSERT SAVED TEMPLATE ---")
            if not saved_templates:
                print("[WARN] Your clipboard is empty. Create an Optional or Priority step and save it first.")
                continue

            print("Available templates:")
            for name in saved_templates.keys():
                print(f"  - {name}")

            template_name = get_input("Enter template name to insert", str)
            if template_name in saved_templates:
                rotation.append(copy.deepcopy(saved_templates[template_name]))
                print(f"[OK] Successfully inserted template '{template_name}'.")
            else:
                print("[WARN] Template not found. Skipping.")

        else:
            print("[FAIL] Invalid choice. Select 0-5.")

    if not rotation:
        print("[WARN] Rotation sequence is empty. Exiting without saving.")
        return

    print("\n=========================================")
    print("             SAVE & EXPORT               ")

    class_name = get_input("Enter Class folder (e.g., assassin)", str, default_class)
    spec_name = get_input("Enter Spec folder (e.g., hatred)", str, default_spec)

    target_dir = os.path.join("data", "rotations", class_name, spec_name)
    os.makedirs(target_dir, exist_ok=True)

    save_path = get_input("Enter filename to save (e.g., Hybrid.json)", str, "StandardRotation.json")

    if not save_path.endswith(".json"):
        save_path += ".json"

    full_path = os.path.join(target_dir, save_path)

    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(rotation, f, indent=4)

    print(f"\n[OK] SUCCESS! Rotation safely exported to {full_path}")


def main():
    parser = argparse.ArgumentParser(description="SwtorSim Rotation Builder (Web UI & CLI)")
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Use the legacy interactive terminal prompt instead of the Web UI.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port for the local Web UI server (default: 8765).",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the Web UI server without automatically opening a browser tab.",
    )
    args = parser.parse_args()

    if args.cli:
        cli_main()
    else:
        launch_web_builder(port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
