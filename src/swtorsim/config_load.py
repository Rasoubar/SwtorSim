import json
import os
from typing import Dict, Any, Tuple
from pathlib import Path
from typing import Dict, List
from src.swtorsim.abilities import AbilityBlueprint
from src.swtorsim.abilities import Ability
from src.swtorsim.effects import ActiveEffect, ProcData



def fqn_to_relative_path(fqn: str) -> Path:
    """Converts dot-notation FQN to a relative filesystem path."""
    return Path(*fqn.strip().split(".")).with_suffix(".json")


def load_complete_loadout(
    selected_fqns: List[str],
    selected_relic_paths: List[str],
    parsed_dir: str = "data/extractor/parsed"
) -> Dict[str, AbilityBlueprint]:
    """Resolves and loads all ability, talent, gear, and relic blueprints into a unified dictionary."""
    base_parsed_path = Path(parsed_dir).resolve()
    blueprints: Dict[str, AbilityBlueprint] = {}

    # 1. Load abilities, passives, tacticals, and implants by FQN
    for fqn in selected_fqns:
        rel_path = fqn_to_relative_path(fqn)
        full_path = base_parsed_path / rel_path

        if not full_path.is_file():
            print(f"⚠️ [WARN] Blueprint file not found for FQN '{fqn}': {full_path}")
            continue

        blueprint = AbilityBlueprint.from_file(full_path)
        blueprints[blueprint.fqn] = blueprint

    # 2. Load relics directly from chosen paths
    for relic_path_str in selected_relic_paths:
        relic_path = Path(relic_path_str).resolve()
        if not relic_path.is_file():
            print(f"⚠️ [WARN] Relic file not found: {relic_path}")
            continue

        relic_blueprint = AbilityBlueprint.from_file(relic_path)
        blueprints[relic_blueprint.fqn] = relic_blueprint

    print(f"✅ Loaded {len(blueprints)} total blueprints into unified loadout database.")
    return blueprints
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

