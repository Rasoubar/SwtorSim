import json
import os


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


def main():
    print("=========================================")
    print("      SWTOR SIM - ROTATION BUILDER       ")
    print("=========================================")

    rotation = []

    while True:
        print("\nWhat kind of step do you want to add to the timeline?")
        print("  1. Fixed Cast (No rules. Engine waits until ability is ready)")
        print("  2. Optional Cast (Has rules. Engine skips it if rules fail)")
        print("  3. Priority Block (A pool of abilities evaluated top-to-bottom)")
        print("  4. Loop Anchor (Marks where the rotation restarts after an opener)")
        print("  0. Finish & Save Rotation")

        choice = get_input("Select an option", int)

        if choice == 0:
            break

        elif choice == 1:
            print("\n--- Adding FIXED Step ---")
            ability_id = get_input("Ability ID (e.g., eradicate)", str)
            rotation.append({
                "type": "fixed",
                "ability_id": ability_id
            })
            print(f"✔ Fixed step '{ability_id}' added.")

        elif choice == 2:
            print("\n--- Adding OPTIONAL Step ---")
            ability_id = get_input("Ability ID (e.g., recklessness)", str)
            rules = build_rules()
            rotation.append({
                "type": "optional",
                "ability_id": ability_id,
                "rules": rules
            })
            print(f"✔ Optional step '{ability_id}' added.")

        elif choice == 3:
            print("\n--- Adding PRIORITY BLOCK ---")
            block_name = get_input("Block Name (e.g., Main Priority Window)", str)
            pool = []

            while True:
                print(f"\n  [Pool: {block_name}] Current size: {len(pool)}")
                add_ability = get_input("  Add an ability to this priority pool? (y/n)", bool, True)
                if not add_ability:
                    break

                ab_id = get_input("  Ability ID", str)
                ab_rules = build_rules(indent="    ")
                pool.append({
                    "ability_id": ab_id,
                    "rules": ab_rules
                })
                print(f"  ✔ Added '{ab_id}' to pool.")

            rotation.append({
                "type": "priority_block",
                "name": block_name,
                "pool": pool
            })
            print(f"✔ Priority Block '{block_name}' added.")

        elif choice == 4:
            print("\n--- Adding LOOP ANCHOR ---")
            rotation.append({
                "type": "loop_anchor"
            })
            print("✔ Loop Anchor added. Everything below this will repeat indefinitely.")

        else:
            print("❌ Invalid choice. Select 0, 1, 2, 3, or 4.")

    if not rotation:
        print("Rotation sequence is empty. Exiting without saving.")
        return

    print("\n=========================================")
    # Create the directory if it doesn't exist to prevent crash
    os.makedirs("data/Rotations", exist_ok=True)

    save_path = get_input("Enter filename to save (e.g., Hybrid.json)", str, "StandardRotation.json")

    # Automatically ensure the file ends with .json
    if not save_path.endswith(".json"):
        save_path += ".json"

    full_path = os.path.join("data/Rotations", save_path)

    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(rotation, f, indent=4)

    print(f"\n✅ SUCCESS! Rotation safely exported to {full_path}")


if __name__ == "__main__":
    main()