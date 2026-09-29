import json
import os
import sys
import copy
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.swtorsim.cli import select_choices_path, select_discipline_path
from src.swtorsim.config_load import fqn_to_relative_path, load_json_file
from src.swtorsim.run_config import resolve_skill_tree_fqns

PARSED_DIR = Path("data/extractor/parsed")


def get_input(prompt, type_func=str, default=None):
    """Helper function to safely capture and format terminal input."""
    default_str = f" [Default: {default}]" if default is not None else " [Required]"
    while True:
        user_input = input(f"{prompt}{default_str}: ").strip()
        if not user_input:
            if default is not None:
                return default
            print("❌ This field is required. Please try again.")
            continue
        try:
            if type_func == bool:
                # Make boolean checking strictly enforce yes/no answers
                if user_input.lower() in ['y', 'yes', 't', 'true', '1']:
                    return True
                elif user_input.lower() in ['n', 'no', 'f', 'false', '0']:
                    return False
                else:
                    print("❌ Please enter 'y' or 'n'.")
                    continue

            return type_func(user_input)
        except ValueError:
            print(f"❌ Invalid format. Expected {type_func.__name__}. Try again.")


def build_rules(indent="  "):
    """Interactively builds a dictionary of conditional rules for a rotation step."""
    rules = {}
    print(f"\n{indent}--- Adding Rules (Conditions) ---")
    print(f"{indent}Examples: caster_energy_below, caster_has_buff, target_hp_below_pct")

    while get_input(f"{indent}Add a rule? (y/n)", bool, False):
        key = get_input(f"{indent}Rule Key", str)

        # Ask if the value needs to be a nested dictionary (e.g., {"name": "Bloodletting", "value": 0.5})
        is_nested = get_input(f"{indent}Is the value for '{key}' a nested dictionary? (y/n)", bool, False)

        if is_nested:
            nested_dict = {}
            print(f"{indent}  [Building Nested Dictionary for '{key}']")
            while True:
                sub_key = get_input(f"{indent}  Sub-key (e.g., 'name' or 'value')", str)
                sub_val_str = get_input(f"{indent}  Value for '{sub_key}'", str)

                # Auto-parse logic for sub-values
                if sub_val_str.lower() in ['true', 'false']:
                    sub_val = sub_val_str.lower() == 'true'
                else:
                    try:
                        sub_val = float(sub_val_str) if '.' in sub_val_str else int(sub_val_str)
                    except ValueError:
                        sub_val = sub_val_str  # Keep as string

                nested_dict[sub_key] = sub_val

                if not get_input(f"{indent}  Add another sub-key to '{key}'? (y/n)", bool, False):
                    break

            rules[key] = nested_dict
            print(f"{indent}✔ Added nested rule: '{key}': {nested_dict}")

        else:
            val_str = get_input(f"{indent}Value for '{key}'", str)

            # Auto-parse logic for flat values
            if val_str.lower() in ['true', 'false']:
                val = val_str.lower() == 'true'
            else:
                try:
                    val = float(val_str) if '.' in val_str else int(val_str)
                except ValueError:
                    val = val_str  # Keep as string

            rules[key] = val
            print(f"{indent}✔ Added rule: '{key}': {val}")

    return rules


@dataclass(frozen=True)
class CastableAbility:
    fqn: str
    name: str
    triggers_gcd: bool


def loadout_fqns(spec_data: dict, choices: dict) -> list[str]:
    """Baseline discipline abilities plus the chosen skill-tree slots, without gear."""
    baseline = spec_data.get("active_abilities", [])
    if not isinstance(baseline, list):
        raise ValueError("Discipline file active_abilities must be a list.")

    tree_fqns = resolve_skill_tree_fqns(spec_data.get("skill_tree", {}), choices)
    ordered: list[str] = []
    seen: set[str] = set()
    for fqn in [*baseline, *tree_fqns]:
        if not isinstance(fqn, str) or not fqn.strip():
            print(f"⚠️ [WARN] Skipping invalid ability id: {fqn!r}")
            continue
        if fqn in seen:
            continue
        seen.add(fqn)
        ordered.append(fqn)
    return ordered


def build_castable_catalog(
    spec_path: str,
    choices_path: str,
    parsed_dir: Path = PARSED_DIR,
) -> list[CastableAbility]:
    """Returns active abilities for a discipline and skill-tree selection, sorted by name."""
    spec_data = load_json_file(spec_path)
    choices = load_json_file(choices_path)
    actives: list[CastableAbility] = []
    passive_count = 0
    talent_count = 0

    for fqn in loadout_fqns(spec_data, choices):
        if fqn.startswith("tal."):
            talent_count += 1
            continue

        full_path = parsed_dir / fqn_to_relative_path(fqn)
        if not full_path.is_file():
            print(f"⚠️ [WARN] Blueprint file not found for FQN '{fqn}': {full_path}")
            continue

        data = load_json_file(str(full_path))
        ability_type = data.get("type")
        if ability_type == "passive":
            passive_count += 1
            continue
        if ability_type != "active":
            print(
                f"⚠️ [WARN] Skipping '{fqn}': type is {ability_type!r}, "
                "expected 'active' or 'passive'."
            )
            continue

        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            name = fqn
        actives.append(CastableAbility(
            fqn=fqn,
            name=name,
            triggers_gcd=data.get("triggers_gcd") is not False,
        ))

    actives.sort(key=lambda ability: (ability.name.lower(), ability.fqn))
    on_gcd = sum(ability.triggers_gcd for ability in actives)
    off_gcd = len(actives) - on_gcd
    print(
        f"\nCastable abilities: {len(actives)} "
        f"({on_gcd} on GCD, {off_gcd} off-GCD). "
        f"Omitted {passive_count} passives and {talent_count} talents."
    )
    return actives


def pick_ability(catalog: list[CastableAbility], prompt: str = "Select ability number: ") -> str:
    """Shows the castable list and returns the chosen ability FQN."""
    if not catalog:
        raise ValueError("No castable abilities to choose from.")

    for idx, ability in enumerate(catalog, 1):
        suffix = "" if ability.triggers_gcd else " (off-GCD)"
        print(f"  [{idx}] {ability.name}{suffix}")

    while True:
        try:
            choice_idx = int(input(prompt).strip()) - 1
            if 0 <= choice_idx < len(catalog):
                return catalog[choice_idx].fqn
            print(f"  ❌ Invalid selection. Please enter a number between 1 and {len(catalog)}.")
        except ValueError:
            print(f"  ❌ Invalid selection. Please enter a number between 1 and {len(catalog)}.")


def rotation_folder_defaults(spec_path: str) -> tuple[str, str]:
    """Class and spec folder names from a discipline path, not its display names."""
    path = Path(spec_path)
    return path.parent.name, path.stem


def main():
    print("=========================================")
    print("      SWTOR SIM - ROTATION BUILDER       ")
    print("=========================================")

    _class_name, _spec, spec_path = select_discipline_path()
    choices_path = select_choices_path()
    catalog = build_castable_catalog(spec_path, choices_path)
    if not catalog:
        print("No castable abilities found. Exiting without saving.")
        return

    default_class, default_spec = rotation_folder_defaults(spec_path)
    rotation = []
    saved_templates = {}  # Local clipboard for the session

    while True:
        print("\nWhat kind of step do you want to add to the timeline?")
        print("  1. Fixed Cast (No rules. Engine waits until ability is ready)")
        print("  2. Optional Cast (Has rules. Engine skips it if rules fail)")
        print("  3. Priority Block (A pool of abilities evaluated top-to-bottom)")
        print("  4. Loop Anchor (Marks where the rotation restarts after an opener)")
        print("  5. Insert Saved Template (Paste a previously saved block/cast)")  # 🟢 NEW
        print("  0. Finish & Save Rotation")

        choice = get_input("Select an option", int)

        if choice == 0:
            break

        elif choice == 1:
            print("\n--- Adding FIXED Step ---")
            ability_id = pick_ability(catalog)
            rotation.append({
                "type": "fixed",
                "ability_id": ability_id
            })
            print(f"✔ Fixed step '{ability_id}' added.")

        elif choice == 2:
            print("\n--- Adding OPTIONAL Step ---")
            ability_id = pick_ability(catalog)
            rules = build_rules()

            step_dict = {
                "type": "optional",
                "ability_id": ability_id,
                "rules": rules
            }
            rotation.append(step_dict)
            print(f"✔ Optional step '{ability_id}' added.")

            # 🟢 NEW: Ask to save as template
            if get_input("  Save this Optional Step as a template for reuse? (y/n)", bool, False):
                t_name = get_input("  Enter a short template name (e.g., 'reck_opt')", str)
                saved_templates[t_name] = step_dict
                print(f"  ✔ Template '{t_name}' saved to clipboard.")

        elif choice == 3:
            print("\n--- Adding PRIORITY BLOCK ---")
            block_name = get_input("Block Name (e.g., Main Priority Window)", str)
            pool = []

            while True:
                print(f"\n  [Pool: {block_name}] Current size: {len(pool)}")
                add_ability = get_input("  Add an ability to this priority pool? (y/n)", bool, True)
                if not add_ability:
                    break

                ab_id = pick_ability(catalog, prompt="  Select ability number: ")
                ab_rules = build_rules(indent="    ")
                pool.append({
                    "ability_id": ab_id,
                    "rules": ab_rules
                })
                print(f"  ✔ Added '{ab_id}' to pool.")

            step_dict = {
                "type": "priority_block",
                "name": block_name,
                "pool": pool
            }
            rotation.append(step_dict)
            print(f"✔ Priority Block '{block_name}' added.")

            # 🟢 NEW: Ask to save as template
            if get_input("  Save this Priority Block as a template for reuse? (y/n)", bool, False):
                t_name = get_input("  Enter a short template name (e.g., 'main_filler')", str)
                saved_templates[t_name] = step_dict
                print(f"  ✔ Template '{t_name}' saved to clipboard.")

        elif choice == 4:
            print("\n--- Adding LOOP ANCHOR ---")
            rotation.append({
                "type": "loop_anchor"
            })
            print("✔ Loop Anchor added. Everything below this will repeat indefinitely.")

        elif choice == 5:
            # 🟢 NEW: Logic to inject templates
            print("\n--- INSERT SAVED TEMPLATE ---")
            if not saved_templates:
                print("❌ Your clipboard is empty. Create an Optional or Priority step and save it first.")
                continue

            print("Available templates:")
            for name in saved_templates.keys():
                print(f"  - {name}")

            template_name = get_input("Enter template name to insert", str)
            if template_name in saved_templates:
                # Use deepcopy so if we change JSON structure later, instances don't share memory
                rotation.append(copy.deepcopy(saved_templates[template_name]))
                print(f"✔ Successfully inserted template '{template_name}'.")
            else:
                print("❌ Template not found. Skipping.")

        else:
            print("❌ Invalid choice. Select 0-5.")

    if not rotation:
        print("Rotation sequence is empty. Exiting without saving.")
        return

    print("\n=========================================")
    print("             SAVE & EXPORT               ")

    class_name = get_input("Enter Class folder (e.g., assassin)", str, default_class)
    spec_name = get_input("Enter Spec folder (e.g., hatred)", str, default_spec)

    target_dir = os.path.join("data", "rotations", class_name, spec_name)
    os.makedirs(target_dir, exist_ok=True)

    save_path = get_input("Enter filename to save (e.g., Hybrid.json)", str, "StandardRotation.json")

    if not save_path.endswith(".json"):
        save_path += ".json"

    full_path = os.path.join(target_dir, save_path)

    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(rotation, f, indent=4)

    print(f"\n✅ SUCCESS! Rotation safely exported to {full_path}")


if __name__ == "__main__":
    main()