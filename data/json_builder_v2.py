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


def build_conditions(prefix=""):
    """Builds a dictionary of conditional rules dynamically."""
    conditions = {}
    print(f"\n{prefix}--- Conditions ---")
    if not get_input(f"{prefix}Do you want to add conditional rules? (y/n)", bool, False):
        return conditions

    while True:
        key = get_input(f"{prefix}Condition Key (e.g. target_hp_below_pct, or press Enter to finish)", str, "")
        if not key:
            break

        # Try to infer the value type based on the key
        if "pct" in key or "amount" in key or "above" in key or "below" in key:
            val = get_input(f"{prefix}  Condition Value (numeric)", float)
        else:
            val = get_input(f"{prefix}  Condition Value (string, e.g. buff name)", str)

        conditions[key] = val
        print(f"{prefix}  ✅ Added rule -> {key}: {val}")

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

def build_ability():
    """Builds a full active ability configuration block."""
    print("\n--- ⚔️ Building an Ability ---")
    ability_key = get_input("Top-Level Key (e.g., THRASH)", str).upper()

    entry_data = {"item_type": "ability"}
    entry_data["id"] = get_input("Internal ID", str, ability_key.lower().replace(" ", "_"))
    entry_data["name"] = get_input("Display Name", str, ability_key.replace("_", " ").title())
    entry_data["energy_cost"] = get_input("Resource Cost (0.0 if channel/free)", float, 0.0)
    entry_data["base_gcd"] = get_input("Base GCD (seconds)", float, 1.5)
    entry_data["cooldown"] = get_input("Cooldown (seconds)", float, 0.0)

    # --- Charge System Logic ---
    max_charges = get_input("Maximum charges (enter 0 if ability does not use charges)", int, 0)
    if max_charges > 0:
        entry_data["max_charges"] = max_charges
        entry_data["recharge_time"] = get_input("Recharge time per charge (seconds)", float, entry_data["cooldown"])

    # --- Tags ---
    if global_tags := collect_list_items("Global Ability Tags"):
        entry_data["tags"] = global_tags

    # --- Conditions ---
    if global_conds := build_conditions(prefix="  "):
        entry_data["conditions"] = global_conds

    # --- Actions Loop ---
    entry_data["actions"] = []
    print("\n--- Main Actions Array ---")
    while True:
        entry_data["actions"].append(build_action(is_nested= True, depth = 1))
        if not get_input("\nWould you like to add another main action to this ability? (y/n)", bool, False):
            break

    return ability_key, entry_data

def build_proc():
    """Builds a passive tracking observer proc condition blueprint."""
    print("\n--- ⚡ Building a Proc ---")
    proc_key = get_input("Top-Level Key (e.g., LIGHTNING_CHARGE)", str).upper()

    entry_data = {"item_type": "proc"}
    entry_data["proc_name"] = get_input("Display Name", str, proc_key.replace("_", " ").title())

    # Prompting for the specific trigger hooks your engine uses
    entry_data["trigger"] = get_input("Trigger condition (e.g., hit, cast, periodic, heal)", str, "hit").lower()

    # Required tags. If it's periodic, usually it won't need tags.
    if req_tags := collect_list_items(f"Required Tags to trigger '{entry_data['trigger']}'"):
        entry_data["required_tags"] = req_tags

    entry_data["chance"] = get_input("Proc Chance (0.0 to 1.0)", float, 1.0)
    entry_data["icd"] = get_input("Internal Cooldown (or Tick Interval if 'periodic')", float, 0.0)

    if entry_data["icd"] > 0.0:
        entry_data["affected_by_cdr"] = get_input("Is ICD affected by Alacrity/CDR? (y/n)", bool, False)

    # Global conditions that must be true for the proc to even attempt to fire
    if global_conds := build_conditions(prefix="  "):
        entry_data["conditions"] = global_conds

    # The payload (what the proc actually does)
    entry_data["actions"] = []
    print("\n--- Proc Actions Array ---")
    while True:
        entry_data["actions"].append(build_action(is_nested=True, depth = 1))
        if not get_input("\nWould you like to add another action to this proc? (y/n)", bool, False):
            break

    return proc_key, entry_data


def build_permanent_buff():
    """Builds a minimalist permanent baseline passive buff object mapping."""
    print("\n--- 🛡️ Building a Permanent Buff ---")
    buff_key = get_input("Top-Level Key (e.g., MARK_OF_THE_ASSASSIN)", str).upper()

    entry_data = {"item_type": "buff"}

    entry_data["id"] = get_input("Internal ID (numeric)", int, 1000)
    entry_data["effect_name"] = get_input("Display Name", str, buff_key.replace("_", " ").title())

    # What does this buff actually do?
    print("\n[Stat Modification]")
    entry_data["value"] = get_input("Value multiplier (e.g., 1.10 for 10% damage increase)", float, 1.0)

    # Are there restrictions on what this buff applies to?
    if req_tags := collect_list_items("Required Tags (e.g., 'melee', 'direct_damage' - leave empty if global)"):
        entry_data["required_tags"] = req_tags

    return buff_key, entry_data

def main():


    print("\n=============================================")
    print(" SwtorSim JSON Structure Generator CLI v2.1  ")
    print("=============================================")

    # --- 1. PATH RESOLUTION MENU ---
    print("\n--- File Destination Setup ---")
    char_class = get_input("Class Name (e.g., Assassin, Sorcerer)", str, "Assassin").title()
    char_spec = get_input("Spec Name (e.g., Hatred, Madness)", str, "Hatred").title()

    print("\nWhere does this data belong?")
    print("1. Permanent Base Element (Abilities, Permanent Buffs, Base Procs)")
    print("2. Optional Choice (Relics, Tree Talents, Tacticals)")
    storage_type = get_input("Select (1/2)", str, "1")

    # Initialize variables
    folder_path = f"{char_class}/{char_spec}"
    file_name = ""
    is_choice_format = False

    if storage_type == "1":
        print("\nSelect Base Category:")
        print("1. Abilities")
        print("2. Buffs")
        print("3. Procs")
        base_cat = get_input("Select (1/2/3)", str, "1")

        if base_cat == "1":
            folder_path += "/Abilities"
            file_name = "Abilities.json"
        elif base_cat == "2":
            folder_path += "/Buffs"
            file_name = "PermanentBuffs.json"
        else:
            folder_path += "/Procs"
            file_name = "BaseProcs.json"

    else:
        is_choice_format = True
        folder_path += "/Choices"
        print("\nSelect Optional Choice Category:")
        print("1. Relics")
        print("2. Tree")
        print("3. Tacticals")
        choice_cat = get_input("Select (1/2/3)", str, "3")

        if choice_cat == "1":
            file_name = "Relics.json"
        elif choice_cat == "2":
            file_name = "Tree.json"
        else:
            file_name = "Tacticals.json"

    file_path = f"{folder_path}/{file_name}"
    print(f"\n📂 Target File: {file_path}")

    # --- 2. DATA GENERATION PIPELINE ---
    print("\n--- Build Phase ---")
    print("What are we building?")
    print("1. Create an Ability")
    print("2. Create a Proc")
    print("3. Create a Permanent Buff")
    build_choice = get_input("Select (1/2/3)", str, "1")

    if build_choice == "2":
        lookup_key, entry_data = build_proc()
    elif build_choice == "3":
        lookup_key, entry_data = build_permanent_buff()
    else:
        lookup_key, entry_data = build_ability()

    # --- 3. FILE LOADING ---
    db = {}
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                db = json.load(f)
            except json.JSONDecodeError:
                print("⚠️ File exists but isn't valid JSON. Overwriting.")
                pass

    # --- 4. FORMATTING & APPENDING ---
    print("\n--- Optional Choice Formatting ---")
    is_choice_format = get_input("Format this as an Optional Choice (Relics/Tree/Tacticals)? (y/n)", bool, False)

    if is_choice_format:
        outer_key = get_input("Enter the Top-Level Choice Name (e.g., PenetratingDeath)", str, lookup_key)

        # Safely setup the To_add array if it doesn't exist
        if outer_key not in db:
            db[outer_key] = {"To_add": []}
        elif "To_add" not in db[outer_key]:
            db[outer_key]["To_add"] = []

        # LOOP: Keep adding effects until the user is done
        while True:
            db[outer_key]["To_add"].append({lookup_key: entry_data})
            print(f"  ✅ Wrapped '{lookup_key}' inside '{outer_key}' -> 'To_add'")

            if not get_input("\nDo you want to add ANOTHER effect to this choice? (y/n)", bool, False):
                break

            # If yes, jump back into the builder logic
            print("\nWhat else are we building for this choice?")
            print("1. Create an Ability\n2. Create a Proc\n3. Create a Permanent Buff")
            sub_choice = get_input("Select (1/2/3)", str, "1")
            if sub_choice == "2":
                lookup_key, entry_data = build_proc()
            elif sub_choice == "3":
                lookup_key, entry_data = build_permanent_buff()
            else:
                lookup_key, entry_data = build_ability()
    else:
        db[lookup_key] = entry_data
        print(f"  ✅ Added '{lookup_key}' directly to root.")

    # --- 5. DISK SAVING ---
    os.makedirs(folder_path, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2)
    print(f"\n🎉 Successfully saved to {file_path}")


if __name__ == "__main__":
    main()