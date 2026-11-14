"""Load and validate the diminishing-returns run config.

Each spec names a simulator run config. The loadout (discipline, build, rotation,
choices, weapons, tactical, legendaries, and the equipped relic pair) comes from
that file. Fight length, dummy HP, level, seed, stem matching, and the armor
debuff stay on the DR config and apply to every spec.
"""

from dataclasses import dataclass, replace

from src.swtorsim.config_load import load_json_file
from src.swtorsim.run_config import RunConfig, load_run_config, validate_run_config

RELIC_STATS = ("Mastery", "Power", "Crit")
JITTER_STATS = ("Mastery", "Power")
# Config labels that differ from the stat key stored on a build and in the sim.
BUILD_STAT_NAMES = {"Crit Rating": "Critical Rating"}

VARIANT_ORDER = ("none", "mastery_power", "mastery_crit", "power_crit")
VARIANT_STATS = {
    "none": (),
    "mastery_power": ("Mastery", "Power"),
    "mastery_crit": ("Mastery", "Crit"),
    "power_crit": ("Power", "Crit"),
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


def build_stat_name(name: str) -> str:
    """The key used in build files and the sim for a config stat label."""
    return BUILD_STAT_NAMES.get(name, name)


def relic_line(pair_key: str) -> str:
    """The equipped pair, as a plot subtitle such as 'Mastery + Power Relics'."""
    return " + ".join(VARIANT_STATS[pair_key]) + " Relics"


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
    """Loads a dr_config.json. Each spec's ``run_config`` is a simulator run config path."""
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
    name = _require_str(row, "name", errors, label)
    run_config_path = _require_str(row, "run_config", errors, label)
    if errors:
        _raise(path, errors)

    try:
        raw_run = load_json_file(run_config_path)
    except FileNotFoundError as exc:
        raise ValueError(
            f"Invalid DR config '{path}':\n"
            f"- {label} '{name}' run config '{run_config_path}' was not found."
        ) from exc
    if not isinstance(raw_run, dict):
        raise ValueError(
            f"Invalid DR config '{path}':\n"
            f"- {label} '{name}' run config '{run_config_path}' must be a JSON object."
        )

    try:
        loaded = load_run_config(run_config_path, environment=_run_config_environment(raw_run))
    except (ValueError, FileNotFoundError) as exc:
        raise ValueError(
            f"Invalid DR config '{path}':\n- {label} '{name}': {exc}"
        ) from exc

    run_config = replace(
        loaded,
        mode="BATCH",
        iterations=1,
        duration=duration,
        dummy_hp=dummy_hp,
        training_dummy_armor_debuff=training_dummy,
        enable_stem_matching=stem_matching,
        level=level,
        seed=seed,
    )
    relic_fqns = list(run_config.relic_fqns)
    known = set(relics.values())
    if len(relic_fqns) != 2 or len(set(relic_fqns)) != 2 or any(fqn not in known for fqn in relic_fqns):
        names = ", ".join(RELIC_STATS)
        raise ValueError(
            f"Invalid DR config '{path}':\n"
            f"- {label} '{name}' relic_fqns must be two of the relics listed under 'relics' ({names})."
        )

    stats_path = run_config.stats_path
    stats = load_json_file(stats_path)
    if not isinstance(stats, dict):
        raise ValueError(f"Invalid DR config '{path}':\n- {label} build '{stats_path}' must be a JSON object.")
    for stat in (sweep_stat, *JITTER_STATS):
        build_stat = build_stat_name(stat)
        value = stats.get(build_stat)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"Invalid DR config '{path}':\n"
                f"- {label} build '{stats_path}' must contain a numeric '{build_stat}' to overwrite."
            )

    validate_run_config(run_config)
    for fqns in _variant_lists(relics):
        validate_run_config(with_relics(run_config, fqns))

    pair_key = _pair_key(relic_fqns, relics)
    return SpecEntry(name=name, run_config=run_config, pair_key=pair_key)


def _run_config_environment(raw: dict) -> str:
    """The data set for a run config.

    An ``environment`` field wins. Otherwise a discipline path under
    ``data/extractor/pts/`` loads PTS data, and every other path loads live.
    """
    explicit = raw.get("environment")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()
    spec_path = str(raw.get("spec_path") or "").replace("\\", "/").lower()
    if "/extractor/pts/" in spec_path:
        return "pts"
    return "live"


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
        return "Crit Rating", 0.0, 1.0
    stat = value.get("stat")
    if not isinstance(stat, str) or not stat.strip():
        errors.append("'sweep.stat' must be a non-empty string.")
        stat = "Crit Rating"
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
        errors.append("'relics' must map Mastery, Power, and Crit to relic FQNs.")
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
