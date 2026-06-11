from abilities import Ability
from entities import ProcData, ActiveBuff
import json
import os
from typing import Dict, Any


# Ensure you keep your existing Ability class configuration unchanged here!

def load_abilities_from_json(filepath: str) -> Dict[str, Ability]:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Configuration file not found at: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        raw_json_data = json.load(f)

    # Safeguard against double-serialized JSON content
    if isinstance(raw_json_data, str):
        print("⚠️ Warning: JSON parsed as string. Attempting secondary unpacking...")
        raw_json_data = json.loads(raw_json_data)

    # Structural check before we hit the parsing pipeline
    if not isinstance(raw_json_data, dict):
        raise TypeError(f"Expected JSON root to be a Dictionary/Object, got {type(raw_json_data)}")

    ability_registry: Dict[str, Ability] = {}

    # 🟢 FIXED: Actively instantiate the elements and save them to your dict
    for ability_name, config in raw_json_data.items():
        # Ensure the underlying class blueprint configuration dictionary knows its identifier name
        if "name" not in config:
            config["name"] = ability_name

        # Instantiate your custom OOP Ability instance layout
        ability_registry[ability_name] = Ability(config)

    return ability_registry


def load_passives_from_json(filepath: str) -> Dict[str, Any]:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Passives configuration not found at: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    if isinstance(raw_data, str):
        raw_data = json.loads(raw_data)

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
                required_tag=raw_data.get("required_tag"),
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
                    required_tag=block.get("required_tag"),
                    chance=block.get("chance", 1.0),
                    icd=block.get("icd", 0.0),
                    affected_by_cdr=block.get("affected_by_cdr", False),
                    conditions=block.get("conditions")
                )

    return proc_registry


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
def load_abilities_from_json1(raw_json_data):
    processed_abilities = {}

    for ability_name, config in raw_json_data.items():
        for action in config.get("actions", []):
            if "tags" not in action:
                action["tags"] = []
            action["tags"].append(f"ability:{ability_name}")

        processed_abilities[ability_name] = Ability(config)

    return processed_abilities