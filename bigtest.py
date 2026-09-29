import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def find_project_root() -> Path:
    """Traverses upward to resolve the SwtorSim root folder."""
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / "data").exists() and (parent / "src").exists():
            return parent
    return current


PROJECT_ROOT = find_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.swtorsim.cli import (
    load_discipline_fqns,
    prompt_optional_choices,
    select_discipline_path,
    select_rotation_path,
    select_stats_path,
)
from src.swtorsim.config_load import (
    load_character_stats_from_json,
    load_complete_loadout,
    load_permanent_effects_from_json,
    load_rotation_from_json,
)
from src.swtorsim.modifiers import Modifier, load_stat_map, resolve_stat
from src.swtorsim.setup import prepare_simulation


@dataclass
class SourcedModifier:
    source_name: str
    source_fqn: str
    source_category: str
    source_type: str
    modifier: Modifier


def load_json_for_fqn(fqn: str, parsed_dir: Path) -> Optional[Dict[str, Any]]:
    """Loads a blueprint JSON file by translating its dotted FQN to disk path."""
    rel_path = Path(*fqn.split(".")).with_suffix(".json")
    full_path = parsed_dir / rel_path
    if full_path.is_file():
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def load_json_for_path(path_str: str) -> Optional[Dict[str, Any]]:
    """Loads a JSON file from either an absolute path or relative to project root."""
    p = Path(path_str)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    if p.is_file():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def categorize_blueprint(fqn: str, raw_type: str = "") -> str:
    """Classifies the blueprint into a semantic category for structured output."""
    if fqn.startswith("tal."):
        return "Passive Talents"
    if fqn.startswith("abl."):
        return "Active Abilities"
    if "tactical" in fqn or "implant" in fqn or "gear" in fqn:
        return "Gear / Tacticals"
    if "relic" in fqn:
        return "Relics"
    if raw_type:
        return raw_type.capitalize()
    return "Miscellaneous"


def format_action_summary(action: Dict[str, Any]) -> str:
    """Produces a concise summary string for any action node."""
    action_type = action.get("action_type", "unknown_action")
    parts = [f"action={action_type}"]

    if action_type == "modify_stat":
        raw_stat = action.get("stat") or action.get("name", "")
        stat_name = resolve_stat(raw_stat)
        val = action.get("amount_min", action.get("amount_percent", 0.0))
        parts.append(f"stat='{stat_name}'")
        parts.append(
            f"val={val:+.4f}"
            if isinstance(val, (int, float))
            else f"val={val}"
        )
        if action.get("tags"):
            parts.append(f"tags={action.get('tags')}")
        if action.get("impact"):
            parts.append(f"impact={action.get('impact')}")

    elif action_type == "modify_meta_stat":
        ints = action.get("ints") or {}
        floats = action.get("floats") or {}
        raw_stat = ints.get("stat", action.get("stat", ""))
        stat_name = resolve_stat(raw_stat)
        val = floats.get("amount", 0.0)
        parts.append(f"stat='{stat_name}'")
        parts.append(
            f"val={val:+.4f}"
            if isinstance(val, (int, float))
            else f"val={val}"
        )
        if action.get("tags"):
            parts.append(f"tags={action.get('tags')}")

    elif action_type == "call_effect":
        parts.append(f"target_effect={action.get('effect')}")
        from_actor = action.get("from_actor")
        to_actor = action.get("to_actor")
        if from_actor or to_actor:
            parts.append(f"flow=({from_actor} -> {to_actor})")

    elif action_type in ("apply_buff", "apply_debuff"):
        for k in ("buff_name", "effect", "duration", "charges", "max_stacks"):
            if action.get(k) is not None:
                parts.append(f"{k}={action[k]}")

    elif action_type in ("damage", "heal"):
        for k in (
            "damage_type",
            "heal_type",
            "amount_min",
            "amount_max",
            "coefficient",
        ):
            if action.get(k) is not None:
                parts.append(f"{k}={action[k]}")

    else:
        skip = {"action_type"}
        extra = [
            f"{k}={v}"
            for k, v in action.items()
            if k not in skip and v is not None and v != {} and v != []
        ]
        parts.extend(extra[:4])

    return " | ".join(parts)


def extract_blueprint_modifiers(
    data: Dict[str, Any], fqn: str, name: str, category: str
) -> List[SourcedModifier]:
    """Scans root stat_changes and effect actions in a blueprint JSON."""
    results: List[SourcedModifier] = []

    # 1. Talent stat_changes
    stat_changes = data.get("stat_changes")
    if isinstance(stat_changes, list):
        for change in stat_changes:
            if isinstance(change, dict):
                try:
                    mod = Modifier.from_stat_change(change)
                    results.append(
                        SourcedModifier(
                            source_name=name,
                            source_fqn=fqn,
                            source_category=category,
                            source_type="stat_change",
                            modifier=mod,
                        )
                    )
                except Exception:
                    pass

    # 2. Effect branch actions
    effects = data.get("effects")
    if isinstance(effects, list):
        for effect in effects:
            if not isinstance(effect, dict):
                continue
            for branch in effect.get("branches", []):
                if not isinstance(branch, dict):
                    continue
                for action in branch.get("actions", []):
                    if not isinstance(action, dict):
                        continue
                    action_type = action.get("action_type")
                    if action_type == "modify_stat":
                        try:
                            mod = Modifier.from_modify_stat(action)
                            results.append(
                                SourcedModifier(
                                    source_name=name,
                                    source_fqn=fqn,
                                    source_category=category,
                                    source_type="modify_stat",
                                    modifier=mod,
                                )
                            )
                        except Exception:
                            pass
                    elif action_type == "modify_meta_stat":
                        try:
                            mod = Modifier.from_modify_meta_stat(action)
                            results.append(
                                SourcedModifier(
                                    source_name=name,
                                    source_fqn=fqn,
                                    source_category=category,
                                    source_type="modify_meta_stat",
                                    modifier=mod,
                                )
                            )
                        except Exception:
                            pass

    return results


def print_loaded_effects_registry(
    blueprints_data: List[Tuple[str, str, str, Dict[str, Any]]]
) -> None:
    """Prints a structured breakdown of every loaded effect and stat alteration across all blueprints."""
    categorized = defaultdict(list)
    total_effects_count = 0

    for name, fqn, category, raw_json in blueprints_data:
        categorized[category].append((name, fqn, raw_json))
        effects = raw_json.get("effects") or []
        total_effects_count += (
            len(effects) if isinstance(effects, list) else 0
        )

    print("\n" + "=" * 90)
    print(
        f"📜 ALL LOADED EFFECTS & BLUEPRINTS ({len(blueprints_data)} Blueprints | {total_effects_count} Effects)"
    )
    print("=" * 90)

    category_order = [
        "Active Abilities",
        "Passive Talents",
        "Gear / Tacticals",
        "Relics",
        "Debuff Module",
        "Miscellaneous",
    ]
    sorted_categories = sorted(
        categorized.keys(),
        key=lambda c: (
            category_order.index(c) if c in category_order else 99,
            c,
        ),
    )

    for cat in sorted_categories:
        bp_list = categorized[cat]
        print(f"\n{'#' * 90}")
        print(f"CATEGORY: {cat.upper()} ({len(bp_list)} blueprints)")
        print(f"{'#' * 90}")

        for name, fqn, raw_json in sorted(bp_list, key=lambda x: x[0]):
            stat_changes = raw_json.get("stat_changes") or []
            effects = raw_json.get("effects") or []
            tags = raw_json.get("tags") or []

            print(f"\n• {name}  [{fqn}]")
            if tags:
                print(f"  Tags: {tags}")

            # Print static stat changes (talents)
            if stat_changes and isinstance(stat_changes, list):
                print(f"  [Stat Changes ({len(stat_changes)})]")
                for idx, sc in enumerate(stat_changes):
                    if not isinstance(sc, dict):
                        continue
                    sc_stat = resolve_stat(sc.get("name") or sc.get("stat", ""))
                    sc_val = sc.get("value", 0.0)
                    impact = sc.get("impact")
                    impact_str = (
                        f" -> Impact: {impact.get('fqn', impact)}"
                        if isinstance(impact, dict)
                        else f" -> Impact: {impact}"
                        if impact
                        else ""
                    )
                    print(
                        f"    - #{idx}: {sc_stat}: {sc_val:+.4f}{impact_str}"
                    )

            # Print dynamic effects
            if effects and isinstance(effects, list):
                print(f"  [Effects ({len(effects)})]")
                for e_idx, eff in enumerate(effects):
                    if not isinstance(eff, dict):
                        continue
                    eff_id = eff.get("id", eff.get("effect_id", e_idx))
                    eff_comment = eff.get("comment") or eff.get("name") or ""
                    header_extra = f" - '{eff_comment}'" if eff_comment else ""
                    print(f"    Effect #{e_idx} (ID: {eff_id}){header_extra}:")

                    # Extract all actions from branches or direct node
                    actions: List[Tuple[int, Dict[str, Any]]] = []
                    if "branches" in eff and isinstance(eff["branches"], list):
                        for b_idx, br in enumerate(eff["branches"]):
                            if isinstance(br, dict):
                                for act in br.get("actions", []):
                                    if isinstance(act, dict):
                                        actions.append((b_idx, act))
                    elif "actions" in eff and isinstance(eff["actions"], list):
                        for act in eff["actions"]:
                            if isinstance(act, dict):
                                actions.append((0, act))

                    if actions:
                        for b_idx, act in actions:
                            print(
                                f"      [Branch {b_idx}] {format_action_summary(act)}"
                            )
                    else:
                        print("      (No actions registered)")
            elif not stat_changes:
                print("  (No static stat changes or dynamic effects)")


def run_ability_modifier_matrix() -> None:
    # 0. Load Stat Mappings
    csv_path = PROJECT_ROOT / "data" / "modifier_id_mapping.csv"
    load_stat_map(csv_path)

    print("=" * 90)
    print("  ASSASSIN LOADOUT: EFFECTS & MODIFIER MATRIX INSPECTION")
    print("=" * 90)

    # 1. Interactive Prompts[cite: 1]
    class_name, spec_name, spec_path = select_discipline_path()
    stats_path = select_stats_path()
    rotation_path = select_rotation_path(spec_name)

    # 2. Gather All Selected FQNs[cite: 1]
    discipline_fqns = load_discipline_fqns(spec_path)
    selected_gear_fqns, selected_relic_paths = prompt_optional_choices(
        class_name
    )
    all_selected_fqns = discipline_fqns + selected_gear_fqns

    # 3. Load Complete Blueprints Database[cite: 1]
    parsed_dir = PROJECT_ROOT / "data" / "extractor" / "parsed"
    loadout_blueprints = load_complete_loadout(
        selected_fqns=all_selected_fqns,
        selected_relic_paths=selected_relic_paths,
        parsed_dir=str(parsed_dir),
    )

    stats_config = load_character_stats_from_json(class_name, stats_path)
    rotation_config = load_rotation_from_json(rotation_path)
    debuff_module_path = PROJECT_ROOT / "data" / "DebuffModule.json"
    debuff_module = load_permanent_effects_from_json(str(debuff_module_path))

    # 4. Construct Simulation Runtime[cite: 1]
    _, player, _ = prepare_simulation(
        rotation_config=rotation_config,
        stats_config=stats_config,
        loadout_blueprints=loadout_blueprints,
        dummy_hp=10000000,
        debuff_module=debuff_module,
    )

    # 5. Collect Raw Data for All Loaded Blueprints
    blueprints_raw: List[Tuple[str, str, str, Dict[str, Any]]] = []
    all_sourced_modifiers: List[SourcedModifier] = []

    for fqn, bp in loadout_blueprints.items():
        bp_name = getattr(bp, "name", fqn)
        raw_json = getattr(bp, "raw_data", None)
        if not raw_json:
            raw_json = load_json_for_fqn(fqn, parsed_dir)

        category = categorize_blueprint(fqn, getattr(bp, "type", ""))
        if raw_json:
            blueprints_raw.append((bp_name, fqn, category, raw_json))
            mods = extract_blueprint_modifiers(
                raw_json, fqn, bp_name, category
            )
            all_sourced_modifiers.extend(mods)

    # Ingest Relic Files if not captured in loadout_blueprints[cite: 1]
    for relic_path in selected_relic_paths:
        raw_json = load_json_for_path(relic_path)
        if raw_json:
            r_name = raw_json.get("name", Path(relic_path).stem)
            r_fqn = raw_json.get("fqn", Path(relic_path).stem)
            category = "Relics"
            blueprints_raw.append((r_name, r_fqn, category, raw_json))
            mods = extract_blueprint_modifiers(
                raw_json, r_fqn, r_name, category
            )
            all_sourced_modifiers.extend(mods)

    # Ingest DebuffModule.json
    raw_debuff_json = load_json_for_path(str(debuff_module_path))
    if raw_debuff_json:
        d_name = raw_debuff_json.get("name", "Target Debuff Module")
        d_fqn = "module.debuff.target"
        category = "Debuff Module"
        blueprints_raw.append((d_name, d_fqn, category, raw_debuff_json))
        mods = extract_blueprint_modifiers(
            raw_debuff_json, d_fqn, d_name, category
        )
        all_sourced_modifiers.extend(mods)

    # 6. Print the Complete Registry of Loaded Effects
    print_loaded_effects_registry(blueprints_raw)

    # 7. Partition Modifiers into Global and Scoped
    global_modifiers: List[SourcedModifier] = []
    scoped_modifiers: List[SourcedModifier] = []

    for sm in all_sourced_modifiers:
        if not sm.modifier.targets:
            global_modifiers.append(sm)
        else:
            scoped_modifiers.append(sm)

    # 8. Retrieve and Sort Unique Active Abilities[cite: 1]
    unique_active_abilities = {
        id(abl): abl for abl in player.ability_db.values()
    }.values()
    sorted_active = sorted(
        unique_active_abilities, key=lambda a: getattr(a, "name", str(a))
    )

    # 9. Print Scoped Ability Matches
    print("\n" + "=" * 90)
    print(f"🎯 ABILITY-SPECIFIC MODIFIER MATCHES ({len(sorted_active)} Abilities)")
    print("=" * 90)

    abilities_with_mods = 0

    for abl in sorted_active:
        abl_name = getattr(abl, "name", "Unknown Ability")
        abl_fqn = getattr(abl, "fqn", "")
        abl_tags = frozenset(getattr(abl, "tags", []))

        matched_scoped: List[Tuple[SourcedModifier, str]] = []
        for sm in scoped_modifiers:
            mod = sm.modifier
            if mod.applies_to(ability_fqn=abl_fqn, ability_tags=abl_tags):
                reasons = []
                if abl_fqn and abl_fqn in mod.targets:
                    reasons.append("Direct FQN")
                matching_tags = (
                    abl_tags.intersection(mod.targets)
                    if abl_tags
                    else frozenset()
                )
                if matching_tags:
                    reasons.append(f"Tag: {list(matching_tags)}")
                reason_str = " & ".join(reasons) if reasons else "Scope Match"
                matched_scoped.append((sm, reason_str))

        tag_list_str = ", ".join(abl_tags) if abl_tags else "None"
        print(f"\n⚡ {abl_name}  [{abl_fqn}]")
        print(f"   Tags: {tag_list_str}")

        if matched_scoped:
            abilities_with_mods += 1
            print(f"   Applied Scoped Modifiers ({len(matched_scoped)}):")
            for sm, reason in matched_scoped:
                val_display = (
                    f"{sm.modifier.value:+.4f}"
                    if isinstance(sm.modifier.value, float)
                    else str(sm.modifier.value)
                )
                print(
                    f"     • [{sm.source_name}] ({sm.source_type}) -> {sm.modifier.stat}: {val_display}"
                )
                print(f"       Matched via: {reason}")
        else:
            print("   Applied Scoped Modifiers: None (Global modifiers only)")

    # 10. Print Global Modifiers
    print("\n" + "=" * 90)
    print(f"🌐 PLAYER-WIDE GLOBAL MODIFIERS ({len(global_modifiers)} Modifiers)")
    print("=" * 90)
    print("These modifiers apply unconditionally across all actions:")

    for sm in global_modifiers:
        val_display = (
            f"{sm.modifier.value:+.4f}"
            if isinstance(sm.modifier.value, float)
            else str(sm.modifier.value)
        )
        print(
            f" • [{sm.source_name}] ({sm.source_category} :: {sm.source_type}) -> {sm.modifier.stat}: {val_display}"
        )

    # 11. Final Summary Metrics
    print("\n" + "=" * 90)
    print("📊 LOADOUT BREAKDOWN SUMMARY")
    print("=" * 90)
    print(f"Total Blueprints Loaded   : {len(blueprints_raw)}")
    print(f"Active Abilities Evaluated: {len(sorted_active)}")
    print(f"Abilities With Bonuses    : {abilities_with_mods}")
    print(f"Total Scoped Modifiers    : {len(scoped_modifiers)}")
    print(f"Total Global Modifiers    : {len(global_modifiers)}")
    print("=" * 90)


if __name__ == "__main__":
    run_ability_modifier_matrix()