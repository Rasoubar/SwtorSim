from pathlib import Path

from src.swtorsim.config_load import load_json_file
from src.swtorsim.run_config import (
    BUILDS_DIR,
    CHOICES_DIR,
    DISCIPLINES_DIR,
    GEAR_PATH,
    LEGENDARY_PREFIX,
    RELICS_PATH,
    ROTATIONS_DIR,
    TACTICAL_PREFIX,
    TRAINING_DUMMY_ARMOR_DEBUFF_LABEL,
    RunConfig,
    discipline_names,
    filter_gear_for_class,
    relic_menu_label,
    validate_run_config,
)


def prompt_menu_choice(options: list[str], prompt: str) -> str:
    """Displays a numbered list and prompts until the selection is valid."""
    for idx, name in enumerate(options, 1):
        print(f"  [{idx}] {name}")

    while True:
        try:
            choice_idx = int(input(prompt).strip()) - 1
            if 0 <= choice_idx < len(options):
                return options[choice_idx]
            print(f"  ❌ Invalid selection. Please enter a number between 1 and {len(options)}.")
        except ValueError:
            print(f"  ❌ Invalid selection. Please enter a number between 1 and {len(options)}.")


def collect_run_config_interactive() -> RunConfig:
    """Prompts for every selection and returns a validated run config."""
    mode, iterations = prompt_run_mode()

    print("=== SWTOR Combat Simulator Loadout Setup ===")
    class_name, spec, spec_path = select_discipline_path()
    stats_path = select_stats_path()
    rotation_path = select_rotation_path()
    choices_path = select_choices_path()
    tactical_fqn = select_tactical(class_name)
    legendary_fqns = select_legendaries(class_name)
    relic_fqns = select_relics()
    training_dummy_armor_debuff = prompt_training_dummy_armor_debuff()

    config = RunConfig(
        spec_path=spec_path,
        class_name=class_name,
        spec=spec,
        stats_path=stats_path,
        rotation_path=rotation_path,
        choices_path=choices_path,
        tactical_fqn=tactical_fqn,
        legendary_fqns=legendary_fqns,
        relic_fqns=relic_fqns,
        training_dummy_armor_debuff=training_dummy_armor_debuff,
        mode=mode,
        iterations=iterations,
    )
    validate_run_config(config)
    return config


def select_discipline_path(
    disciplines_dir: str = DISCIPLINES_DIR,
) -> tuple[str, str, str]:
    """Prompts for a class (tab_name) and spec (package_name). Returns both plus the JSON path."""
    disciplines = index_disciplines(disciplines_dir)

    print("\n📂 Available Classes:")
    class_name = prompt_menu_choice(sorted(disciplines), "Select Class Number: ")

    print(f"\n📂 Available Specs for {class_name}:")
    spec = prompt_menu_choice(sorted(disciplines[class_name]), "Select Spec Number: ")
    return class_name, spec, disciplines[class_name][spec]


def index_disciplines(disciplines_dir: str = DISCIPLINES_DIR) -> dict[str, dict[str, str]]:
    """Maps tab_name -> package_name -> discipline JSON path."""
    root = Path(disciplines_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"Discipline directory not found: {disciplines_dir}")

    disciplines: dict[str, dict[str, str]] = {}
    for path in sorted(root.rglob("*.json")):
        if not path.is_file():
            continue
        spec_data = load_json_file(str(path))
        class_name, spec = discipline_names(spec_data, str(path))
        specs = disciplines.setdefault(class_name, {})
        if spec in specs:
            raise ValueError(
                f"Duplicate spec '{spec}' for class '{class_name}' in '{path}'."
            )
        specs[spec] = str(path)

    if not disciplines:
        raise FileNotFoundError(f"No discipline JSON files found in '{disciplines_dir}'.")
    return disciplines


def select_stats_path(builds_dir: str = BUILDS_DIR) -> str:
    """Prompts for a build JSON from the top level of the builds directory."""
    options = catalog_json_files(builds_dir, recursive=False)
    print(f"\n📂 Available Builds in '{builds_dir}':")
    choice = prompt_menu_choice(sorted(options), "Select Build Number: ")
    return options[choice]


def select_rotation_path(rotations_dir: str = ROTATIONS_DIR) -> str:
    """Prompts for a rotation JSON, including files in subdirectories."""
    options = catalog_json_files(rotations_dir, recursive=True)
    print(f"\n📂 Available Rotations in '{rotations_dir}':")
    choice = prompt_menu_choice(sorted(options), "Select Rotation Number: ")
    return options[choice]


def select_choices_path(choices_dir: str = CHOICES_DIR) -> str:
    """Prompts for a skill-tree choice JSON, including files in subdirectories."""
    options = catalog_json_files(choices_dir, recursive=True)
    print(f"\n📂 Available Skill Tree Choices in '{choices_dir}':")
    choice = prompt_menu_choice(sorted(options), "Select Choices Number: ")
    return options[choice]


def catalog_json_files(directory: str, recursive: bool) -> dict[str, str]:
    """Maps a display label (path without .json) to the file path. Raises if the catalog is empty."""
    root = Path(directory)
    if not root.is_dir():
        raise FileNotFoundError(f"Catalog directory not found: {directory}")

    paths = root.rglob("*.json") if recursive else root.glob("*.json")
    options: dict[str, str] = {}
    for path in sorted(paths):
        if not path.is_file():
            continue
        label = path.relative_to(root).with_suffix("").as_posix()
        options[label] = str(path)

    if not options:
        raise FileNotFoundError(f"No JSON files found in '{directory}'.")
    return options


def select_tactical(
    class_name: str,
    gear_path: str = GEAR_PATH,
) -> str:
    """Prompts for one class-compatible tactical and returns its FQN."""
    tacticals = _gear_options(class_name, TACTICAL_PREFIX, gear_path)
    print("\n📂 Available Tacticals:")
    chosen_name = prompt_menu_choice(sorted(tacticals), "Select Tactical Number: ")
    return tacticals[chosen_name]


def select_legendaries(
    class_name: str,
    gear_path: str = GEAR_PATH,
) -> list[str]:
    """Prompts for two unique class-compatible legendary implants and returns their FQNs."""
    legendaries = _gear_options(class_name, LEGENDARY_PREFIX, gear_path)
    if len(legendaries) < 2:
        raise ValueError(
            f"Need at least 2 legendary implants for class '{class_name}', found {len(legendaries)}."
        )
    print("\n📂 Available Legendary Implants (Select 2):")
    options = sorted(legendaries)

    first_choice = prompt_menu_choice(options, "Select First Legendary Number: ")
    options.remove(first_choice)
    second_choice = prompt_menu_choice(options, "Select Second Legendary Number: ")
    return [legendaries[first_choice], legendaries[second_choice]]


def select_relics(relics_path: str = RELICS_PATH) -> list[str]:
    """Prompts for 0, 1, or 2 unique relics and returns their FQNs."""
    catalog = load_json_file(relics_path)
    if not isinstance(catalog, list):
        raise ValueError(f"Relic catalog '{relics_path}' must be a JSON array.")

    print("\n📂 Relics:")
    count = _prompt_relic_count()
    if count == 0:
        return []

    remaining = [fqn for fqn in catalog if isinstance(fqn, str) and fqn.strip()]
    if len(remaining) < count:
        raise ValueError(
            f"Relic catalog '{relics_path}' does not contain {count} relics."
        )

    selected: list[str] = []
    for index in range(1, count + 1):
        labels = _relic_menu_options(remaining)
        print(f"\n📂 Relic {index}:")
        chosen_label = prompt_menu_choice(sorted(labels), "Select Relic Number: ")
        chosen = labels[chosen_label]
        selected.append(chosen)
        remaining.remove(chosen)
    return selected


def _prompt_relic_count() -> int:
    """Asks for a relic count of 0, 1, or 2."""
    while True:
        user_input = input("How many relics? (0-2): ").strip()
        if user_input in {"0", "1", "2"}:
            return int(user_input)
        print("  ❌ Enter 0, 1, or 2.")


def _relic_menu_options(fqns: list[str]) -> dict[str, str]:
    """Maps a menu label to a relic FQN. Duplicate short labels fall back to the full FQN."""
    short_counts: dict[str, int] = {}
    for fqn in fqns:
        label = relic_menu_label(fqn)
        short_counts[label] = short_counts.get(label, 0) + 1

    options: dict[str, str] = {}
    for fqn in fqns:
        label = relic_menu_label(fqn)
        if short_counts[label] > 1:
            label = fqn
        options[label] = fqn
    return options


def prompt_training_dummy_armor_debuff() -> bool:
    """Asks whether the operation training dummy armor debuff is on the target."""
    print("\n📂 Target Debuff:")
    choice = prompt_menu_choice(
        ["No", TRAINING_DUMMY_ARMOR_DEBUFF_LABEL],
        "Select Target Debuff: ",
    )
    return choice == TRAINING_DUMMY_ARMOR_DEBUFF_LABEL


def prompt_run_mode() -> tuple[str, int]:
    """Prompts for a single test run or a Monte Carlo batch, plus the iteration count."""
    print("\n📂 Select Execution Mode:")
    mode_options = ["TEST (Single Test Run)", "BATCH (Monte Carlo Simulation)"]
    selected = prompt_menu_choice(mode_options, "Select Mode Number: ")

    if "TEST" in selected:
        return "TEST", 1

    user_input = input("\nEnter number of iterations [Default: 1000]: ").strip()
    if not user_input:
        return "BATCH", 1000

    try:
        iterations = int(user_input)
        return "BATCH", iterations if iterations > 0 else 1000
    except ValueError:
        print("⚠️ Invalid input. Using default (1000).")
        return "BATCH", 1000


def _gear_options(class_name: str, prefix: str, gear_path: str) -> dict[str, str]:
    gear_data = load_json_file(gear_path)
    if not isinstance(gear_data, dict):
        raise ValueError(f"Gear catalog '{gear_path}' must be a JSON object.")
    options = filter_gear_for_class(gear_data, prefix, class_name)
    if not options:
        kind = "tacticals" if prefix == TACTICAL_PREFIX else "legendary implants"
        raise ValueError(f"No {kind} available for class '{class_name}'.")
    return options
