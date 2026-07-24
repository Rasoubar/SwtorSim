import os
import json
from typing import Tuple
from src.swtorsim.config_load import load_json_file


def prompt_menu_choice(options: list[str], prompt: str) -> str:
    """Helper to display a numbered list and repeatedly prompt until a valid choice is made."""
    #Made by Gemini
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


def select_loadout_paths(data_root: str = "data"):
    """Interactively prompts the user to select Class, Spec, Build, and Rotation."""
    #Made by gemini from previous code.

    print("=== SWTOR Combat Simulator Environment Setup ===")

    # 1. Select Class
    print(f"\n📂 Available Classes inside '{data_root}':")
    class_options = sorted([
        d for d in os.listdir(data_root)
        if os.path.isdir(os.path.join(data_root, d))
    ])
    class_name = prompt_menu_choice(class_options, "Select Class Number: ")
    class_dir = os.path.join(data_root, class_name)

    # 2. Select Specialization
    print(f"\n📂 Available Specializations inside '{class_name}':")
    spec_options = sorted([
        d for d in os.listdir(class_dir)
        if os.path.isdir(os.path.join(class_dir, d))
    ])
    spec_name = prompt_menu_choice(spec_options, "Select Specialization Number: ")
    base_dir = os.path.join(data_root, class_name, spec_name)

    # 3. Select Stat Profile
    builds_dir = os.path.join(base_dir, "PlayerBuilds")
    print(f"\n📂 Available Stat Profiles in '{builds_dir}':")
    stat_options = sorted([f for f in os.listdir(builds_dir) if f.endswith(".json")])
    stats_choice = prompt_menu_choice(stat_options, "Select Stats Profile Number: ")

    with open(os.path.join(builds_dir, stats_choice), "r", encoding="utf-8") as f:
        stats_data = json.load(f)

    character_stats = {
        "class_name": class_name,
        "stats": stats_data
    }

    # 4. Select Rotation
    rotations_dir = os.path.join(base_dir, "Rotations")
    print(f"\n📂 Available Rotations in '{rotations_dir}':")
    rotation_options = sorted([f for f in os.listdir(rotations_dir) if f.endswith(".json")])
    rotation_file = prompt_menu_choice(rotation_options, "Select Rotation Sequence Number: ")
    rotation_path = os.path.join(rotations_dir, rotation_file)

    return base_dir, character_stats, rotation_path


def _process_item_additions(to_add_list: list, abilities: dict, procs: dict, buffs: dict) -> None:
    """Helper to unpack inner additions and categorize them into respective raw dicts."""
    #made by gemini from my previous draft_choices code

    for addition in to_add_list:
        for inner_name, inner_config in addition.items():
            inner_type = inner_config.get("item_type", "unknown").lower()
            inner_config["name"] = inner_name

            if inner_type == "ability":
                abilities[inner_name] = inner_config
            elif inner_type == "proc":
                procs[inner_name] = inner_config
            elif inner_type == "buff":
                buffs[inner_name] = inner_config
            else:
                print(f"⚠️ Unknown item type '{inner_type}' in {inner_name}")


def draft_choices(
        filepath: str,
        prompt_title: str,
        max_picks: int | None = None,
        check_levels: bool = False
) -> Tuple[dict, dict, dict]:
    """Interactively drafts items from a JSON file based on specific rules."""
    #Adapted by gemini from my code

    raw_data = load_json_file(filepath)

    selected_raw_abilities = {}
    selected_raw_procs = {}
    selected_raw_buffs = {}
    picked_levels = set()
    picks = 0

    print(f"\n--- {prompt_title} ---")

    for item_name, item_data in raw_data.items():
        if max_picks and picks >= max_picks:
            print(f"🛑 Max limit of {max_picks} reached. Skipping remaining.")
            break

        to_add_list = item_data.get("To_add", [])
        if not to_add_list:
            continue

        # Safely inspect item type without risking an IndexError
        first_entry = next(iter(to_add_list[0].values()), {})
        primary_type = first_entry.get("item_type", "unknown").lower()
        item_level = item_data.get("level")

        if check_levels and item_level in picked_levels:
            continue

        while True:
            choice = input(f"Equip '{item_name}' ({primary_type})? [y/n]: ").strip().lower()
            if choice in ['y', 'yes']:
                _process_item_additions(
                    to_add_list,
                    selected_raw_abilities,
                    selected_raw_procs,
                    selected_raw_buffs
                )
                if check_levels and item_level:
                    picked_levels.add(item_level)
                picks += 1
                print("  ✅ Added")
                break
            elif choice in ['n', 'no', '']:
                break
            else:
                print("  ❌ Please enter 'y' for yes or 'n' for no.")

    return selected_raw_abilities, selected_raw_buffs, selected_raw_procs


def prompt_optional_choices(base_dir: str) -> Tuple[dict, dict, dict]:
    """Interactively drafts optional choices for relics, tactical, tree, and implants."""
    #Made by gemini from my old code
    choice_dict = {
        "relics": f"{base_dir}/choices/relics.json",
        "tree": f"{base_dir}/choices/tree.json",
        "tactical": f"{base_dir}/choices/tacticals.json",
        "implants": f"{base_dir}/choices/implants.json"
    }

    relics = draft_choices(choice_dict["relics"], prompt_title="Relics", max_picks=2)
    tactical = draft_choices(choice_dict["tactical"], prompt_title="Tactical", max_picks=1)
    tree = draft_choices(choice_dict["tree"], prompt_title="Tree", check_levels=True)
    implants = draft_choices(choice_dict["implants"], prompt_title="Implant", max_picks=2)

    raw_abilities = relics[0] | tactical[0] | tree[0] | implants[0]
    raw_buffs = relics[1] | tactical[1] | tree[1] | implants[1]
    raw_procs = relics[2] | tactical[2] | tree[2] | implants[2]

    return raw_abilities, raw_buffs, raw_procs


def prompt_run_mode() -> Tuple[str, int]:
    """Prompts the user to select execution mode and iteration count for Monte Carlo."""
    #Made by gemini, this part is too boring
    print("\n📂 Select Execution Mode:")
    mode_options = ["TEST (Single Test Run)", "BATCH (Monte Carlo Simulation)"]
    selected = prompt_menu_choice(mode_options, "Select Mode Number: ")

    if "TEST" in selected:
        return "TEST", 1

    # Prompt for iterations if BATCH is chosen
    user_input = input("\nEnter number of iterations [Default: 1000]: ").strip()

    if not user_input:
        return "BATCH", 1000

    try:
        iterations = int(user_input)
        return "BATCH", iterations if iterations > 0 else 1000
    except ValueError:
        print("⚠️ Invalid input. Using default (1000).")
        return "BATCH", 1000