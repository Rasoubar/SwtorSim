import os
from typing import List, Tuple
from src.swtorsim.config_load import load_json_file

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
}


def prompt_menu_choice(options: list[str], prompt: str) -> str:
    """Helper to display a numbered list and repeatedly prompt until a valid choice is made."""
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


def select_discipline_path(disciplines_dir: str = "data/extractor/disciplines") -> Tuple[str, str, str]:
    """Interactively prompts the user to select Class and Specialization JSON."""
    print("=== SWTOR Combat Simulator Loadout Setup ===")

    print(f"\n📂 Available Classes inside '{disciplines_dir}':")
    class_options = sorted([
        d for d in os.listdir(disciplines_dir)
        if os.path.isdir(os.path.join(disciplines_dir, d))
    ])
    class_name = prompt_menu_choice(class_options, "Select Class Number: ")
    class_dir = os.path.join(disciplines_dir, class_name)

    print(f"\n📂 Available Specializations inside '{class_name}':")
    spec_files = sorted([
        f for f in os.listdir(class_dir)
        if f.endswith(".json")
    ])
    spec_choice = prompt_menu_choice(spec_files, "Select Specialization Number: ")
    spec_path = os.path.join(class_dir, spec_choice)
    spec_name = os.path.splitext(spec_choice)[0]

    return class_name, spec_name, spec_path


def select_stats_path(stats_dir: str = "data/Choices/Stats") -> str:
    """Prompts user to select a stats profile JSON."""
    print(f"\n📂 Available Stat Profiles in '{stats_dir}':")
    stat_options = sorted([f for f in os.listdir(stats_dir) if f.endswith(".json")])
    stats_choice = prompt_menu_choice(stat_options, "Select Stats Profile Number: ")
    return os.path.join(stats_dir, stats_choice)


def select_rotation_path(spec_name: str, specs_dir: str = "data/Choices/Specs") -> str:
    """Prompts user to select a rotation sequence JSON for the chosen specialization."""
    rotations_dir = os.path.join(specs_dir, spec_name, "Rotations")
    print(f"\n📂 Available Rotations in '{rotations_dir}':")
    rotation_options = sorted([f for f in os.listdir(rotations_dir) if f.endswith(".json")])
    rotation_file = prompt_menu_choice(rotation_options, "Select Rotation Sequence Number: ")
    return os.path.join(rotations_dir, rotation_file)


def _filter_gear_by_type_and_class(
    gear_data: dict[str, str], prefix: str, class_name: str
) -> dict[str, str]:
    """Filters gear items by FQN prefix and class compatibility."""
    keywords = CLASS_FQN_KEYWORDS.get(class_name.lower(), [])
    filtered = {}

    for name, fqn in gear_data.items():
        if not fqn.startswith(prefix):
            continue

        if "generic" in fqn or any(k in fqn for k in keywords):
            filtered[name] = fqn

    return filtered


def select_tactical(
    class_name: str,
    gear_path: str = "data/extractor/gear_abilities_talents.json",
) -> str:
    """Prompts user to select 1 Tactical and returns its FQN."""
    gear_data = load_json_file(gear_path)
    tacticals = _filter_gear_by_type_and_class(gear_data, "abl.itm.tactical.", class_name)

    print("\n📂 Available Tacticals:")
    options = sorted(tacticals.keys())
    chosen_name = prompt_menu_choice(options, "Select Tactical Number: ")
    return tacticals[chosen_name]


def select_implants(
    class_name: str,
    gear_path: str = "data/extractor/gear_abilities_talents.json",
) -> List[str]:
    """Prompts user to select 2 unique Legendary Implants and returns their FQNs."""
    gear_data = load_json_file(gear_path)
    implants = _filter_gear_by_type_and_class(gear_data, "abl.itm.legendary.", class_name)

    print("\n📂 Available Legendary Implants (Select 2):")
    options = sorted(implants.keys())

    first_choice = prompt_menu_choice(options, "Select First Implant Number: ")
    options.remove(first_choice)

    second_choice = prompt_menu_choice(options, "Select Second Implant Number: ")

    return [implants[first_choice], implants[second_choice]]


def prompt_optional_choices(class_name: str) -> Tuple[List[str], List[str]]:
    """Prompts for tacticals, implants, and relics.

    Returns:
        (gear_fqns, relic_paths)
    """
    tactical_fqn = select_tactical(class_name)
    implant_fqns = select_implants(class_name)
    relic_paths = select_relics()

    gear_fqns = [tactical_fqn, *implant_fqns]
    return gear_fqns, relic_paths

def _traverse_relic_folder(current_dir: str) -> str:
    """Interactively navigates subdirectories until a leaf folder is reached,

    then selects the single JSON file inside it.
    """
    while True:
        subdirs = sorted([
            d
            for d in os.listdir(current_dir)
            if os.path.isdir(os.path.join(current_dir, d))
        ])
        if not subdirs:
            break

        print(f"\n📂 Choices in '{os.path.basename(current_dir)}':")
        choice = prompt_menu_choice(subdirs, "Select Folder Number: ")
        current_dir = os.path.join(current_dir, choice)

    # Reached the final folder; pick the single JSON inside it
    json_files = [f for f in os.listdir(current_dir) if f.endswith(".json")]
    if not json_files:
        raise FileNotFoundError(f"No JSON file found in '{current_dir}'")

    selected_file = os.path.join(current_dir, json_files[0])
    print(f"  ✅ Selected: {os.path.basename(current_dir)} ({json_files[0]})")
    return selected_file


def select_relics(
    relic_dir: str = "data/extractor/parsed/abl/itm/relic", count: int = 2
) -> List[str]:
    """Prompts user to select relics by directory path."""
    print(f"\n=== Select {count} Relics ===")
    selected_relic_paths = []

    for i in range(1, count + 1):
        print(f"\n--- Relic #{i} ---")
        relic_path = _traverse_relic_folder(relic_dir)
        selected_relic_paths.append(relic_path)

    return selected_relic_paths


def select_skill_tree_choices(skill_tree_data: dict) -> List[str]:
    """Prompts the user to pick one talent/ability per level tier in the skill tree."""
    selected_fqns: List[str] = []
    sorted_tiers = sorted(skill_tree_data.keys(), key=int)

    print("\n=== Select Skill Tree Talents ===")
    for tier in sorted_tiers:
        tier_choices = skill_tree_data[tier]
        sorted_choice_keys = sorted(tier_choices.keys(), key=int)

        # Build human-readable lines showing the FQNs in each slot
        display_options = [
            ", ".join(tier_choices[k]) for k in sorted_choice_keys
        ]

        print(f"\n📂 Level {tier} Option:")
        chosen_display = prompt_menu_choice(display_options, f"Select Tier {tier} Choice: ")
        chosen_idx = sorted_choice_keys[display_options.index(chosen_display)]
        selected_fqns.extend(tier_choices[chosen_idx])

    return selected_fqns


def load_discipline_fqns(spec_path: str) -> List[str]:
    """Loads a discipline JSON, grants baseline abilities, and prompts for skill tree choices."""
    spec_data = load_json_file(spec_path)
    baseline_fqns: List[str] = spec_data.get("active_abilities", [])

    skill_tree_data = spec_data.get("skill_tree", {})
    tree_fqns = select_skill_tree_choices(skill_tree_data) if skill_tree_data else []

    return baseline_fqns + tree_fqns

def prompt_run_mode() -> Tuple[str, int]:
    """Prompts user to select execution mode and iteration count."""
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