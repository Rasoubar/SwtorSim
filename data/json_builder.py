import json
import os


def get_input(prompt, type_func=str, default=None):
    """Helper function to handle inputs, defaults, and clean type conversions."""
    default_str = f" [Press Enter for: {default}]" if default is not None else " [Required]"
    user_input = input(f"{prompt}{default_str}: ").strip()

    if not user_input:
        if default is not None:
            return default
        print("❌ This field is required. Please enter a value.")
        return get_input(prompt, type_func, default)

    try:
        if type_func == bool:
            return user_input.lower() in ['true', 't', 'y', 'yes', '1']
        return type_func(user_input)
    except ValueError:
        print(f"❌ Input type error. Expected a {type_func.__name__}. Please try again.")
        return get_input(prompt, type_func, default)


def collect_list_items(prompt_label):
    """Collects individual string identifiers one-by-one until an empty line is provided."""
    print(f"\n--- Adding items for list: {prompt_label} ---")
    print("Type an item and press Enter. Press Enter on a completely blank line when finished.")
    items = []
    while True:
        user_input = input(f"Enter item (Current list size: {len(items)}): ").strip()
        if not user_input:
            break
        if user_input not in items:
            items.append(user_input)
            print(f"Added: '{user_input}'")
        else:
            print("⚠️ Already added.")
    return items


def build_conditions():
    """Builds the conditions dictionary for an action."""
    conditions = {}
    if get_input("\nDoes this have specific execution conditions? (y/n)", bool, False):
        print("Available rules: target_hp_below_pct, target_has_debuff, caster_has_buff, etc.")
        while True:
            key = get_input("Condition Key (or press Enter to finish)", str, "")
            if not key:
                break

            # Auto-detect if value should be a float or a string based on common rules
            if "pct" in key or "amount" in key:
                val = get_input(f"Value for '{key}'", float)
            elif "has_dot" in key:
                val = get_input(f"Value for '{key}' (true/false)", bool)
            else:
                val = get_input(f"Value for '{key}'", str)

            conditions[key] = val
            print(f"Added condition: {key} = {val}")
    return conditions


def build_action(is_nested=False, depth=0):
    """Builds a single action dictionary interactively, supporting recursive nesting."""
    prefix = "  " * depth + ("↪ " if is_nested else "")
    print(f"\n{prefix}--- Building Action ---")

    action_type = get_input(
        f"{prefix}Action type ('damage', 'buff', 'debuff', 'resource_gain', 'cooldown_mod', 'dot', 'channel')",
        str).lower()
    action = {"action_type": action_type}

    action["delay"] = get_input(f"{prefix}Delay (seconds)", float, 0.0)

    if action_type == "damage":
        action["attack_type"] = get_input(f"{prefix}Attack Type (1=melee, 2=ranged, 3=force, 4=tech)", int, 1)
        action["damage_type"] = get_input(f"{prefix}Damage Type (1=kinetic, 2=energy, 3=elemental, 4=internal)", int, 1)

        if action["attack_type"] in [3, 4]:
            action["hand"] = "main"
        else:
            action["hand"] = get_input(f"{prefix}Hand ('main' or 'off')", str, "main")

        action["amp"] = get_input(f"{prefix}Amp", float, 0.0)
        action["coeff"] = get_input(f"{prefix}Coeff", float, 0.0)
        action["shp_min"] = get_input(f"{prefix}SHP Min", float, 0.0)
        action["shp_max"] = get_input(f"{prefix}SHP Max", float, 0.0)
        action["impact_delay"] = get_input(f"{prefix}Impact Delay", float, 0.0)

    elif action_type == "dot":
        action["tick_interval"] = get_input(f"{prefix}Tick Interval (seconds)", float, 1.0)
        action["duration"] = get_input(f"{prefix}Duration (seconds)", float, 15.0)
        action["ticks_remaining"] = get_input(f"{prefix}Ticks Remaining (99 for infinite)", int, 15)
        action["name"] = get_input(f"{prefix}Name (needed for overwrite)", str)
        action["effect_name"] = get_input(f"{prefix}Effect Name", str)

        action["tick_actions"] = []
        print(f"\n{prefix}--- Entering tick actions for DoT '{action['name']}' ---")
        while True:
            action["tick_actions"].append(build_action(is_nested=True, depth=depth + 1))
            if not get_input(f"{prefix}Add another tick action? (y/n)", bool, False):
                break

    elif action_type == "channel":
        action["channel_ticks"] = get_input(f"{prefix}Total Channel Ticks", int, 4)
        action["tick_interval"] = get_input(f"{prefix}Tick Interval (seconds)", float, 1.0)

        action["actions"] = []
        print(f"\n{prefix}--- Entering actions for Channel ---")
        while True:
            action["actions"].append(build_action(is_nested=True, depth=depth + 1))
            if not get_input(f"{prefix}Add another action to this channel? (y/n)", bool, False):
                break

    elif action_type == "buff":
        action["id"] = get_input(f"{prefix}Buff ID", int, 0)
        action["value"] = get_input(f"{prefix}Buff Value", float, 0.0)
        action["effect_name"] = get_input(f"{prefix}Effect Name", str)
        action["target_hp_threshold"] = get_input(f"{prefix}Target HP Threshold (0.0 for none)", float, 0.0)
        action["duration"] = get_input(f"{prefix}Duration (seconds)", float, 10.0)
        if req_tags := collect_list_items("Required Tags"):
            action["required_tags"] = req_tags

    elif action_type == "debuff":
        action["id"] = get_input(f"{prefix}Debuff ID", int, 0)
        action["value"] = get_input(f"{prefix}Debuff Value", float, 0.0)
        action["effect_name"] = get_input(f"{prefix}Effect Name", str)
        action["duration"] = get_input(f"{prefix}Duration (seconds)", float, 10.0)

    elif action_type == "resource_gain":
        action["value"] = get_input(f"{prefix}Amount of Resource Given", float, 0.0)

    elif action_type == "cooldown_mod":
        action["target_tags"] = collect_list_items("Target Tags to alter cooldown")
        action["reset"] = get_input(f"{prefix}Is the cooldown completely reset? (y/n)", bool, False)
        if not action["reset"]:
            action["value"] = get_input(f"{prefix}Cooldown reduction value (seconds)", float, 0.0)

    else:
        print(f"⚠️ Warning: Unrecognized action type '{action_type}'. Building as a generic empty action.")

    if global_conds := build_conditions():
        action["conditions"] = global_conds

    if action_tags := collect_list_items("Action Tags"):
        action["tags"] = action_tags

    # ============================================
    # 🟢 THE NESTED ACTION GATE (Recursion)
    # ============================================
    if get_input(f"\n{prefix}Does this [{action_type}] action have nested 'on_success_actions'? (y/n)", bool, False):
        action["on_success_actions"] = []
        print(f"\n{prefix}>>> Entering Nested 'on_success' Actions for [{action_type}] <<<")

        while True:
            child_action = build_action(is_nested=True, depth=depth + 1)
            action["on_success_actions"].append(child_action)

            if not get_input(f"{prefix}Add another nested action to this [{action_type}] parent? (y/n)", bool, False):
                break

        print(f"{prefix}<<< Finished Nested Actions for [{action_type}] >>>\n")

    return action


def main():
    print("=== SWTOR Simulator JSON Ability Builder ===")
    file_path = get_input("Target JSON file path (e.g., data/Abilities.json)", str, "data/Abilities.json")

    # Load existing db if it exists so we don't overwrite the whole file
    db = {}
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                db = json.load(f)
            print(f"Loaded existing database with {len(db)} entries.")
        except json.JSONDecodeError:
            print("Warning: Could not parse existing JSON. Starting fresh.")

    while True:
        lookup_key = get_input("\nEnter EXACT Ability Name string (e.g., 'SABER STRIKE')").upper()

        entry_data = {
            "name": get_input("Readable Name (e.g., 'Saber Strike')", str, lookup_key.title()),
            "cooldown": get_input("Cooldown (seconds)", float, 0.0),
            "triggers_gcd": get_input("Triggers GCD? (y/n)", bool, True)
        }

        if entry_data["triggers_gcd"]:
            entry_data["base_gcd"] = get_input("Base GCD pacing step time (seconds)", float, 1.5)

        entry_data["energy_cost"] = get_input(
            "Resource cost to cast (Note: If this holds a Channel, set base cost to 0.0)", float, 0.0
        )

        # The new Charge System Logic
        max_charges = get_input("Maximum charges (enter 0 if ability does not use charges)", int, 0)
        if max_charges > 0:
            entry_data["max_charges"] = max_charges
            entry_data["recharge_time"] = get_input("Recharge time per charge (seconds)", float, entry_data["cooldown"])

        if global_tags := collect_list_items("Global Ability Context Tags"):
            entry_data["tags"] = global_tags

        if global_conds := build_conditions():
            entry_data["conditions"] = global_conds

        entry_data["actions"] = []
        print("\n--- Main Actions Array ---")
        while True:
            entry_data["actions"].append(build_action())
            if not get_input("\nWould you like to add another sub-action effect to this ability? (y/n)", bool, False):
                break

        db[lookup_key] = entry_data

        # Safely create directory if missing and save
        os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else ".", exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2)

        print(f"✅ {lookup_key} successfully saved to {file_path}")

        if not get_input("\nBuild another ability? (y/n)", bool, True):
            break


if __name__ == "__main__":
    main()