import json
import os


def get_input(prompt, type_func=str, default=None):
    """Helper function to handle inputs, defaults, and data types."""
    default_str = f" [Default: {default}]" if default is not None else " [Required]"
    user_input = input(f"{prompt}{default_str}: ").strip()
    if not user_input:
        if default is not None:
            return default
        print("❌ This field is required. Please try again.")
        return get_input(prompt, type_func, default)
    try:
        if type_func == bool:
            return user_input.lower() in ['true', 't', 'y', 'yes', '1']
        return type_func(user_input)
    except ValueError:
        print(f"❌ Invalid format. Expected {type_func.__name__}. Try again.")
        return get_input(prompt, type_func, default)


def collect_tags_interactively(prompt_label):
    """Collects tags one by one until the user presses Enter on an empty line."""
    print(f"\n--- Entering tags for {prompt_label} ---")
    print("Type a tag and press Enter. Press Enter on an empty line when finished.")
    tags = []
    while True:
        tag_input = input(f"Add tag (Current count: {len(tags)}): ").strip()
        if not tag_input:
            break
        if tag_input not in tags:
            tags.append(tag_input)
            print(f"Added tag: '{tag_input}'")
        else:
            print("⚠️ Tag already added.")
    return tags


def build_conditions():
    """Builds the optional conditions block for damage actions."""
    if not get_input("Add conditions to this action? (y/n)", bool, False):
        return None

    conditions = {}
    if get_input("Does it require a DOT? (y/n)", bool, False):
        conditions["has_dot"] = True
        if get_input("Does it require an exact DOT amount? (y/n)", bool, False):
            conditions["exact_dot_amount"] = True
            conditions["required_count"] = get_input("Required count of DOTs", int, 1)
    return conditions


def build_action():
    """Builds a single action dictionary interactively."""
    action_type = get_input("Action type ('damage', 'buff', etc.)", str).lower()
    action = {"action_type": action_type}

    if action_type == "damage":
        action["attack_type"] = get_input("Attack Type (1=Melee, 2=Ranged, 3=Force/Tech)", int)
        action["damage_type"] = get_input("Damage Type (1=Weapon, 2=Energy, 3=Kinetic, 4=Internal/Elemental)", int)
        action["amp"] = get_input("Developer Multiplier Modifier (amp)", float, 0.0)
        action["coeff"] = get_input("Damage Coefficient multiplier", float)
        action["shp_min"] = get_input("Standard Health Percent Min (shp_min)", float)
        action["shp_max"] = get_input("Standard Health Percent Max (shp_max)", float)
        action["delay"] = get_input("Action execution timing delay", float, 0.0)
        action["impact_delay"] = get_input("Visual impact travel timing delay", float, 0.0)

        # 🟢 Overhauled tag list compilation pattern
        action["tags"] = collect_tags_interactively("Damage Action")

        conds = build_conditions()
        if conds:
            action["conditions"] = conds

    elif action_type == "buff":
        action["effect_name"] = get_input("Buff target unique effect name", str)
        action["stat_name"] = get_input("Target modification key identifier string", str)
        action["value"] = get_input("Modification metric value multiplier", float)
        action["duration"] = get_input("Buff active lifespan frame duration", float)
        action["max_stacks"] = get_input("Maximum stack registry cap", int, 1)

    return action


def build_ability():
    """Builds a full active ability tree configuration block."""
    ability_name = get_input("Ability Name (e.g. THRASH)", str).upper()

    ability_data = {
        "name": get_input("Display name text", str, ability_name.capitalize()),
        "cooldown": get_input("Ability baseline tracking cooldown", float, 0.0),
        "triggers_gcd": get_input("Does it respect/trigger the Global Cooldown? (y/n)", bool, True),
        "base_gcd": get_input("Baseline GCD frame interval", float, 1.5),
        "energy_cost": get_input("Resource optimization cost reduction metric", float, 0.0),
        "restrictions": {},
        "actions": []
    }

    # Add dynamic execution requirements if necessary
    if get_input("Add target health conditions? (y/n)", bool, False):
        ability_data["restrictions"]["target_hp_below_pct"] = get_input(
            "Target health percentage boundary threshold (0.X format)", float)

    # Loop to collect underlying hits/actions
    num_actions = get_input("How many actions/strikes does this ability perform?", int, 1)
    for i in range(num_actions):
        print(f"\n--- Configuring Action {i + 1} of {num_actions} ---")
        ability_data["actions"].append(build_action())

    return {ability_name: ability_data}


def build_proc():
    """Builds a passive tracking observer proc condition blueprint."""
    proc_key = get_input("Proc Key Identifier (e.g. LIGHTNING_CHARGE)", str).upper()
    proc_name = get_input("Display text description name", str, proc_key.replace("_", " ").title())

    proc_data = {
        "proc_name": proc_name,
        "trigger": get_input("Trigger window frame descriptor event ('hit' or 'crit')", str).lower(),
    }

    req_tag = input("Required tag constraint metric (leave blank if none): ").strip()
    if req_tag:
        proc_data["required_tag"] = req_tag

    proc_data["chance"] = get_input("Proc activation probability chance scalar (0.X format)", float, 1.0)
    proc_data["icd"] = get_input("Internal tracking layout Cooldown (ICD)", float, 0.0)
    proc_data["affected_by_cdr"] = get_input("Is ICD affected by character CDR math? (y/n)", bool, False)

    print("\nDefine the operational sub-action sequence this proc fires:")
    proc_data["action"] = build_action()

    return {proc_key: proc_data}


def build_permanent_buff():
    """🟢 NEW: Builds a minimalist permanent baseline passive buff object mapping."""
    buff_key = get_input("Permanent Buff Key Identifier (e.g. MARK_OF_THE_ASSASSIN)", str).upper()

    print("\n--- Configuring Permanent Baseline Stance / Passive Aura ---")
    buff_data = {
        "id": get_input("Jedipedia structural attribute identifier integer mapping (id)", int),
        "value": get_input("Modification metric property value (Use 0.X format if percent modification)", float)
    }

    # 🟢 Overhauled tag list compilation pattern for permanent buffs
    buff_data["required_tags"] = collect_tags_interactively("Permanent Buff")

    effect_name = input("Unique structural display effect name (leave blank to auto-generate from key): ").strip()
    buff_data["effect_name"] = effect_name if effect_name else None

    if get_input("Does this buff require a target execution HP threshold? (y/n)", bool, False):
        buff_data["target_hp_threshold"] = get_input("Execute health percentage tracking boundary (0.X format)", float)
    else:
        buff_data["target_hp_threshold"] = None

    return {buff_key: buff_data}


def main():
    print("Welcome to the SwtorSim JSON Structure Generator CLI!")
    print("1. Create an Ability Blueprint Collection")
    print("2. Create a Combat Observer Passive Proc Rule")
    print("3. Create a Permanent Background Passive Buff / Stance 🟢")
    choice = get_input("What system structure layout do you want to compile? (1, 2, or 3)", int, 1)

    if choice == 1:
        final_json = build_ability()
    elif choice == 2:
        final_json = build_proc()
    elif choice == 3:
        final_json = build_permanent_buff()
    else:
        print("❌ Invalid menu choice index logic.")
        return

    print("\n================ GENERATED JSON ================")
    print(json.dumps(final_json, indent=2))
    print("=================================================")

    # Option to save file locally
    if get_input("Save this configured payload snippet to disk? (y/n)", bool, True):
        filename = get_input("Provide clean output path/filename (e.g. data/Buffs.json)", str)

        # Simple appending logic check if file exists to grow dictionaries cleanly
        existing_data = {}
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            except Exception:
                pass

        # Merge new definition mapping node keys
        existing_data.update(final_json)

        try:
            os.makedirs(os.path.dirname(filename), exist_ok=True)
        except Exception:
            pass

        with open(filename, "a", encoding="utf-8") as f:
            json.dump(existing_data, f, indent=2)
        print(f"🟢 Successfully recorded and synchronized dataset nodes into: {filename}")


if __name__ == "__main__":
    main()