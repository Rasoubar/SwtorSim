"""Configuration loaders for character stats, rotations, skill-tree loadouts, and target dummy debuffs."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, NamedTuple
from src.swtorsim.abilities import AbilityBlueprint
from src.swtorsim.effects import ActiveEffect as ParsedEffect
from src.swtorsim.run_config import (
    TRAINING_DUMMY_ARMOR_DEBUFF_LABEL,
    RunConfig,
    get_training_dummy_armor_debuff_path,
    apply_weapon_ranges,
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
    env = getattr(config, "environment", "live")
    from src.swtorsim.settings import get_extractor_data_dir, set_data_environment
    set_data_environment(env)
    parsed_dir = str(get_extractor_data_dir(env) / "parsed")
    loadout_blueprints = load_complete_loadout(
        selected_fqns_from_config(config), parsed_dir=parsed_dir
    )
    debuff_module: dict[str, Any] = {}
    if config.training_dummy_armor_debuff:
        debuff_path = get_training_dummy_armor_debuff_path(env)
        debuff_module.update(load_training_dummy_armor_debuffs(debuff_path=debuff_path))
    stats_config = load_character_stats_from_json(
        config.class_name, config.stats_path, config.level
    )
    apply_weapon_ranges(stats_config["stats"], config)
    return SimulationInputs(
        rotation_config=load_rotation_from_json(config.rotation_path),
        stats_config=stats_config,
        loadout_blueprints=loadout_blueprints,
        debuff_module=debuff_module,
    )


_DUMMY_DEBUFF_ROUTING = (
    (
        "Sundered (Physical)",
        {"STAT_rtg_armor"},
        frozenset(("tag.abl.debuff.armor_reduced_stacks_by_tag", "tag.abl.debuff.armor_reduced", "tag.abl.dispel_type.physical")),
    ),
    (
        "Beat Down (Physical)",
        {"stat_cbt_damage_taken_scale_channel_melee_modifier_percentage"},
        frozenset(("tag.abl.debuff.melee_vulnerability", "tag.abl.dispel_type.physical")),
    ),
    (
        "Marked (Physical)",
        {"stat_cbt_damage_taken_scale_channel_ranged_modifier_percentage"},
        frozenset(("tag.abl.debuff.ranged_vulnerability", "tag.abl.dispel_type.physical")),
    ),
    (
        "Vulnerable (Force)",
        {"stat_cbt_damage_taken_scale_channel_force_modifier_percentage"},
        frozenset(("tag.abl.debuff.force_vulnerability", "tag.abl.dispel_type.force")),
    ),
    (
        "Susceptible (Tech)",
        {"stat_cbt_damage_taken_scale_channel_tech_modifier_percentage"},
        frozenset(("tag.abl.debuff.tech_vulnerability", "tag.abl.dispel_type.tech")),
    ),
    (
        "Assailable (Mental)",
        {
            "stat_cbt_damage_taken_scale_type_elemental_modifier_percentage",
            "stat_cbt_damage_taken_scale_type_internal_modifier_percentage",
        },
        frozenset(("tag.abl.debuff.elemental_and_internal_vulnerability", "tag.abl.dispel_type.mental")),
    ),
    (
        "Overwhelmed (Mental)",
        {"46", "STAT_cbt_damage_received_modifier_percentage"},
        frozenset(("tag.abl.debuff.aoe_vulnerability", "tag.abl.dispel_type.mental")),
    ),
)


def load_training_dummy_armor_debuff(debuff_path: str | None = None) -> ParsedEffect:
    """Loads the operation dummy armor debuff as a permanent target effect."""
    target_path = debuff_path or get_training_dummy_armor_debuff_path()
    data = load_json_file(target_path)
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
            f"'{target_path}' has no stat modifiers to apply."
        )
    parsed.name = TRAINING_DUMMY_ARMOR_DEBUFF_LABEL
    return parsed


def load_training_dummy_armor_debuffs(debuff_path: str | None = None) -> Dict[str, ParsedEffect]:
    """Decomposes the operation dummy armor debuff into the 7 canonical permanent raid debuffs."""
    base_effect = load_training_dummy_armor_debuff(debuff_path=debuff_path)
    debuffs: Dict[str, ParsedEffect] = {}
    for debuff_name, stat_keys, tags in _DUMMY_DEBUFF_ROUTING:
        matched_mods = [m for m in base_effect.modifiers if str(m.stat) in stat_keys]
        if not matched_mods:
            continue
        debuffs[debuff_name] = ParsedEffect(
            fqn=base_effect.fqn,
            name=debuff_name,
            number=base_effect.number,
            tags=tags,
            expires_at=None,
            duration=0.0,
            tick_interval=None,
            stacks=1,
            max_stacks=1,
            initial_stacks=1,
            scales_with_stacks=False,
            modifiers=matched_mods,
            branches=[],
            is_passive=True,
        )
    return debuffs


def selected_fqns_from_config(config: RunConfig) -> List[str]:
    """Baseline discipline abilities, the chosen skill-tree slots, then gear and relic FQNs."""
    spec_data = load_json_file(config.spec_path)
    baseline = spec_data.get("active_abilities", [])
    if not isinstance(baseline, list):
        raise ValueError(f"Discipline file '{config.spec_path}' active_abilities must be a list.")

    if getattr(config, "choices", None):
        choices = config.choices
    elif config.choices_path and config.choices_path.strip() not in ("", "."):
        choices = load_json_file(config.choices_path)
    else:
        choices = {}
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
    parsed_dir: str | None = None,
) -> Dict[str, AbilityBlueprint]:
    """Resolves ability, talent, gear, and relic FQNs into a unified blueprint dictionary."""
    if parsed_dir is None:
        from src.swtorsim.settings import get_extractor_data_dir
        base_parsed_path = (get_extractor_data_dir() / "parsed").resolve()
    else:
        base_parsed_path = Path(parsed_dir).resolve()
    blueprints: Dict[str, AbilityBlueprint] = {}

    for fqn in selected_fqns:
        if not fqn or not isinstance(fqn, str) or not fqn.strip():
            continue
        rel_path = fqn_to_relative_path(fqn)
        full_path = base_parsed_path / rel_path

        if not full_path.is_file():
            print(f"[WARN] Blueprint file not found for FQN '{fqn}': {full_path}")
            continue

        blueprint = AbilityBlueprint.from_file(full_path)
        blueprints[blueprint.fqn] = blueprint

    print(f"[OK] Loaded {len(blueprints)} total blueprints into unified loadout database.")
    return blueprints


# -----------------------------------------------------------------------------
# JSON Helpers & Config Loaders
# -----------------------------------------------------------------------------

def load_json_file(filepath: str) -> Any:
    """Helper to open, load, and validate JSON files safely."""
    if not filepath or not str(filepath).strip():
        raise FileNotFoundError("Configuration file path is empty.")
    if os.path.isdir(filepath):
        raise FileNotFoundError(f"Configuration file path is a directory: {filepath}")
    if not os.path.exists(filepath):
        p = Path(filepath)
        if not p.is_absolute():
            project_root = Path(__file__).resolve().parent.parent.parent
            candidate = project_root / p
            if candidate.is_file():
                filepath = str(candidate)

    if not os.path.exists(filepath):
        p = Path(filepath)
        if not p.is_absolute():
            parts = p.parts
            project_root = Path(__file__).resolve().parent.parent.parent
            for base_dir in (project_root, Path(".")):
                curr = base_dir
                matched = True
                for part in parts:
                    found = False
                    try:
                        for child in curr.iterdir():
                            if child.name.lower() == part.lower():
                                curr = child
                                found = True
                                break
                    except Exception:
                        pass
                    if not found:
                        matched = False
                        break
                if matched and curr.is_file():
                    filepath = str(curr)
                    break

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Configuration file not found at: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    if isinstance(raw_data, str):
        raw_data = json.loads(raw_data)

    return raw_data


FORCE_TECH_POWER_KEY = "Force-Tech Power"


def expand_force_tech_power(stats: dict) -> dict:
    """Copy the shared build key onto Force Power and Tech Power.

    One attack reads only one of those stats: force hits use Force Power,
    tech hits use Tech Power. The same number on both does not add twice.
    """
    if not isinstance(stats, dict) or FORCE_TECH_POWER_KEY not in stats:
        return stats
    value = stats.pop(FORCE_TECH_POWER_KEY)
    stats["Force Power"] = value
    stats["Tech Power"] = value
    return stats


def load_character_stats_from_json(class_name: str, filepath: str, level: int) -> dict:
    """Loads character stat profile JSON and formats it for the player."""
    stats_data = load_json_file(filepath)
    if isinstance(stats_data, dict):
        expand_force_tech_power(stats_data)
    return {
        "class_name": class_name,
        "level": level,
        "stats": stats_data
    }


def load_rotation_from_json(filepath: str) -> Any:
    """Loads rotation step sequences directly from a JSON file."""
    return load_json_file(filepath)