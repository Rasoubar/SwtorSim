"""Interactive CLI and browser-based rotation builder for authoring SwtorSim rotation JSON files."""

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

from src.swtorsim.cli import (
    index_disciplines,
    select_choices_path,
    select_discipline_path,
    select_legendaries,
    select_relics,
    select_tactical,
)
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
    get_disciplines_dir,
    get_gear_path,
    get_relics_path,
    normalize_pre_combat,
    relic_menu_label,
    resolve_env_extractor_path,
    resolve_skill_tree_fqns,
)
from src.swtorsim.settings import get_extractor_data_dir
from src.swtorsim.cast_timeline import CastTimelineRecorder, ability_name_to_slug  # noqa: F401

PARSED_DIR = SWTORSIM_ROOT / "data" / "extractor" / "live" / "parsed"
UI_HTML_PATH = SWTORSIM_ROOT / "tools" / "rotation_builder_ui.html"
TIMELINE_UI_PATH = SWTORSIM_ROOT / "tools" / "rotation_timeline_ui.html"
MAP_UI_PATH = SWTORSIM_ROOT / "tools" / "rotation_map_ui.html"


# ---------------------------------------------------------------------------
# Data Structures & Catalog Discovery
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CastableAbility:
    """Metadata for a castable active ability discovered from a discipline loadout."""

    fqn: str
    name: str
    triggers_gcd: bool
    slug: str = ""
    cooldown: float = 0.0
    energy_cost: float = 0.0
    max_charges: int | None = None
    activation_type: str = "instant"
    activation_duration: float = 0.0


# ability_name_to_slug lives in src/swtorsim/cast_timeline.py (shared with the simulator); re-exported here.


def _resolve_workspace_path(rel_or_abs: str | Path) -> Path:
    """Resolves a path relative to SWTORSIM_ROOT if it is not already absolute/existing."""
    if not rel_or_abs or not str(rel_or_abs).strip():
        return Path("")
    p = Path(rel_or_abs)
    if p.exists() and p != Path("."):
        return p.resolve()
    candidate = SWTORSIM_ROOT / p
    if candidate.exists() and candidate != SWTORSIM_ROOT:
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
    parsed_dir: Path | None = None,
    tactical_fqn: str = "",
    legendary_fqns: list[str] | None = None,
    relic_fqns: list[str] | None = None,
    env: str = "live",
) -> list[CastableAbility]:
    """Returns active abilities for a discipline, skill-tree selection, and optional gear/relics, sorted by name."""
    active_env = str(env).lower().strip()
    if parsed_dir is None or parsed_dir == PARSED_DIR:
        parsed_dir = SWTORSIM_ROOT / get_extractor_data_dir(active_env) / "parsed"
    resolved_spec = _resolve_workspace_path(spec_path)
    spec_data = load_json_file(str(resolved_spec))
    if isinstance(choices_path, dict):
        choices = choices_path
    elif choices_path and Path(choices_path).is_file():
        resolved_choices = _resolve_workspace_path(choices_path)
        choices = load_json_file(str(resolved_choices))
    else:
        choices = {}

    actives: list[CastableAbility] = []
    passive_count = 0
    talent_count = 0

    for fqn in loadout_fqns(
        spec_data,
        choices,
        tactical_fqn=tactical_fqn,
        legendary_fqns=legendary_fqns,
        relic_fqns=relic_fqns,
    ):
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
    parsed_dir: Path | None = None,
    env: str = "live",
) -> dict[str, Any]:
    active_env = str(env).lower().strip()
    cand = resolve_env_extractor_path(spec_path, active_env)
    if _resolve_workspace_path(cand).is_file():
        spec_path = cand
    if parsed_dir is None or parsed_dir == PARSED_DIR:
        parsed_dir = SWTORSIM_ROOT / get_extractor_data_dir(active_env) / "parsed"
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

    choices_dict: dict = {}
    if isinstance(choices, str) and choices.strip():
        resolved_choices = _resolve_workspace_path(choices)
        if resolved_choices.is_file():
            try:
                loaded = load_json_file(str(resolved_choices))
                if isinstance(loaded, dict):
                    choices_dict = loaded
            except Exception:
                choices_dict = {}
    elif isinstance(choices, dict):
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
                    bp_icon = ""
                    if bp_path.is_file():
                        try:
                            bp_doc = load_json_file(str(bp_path))
                            bp_name = bp_doc.get("name") or bp_name
                            bp_type = bp_doc.get("type") or bp_type
                            bp_icon = bp_doc.get("icon") or ""
                        except Exception:
                            pass
                    entries.append({"fqn": fqn, "name": bp_name, "type": bp_type, "icon": bp_icon})
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
                    "icon": doc.get("icon") or "",
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

            eff_icon = eff.get("icon") or doc.get("icon") or ""

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
                    "icon": eff_icon,
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
                                "icon": eff_icon,
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
                        "icon": eff_icon,
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
                        "icon": eff_icon,
                    }
                if is_proc_init and clean_name not in procs_map:
                    procs_map[clean_name] = {
                        "name": clean_name,
                        "source_name": parent_name,
                        "source_fqn": fqn,
                        "icd": duration,
                        "kind": "proc_buff",
                        "icon": eff_icon,
                    }

    abilities_list.sort(key=lambda a: (a["name"].lower(), a["fqn"]))
    caster_buffs_list = sorted(caster_buffs_map.values(), key=lambda b: b["name"].lower())
    target_debuffs_list = sorted(target_debuffs_map.values(), key=lambda d: d["name"].lower())
    procs_list = sorted(procs_map.values(), key=lambda p: p["name"].lower())

    # Class-filtered gear options
    gear_path = _resolve_workspace_path(get_gear_path(active_env))
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
        "environment": active_env,
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
    {
        "key": "ability_cooldown_above",
        "label": "Ability Cooldown Above (sec)",
        "category": "Cooldowns & Procs",
        "value_type": "ability_cooldown",
        "description": "True if the specified ability's remaining cooldown is > value seconds.",
    },
]

KNOWN_RULE_KEYS = {item["key"] for item in CONDITION_METADATA} | {
    "caster_has_buff_stacks",
    "caster_buff_charges",
    "target_has_debuff_stacks",
}


def normalize_rotation_steps(raw_steps: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Normalizes loaded rotation steps and repairs common hand-authored JSON issues
    (such as rule keys accidentally placed on the pool entry dict outside 'rules').
    """
    if isinstance(raw_steps, dict):
        raw_steps = raw_steps.get("sequence") or raw_steps.get("steps") or []
    if not isinstance(raw_steps, list):
        raise ValueError("Rotation file must be a JSON array of steps or contain a 'sequence' array.")

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
            lead_val = step.get("lead_time") if "lead_time" in step else step.get("pre_cast_offset")
            norm_fixed = {
                "type": "fixed",
                "ability_id": str(step.get("ability_id") or ""),
            }
            if lead_val is not None:
                norm_fixed["lead_time"] = float(lead_val)
            normalized.append(norm_fixed)
        elif step_type == "optional":
            rules = dict(step.get("rules") or {})
            lead_time = float(step.get("lead_time") or step.get("pre_cast_offset") or 0.0)
            for k, v in step.items():
                if k not in ("type", "ability_id", "rules", "lead_time", "pre_cast_offset") and k in KNOWN_RULE_KEYS:
                    rules[k] = v
                    warnings.append(
                        f"Step #{idx + 1} (Optional '{step.get('ability_id')}'): moved misplaced rule '{k}' into 'rules'."
                    )
            lead_val = step.get("lead_time") if "lead_time" in step else step.get("pre_cast_offset")
            norm_step = {
                "type": "optional",
                "ability_id": str(step.get("ability_id") or ""),
                "rules": rules,
            }
            if lead_val is not None:
                norm_step["lead_time"] = float(lead_val)
            normalized.append(norm_step)
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
                entry: dict[str, Any] = {
                    "ability_id": str(item.get("ability_id") or ""),
                    "rules": rules,
                }
                lead_val = item.get("lead_time") if "lead_time" in item else item.get("pre_cast_offset")
                if lead_val is not None:
                    entry["lead_time"] = float(lead_val)
                clean_pool.append(entry)
            norm_block: dict[str, Any] = {
                "type": "priority_block",
                "name": block_name,
                "pool": clean_pool,
            }
            block_lead = step.get("lead_time") if "lead_time" in step else step.get("pre_cast_offset")
            if block_lead is not None:
                norm_block["lead_time"] = float(block_lead)
            normalized.append(norm_block)
        else:
            warnings.append(f"Step #{idx + 1}: unknown step type '{step_type}'.")

    return normalized, warnings


def normalize_pre_combat_steps(raw: Any) -> list[dict[str, Any]]:
    """Extracts the canonical pre-combat step list from a rotation file (``[]`` for bare arrays).

    Keeps only known keys per step kind and drops defaults (``keep_timed_effects: true``,
    ``wait_for_cooldown: false``) so saved files stay minimal.
    """
    if not isinstance(raw, dict):
        return []
    clean: list[dict[str, Any]] = []
    for step in normalize_pre_combat(raw.get("precast"), raw.get("pre_combat")):
        if step.get("swap_tactical"):
            out: dict[str, Any] = {"swap_tactical": str(step["swap_tactical"])}
            if step.get("keep_timed_effects", True) is False:
                out["keep_timed_effects"] = False
        elif "wait_until" in step:
            out = {"wait_until": dict(step.get("wait_until") or {})}
            if step.get("max_wait") is not None:
                out["max_wait"] = float(step["max_wait"])
        elif "wait" in step:
            out = {"wait": float(step["wait"])}
        else:
            out = {"ability": str(step.get("ability"))}
            if step.get("target") in ("self", "target"):
                out["target"] = step["target"]
            if step.get("wait_for_cooldown"):
                out["wait_for_cooldown"] = True
                if step.get("max_wait") is not None:
                    out["max_wait"] = float(step["max_wait"])
        clean.append(out)
    return clean


def normalize_weave_steps(raw: Any) -> list[dict[str, Any]]:
    """Extracts the loop-only "always weave" entries from a rotation file (``[]`` for bare arrays).

    Accepts the file wrapper (``{"weave": [...]}``) or the entry list itself. Each entry is
    ``{"ability_id", "rules"}`` plus an optional ``lead_time``, like an optional step without a position.
    """
    entries = raw.get("weave") if isinstance(raw, dict) else raw
    clean: list[dict[str, Any]] = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or entry.get("type") or not entry.get("ability_id"):
            continue
        out: dict[str, Any] = {"ability_id": str(entry["ability_id"]), "rules": dict(entry.get("rules") or {})}
        lead_val = entry.get("lead_time") if "lead_time" in entry else entry.get("pre_cast_offset")
        if lead_val is not None:
            out["lead_time"] = float(lead_val)
        clean.append(out)
    return clean


def normalize_pull_gate(raw: Any) -> dict[str, Any]:
    """Extracts ``pull_conditions`` / ``pull_max_wait`` from a rotation file (empty dict when unset)."""
    if not isinstance(raw, dict):
        return {}
    conds = raw.get("pull_conditions")
    if not isinstance(conds, dict) or not conds:
        return {}
    gate: dict[str, Any] = {"pull_conditions": dict(conds)}
    if raw.get("pull_max_wait") is not None:
        gate["pull_max_wait"] = float(raw["pull_max_wait"])
    return gate


def build_rotation_file_data(
    steps: list[dict[str, Any]],
    pre_combat: list[dict[str, Any]] | None,
    pull_conditions: dict[str, Any] | None = None,
    pull_max_wait: float | None = None,
    weave: list[dict[str, Any]] | None = None,
) -> Any:
    """Rotation file payload: a bare step array, or a ``{"pre_combat", "pull_conditions", "weave", "sequence"}``
    wrapper when pre-combat steps, fight-start (pull) conditions or loop-only weave entries are set."""
    pre = normalize_pre_combat_steps({"pre_combat": pre_combat or []})
    gate = normalize_pull_gate({"pull_conditions": pull_conditions, "pull_max_wait": pull_max_wait})
    weave_entries = normalize_weave_steps(weave or [])
    if not pre and not gate and not weave_entries:
        return steps
    data: dict[str, Any] = {}
    if pre:
        data["pre_combat"] = pre
    data.update(gate)
    if weave_entries:
        data["weave"] = weave_entries
    data["sequence"] = steps
    return data


def class_tactical_fqns(class_name: str, env: str = "live") -> list[str]:
    """Tactical FQNs available to ``class_name`` (class-specific and generic)."""
    gear_path = _resolve_workspace_path(get_gear_path(str(env).lower().strip()))
    gear_data = load_json_file(str(gear_path)) if gear_path.is_file() else {}
    return sorted(filter_gear_for_class(gear_data, TACTICAL_PREFIX, class_name).values())


def get_workspace_catalog(env: str = "live") -> dict[str, Any]:
    """Returns available disciplines, choices files, run configs, existing rotations, and relics."""
    active_env = str(env).lower().strip()
    disc_dir_rel = get_disciplines_dir(active_env)
    parsed_dir = SWTORSIM_ROOT / get_extractor_data_dir(active_env) / "parsed"
    relics_path_rel = get_relics_path(active_env)
    disc_dir = _resolve_workspace_path(disc_dir_rel)
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

    def _scan_json_dir(dir_rel: str) -> list[dict[str, Any]]:
        base = _resolve_workspace_path(dir_rel)
        items: list[dict[str, Any]] = []
        if not base.is_dir():
            return items
        for path in sorted(base.rglob("*.json")):
            if not path.is_file():
                continue
            rel = path.relative_to(base)
            is_custom = any(p.lower() == "custom" for p in rel.parts)
            label = rel.with_suffix("").as_posix()
            try:
                rel_path = path.resolve().relative_to(SWTORSIM_ROOT).as_posix()
            except ValueError:
                rel_path = str(path)
            items.append({"label": label, "path": rel_path, "name": path.name, "is_custom": is_custom})
        return items

    def _scan_rotations(dir_rel: str) -> list[dict[str, Any]]:
        base = _resolve_workspace_path(dir_rel)
        items: list[dict[str, Any]] = []
        if not base.is_dir():
            return items
        for path in sorted(base.rglob("*.json")):
            if not path.is_file():
                continue
            rel = path.relative_to(base)
            parts = rel.parts
            is_custom = len(parts) > 0 and parts[0].lower() == "custom"
            if is_custom:
                cls = parts[1].lower() if len(parts) >= 3 else ""
                sp = parts[2].lower() if len(parts) >= 4 else ""
                clean_label = "/".join(parts[1:]).removesuffix(".json") if len(parts) >= 2 else rel.with_suffix("").as_posix()
            else:
                cls = parts[0].lower() if len(parts) >= 2 else ""
                sp = parts[1].lower() if len(parts) >= 3 else ""
                clean_label = rel.with_suffix("").as_posix()
            try:
                rel_path = path.resolve().relative_to(SWTORSIM_ROOT).as_posix()
            except ValueError:
                rel_path = str(path)
            items.append({
                "label": clean_label,
                "name": path.name,
                "path": rel_path,
                "class": cls,
                "spec": sp,
                "is_custom": is_custom,
            })
        return items

    choices_files_raw = _scan_json_dir(CHOICES_DIR)
    choices_files = []
    for cf in choices_files_raw:
        target = _resolve_workspace_path(cf["path"])
        if target.is_file():
            try:
                doc = load_json_file(str(target))
                # Must be a skill-tree choices dictionary (not a rotation list or stat build)
                if isinstance(doc, dict) and not doc.get("stats") and not doc.get("gear") and not isinstance(doc.get("steps"), list):
                    choices_files.append(cf)
            except Exception:
                pass
    rotations_files = _scan_rotations(ROTATIONS_DIR)
    run_configs = _scan_json_dir("data/run_config")
    builds_files = _scan_json_dir(BUILDS_DIR)

    relics_path = _resolve_workspace_path(relics_path_rel)
    relics_raw = load_json_file(str(relics_path)) if relics_path.is_file() else []
    relics_list = []
    for fqn in relics_raw:
        if not isinstance(fqn, str):
            continue
        short_lbl = relic_menu_label(fqn)
        r_name = short_lbl
        r_type = "active" if ".onuse." in fqn else "passive"
        bp_file = parsed_dir / fqn_to_relative_path(fqn)
        if bp_file.is_file():
            try:
                bp_doc = load_json_file(str(bp_file))
                r_name = bp_doc.get("name") or short_lbl
                r_type = bp_doc.get("type") or r_type
            except Exception:
                pass
        tag_lbl = "On-Use" if r_type == "active" else "Proc"
        relics_list.append(
            {
                "label": f"{r_name} [{tag_lbl}] ({short_lbl})",
                "name": r_name,
                "short_label": short_lbl,
                "type": r_type,
                "fqn": fqn,
            }
        )

    return {
        "environment": active_env,
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
    env = payload.get("env") or payload.get("environment") or "live"
    active_env = str(env).lower().strip()
    parsed_dir = SWTORSIM_ROOT / get_extractor_data_dir(active_env) / "parsed"
    level = int(payload.get("level") or (85 if active_env == "pts" else 80))
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
    weave_entries = normalize_weave_steps(payload.get("weave") or [])
    if weave_entries:
        # Loop-only weave entries travel with the steps in the dict form Rotation understands.
        rotation_steps = {"sequence": rotation_steps, "weave": weave_entries}
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
    loadout_bps = load_complete_loadout(fqns, parsed_dir=str(parsed_dir))
    stats_cfg = load_character_stats_from_json(class_name, stats_path, level)
    debuff_mod = {}
    try:
        debuff = load_training_dummy_armor_debuff()
        debuff_mod[debuff.name] = debuff
    except Exception:
        pass

    precast_opt = payload.get("precast")
    pre_combat_opt = payload.get("pre_combat")
    gate = normalize_pull_gate(payload)
    sim, player, target = prepare_simulation(
        rotation_steps,
        stats_cfg,
        loadout_bps,
        10_000_000,
        debuff_mod,
        precast=precast_opt,
        pre_combat=pre_combat_opt,
        pull_conditions=gate.get("pull_conditions"),
        pull_max_wait=gate.get("pull_max_wait"),
    )
    player.rotation = Rotation("PreviewRotation", rotation_steps)

    # Per-cast rows (step, resource, buffs, cast/channel timing) for the preview table and Cast Timeline
    recorder = CastTimelineRecorder(player).install()

    schedule_periodic(player, target, sim)
    sim.run_timed(duration=duration)

    total_dmg = getattr(sim.tracker, "total_damage", 0.0) if hasattr(sim, "tracker") and sim.tracker else (target.max_hp - target.hp)
    combat_dur = sim.get_combat_duration() if getattr(sim, "combat_start_time", None) is not None else duration
    dps = total_dmg / combat_dur if combat_dur > 0 else 0.0

    # T0 = first damage (pre-combat rows get negative combat_time); raw sim time stays in "time"
    t0 = sim.combat_start_time if sim.combat_start_time is not None else (sim.pre_combat_end_time or 0.0)
    cast_log = recorder.finalize(t0)
    runner = getattr(player, "pre_combat", None)
    swaps = [
        {**sw, "time": round(sw["t"], 2), "combat_time": round(sw["t"] - t0, 2)}
        for sw in (getattr(runner, "swaps", None) or [])
    ]
    skipped = [
        {**sk, "time": round(sk["t"], 2), "combat_time": round(sk["t"] - t0, 2)}
        for sk in (getattr(runner, "skipped", None) or [])
    ]

    return {
        "duration": duration,
        "total_damage": round(total_dmg, 0),
        "dps": round(dps, 1),
        "casts": cast_log,
        "combat_start_time": round(t0, 2),
        "pre_combat_duration": round(max(0.0, t0), 2),
        "tactical_swaps": swaps,
        "pre_combat_skipped": skipped,
        "final_tactical": getattr(player, "tactical_fqn", ""),
        "pull_gate_wait": (
            round(runner.pull_time - runner.pull_gate_start, 2)
            if runner is not None and runner.pull_time is not None and runner.pull_gate_start is not None
            else None
        ),
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
            page_path = {
                "/": UI_HTML_PATH,
                "/index.html": UI_HTML_PATH,
                "/timeline": TIMELINE_UI_PATH,
                "/timeline.html": TIMELINE_UI_PATH,
                "/map": MAP_UI_PATH,
                "/map.html": MAP_UI_PATH,
            }.get(route)
            if page_path is not None:
                if not page_path.is_file():
                    self._send_json({"error": f"UI file not found at {page_path}"}, status=500)
                    return
                html_bytes = page_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(html_bytes)
                return

            if route.startswith("/icons/"):
                icon_name = Path(route).name
                if not icon_name.lower().endswith(".png"):
                    icon_name = f"{icon_name}.png"
                icon_file = None
                for cand_dir in (
                    SWTORSIM_ROOT / "tools" / "web" / "icons",
                    SWTORSIM_ROOT / "data" / "extractor" / "live" / "icons",
                    SWTORSIM_ROOT / "data" / "extractor" / "pts" / "icons",
                ):
                    cand_path = cand_dir / icon_name
                    if cand_path.is_file():
                        icon_file = cand_path
                        break
                    lower_path = cand_dir / icon_name.lower()
                    if lower_path.is_file():
                        icon_file = lower_path
                        break
                if icon_file is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                png_bytes = icon_file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(png_bytes)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(png_bytes)
                return

            if route == "/api/catalog":
                qs = parse_qs(parsed.query)
                env = (qs.get("env") or ["live"])[0]
                self._send_json(get_workspace_catalog(env=env))
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
                        "pre_combat": normalize_pre_combat_steps(raw_data),
                        "weave": normalize_weave_steps(raw_data),
                        **normalize_pull_gate(raw_data),
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
                env = payload.get("env") or "live"
                if not spec_path:
                    self._send_json({"error": "spec_path is required."}, status=400)
                    return
                result = discover_loadout_catalog(
                    spec_path=spec_path,
                    choices=choices,
                    tactical_fqn=tactical_fqn,
                    legendary_fqns=legendary_fqns,
                    relic_fqns=relic_fqns,
                    env=env,
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
                custom_dir = SWTORSIM_ROOT / "data" / "rotations" / "custom" / class_folder / spec_folder
                custom_dir.mkdir(parents=True, exist_ok=True)
                full_path = custom_dir / filename

                file_data = build_rotation_file_data(
                    steps, payload.get("pre_combat"), payload.get("pull_conditions"), payload.get("pull_max_wait"),
                    weave=payload.get("weave"),
                )
                formatted = json.dumps(file_data, indent=4, ensure_ascii=False)
                # Write with Windows CRLF line endings per Rule #6
                formatted_crlf = formatted.replace("\r\n", "\n").replace("\n", "\r\n") + "\r\n"
                full_path.write_bytes(formatted_crlf.encode("utf-8"))

                rel_saved = full_path.relative_to(SWTORSIM_ROOT).as_posix()
                print(f"[OK] Saved custom rotation to {rel_saved}")
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

    class_name, _spec, spec_path = select_discipline_path()
    choices_path = select_choices_path()
    tactical_fqn = select_tactical(class_name)
    legendary_fqns = select_legendaries(class_name)
    relic_fqns = select_relics()
    catalog = build_castable_catalog(
        spec_path,
        choices_path,
        tactical_fqn=tactical_fqn,
        legendary_fqns=legendary_fqns,
        relic_fqns=relic_fqns,
    )
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

            lead_time = get_input("  Lead time before next GCD in seconds (e.g., 0.2, 0.0 for instant at GCD):", float, 0.0)
            step_dict = {"type": "optional", "ability_id": ability_id, "rules": rules}
            if lead_time > 0.0:
                step_dict["lead_time"] = lead_time
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
