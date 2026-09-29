import json
import os
from pathlib import Path
from typing import Any, Dict, List, NamedTuple
from src.swtorsim.abilities import AbilityBlueprint
from src.swtorsim.effects import ActiveEffect
from src.swtorsim.effects_temp import ActiveEffect as ParsedEffect
from src.swtorsim.run_config import (
    TRAINING_DUMMY_ARMOR_DEBUFF_LABEL,
    TRAINING_DUMMY_ARMOR_DEBUFF_PATH,
    RunConfig,
    resolve_skill_tree_fqns,
    validate_run_config,
)


def fqn_to_relative_path(fqn: str) -> Path:
    """Converts dot-notation FQN to a relative filesystem path."""
    return Path(*fqn.strip().split(".")).with_suffix(".json")


class SimulationInputs(NamedTuple):
    """Objects already expected by Tester."""

    rotation_config: Any
    stats_config: dict
    loadout_blueprints: Dict[str, AbilityBlueprint]
    debuff_module: Dict[str, Any]


def load_from_run_config(config: RunConfig) -> SimulationInputs:
    """Resolves a run config into rotation, stats, blueprints, and debuffs."""
    validate_run_config(config)
    loadout_blueprints = load_complete_loadout(selected_fqns_from_config(config))
    debuff_module: dict[str, Any] = {}
    if config.training_dummy_armor_debuff:
        debuff = load_training_dummy_armor_debuff()
        debuff_module[debuff.name] = debuff
    return SimulationInputs(
        rotation_config=load_rotation_from_json(config.rotation_path),
        stats_config=load_character_stats_from_json(config.class_name, config.stats_path),
        loadout_blueprints=loadout_blueprints,
        debuff_module=debuff_module,
    )


def load_training_dummy_armor_debuff() -> ParsedEffect:
    """Loads the operation dummy armor debuff as a permanent target effect."""
    data = load_json_file(TRAINING_DUMMY_ARMOR_DEBUFF_PATH)
    fqn = data.get("fqn") or ""
    parsed = None
    for node in data.get("effects") or []:
        effect = ParsedEffect.from_effect_node(
            fqn, TRAINING_DUMMY_ARMOR_DEBUFF_LABEL, node
        )
        if effect.modifiers:
            parsed = effect
            break
    if parsed is None:
        raise ValueError(
            f"'{TRAINING_DUMMY_ARMOR_DEBUFF_PATH}' has no stat modifiers to apply."
        )
    parsed.name = TRAINING_DUMMY_ARMOR_DEBUFF_LABEL
    return parsed


def selected_fqns_from_config(config: RunConfig) -> List[str]:
    """Baseline discipline abilities, the chosen skill-tree slots, then gear and relic FQNs."""
    spec_data = load_json_file(config.spec_path)
    baseline = spec_data.get("active_abilities", [])
    if not isinstance(baseline, list):
        raise ValueError(f"Discipline file '{config.spec_path}' active_abilities must be a list.")

    choices = load_json_file(config.choices_path)
    tree_fqns = resolve_skill_tree_fqns(spec_data.get("skill_tree", {}), choices)
    return [
        *baseline,
        *tree_fqns,
        config.tactical_fqn,
        *config.legendary_fqns,
        *config.relic_fqns,
    ]


def load_complete_loadout(
    selected_fqns: List[str],
    parsed_dir: str = "data/extractor/parsed",
) -> Dict[str, AbilityBlueprint]:
    """Resolves ability, talent, gear, and relic FQNs into a unified blueprint dictionary."""
    base_parsed_path = Path(parsed_dir).resolve()
    blueprints: Dict[str, AbilityBlueprint] = {}

    for fqn in selected_fqns:
        rel_path = fqn_to_relative_path(fqn)
        full_path = base_parsed_path / rel_path

        if not full_path.is_file():
            print(f"⚠️ [WARN] Blueprint file not found for FQN '{fqn}': {full_path}")
            continue

        blueprint = AbilityBlueprint.from_file(full_path)
        blueprints[blueprint.fqn] = blueprint

    print(f"✅ Loaded {len(blueprints)} total blueprints into unified loadout database.")
    return blueprints


# -----------------------------------------------------------------------------
# JSON Helpers & Config Loaders
# -----------------------------------------------------------------------------

def load_json_file(filepath: str) -> Any:
    """Helper to open, load, and validate JSON files safely."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Configuration file not found at: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    if isinstance(raw_data, str):
        raw_data = json.loads(raw_data)

    return raw_data


def load_permanent_effects_from_dict(raw_data: dict) -> Dict[str, ActiveEffect]:
    """Converts raw debuff configs into ActiveEffect instances."""
    registry = {}
    for k, v in raw_data.items():
        buff = ActiveEffect.from_dict(v, k)
        registry[buff.effect_name] = buff
    return registry


def load_permanent_effects_from_json(filepath: str) -> Dict[str, ActiveEffect]:
    """Loads permanent debuff module definitions from JSON into ActiveEffect instances."""
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