import json
import os

# Locate or create the local abilities database file
FILE_PATH = "abilities.json"


def load_database():
    if os.path.exists(FILE_PATH):
        try:
            with open(FILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("⚠️ Warning: abilities.json was corrupted or empty. Starting fresh.")
            return {}
    return {}


def save_database(db):
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2)
    print(f"\n✅ Database successfully updated and written to '{FILE_PATH}'!")


def get_float(prompt, default=0.0):
    val = input(f"{prompt} [{default}]: ").strip()
    return float(val) if val else default


def get_int(prompt, default=0):
    val = input(f"{prompt} [{default}]: ").strip()
    return int(val) if val else default


def get_bool(prompt):
    val = input(f"{prompt} (y/n): ").strip().lower()
    return val == 'y'


def collect_ability_restrictions():
    """Handles hard gating requirements at the top level of the ability."""
    restrictions = {}
    if not get_bool("Does this ability itself have casting restrictions/thresholds?"):
        return restrictions

    print("\n--- Available Ability Restrictions ---")
    print("1. target_hp_below_pct")
    print("2. target_has_debuff")
    print("3. caster_requires_buff")

    choice = input("Select restriction type number (leave blank to skip): ").strip()

    if choice == "1":
        restrictions["target_hp_below_pct"] = get_float("Enter target HP threshold float (e.g., 0.30)")
    elif choice == "2":
        restrictions["target_has_debuff"] = input("Enter required target debuff name string: ").strip()
    elif choice == "3":
        restrictions["caster_requires_buff"] = input("Enter required caster buff name string: ").strip()

    return restrictions


def collect_conditions():
    """Handles execution pipeline conditions embedded inside individual actions."""
    conditions = {}
    if not get_bool("Add validation conditions to this action?"):
        return conditions

    print("\n--- Available Action Condition Rules ---")
    print(
        "1. exact_dot_amount\n2. has_dot\n3. has_debuff\n4. has_buff\n5. target_hp_below_pct\n6. does_not_have_debuff")

    choice = input("Select condition type number: ").strip()

    if choice == "1":
        conditions["exact_dot_amount"] = True
        conditions["required_count"] = get_int("Enter required_count")
    elif choice == "2":
        conditions["has_dot"] = True
    elif choice == "3":
        conditions["has_debuff"] = input("Enter target debuff name string: ").strip()
    elif choice == "4":
        conditions["has_buff"] = input("Enter caster buff name string: ").strip()
    elif choice == "5":
        conditions["target_hp_below_pct"] = get_float("Enter HP threshold float (e.g. 0.30)")
    elif choice == "6":
        conditions["does_not_have_debuff"] = input("Enter target debuff name to avoid: ").strip()

    return conditions


def run_wizard():
    print("==================================================")
    print("      SWTOR SIMULATOR: DATA ENTRY WIZARD          ")
    print("==================================================")

    db = load_database()

    ability_key = input("Ability ID Key (e.g., 'Thrash'): ").strip()
    if not ability_key:
        print("❌ Ability Key cannot be blank. Exiting.")
        return

    name = input(f"Ability Display Name (e.g., 'Thrash'): ").strip()
    energy_cost = get_int("Energy / Force Resource Cost", default=0)
    cooldown = get_float("Ability Cooldown (seconds)", default=0.0)

    # NEW: Top-Level Ability Restrictions Checklist
    ability_restrictions = collect_ability_restrictions()

    triggers_gcd = get_bool("Does this ability trigger the Global Cooldown?")
    base_gcd = get_float("Base GCD window", default=1.5) if triggers_gcd else 1.5

    ability_blueprint = {
        "name": name,
        "energy_cost": energy_cost,
        "cooldown": cooldown,
        "restrictions": ability_restrictions,  # Embedded directly at the outer layer
        "triggers_gcd": triggers_gcd,
        "base_gcd": base_gcd,
        "actions": []
    }

    adding_actions = True
    while adding_actions:
        print(f"\n--- Configuring Action #{len(ability_blueprint['actions']) + 1} ---")
        action_type = input("Action Type (direct_hit / dot / buff / debuff): ").strip().lower()

        action = {
            "type": action_type
        }

        # 1. DIRECT DAMAGE ROUTING WINDOW
        if action_type in ["damage", "direct_hit"]:
            action["delay"] = get_float("Action execution delay offset (seconds)")
            attack_type = get_int("Attack Type (1=Melee, 2=Ranged, 3=Force, 4=Tech)", default=1)
            action["attack type"] = attack_type

            # Dynamic Gating Constraint Checklist (No damage type for Melee/Ranged)
            if attack_type in [1, 2]:
                print("   ℹ️ Melee/Ranged type selected: Automatically skipping damage type field.")
            else:
                action["damage type"] = get_int("Damage Type (1=Kinetic, 2=Energy, 3=Elemental, 4=Internal)", default=1)

            action["coeff"] = get_float("Ability Scaling Coefficient (coeff)")
            action["amp"] = get_float("Amount Modifier Percent (amp)")
            action["shp_min"] = get_float("Standard Health Percent Minimum (shp_min)")
            action["shp_max"] = get_float("Standard Health Percent Maximum (shp_max)")

            tags_input = input("Action Tags (comma-separated, e.g., 'direct, melee'): ").strip()
            action["tags"] = [t.strip() for t in tags_input.split(",")] if tags_input else []

        # 2. PERIODIC DOT ROUTING WINDOW (Bypasses top-level delay prompt)
        elif action_type == "dot":
            action["attack type"] = get_int("Attack Type (1=Melee, 2=Ranged, 3=Force, 4=Tech)", default=3)
            action["damage type"] = get_int("Damage Type (1=Kinetic, 2=Energy, 3=Elemental, 4=Internal)", default=1)
            action["coeff"] = get_float("Tick Scaling Coefficient (coeff)")
            action["amp"] = get_float("Tick Amount Modifier Percent (amp)")
            action["shp_min"] = get_float("Tick Standard Health Percent Min (shp_min)")
            action["shp_max"] = get_float("Tick Standard Health Percent Max (shp_max)")
            action["interval"] = get_float("Time between ticks (interval)")
            action["total_ticks"] = get_int("Total number of periodic iterations")

            # Nested delay check inside instant tick configuration gate
            action["instant_tick"] = get_bool("Does this DoT tick instantly on application?")
            if action["instant_tick"]:
                action["instant_tick_delay"] = get_float("Instant tick compensation delay (instant_tick_delay)")

            tags_input = input("DoT Tags (comma-separated): ").strip()
            action["tags"] = [t.strip() for t in tags_input.split(",")] if tags_input else []

        # 3. CASTER STAT BUFF WINDOW
        elif action_type == "buff":
            action["delay"] = get_float("Action execution delay offset (seconds)")
            action["id"] = get_int("Effect Tracking ID (id matches your EFFECTS database registry)")
            action["effect_name"] = input("Unique Effect Name Identifier (effect_name): ").strip()
            action["stat_name"] = input("Stat to modify (stat_name, e.g., 'Critical Chance'): ").strip()
            action["value"] = get_float("Modifier Value (value)")
            action["duration"] = get_float("Buff active lifespan duration")
            action["affected_by_cdr"] = get_bool("Is this buff duration compressed by Alacrity/CDR?")

        # 4. TARGET DEBUFF WINDOW
        elif action_type == "debuff":
            action["delay"] = get_float("Action execution delay offset (seconds)")
            action["id"] = get_int("Effect Tracking ID (id matches your EFFECTS database registry)")
            action["effect_name"] = input("Unique Target Debuff Name (effect_name): ").strip()
            action["stat_name"] = input("Stat to modify (stat_name, e.g., 'Armor Debuff'): ").strip()
            action["value"] = get_float("Modifier Value (value)")
            action["duration"] = get_float("Debuff active lifespan duration")

        # 5. CONDITIONS PIPELINE (Includes the new option 6)
        conds = collect_conditions()
        if conds:
            action["conditions"] = conds

        ability_blueprint["actions"].append(action)
        adding_actions = get_bool("\nAdd another action block to this ability configuration?")

    # Save to file
    db[ability_key] = ability_blueprint
    save_database(db)


if __name__ == "__main__":
    while True:
        run_wizard()
        if not get_bool("\nConfigure another separate ability entry?"):
            print("Wizard closing. Happy parsing!")
            break