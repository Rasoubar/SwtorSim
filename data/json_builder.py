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
            print(f"   Saved: '{user_input}'")
        else:
            print("   ⚠️ This item has already been added to the list.")

    return items if items else None


def build_conditions():
    """Builds a condition dictionary checking health thresholds, buffs, or debuffs."""
    conditions = {}
    print("\n--- Optional Special Conditions (Skip any by typing 'none') ---")

    target_hp = get_input("Only trigger if target health is below percentage? (e.g. 0.3 for 30%, or 'none')", str,
                          "none")
    if target_hp != "none":
        conditions["target_hp_below_pct"] = float(target_hp)

    has_debuff = get_input("Must the target have a specific debuff active? (Enter name, or 'none')", str, "none")
    if has_debuff != "none":
        conditions["target_has_debuff"] = has_debuff

    caster_buff = get_input("Must the player have a specific buff active? (Enter name, or 'none')", str, "none")
    if caster_buff != "none":
        conditions["caster_has_buff"] = caster_buff

    exact_dots = get_input("Require an exact number of active DoTs on the target? (Enter number, or 'none')", str,
                           "none")
    if exact_dots != "none":
        conditions["exact_dot_amount"] = int(exact_dots)

    return conditions if conditions else None


def build_action():
    """Builds an individual effect dictionary processed by the action router."""
    print("\n--- Adding Effect/Impact ---")
    action_types = {1: "damage", 2: "dot", 3: "buff", 4: "resource_gain", 5: "cooldown_mod"}
    print(
        "Choose the effect type:\n 1: Direct Damage\n 2: Damage over Time (DoT)\n 3: Temporary Buff\n 4: Resource/Force Gain\n 5: Cooldown Modification")
    choice = get_input("Enter your choice number", int, 1)
    action_type = action_types.get(choice, "damage")

    action = {"action_type": action_type}

    if action_type == "damage":
        action.update({
            "attack_type": get_input("Attack Type (1 = Melee, 3 = Force)", int, 1),
            "damage_type": get_input("Damage Type (1 = Kinetic, 2 = Energy, 3 = Elemental, 4 = Internal)", int, 1),
            "amp": get_input("Jedipedia Damage Multiplier (Amp)", float, 0.0),
            "coeff": get_input("Jedipedia Standard Scaling Factor (Coeff)", float, 0.0),
            "shp_min": get_input("Jedipedia Bonus Damage Min (Standard Health Percent Min)", float, 0.0),
            "shp_max": get_input("Jedipedia Bonus Damage Max (Standard Health Percent Max)", float, 0.0),
            "delay": get_input("Delay after cast finishes before calculating damage (seconds)", float, 0.0),
            "impact_delay": get_input("Animation land delay before damage hits target (seconds)", float, 0.2)
        })
        if tags := collect_list_items("Damage Context Tags"):
            action["tags"] = tags

    elif action_type == "dot":
        action.update({
            "id": get_input("Unique numerical ID for this status tracking", int),
            "effect_name": get_input("Display Name of the DoT debuff", str),
            "interval": get_input("Time between ticks (seconds)", float, 1.0),
            "total_ticks": get_input("Total number of times the DoT will tick", int, 6)
        })
        if tags := collect_list_items("DoT Context Tags"):
            action["tags"] = tags

    elif action_type == "buff":
        action.update({
            "id": get_input("Unique numerical ID for this status tracking", int),
            "value": get_input("Stat increase percentage/multiplier value", float, 0.0),
            "duration": get_input("How long does the buff last? (seconds)", float, 15.0),
            "effect_name": get_input("Display Name of the Buff", str),
            "charges": get_input("Starting/gained number of stacks/charges", int, 1),
            "max_charges": get_input("Maximum stack capacity", int, 1),
            "affected_by_cdr": get_input("Is this buff duration reduced by your cooldown stats?", bool, False)
        })
        if req_tags := collect_list_items("Ability Tags this Buff affects"):
            action["required_tags"] = req_tags

    elif action_type == "resource_gain":
        action.update({
            "value": get_input("Amount of Force/Resource restored", float, 1.0)
        })

    elif action_type == "cooldown_mod":
        action.update({
            "reset": get_input("Does this completely reset the cooldown?", bool, True)
        })
        if not action["reset"]:
            action["value"] = get_input("Amount of time subtracted from cooldown (seconds)", float, 1.5)
        if target_tags := collect_list_items("Target Ability Tags to reduce cooldown on"):
            action["target_tags"] = target_tags

    if conds := build_conditions():
        action["conditions"] = conds

    return action


def main():
    print("=== SWTOR Combat Simulator Data Generator ===")
    file_path = input("Enter path to JSON file (e.g. data/HatredAssassinAbilities.json): ").strip()

    db = {}
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                db = json.load(f)
            print(f"📖 Loaded {len(db)} existing abilities from file successfully.")
        except Exception:
            print("⚠️ Could not parse existing file. Creating a fresh database.")

    lookup_key = input("Enter Ability Key (CAPSLOCKED, e.g. 'LEECHING_STRIKE'): ").strip().upper()

    print("\n--- Base Ability Configuration ---")
    entry_data = {
        "name": get_input("Display Name of the ability", str, lookup_key.replace("_", " ").capitalize()),
        "cooldown": get_input("Cooldown time (seconds, use 0 for none)", float, 0.0),
        "triggers_gcd": get_input("Does this trigger the Global Cooldown (GCD)?", bool, True)
    }

    if entry_data["triggers_gcd"]:
        entry_data["base_gcd"] = get_input("Base GCD pacing step time (seconds)", float, 1.5)

    entry_data["energy_cost"] = get_input("Force cost to cast this ability", float, 0.0)
    max_charges = get_input("Maximum charges (enter 0 if ability does not use charges)", int, 0)
    if max_charges > 0:
        entry_data["max_charges"] = max_charges
        entry_data["recharge_time"] = get_input("Recharge time per charge (seconds)", float, entry_data["cooldown"])

    if global_tags := collect_list_items("Global Ability Context Tags"):
        entry_data["tags"] = global_tags

    if global_conds := build_conditions():
        entry_data["conditions"] = global_conds

    entry_data["actions"] = []
    while True:
        entry_data["actions"].append(build_action())
        if not get_input("\nWould you like to add another sub-action effect to this ability?", bool, False):
            break

    db[lookup_key] = entry_data

    os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else ".", exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Done! The ability has been added/updated under key: '{lookup_key}'")


if __name__ == "__main__":
    main()