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


def collect_list_items(prompt_label):
    """Collects individual strings one-by-one into an array until given an empty line."""
    print(f"\n--- Entering array values for {prompt_label} ---")
    print("Type a value and press Enter. Press Enter on an empty line when finished.")
    items = []
    while True:
        user_input = input(f"Add item (Current count: {len(items)}): ").strip()
        if not user_input:
            break
        if user_input not in items:
            items.append(user_input)
            print(f"Added: '{user_input}'")
        else:
            print("⚠️ Already added.")
    return items


def build_restrictions():
    """Builds the strict structural restrictions block for abilities."""
    if not get_input("Add restrictions to this item? (y/n)", bool, False):
        return {}

    restrictions = {}

    if get_input("Does it require target health conditions? (y/n)", bool, False):
        pct_val = get_input("Target health percentage threshold (0.X format)", float)

        if get_input("   Add bypass if buff active? (y/n)", bool, False):
            restrictions["target_hp_below_pct"] = {
                "pct": pct_val,
                "bypass_if_buff_active": collect_list_items("Bypass Buff List")
            }
        else:
            restrictions["target_hp_below_pct"] = pct_val

    if get_input("Does it require the target to have a debuff? (y/n)", bool, False):
        restrictions["target_has_debuff"] = collect_list_items("Target Debuff List")

    if get_input("Does it require the caster to have a buff? (y/n)", bool, False):
        restrictions["caster_has_buff"] = collect_list_items("Caster Buff List")

    return restrictions


def build_conditions():
    """Builds the conditional object logic block matching the CONDITION_REGISTRY keys."""
    if not get_input("Add conditions to this item? (y/n)", bool, False):
        return {}

    conditions = {}

    # 1. target_hp_below_pct
    if get_input("Does it require target health conditions (target_hp_below_pct)? (y/n)", bool, False):
        conditions["target_hp_below_pct"] = get_input("Target health percentage threshold (0.X format)", float)

    # 2. target_has_debuff
    if get_input("Does it require a specific debuff on target (target_has_debuff)? (y/n)", bool, False):
        conditions["target_has_debuff"] = get_input("Debuff name", str)

    # 3. target_doesnt_have_debuff
    if get_input("Does it require the target to NOT have a debuff (target_doesnt_have_debuff)? (y/n)", bool, False):
        conditions["target_doesnt_have_debuff"] = get_input("Debuff name", str)

    # 4. caster_has_buff
    if get_input("Does it require a certain buff on caster (caster_has_buff)? (y/n)", bool, False):
        conditions["caster_has_buff"] = get_input("Buff name", str)

    # 5 & 6. exact_dot_amount / has_dot
    if get_input("Does it require a DOT condition? (y/n)", bool, False):
        if get_input("Does it require an exact DOT amount (exact_dot_amount)? (y/n)", bool, False):
            conditions["exact_dot_amount"] = get_input("Required count of DOTs", int, 1)
        else:
            conditions["has_dot"] = True

    return conditions


def build_action():
    """Builds a single action dictionary interactively."""
    # 🟢 UPDATED: Added 'dot' cleanly as an optional first-class action type choice
    action_type = get_input("Action type ('damage', 'buff', 'debuff', 'resource_gain', 'cooldown_mod', 'dot')",
                            str).lower()
    action = {"action_type": action_type}

    if action_type == "damage":
        action["attack_type"] = get_input("Attack Type (1=Melee, 2=Ranged, 3=Force, 4=Tech)", int)

        if action["attack_type"] in [3, 4]:
            action["damage_type"] = get_input("Damage Type (1=Kinetic, 2=Energy, 3=Elemental, 4=Internal)", int)
        else:
            if get_input("Include optional damage type? (y/n)", bool, False):
                action["damage_type"] = get_input("Damage Type (1=Kinetic, 2=Energy, 3=Elemental, 4=Internal)", int)

        action["amp"] = get_input("Amount Modifier Percent(amp)", float)
        action["coeff"] = get_input("Coefficient", float)
        action["shp_min"] = get_input("Standard Health Percent Min (shp_min)", float)
        action["shp_max"] = get_input("Standard Health Percent Max (shp_max)", float)
        action["delay"] = get_input("Action execution timing delay", float, 0.0)
        action["impact_delay"] = get_input("Impact timing delay", float, 0.0)
        tags = collect_list_items("Action Tags")
        if len(tags) != 0:
            action["tags"] = tags

    elif action_type in ["buff", "debuff"]:
        action["id"] = get_input("Jedipedia stat altered ID", int)
        action["value"] = get_input("Modification metric value multiplier", float)
        action["duration"] = get_input("Active lifespan duration", float)
        tags = collect_list_items("Effect Required Tags")
        if len(tags) != 0:
            action["required_tags"] = tags

        eff_name = input("Display text effect name (leave blank for auto-generate): ").strip()
        action["effect_name"] = eff_name if eff_name else None

        if get_input("Does the effect have charges that are not consumed? (y/n)", bool, False):
            action["charges"] = get_input("Charges to add", int)
            action["max_charges"] = get_input("Max charges", int)

        if get_input("Does effect have consumable charges? (y/n)", bool, False):
            action["consumable_charges"] = get_input("Consumable charges", int)

        # 🟢 ENFORCED: Always have charges if max_charges or consumable_charges are tracking
        if "max_charges" in action or "consumable_charges" in action:
            if "charges" not in action:
                action["charges"] = get_input("Initial baseline tracking charges (Required for caps)", int, 1)

        if get_input("Does it require target hp threshold filter? (y/n)", bool, False):
            action["target_hp_threshold"] = get_input("Target execute threshold (0.X format)", float)

        action["affected_by_cdr"] = get_input("Is the cooldown affected by CDR? (y/n)", bool, False)

    elif action_type == "resource_gain":
        action["value"] = get_input("Value gained", float)
        if get_input("Is there a resource generation delay? (y/n)", bool, False):
            action["delay"] = get_input("Delay duration seconds", float)

    elif action_type == "cooldown_mod":
        action["ability_name"] = get_input("Target ability string name", str)
        action["reset"] = get_input("Completely reset cooldown? (y/n)", bool, False)
        if not action["reset"]:
            action["value"] = get_input("How much time to take off the cooldown", float)

    # 🟢 NEW: Handles configuring nested DoT structural components recursively
    elif action_type == "dot":
        action["interval"] = get_input("Tick loop interval duration (seconds)", float, 3.0)
        action["total_ticks"] = get_input("Total baseline tick count", int, 4)
        action["instant_tick"] = get_input("Does this DoT tick instantly upon initial application? (y/n)", bool, False)
        if action["instant_tick"]:
            action["instant_tick_delay"] = get_input("Instant tick relative delay duration", float, 0.0)

        action["actions"] = []
        num_actions = get_input("How many separate conditional component actions does this DoT possess?", int, 1)
        for i in range(num_actions):
            print(f"\n--- Configuring DoT Conditional Component Action {i + 1} of {num_actions} ---")
            action["actions"].append(build_action())

    conds = build_conditions()
    if conds:
        action["conditions"] = conds

    return action


def build_ability():
    """Builds a full active ability tree configuration block."""
    ability_name = get_input("Ability Name (e.g. THRASH)", str).upper()

    ability_data = {
        "name": get_input("Display name text", str, ability_name.capitalize()),
        "cooldown": get_input("Ability cooldown", float, 0.0),
        "triggers_gcd": get_input("Does it respect/trigger the Global Cooldown? (y/n)", bool, True),
        "base_gcd": get_input("Baseline GCD", float, 1.5),
        "energy_cost": get_input("Energy cost", float, 0.0),
        "restrictions": {},
        "tags": [],
        "actions": []
    }

    ability_data["restrictions"] = build_restrictions()

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
        "trigger": get_input("Trigger frame event ('hit' or 'crit')", str).lower()
    }

    req_tag = input("Required hit tag constraint (leave blank if none): ").strip()
    if req_tag:
        proc_data["required_tag"] = req_tag

    proc_data["chance"] = get_input("Proc activation probability chance scalar (0.X format)", float, 1.0)
    proc_data["icd"] = get_input("Internal tracking Cooldown (ICD)", float, 0.0)
    proc_data["affected_by_cdr"] = get_input("Is ICD affected by character CDR math? (y/n)", bool, False)

    print("\nDefine the operational sub-action sequence this proc fires:")
    proc_data["action"] = build_action()

    print(f"\n--- Configuring Conditions for Proc: {proc_key} ---")
    proc_data["conditions"] = build_conditions()

    return {proc_key: proc_data}


def build_permanent_buff():
    """Builds a minimalist permanent baseline passive buff object mapping."""
    buff_key = get_input("Permanent Buff Key Identifier (e.g. MARK_OF_THE_ASSASSIN)", str).upper()

    print("\n--- Configuring Permanent Baseline Stance / Passive Aura ---")
    buff_data = {}
    buff_data["id"] = get_input("Jedipedia stat altered ID", int)
    buff_data["value"] = get_input("Modification metric value multiplier", float)
    tags = collect_list_items("Buff Required Tags")
    if len(tags) != 0:
        buff_data["required_tags"] = tags

    eff_name = input("Display text effect name (leave blank for auto-generate): ").strip()
    buff_data["effect_name"] = eff_name if eff_name else None

    if get_input("Does it require target hp threshold filter? (y/n)", bool, False):
        buff_data["target_hp_threshold"] = get_input("Target execute threshold (0.X format)", float)

    return {buff_key: buff_data}


def main():
    print("Welcome to the SwtorSim JSON Structure Generator CLI!")
    print("1. Create an Ability")
    print("2. Create a Proc")
    print("3. Create a Permanent Buff")
    # 🟢 REMOVED option 4 since DoT configurations now live seamlessly inside standard action arrays
    choice = get_input("What would you like to create? (1, 2, or 3)", int, 1)

    if choice == 1:
        final_json = build_ability()
    elif choice == 2:
        final_json = build_proc()
    elif choice == 3:
        final_json = build_permanent_buff()
    else:
        print("❌ Invalid menu choice.")
        return

    print("\n================ GENERATED JSON ================")
    print(json.dumps(final_json, indent=2))
    print("=================================================")

    if get_input("Save this configured payload snippet to disk? (y/n)", bool, True):
        filename = get_input("Provide clean output path/filename (e.g. data/Abilities.json)", str)

        existing_data = {}
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            except Exception:
                pass

        existing_data.update(final_json)

        try:
            os.makedirs(os.path.dirname(filename), exist_ok=True)
        except Exception:
            pass

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, indent=2)
        print(f"Successfully recorded and synchronized dataset nodes into: {filename}")


if __name__ == "__main__":
    main()