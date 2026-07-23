import json
import os
from typing import Dict, Any, Tuple

from src.swtorsim.abilities import Ability
from src.swtorsim.effects import ActiveEffect, ProcData


# -----------------------------------------------------------------------------
# JSON Helper
# -----------------------------------------------------------------------------

def _load_json_file(filepath: str) -> Any:
    """Helper to open, load, and validate JSON files safely."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Configuration file not found at: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # Safeguard against double-serialized JSON content
    if isinstance(raw_data, str):
        raw_data = json.loads(raw_data)

    return raw_data


def load_abilities_from_dict(raw_data: dict) -> Dict[str, Ability]:
    registry = {}
    for k, v in raw_data.items():
        ability = Ability.from_dict(v, k)
        registry[ability.name] = ability
    return registry


def load_passives_from_dict(raw_data: dict) -> Dict[str, ProcData]:
    registry = {}
    for k, v in raw_data.items():
        proc = ProcData.from_dict(v, k)
        registry[proc.name] = proc
    return registry


def load_permanent_buffs_from_dict(raw_data: dict) -> Dict[str, ActiveEffect]:
    registry = {}
    for k, v in raw_data.items():
        buff = ActiveEffect.from_dict(v, k)
        registry[buff.effect_name] = buff
    return registry
# -----------------------------------------------------------------------------
# JSON Loaders (Normalized Wrappers)
# -----------------------------------------------------------------------------

def load_abilities_from_json(filepath: str) -> Dict[str, Ability]:
    return load_abilities_from_dict(_load_json_file(filepath))


def load_passives_from_json(filepath: str) -> Dict[str, ProcData]:
    return load_passives_from_dict(_load_json_file(filepath))


def load_permanent_buffs_from_json(filepath: str) -> Dict[str, ActiveEffect]:
    return load_permanent_buffs_from_dict(_load_json_file(filepath))


def load_rotation_from_json(filepath: str) -> Any:
    return _load_json_file(filepath)


def load_character_stats_from_json(filepath: str) -> dict:
    return _load_json_file(filepath)


# -----------------------------------------------------------------------------
# Interactive Drafter CLI
# -----------------------------------------------------------------------------

def draft_choices(
        filepath: str,
        prompt_title: str,
        max_picks: int | None = None,
        check_levels: bool = False
) -> Tuple[dict, dict, dict]:

    """Interactively drafts items from a JSON file based on specific rules."""
    raw_data = _load_json_file(filepath)

    selected_raw_abilities = {}
    selected_raw_procs = {}
    selected_raw_buffs = {}
    picked_levels = set()
    picks = 0

    print(f"\n--- {prompt_title} ---")

    for item_name, item_data in raw_data.items():
        if max_picks and picks >= max_picks:
            print(f"🛑 Max limit of {max_picks} reached. Skipping remaining.")
            break

        to_add_list = item_data.get("To_add", [])
        if not to_add_list:
            continue

        first_data = list(to_add_list[0].values())[0]
        item_level = item_data.get("level")
        primary_type = first_data.get("item_type", "unknown").lower()

        if check_levels and item_level in picked_levels:
            continue

        while True:
            choice = input(f"Equip '{item_name}' ({primary_type})? [y/n]: ").strip().lower()
            if choice in ['y', 'yes']:
                for addition in to_add_list:
                    for inner_name, inner_config in addition.items():
                        inner_type = inner_config.get("item_type", "unknown").lower()
                        inner_config["name"] = inner_name

                        if inner_type == "ability":
                            selected_raw_abilities[inner_name] = inner_config
                        elif inner_type == "proc":
                            selected_raw_procs[inner_name] = inner_config
                        elif inner_type == "buff":
                            selected_raw_buffs[inner_name] = inner_config
                        else:
                            print(f"⚠️ Unknown item type '{inner_type}' in {inner_name}")

                if check_levels and item_level:
                    picked_levels.add(item_level)
                picks += 1
                print("  ✅ Added")
                break
            elif choice in ['n', 'no', '']:
                break

    return selected_raw_abilities, selected_raw_buffs, selected_raw_procs


def optional_choices(choice_dict: dict) -> Tuple[Dict[str, Ability], Dict[str, ActiveEffect], Dict[str, ProcData]]:
    """Drafts optional items and converts raw selections into custom objects."""
    relics = draft_choices(choice_dict["relics"], prompt_title="Relics", max_picks=2)
    tactical = draft_choices(choice_dict["tactical"], prompt_title="Tactical", max_picks=1)
    tree = draft_choices(choice_dict["tree"], prompt_title="Tree", check_levels=True)
    implants = draft_choices(choice_dict["implants"], prompt_title="Implant", max_picks=2)

    raw_abilities = relics[0] | tactical[0] | tree[0] | implants[0]
    raw_buffs = relics[1] | tactical[1] | tree[1] | implants[1]
    raw_procs = relics[2] | tactical[2] | tree[2] | implants[2]

    abilities = load_abilities_from_dict(raw_abilities)
    buffs = load_permanent_buffs_from_dict(raw_buffs)
    procs = load_passives_from_dict(raw_procs)

    return abilities, buffs, procs