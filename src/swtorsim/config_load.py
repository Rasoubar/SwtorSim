import json
import os
from typing import Dict, Any, Tuple

from src.swtorsim.abilities import Ability
from src.swtorsim.effects import ActiveEffect, ProcData


# -----------------------------------------------------------------------------
# JSON Helper
# -----------------------------------------------------------------------------

def load_json_file(filepath: str) -> Any:
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
    """Converts a dictionary of raw ability configs into Ability instances."""
    registry = {}
    for k, v in raw_data.items():
        ability = Ability.from_dict(v, k)
        registry[ability.name] = ability
    return registry


def load_procs_from_dict(raw_data: dict) -> Dict[str, ProcData]:
    """Converts a dictionary of raw proc configs into ProcData instances."""
    registry = {}
    for k, v in raw_data.items():
        proc = ProcData.from_dict(v, k)
        registry[proc.name] = proc
    return registry


def load_permanent_effects_from_dict(raw_data: dict) -> Dict[str, ActiveEffect]:
    """Converts a dictionary of raw effects configs into ActiveEffect instances."""
    registry = {}
    for k, v in raw_data.items():
        buff = ActiveEffect.from_dict(v, k)
        registry[buff.effect_name] = buff
    return registry

# -----------------------------------------------------------------------------
# JSON Loaders (Normalized Wrappers)
# -----------------------------------------------------------------------------

def load_abilities_from_json(filepath: str) -> Dict[str, Ability]:
    """Loads ability definitions from a JSON file into Ability instances."""
    raw_data = load_json_file(filepath)
    return load_abilities_from_dict(raw_data)


def load_procs_from_json(filepath: str) -> Dict[str, ProcData]:
    """Loads proc definitions from a JSON file into ProcData instances."""
    raw_data = load_json_file(filepath)
    return load_procs_from_dict(raw_data)


def load_permanent_effects_from_json(filepath: str) -> Dict[str, ActiveEffect]:
    """Loads permanent effect definitions from a JSON file into ActiveEffect instances."""
    raw_data = load_json_file(filepath)
    return load_permanent_effects_from_dict(raw_data)

def load_character_stats_from_json(class_name: str, filepath: str) -> dict:
    """Loads character stat profile JSON and formats it for the player."""
    stats_data = load_json_file(filepath)
    return {
        "class_name": class_name,
        "stats": stats_data
    }


def load_rotation_from_json(filepath: str) -> Any:
    """Loads rotation step sequences directly from a JSON file."""
    return load_json_file(filepath)



# -----------------------------------------------------------------------------
# Interactive Drafter CLI
# -----------------------------------------------------------------------------


def build_complete_loadout(
        base_dir: str,
        raw_opt_abilities: dict,
        raw_opt_buffs: dict,
        raw_opt_procs: dict
) -> Tuple[Dict[str, Ability], Dict[str, ProcData], Dict[str, ActiveEffect]]:
    """Loads base databases and merges optional drafted dicts into active registries."""
    abilities_db = load_abilities_from_json(f"{base_dir}/Abilities.json")
    effects_db = load_permanent_effects_from_json(f"{base_dir}/PermanentBuffs.json")
    procs_db = load_procs_from_json(f"{base_dir}/BaseProcs.json")

    # Convert drafted raw dicts and update base databases
    abilities_db.update(load_abilities_from_dict(raw_opt_abilities))
    effects_db.update(load_permanent_effects_from_dict(raw_opt_buffs))
    procs_db.update(load_procs_from_dict(raw_opt_procs))

    return abilities_db, procs_db, effects_db