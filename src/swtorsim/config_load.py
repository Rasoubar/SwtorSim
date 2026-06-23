from src.swtorsim.abilities import Ability
from src.swtorsim.entities import ProcData, ActiveBuff
import json
import os
from typing import Dict, Any


# Ensure you keep your existing Ability class configuration unchanged here!
def load_abilities_from_dict(raw_data):
    ability_registry: Dict[str, Ability] = {}
    for ability_name, config in raw_data.items():
        # Ensure the underlying class blueprint configuration dictionary knows its identifier name
        if "name" not in config:
            config["name"] = ability_name

        # Instantiate your custom OOP Ability instance layout
        ability_registry[ability_name] = Ability(config)

    return ability_registry

def load_abilities_from_json(filepath: str) -> Dict[str, Ability]:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Configuration file not found at: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        raw_json_data = json.load(f)

    # Safeguard against double-serialized JSON content
    if isinstance(raw_json_data, str):
        print("SAFEGUARD")
        print("⚠️ Warning: JSON parsed as string. Attempting secondary unpacking...")
        raw_json_data = json.loads(raw_json_data)

    # Structural check before we hit the parsing pipeline
    if not isinstance(raw_json_data, dict):
        raise TypeError(f"Expected JSON root to be a Dictionary/Object, got {type(raw_json_data)}")

    return load_abilities_from_dict(raw_json_data)


def load_passives_from_dict(raw_data):
    proc_registry = {}

    # Case A: If your JSON file matches a grouped dictionary mapping pattern:
    if isinstance(raw_data, dict):
        # Check if it's a single proc wrapped at root, or a multi-proc collection
        if "proc_name" in raw_data:
            # Single flat proc file (like your current BaseAssassinProcs.json layout)
            name = raw_data["proc_name"]
            proc_registry[name] = ProcData(
                name=name,
                trigger=raw_data.get("trigger", "hit"),
                actions=raw_data.get("actions", []),
                required_tags=raw_data.get("required_tags"),
                chance=raw_data.get("chance", 1.0),
                icd=raw_data.get("icd", 0.0),
                affected_by_cdr=raw_data.get("affected_by_cdr", False),
                conditions=raw_data.get("conditions")
            )
        else:
            # Multi-proc database map collection layout
            for key, block in raw_data.items():
                name = block.get("proc_name", key)
                proc_registry[name] = ProcData(
                    name=name,
                    trigger=block.get("trigger", "hit"),
                    actions=block.get("actions", []),
                    required_tags=block.get("required_tags"),
                    chance=block.get("chance", 1.0),
                    icd=block.get("icd", 0.0),
                    affected_by_cdr=block.get("affected_by_cdr", False),
                    conditions=block.get("conditions")
                )

    return proc_registry


def load_passives_from_json(filepath: str) -> Dict[str, Any]:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Passives configuration not found at: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
       raw_data = json.load(f)
    if isinstance(raw_data, str):
        raw_data = json.loads(raw_data)

    return load_passives_from_dict(raw_data)


def load_permanent_buffs_from_dict(raw_data):
    buff_registry: Dict[str, ActiveBuff] = {}

    for buff_key, block in raw_data.items():
        # 🟢 AUTO GENERATION: Fallback to the dictionary key if effect_name is null/empty
        effect_name = block.get("effect_name") or buff_key

        # 🟢 PERMANENT INJECTION: Duration is omitted entirely, forcing math infinity
        expires_at = float('inf')

        # Instantiate matching the positional order of your ActiveBuff constructor:
        # (id_num, effect_name, stat_name, value, expires_at, source_ability, ...)
        buff_registry[effect_name] = ActiveBuff(
            id_num=block.get("id"),
            effect_name=effect_name,
            stat_name=None,  # Note: Leave None or pass string if you have an ID-to-Name map lookup
            value=block.get("value"),
            expires_at=expires_at,  # Set to math infinity
            source_ability=buff_key,  # Uses the top-level string key as source descriptive context
            required_tags=block.get("required_tags", None),
            charges=1,  # Default baseline parameters for status indicators
            consumable_charges=None,
            max_charges=1,
            target_hp_threshold=block.get("target_hp_threshold")
        )

    return buff_registry

def load_permanent_buffs_from_json(filepath: str) -> Dict[str, ActiveBuff]:
    """
    Loads raw permanent buff configurations out of JSON files and maps them
    strictly to the positional slots layout of the ActiveBuff class container.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Permanent buff blueprint not found at: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    if isinstance(raw_data, str):
        raw_data = json.loads(raw_data)

    return load_permanent_buffs_from_dict(raw_data)


def draft_choices(filepath, prompt_title, max_picks=None, check_levels=False):
    """Interactively drafts items from a JSON file based on specific rules."""
    with open(filepath, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    selected_raw_abilities = {}
    selected_raw_procs = {}
    selected_raw_buffs = {}
    picked_levels = set()
    picks = 0
    print(f"\n--- {prompt_title} ---")

    for item_name, item_data in raw_data.items():
        # Rule 1: Max Picks (for Relics/Tacticals)
        if max_picks and picks >= max_picks:
            print(f"🛑 Max limit of {max_picks} reached. Skipping remaining.")
            break

        # Safely grab the "To_add" array
        to_add_list = item_data.get("To_add", [])
        if not to_add_list:
            continue

        # Peek at the FIRST item in the array to get level and type for the prompt
        first_key = list(to_add_list[0].keys())[0]
        first_data = to_add_list[0][first_key]

        item_level = item_data.get("level")
        print(item_level)
        primary_type = first_data.get("item_type", "unknown").lower()

        # Rule 2: Level/Row restrictions (for Skill Tree)
        if check_levels and item_level in picked_levels:
            # Silently skip if they already picked a talent for this level
            continue

        # The Prompt
        while True:
            choice = input(f"Equip '{item_name}' ({primary_type})? [y/n]: ").strip().lower()
            if choice in ['y', 'yes']:
                # Iterate through EVERYTHING inside the To_add array and route it
                for addition in to_add_list:
                    for inner_name, inner_config in addition.items():
                        inner_type = inner_config.get("item_type", "unknown").lower()
                        inner_config["name"] = inner_name  # Inject name for the builder

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

def optional_choices(choice_dict):
    print("choices")
    relics = draft_choices(choice_dict["relics"], prompt_title="Relics", max_picks=2)
    tactical = draft_choices(choice_dict["tactical"], prompt_title="Tactical", max_picks=1)
    tree = draft_choices(choice_dict["tree"], prompt_title="Tree", check_levels=True)
    implants = draft_choices(choice_dict["implants"], prompt_title="Implant", max_picks=2)
    raw_abilities = relics[0] | tactical[0] | tree[0] |implants[0]
    raw_buffs = relics[1] | tactical[1] | tree[1] | implants[1]
    raw_procs = relics[2] | tactical[2] | tree[2] | implants[2]

    abilities = load_abilities_from_dict(raw_abilities)
    buffs = load_permanent_buffs_from_dict(raw_buffs)
    procs = load_passives_from_dict(raw_procs)

    return abilities,buffs,procs

def load_rotation_from_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)