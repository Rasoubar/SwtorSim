"""Load and validate the diminishing-returns run config."""

from dataclasses import dataclass, replace

from src.swtorsim.config_load import load_json_file
from src.swtorsim.run_config import RunConfig, discipline_names, validate_run_config

RELIC_STATS = ("Mastery", "Power", "Critical Rating")
JITTER_STATS = ("Mastery", "Power")

VARIANT_ORDER = ("none", "mastery_power", "mastery_crit", "power_crit")
VARIANT_STATS = {
    "none": (),
    "mastery_power": ("Mastery", "Power"),
    "mastery_crit": ("Mastery", "Critical Rating"),
    "power_crit": ("Power", "Critical Rating"),
}
PAIR_LABELS = {
    "mastery_power": "Mastery & Power",
    "mastery_crit": "Mastery & Crit",
    "power_crit": "Power & Crit",
}
PAIR_COLORS = {
    "mastery_power": "blue",
    "mastery_crit": "orange",
    "power_crit": "red",
}

_SPEC_KEYS = (
    "name",
    "spec_path",
    "stats_path",
    "rotation_path",
    "choices_path",
    "tactical_fqn",
    "legendary_fqns",
    "relic_fqns",
)


@dataclass
class SpecEntry:
    """One discipline to sweep, plus the relic pair used for its derivative plot."""

    name: str
    run_config: RunConfig
    pair_key: str


@dataclass
class DrConfig:
    """General settings and the specs to run."""

    game_version: str
    author: str
    gear_label: str
    expected_mastery_multiplier: float
    sweep_stat: str
    sweep_min: float
    sweep_max: float
    jitter_mastery: float
    jitter_power: float
    samples_per_variant: int
    level: int
    relics: dict[str, str]
    seed: int
    specs: list[SpecEntry]

    def variant_relics(self) -> dict[str, list[str]]:
        """The four relic setups, in run order. Values are relic FQNs."""
        relics = self.relics
        return {
            key: [relics[stat] for stat in VARIANT_STATS[key]]
            for key in VARIANT_ORDER
        }


def load_dr_config(path: str) -> DrConfig:
    """Loads a dr_config.json and validates every spec against the sim's run config rules."""
    raw = load_json_file(path)
    if not isinstance(raw, dict):
        raise ValueError(f"DR config '{path}' must be a JSON object.")

    errors: list[str] = []
    game_version = _require_str(raw, "game_version", errors)
    author = _require_str(raw, "author", errors)
    gear_label = _require_str(raw, "gear_label", errors)
    level = _require_positive_int(raw, "level", errors)
    duration = _require_positive_int(raw, "duration", errors)
    dummy_hp = _require_positive_int(raw, "dummy_hp", errors)
    training_dummy = _require_bool(raw, "training_dummy_armor_debuff", errors)
    stem_matching = _require_bool(raw, "enable_stem_matching", errors)
    seed = _require_int(raw, "seed", errors)
    mastery_multiplier = _require_positive_float(raw, "expected_mastery_multiplier", errors)
    sweep_stat, sweep_min, sweep_max = _require_sweep(raw.get("sweep"), errors)
    jitter_mastery, jitter_power = _require_jitter(raw.get("jitter"), errors)
    samples = _require_positive_int(raw, "samples_per_variant", errors)
    relics = _require_relics(raw.get("relics"), errors)
    spec_rows = raw.get("specs")
    if not isinstance(spec_rows, list) or not spec_rows:
        errors.append("'specs' must be a non-empty list.")
        spec_rows = []

    if errors:
        _raise(path, errors)

    specs: list[SpecEntry] = []
    for index, row in enumerate(spec_rows):
        specs.append(_load_spec(
            path,
            index,
            row,
            level=level,
            duration=duration,
            dummy_hp=dummy_hp,
            training_dummy=training_dummy,
            stem_matching=stem_matching,
            seed=seed,
            sweep_stat=sweep_stat,
            relics=relics,
        ))

    return DrConfig(
        game_version=game_version,
        author=author,
        gear_label=gear_label,
        expected_mastery_multiplier=mastery_multiplier,
        sweep_stat=sweep_stat,
        sweep_min=sweep_min,
        sweep_max=sweep_max,
        jitter_mastery=jitter_mastery,
        jitter_power=jitter_power,
        samples_per_variant=samples,
        level=level,
        relics=relics,
        seed=seed,
        specs=specs,
    )


def with_relics(run_config: RunConfig, relic_fqns: list[str]) -> RunConfig:
    """Returns a copy of a run config wearing the given relics."""
    return replace(run_config, relic_fqns=list(relic_fqns))


def _load_spec(
    path: str,
    index: int,
    row,
    level: int,
    duration: int,
    dummy_hp: int,
    training_dummy: bool,
    stem_matching: bool,
    seed: int,
    sweep_stat: str,
    relics: dict[str, str],
) -> SpecEntry:
    label = f"specs[{index}]"
    if not isinstance(row, dict):
        raise ValueError(f"Invalid DR config '{path}':\n- {label} must be an object.")

    errors: list[str] = []
    missing = [key for key in _SPEC_KEYS if key not in row]
    if missing:
        errors.append(f"{label} is missing: {', '.join(missing)}.")
        _raise(path, errors)

    name = _require_str(row, "name", errors, label)
    spec_path = _require_str(row, "spec_path", errors, label)
    stats_path = _require_str(row, "stats_path", errors, label)
    rotation_path = _require_str(row, "rotation_path", errors, label)
    choices_path = _require_str(row, "choices_path", errors, label)
    tactical = _require_str(row, "tactical_fqn", errors, label)
    legendaries = _require_str_list(row, "legendary_fqns", errors, label)
    relic_fqns = _require_str_list(row, "relic_fqns", errors, label)
    if errors:
        _raise(path, errors)

    known = set(relics.values())
    if len(relic_fqns) != 2 or len(set(relic_fqns)) != 2 or any(fqn not in known for fqn in relic_fqns):
        names = ", ".join(RELIC_STATS)
        raise ValueError(
            f"Invalid DR config '{path}':\n"
            f"- {label} '{name}' relic_fqns must be two of the relics listed under 'relics' ({names})."
        )

    stats = load_json_file(stats_path)
    if not isinstance(stats, dict):
        raise ValueError(f"Invalid DR config '{path}':\n- {label} build '{stats_path}' must be a JSON object.")
    for stat in (sweep_stat, *JITTER_STATS):
        value = stats.get(stat)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"Invalid DR config '{path}':\n"
                f"- {label} build '{stats_path}' must contain a numeric '{stat}' to overwrite."
            )

    spec_data = load_json_file(spec_path)
    class_name, spec = discipline_names(spec_data, spec_path)
    run_config = RunConfig(
        spec_path=spec_path,
        class_name=class_name,
        spec=spec,
        stats_path=stats_path,
        rotation_path=rotation_path,
        choices_path=choices_path,
        tactical_fqn=tactical,
        legendary_fqns=legendaries,
        relic_fqns=relic_fqns,
        mode="BATCH",
        iterations=1,
        duration=duration,
        dummy_hp=dummy_hp,
        training_dummy_armor_debuff=training_dummy,
        enable_stem_matching=stem_matching,
        level=level,
        seed=seed,
    )
    validate_run_config(run_config)
    for fqns in _variant_lists(relics):
        validate_run_config(with_relics(run_config, fqns))

    pair_key = _pair_key(relic_fqns, relics)
    return SpecEntry(name=name, run_config=run_config, pair_key=pair_key)


def _variant_lists(relics: dict[str, str]) -> list[list[str]]:
    return [[relics[stat] for stat in VARIANT_STATS[key]] for key in VARIANT_ORDER]


def _pair_key(relic_fqns: list[str], relics: dict[str, str]) -> str:
    wanted = set(relic_fqns)
    for key, stats in VARIANT_STATS.items():
        if key == "none":
            continue
        if {relics[stat] for stat in stats} == wanted:
            return key
    raise ValueError("Could not match relic_fqns to a Mastery/Power/Crit pair.")


def _require_sweep(value, errors: list[str]) -> tuple[str, float, float]:
    if not isinstance(value, dict):
        errors.append("'sweep' must be an object with stat, min, and max.")
        return "Critical Rating", 0.0, 1.0
    stat = value.get("stat")
    if not isinstance(stat, str) or not stat.strip():
        errors.append("'sweep.stat' must be a non-empty string.")
        stat = "Critical Rating"
    elif stat in JITTER_STATS:
        errors.append(f"'sweep.stat' cannot be '{stat}', because that stat is jittered.")
    low = _optional_float(value, "min", errors, "sweep")
    high = _optional_float(value, "max", errors, "sweep")
    if low is not None and high is not None and high <= low:
        errors.append("'sweep.max' must be greater than 'sweep.min'.")
    return stat, low if low is not None else 0.0, high if high is not None else 1.0


def _require_jitter(value, errors: list[str]) -> tuple[float, float]:
    if not isinstance(value, dict):
        errors.append("'jitter' must be an object with positive Mastery and Power widths.")
        return 1.0, 1.0
    widths = []
    for stat in JITTER_STATS:
        width = _optional_float(value, stat, errors, "jitter")
        if width is None:
            widths.append(1.0)
            continue
        if width <= 0:
            errors.append(f"'jitter.{stat}' must be a positive number.")
        widths.append(width)
    extra = sorted(set(value) - set(JITTER_STATS))
    if extra:
        errors.append("'jitter' only supports Mastery and Power, got: " + ", ".join(extra) + ".")
    return widths[0], widths[1]


def _require_relics(value, errors: list[str]) -> dict[str, str]:
    if not isinstance(value, dict):
        errors.append("'relics' must map Mastery, Power, and Critical Rating to relic FQNs.")
        return {}
    missing = [stat for stat in RELIC_STATS if stat not in value]
    if missing:
        errors.append("'relics' is missing: " + ", ".join(missing) + ".")
    extra = sorted(set(value) - set(RELIC_STATS))
    if extra:
        errors.append("'relics' only supports the three passive relics, got: " + ", ".join(extra) + ".")
    relics: dict[str, str] = {}
    for stat in RELIC_STATS:
        fqn = value.get(stat)
        if not isinstance(fqn, str) or not fqn.strip():
            errors.append(f"'relics.{stat}' must be a non-empty FQN.")
            continue
        relics[stat] = fqn
    if len(set(relics.values())) != len(relics):
        errors.append("'relics' FQNs must be unique.")
    return relics


def _require_str(raw: dict, key: str, errors: list[str], label: str | None = None) -> str:
    prefix = f"{label}." if label else ""
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"'{prefix}{key}' must be a non-empty string.")
        return ""
    return value


def _require_str_list(raw: dict, key: str, errors: list[str], label: str) -> list[str]:
    value = raw.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"'{label}.{key}' must be a list of non-empty strings.")
        return []
    return list(value)


def _require_bool(raw: dict, key: str, errors: list[str]) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        errors.append(f"'{key}' must be true or false.")
        return False
    return value


def _require_int(raw: dict, key: str, errors: list[str]) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"'{key}' must be an integer.")
        return 0
    return value


def _require_positive_int(raw: dict, key: str, errors: list[str]) -> int:
    value = _require_int(raw, key, errors)
    if value <= 0:
        errors.append(f"'{key}' must be a positive integer.")
    return value


def _require_positive_float(raw: dict, key: str, errors: list[str]) -> float:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        errors.append(f"'{key}' must be a positive number.")
        return 1.0
    return float(value)


def _optional_float(raw: dict, key: str, errors: list[str], label: str) -> float | None:
    if key not in raw:
        errors.append(f"'{label}.{key}' is missing.")
        return None
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"'{label}.{key}' must be a number.")
        return None
    return float(value)


def _raise(path: str, errors: list[str]) -> None:
    raise ValueError(
        f"Invalid DR config '{path}':\n" + "\n".join(f"- {error}" for error in errors)
    )
