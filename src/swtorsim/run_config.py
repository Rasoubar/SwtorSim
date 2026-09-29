from dataclasses import dataclass, field
from typing import Any

DISCIPLINES_DIR = "data/extractor/disciplines"
BUILDS_DIR = "data/builds"
ROTATIONS_DIR = "data/rotations"
CHOICES_DIR = "data/choices"
GEAR_PATH = "data/extractor/gear_abilities_talents.json"
RELICS_PATH = "data/extractor/relics.json"
TRAINING_DUMMY_ARMOR_DEBUFF_PATH = (
    "data/extractor/parsed/abl/npc/ability/utility/training_dummy_armor_debuff.json"
)
TRAINING_DUMMY_ARMOR_DEBUFF_LABEL = "Training Dummy Armor Debuff"

TACTICAL_PREFIX = "abl.itm.tactical."
LEGENDARY_PREFIX = "abl.itm.legendary."
RELIC_PREFIX = "abl.itm.relic."

CLASS_FQN_KEYWORDS = {
    "assassin": ["sin_shad", "inq_con"],
    "shadow": ["sin_shad", "inq_con"],
    "sorcerer": ["sorc_sage", "inq_con"],
    "sage": ["sorc_sage", "inq_con"],
    "juggernaut": ["jug_guar", "jug_gua", "war_kni"],
    "guardian": ["jug_guar", "jug_gua", "war_kni"],
    "marauder": ["mar_sen", "war_kni"],
    "sentinel": ["mar_sen", "war_kni"],
    "operative": ["op_sco", "ope_sco", "age_smu"],
    "scoundrel": ["op_sco", "ope_sco", "age_smu"],
    "sniper": ["sni_gun", "age_smu"],
    "gunslinger": ["sni_gun", "age_smu"],
    "mercenary": ["mer_com", "merc_com", "bh_tr", "bou_tro"],
    "commando": ["mer_com", "merc_com", "bh_tr", "bou_tro"],
    "powertech": ["pow_vang", "powertech", "bh_tr", "bou_tro"],
    "specialist": ["pow_vang", "powertech", "bh_tr", "bou_tro"],
    "vanguard": ["pow_vang", "powertech", "bh_tr", "bou_tro"],
}

_REQUIRED_CONFIG_KEYS = (
    "spec_path",
    "stats_path",
    "rotation_path",
    "choices_path",
    "tactical_fqn",
    "legendary_fqns",
)


@dataclass
class RunConfig:
    """Selections and run settings passed from the CLI or a run config file into the loaders."""

    spec_path: str
    class_name: str
    spec: str
    stats_path: str
    rotation_path: str
    choices_path: str
    tactical_fqn: str
    legendary_fqns: list[str]
    relic_fqns: list[str] = field(default_factory=list)
    mode: str = "TEST"
    iterations: int = 1000
    duration: int = 1000
    dummy_hp: int = 10_000_000
    training_dummy_armor_debuff: bool = False
    level: int = 85
    seed: int = 42


def load_run_config(path: str) -> RunConfig:
    """Loads a run config JSON, fills class and spec from the discipline file, and validates it."""
    raw = _load_json(path)
    if not isinstance(raw, dict):
        raise ValueError(f"Run config '{path}' must be a JSON object.")

    missing = [key for key in _REQUIRED_CONFIG_KEYS if key not in raw]
    if missing:
        raise ValueError(
            f"Run config '{path}' is missing: {', '.join(missing)}."
        )

    spec_path = _require_config_str(raw, "spec_path")
    spec_data = _load_json(spec_path)
    class_name, spec = discipline_names(spec_data, spec_path)

    config = RunConfig(
        spec_path=spec_path,
        class_name=class_name,
        spec=spec,
        stats_path=_require_config_str(raw, "stats_path"),
        rotation_path=_require_config_str(raw, "rotation_path"),
        choices_path=_require_config_str(raw, "choices_path"),
        tactical_fqn=_require_config_str(raw, "tactical_fqn"),
        legendary_fqns=_require_config_str_list(raw, "legendary_fqns"),
        relic_fqns=_optional_config_str_list(raw, "relic_fqns"),
        mode=_optional_config_str(raw, "mode", "TEST"),
        iterations=_optional_config_int(raw, "iterations", 1000),
        duration=_optional_config_int(raw, "duration", 1000),
        dummy_hp=_optional_config_int(raw, "dummy_hp", 10_000_000),
        training_dummy_armor_debuff=_optional_config_bool(
            raw, "training_dummy_armor_debuff", False
        ),
        level=_optional_config_int(raw, "level", 85),
        seed=_optional_config_int(raw, "seed", 42),
    )
    validate_run_config(config)
    return config


def validate_run_config(
    config: RunConfig,
    gear_path: str = GEAR_PATH,
    relics_path: str = RELICS_PATH,
) -> None:
    """Checks paths, skill-tree choices, class-filtered gear, and unique legendaries and relics."""
    errors: list[str] = []

    for label, path in (
        ("spec_path", config.spec_path),
        ("stats_path", config.stats_path),
        ("rotation_path", config.rotation_path),
        ("choices_path", config.choices_path),
        ("gear catalog", gear_path),
        ("relic catalog", relics_path),
    ):
        if not isinstance(path, str) or not path.strip():
            errors.append(f"{label} must be a non-empty path.")
            continue
        if not _is_file(path):
            errors.append(f"{label} file not found: {path}")

    if config.mode not in ("TEST", "BATCH"):
        errors.append("mode must be 'TEST' or 'BATCH'.")
    for label, value in (
        ("iterations", config.iterations),
        ("duration", config.duration),
        ("dummy_hp", config.dummy_hp),
        ("level", config.level),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            errors.append(f"{label} must be a positive integer.")
    if isinstance(config.seed, bool) or not isinstance(config.seed, int):
        errors.append("seed must be an integer.")
    if not isinstance(config.training_dummy_armor_debuff, bool):
        errors.append("training_dummy_armor_debuff must be true or false.")
    elif config.training_dummy_armor_debuff and not _is_file(TRAINING_DUMMY_ARMOR_DEBUFF_PATH):
        errors.append(
            "Training Dummy Armor Debuff file not found: "
            + TRAINING_DUMMY_ARMOR_DEBUFF_PATH
        )

    if errors:
        _raise_errors(errors)

    spec_data = _load_json(config.spec_path)
    class_name, spec = discipline_names(spec_data, config.spec_path)
    if config.class_name != class_name:
        errors.append(
            f"class_name '{config.class_name}' does not match discipline tab_name '{class_name}'."
        )
    if config.spec != spec:
        errors.append(
            f"spec '{config.spec}' does not match discipline package_name '{spec}'."
        )

    try:
        choices = _load_json(config.choices_path)
        skill_tree = spec_data.get("skill_tree", {})
        resolve_skill_tree_fqns(skill_tree, choices)
    except ValueError as exc:
        errors.extend(str(exc).splitlines())

    gear_data = _load_json(gear_path)
    relic_catalog = _load_json(relics_path)
    if not isinstance(gear_data, dict):
        errors.append(f"Gear catalog '{gear_path}' must be a JSON object.")
        gear_data = {}
    if not isinstance(relic_catalog, list):
        errors.append(f"Relic catalog '{relics_path}' must be a JSON array.")
        relic_catalog = []

    errors.extend(_validate_gear_fqn(
        config.tactical_fqn,
        "tactical_fqn",
        TACTICAL_PREFIX,
        "tactical",
        config.class_name,
        gear_data,
    ))
    errors.extend(_validate_unique_fqns(
        config.legendary_fqns,
        "legendary_fqns",
        expected_count=2,
        prefix=LEGENDARY_PREFIX,
        kind="legendary implant",
        class_name=config.class_name,
        gear_data=gear_data,
    ))
    errors.extend(_validate_relics(config.relic_fqns, relic_catalog))

    if errors:
        _raise_errors(errors)


def discipline_names(spec_data: Any, spec_path: str) -> tuple[str, str]:
    """Returns (class_name, spec) from a discipline document."""
    if not isinstance(spec_data, dict):
        raise ValueError(f"Discipline file '{spec_path}' must be a JSON object.")

    class_name = spec_data.get("tab_name")
    spec = spec_data.get("package_name")
    if not isinstance(class_name, str) or not class_name.strip():
        raise ValueError(f"Discipline file '{spec_path}' is missing tab_name.")
    if not isinstance(spec, str) or not spec.strip():
        raise ValueError(f"Discipline file '{spec_path}' is missing package_name.")
    return class_name, spec


def resolve_skill_tree_fqns(skill_tree: Any, choices: Any) -> list[str]:
    """Maps each skill-tree level to the FQNs in the chosen 1, 2, or 3 slot."""
    if not isinstance(skill_tree, dict):
        raise ValueError("Discipline skill_tree must be a JSON object.")
    if not isinstance(choices, dict):
        raise ValueError(
            "Choices file must be a JSON object mapping skill tree levels to 1, 2, or 3."
        )

    tree = {str(level): slots for level, slots in skill_tree.items()}
    chosen = {str(level): slot for level, slot in choices.items()}
    errors: list[str] = []

    missing = sorted(set(tree) - set(chosen), key=_level_sort_key)
    extra = sorted(set(chosen) - set(tree), key=_level_sort_key)
    if missing:
        errors.append("Choices are missing skill tree levels: " + ", ".join(missing))
    if extra:
        errors.append(
            "Choices include levels that are not in the skill tree: " + ", ".join(extra)
        )

    selected: list[str] = []
    for level in sorted(set(tree) & set(chosen), key=_level_sort_key):
        try:
            slot = normalize_choice_slot(chosen[level])
        except ValueError as exc:
            errors.append(f"Level {level}: {exc}")
            continue

        slots = tree[level]
        if not isinstance(slots, dict):
            errors.append(f"Level {level} skill tree entry must be an object.")
            continue

        slot_map = {str(key): value for key, value in slots.items()}
        fqns = slot_map.get(slot)
        if not isinstance(fqns, list):
            errors.append(f"Level {level} has no option {slot}.")
            continue

        for fqn in fqns:
            if not isinstance(fqn, str) or not fqn.strip():
                errors.append(f"Level {level} option {slot} contains an invalid FQN.")
                continue
            selected.append(fqn)

    if errors:
        raise ValueError("\n".join(errors))
    return selected


def normalize_choice_slot(value: Any) -> str:
    """Accepts 1, 2, or 3 as an int or a numeric string."""
    if isinstance(value, bool):
        raise ValueError("choice must be 1, 2, or 3.")
    if isinstance(value, int) and value in (1, 2, 3):
        return str(value)
    if isinstance(value, str) and value.strip() in {"1", "2", "3"}:
        return value.strip()
    raise ValueError("choice must be 1, 2, or 3.")


def filter_gear_for_class(
    gear_data: dict[str, str],
    prefix: str,
    class_name: str,
) -> dict[str, str]:
    """Keeps gear whose FQN has the given prefix and matches the class or is generic."""
    keywords = CLASS_FQN_KEYWORDS.get(class_name.lower())
    if keywords is None:
        raise ValueError(f"No gear filter keywords for class '{class_name}'.")

    filtered: dict[str, str] = {}
    for name, fqn in gear_data.items():
        if not isinstance(fqn, str) or not fqn.startswith(prefix):
            continue
        if "generic" in fqn or any(keyword in fqn for keyword in keywords):
            filtered[str(name)] = fqn
    return filtered


def relic_menu_label(fqn: str) -> str:
    """Shortens a relic FQN for menus by dropping the shared prefix."""
    if fqn.startswith(RELIC_PREFIX):
        return fqn[len(RELIC_PREFIX):]
    return fqn


def _validate_gear_fqn(
    fqn: Any,
    field_name: str,
    prefix: str,
    kind: str,
    class_name: str,
    gear_data: dict,
) -> list[str]:
    if not isinstance(fqn, str) or not fqn.strip():
        return [f"{field_name} must be a non-empty FQN."]

    known = {
        value
        for value in gear_data.values()
        if isinstance(value, str) and value.startswith(prefix)
    }
    if fqn not in known:
        return [f"{field_name} '{fqn}' is not a known {kind}."]

    try:
        allowed = set(filter_gear_for_class(gear_data, prefix, class_name).values())
    except ValueError as exc:
        return [str(exc)]
    if fqn not in allowed:
        return [f"{field_name} '{fqn}' is not available for class '{class_name}'."]
    return []


def _validate_unique_fqns(
    fqns: Any,
    field_name: str,
    expected_count: int,
    prefix: str,
    kind: str,
    class_name: str,
    gear_data: dict,
) -> list[str]:
    if (
        not isinstance(fqns, list)
        or any(not isinstance(fqn, str) or not fqn.strip() for fqn in fqns)
    ):
        return [f"{field_name} must be a list of FQNs."]
    if len(fqns) != expected_count:
        return [f"{field_name} must contain exactly {expected_count} FQNs."]

    errors: list[str] = []
    if len(set(fqns)) != len(fqns):
        errors.append(f"{field_name} must be unique.")
    for fqn in dict.fromkeys(fqns):
        errors.extend(_validate_gear_fqn(
            fqn, field_name, prefix, kind, class_name, gear_data
        ))
    return errors


def _validate_relics(fqns: Any, relic_catalog: list) -> list[str]:
    if (
        not isinstance(fqns, list)
        or any(not isinstance(fqn, str) or not fqn.strip() for fqn in fqns)
    ):
        return ["relic_fqns must be a list of FQNs."]
    if len(fqns) > 2:
        return ["relic_fqns must contain 0, 1, or 2 FQNs."]

    errors: list[str] = []
    if len(set(fqns)) != len(fqns):
        errors.append("relic_fqns must be unique.")

    known = {fqn for fqn in relic_catalog if isinstance(fqn, str)}
    for fqn in dict.fromkeys(fqns):
        if fqn not in known:
            errors.append(f"relic_fqns entry '{fqn}' is not a known relic.")
    return errors


def _require_config_str(raw: dict, key: str) -> str:
    value = raw[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{key}' must be a non-empty string.")
    return value


def _optional_config_str(raw: dict, key: str, default: str) -> str:
    if key not in raw:
        return default
    value = raw[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{key}' must be a non-empty string.")
    return value


def _require_config_str_list(raw: dict, key: str) -> list[str]:
    value = raw[key]
    if not isinstance(value, list) or any(_blank_string(item) for item in value):
        raise ValueError(f"'{key}' must be a list of non-empty strings.")
    return list(value)


def _blank_string(value: Any) -> bool:
    return not isinstance(value, str) or not value.strip()


def _optional_config_str_list(raw: dict, key: str) -> list[str]:
    if key not in raw:
        return []
    return _require_config_str_list(raw, key)


def _optional_config_bool(raw: dict, key: str, default: bool) -> bool:
    if key not in raw:
        return default
    value = raw[key]
    if not isinstance(value, bool):
        raise ValueError(f"'{key}' must be true or false.")
    return value


def _optional_config_int(raw: dict, key: str, default: int) -> int:
    if key not in raw:
        return default
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"'{key}' must be an integer.")
    return value


def _level_sort_key(level: str) -> tuple[int, int | str]:
    if level.isdigit():
        return (0, int(level))
    return (1, level)


def _is_file(path: str) -> bool:
    from pathlib import Path
    return Path(path).is_file()


def _load_json(path: str) -> Any:
    from src.swtorsim.config_load import load_json_file
    return load_json_file(path)


def _raise_errors(errors: list[str]) -> None:
    raise ValueError("Invalid run config:\n" + "\n".join(f"- {error}" for error in errors))
