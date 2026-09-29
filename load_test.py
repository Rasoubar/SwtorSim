import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.swtorsim.cli import (
    select_discipline_path,
    select_stats_path,
    select_rotation_path,
    load_discipline_fqns,
    prompt_optional_choices,
)
from src.swtorsim.config_load import (
    load_complete_loadout,
    load_character_stats_from_json,
    load_rotation_from_json,
    load_permanent_effects_from_json,
)
from src.swtorsim.setup import prepare_simulation


def test_full_interactive_load():
    print("=" * 80)
    print("  FULL LOADOUT INTERACTIVE VERIFICATION")
    print("=" * 80)

    # 1. Interactive Prompts
    class_name, spec_name, spec_path = select_discipline_path()
    stats_path = select_stats_path()
    rotation_path = select_rotation_path(spec_name)

    # 2. Discipline & Tree Abilities
    discipline_fqns = load_discipline_fqns(spec_path)

    # 3. Gear Prompts (Tacticals, Implants, Relics)
    selected_gear_fqns, selected_relic_paths = prompt_optional_choices(class_name)
    all_selected_fqns = discipline_fqns + selected_gear_fqns

    print("\n" + "-" * 80)
    print(f"📦 Resolving files from disk...")
    print(f"   Selected FQNs (Discipline + Gear) : {len(all_selected_fqns)}")
    print(f"   Selected Relic Paths              : {len(selected_relic_paths)}")
    print("-" * 80)

    # 4. Load Complete Blueprint Database
    loadout_blueprints = load_complete_loadout(
        selected_fqns=all_selected_fqns,
        selected_relic_paths=selected_relic_paths,
        parsed_dir="data/extractor/parsed"
    )

    # 5. Load Real Stats, Rotation, and Debuffs
    stats_config = load_character_stats_from_json(class_name, stats_path)
    rotation_config = load_rotation_from_json(rotation_path)
    debuff_module = load_permanent_effects_from_json("data/DebuffModule.json")

    # 6. Initialize Simulation Entities
    sim, player, target = prepare_simulation(
        rotation_config=rotation_config,
        stats_config=stats_config,
        loadout_blueprints=loadout_blueprints,
        dummy_hp=10000000,
        debuff_module=debuff_module
    )

    # 7. Summary
    pool_name = getattr(player.resource, "name", type(player.resource).__name__)
    max_res = getattr(player.resource, "max_resource", getattr(player.resource, "max_value", "N/A"))
    steps_count = len(rotation_config) if isinstance(rotation_config, list) else len(getattr(player.rotation, "step_list", []))

    print("\n" + "=" * 80)
    print("📊 LOADOUT INITIALIZATION SUMMARY")
    print("=" * 80)
    print(f"Player Name        : {player.name}")
    print(f"Resource Pool      : {pool_name} (Max: {max_res})")
    print(f"Target Dummy HP    : {target.hp:,} (Armor: {target.stats.get('Armor')})")
    print(f"Rotation Steps     : {steps_count} steps configured")
    print(f"Active Lookups     : {len(player.ability_db)} total keys registered in ability_db")
    print(f"Passive Blueprints : {len(player.passive_blueprints)} stored blueprints")

    # Deduplicate active Ability instances for printing
    unique_active_abilities = {id(abl): abl for abl in player.ability_db.values()}.values()
    sorted_active = sorted(unique_active_abilities, key=lambda a: getattr(a, "name", str(a)))

    # 8. Print Active Abilities
    print("\n" + "=" * 80)
    print(f"⚔️  ACTIVE ABILITIES INSTANTIATED ({len(sorted_active)} unique abilities)")
    print("=" * 80)
    for abl in sorted_active:
        name = getattr(abl, "name", "Unknown Ability")
        fqn = getattr(abl, "fqn", "N/A")
        cost = getattr(abl, "energy_cost", 0.0)
        cd = getattr(abl, "cooldown", 0.0)
        gcd = getattr(abl, "base_gcd", 1.5)
        eff_count = len(getattr(abl, "effects", {}))
        entry_ids = getattr(abl, "entry_effect_ids", [])
        tags = getattr(abl, "tags", [])

        print(f" • {name:<28} | CD: {cd:>4.1f}s | GCD: {gcd:>3.1f}s | Cost: {cost:>4.1f} | Effects: {eff_count:>2} | Entry IDs: {entry_ids}")
        print(f"   FQN : {fqn}")
        if tags:
            print(f"   Tags: {list(tags)}")
        print()

    # 9. Print Passive Blueprints
    sorted_passives = sorted(player.passive_blueprints.values(), key=lambda bp: bp.name)

    print("=" * 80)
    print(f"🛡️  PASSIVE BLUEPRINTS STORED ({len(sorted_passives)} blueprints)")
    print("=" * 80)
    for bp in sorted_passives:
        print(f" • {bp.name:<32} | Type: {bp.type:<7} | Effects: {len(bp.effects):>2} | Entry IDs: {bp.entry_effect_ids}")
        print(f"   FQN : {bp.fqn}")
        if bp.tags:
            print(f"   Tags: {list(bp.tags)}")
        print()

    # 10. Verification Check for Active Abilities Dual-Indexing
    missing_keys = []
    for fqn, bp in loadout_blueprints.items():
        if bp.type == "active" and not fqn.startswith("tal."):
            name_key = bp.name.lower().replace(" ", "_")
            if fqn not in player.ability_db or name_key not in player.ability_db:
                missing_keys.append((fqn, name_key))

    if missing_keys:
        print(f"❌ FAILED: Missing dual-index keys: {missing_keys}")
    else:
        print("✅ Dual-indexing verified across all active abilities.")

    print("\n" + "=" * 80)
    print("🎉 FULL LOADOUT VERIFICATION COMPLETE!")
    print("=" * 80)


if __name__ == "__main__":
    test_full_interactive_load()