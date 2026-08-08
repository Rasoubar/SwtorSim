import random
from src.swtorsim.cli import select_loadout_paths, prompt_optional_choices, prompt_run_mode
from src.swtorsim.config_load import load_rotation_from_json, build_complete_loadout, load_character_stats_from_json, \
    load_permanent_effects_from_json
from src.swtorsim.tester import Tester


def run():
    """Interactively prompts for loadout choices, loads databases, and executes simulation test mode."""
    #Adapted by gemini from previous code. And the comments are nice too ig.

    run_mode, iterations = prompt_run_mode()

    # 1. Prompt user for class/spec/build/rotation selections
    class_name, base_dir, stats_path, rotation_path = select_loadout_paths()

    # 2. Prompt user for optional gear/tree choices (relics, tacticals, tree, implants)
    raw_opt_abilities, raw_opt_effects, raw_opt_procs = prompt_optional_choices(base_dir)

    # 3. Load rotation, character stats and build full database loadout
    stats_config = load_character_stats_from_json(class_name, stats_path)
    rotation_config = load_rotation_from_json(rotation_path)
    abilities_db, procs_db, buffs_db = build_complete_loadout(
        base_dir, raw_opt_abilities, raw_opt_effects, raw_opt_procs
    )
    debuff_module = load_permanent_effects_from_json("data/DebuffModule.json")
    print(debuff_module)

    # 4. Initialize and run tester
    tester = Tester(
        rotation_config=rotation_config,
        stats_config=stats_config,
        abilities_db=abilities_db,
        procs_db=procs_db,
        buffs_db=buffs_db,
        duration=1000,
        dummy_hp=10000000,
        debuff_module=debuff_module
    )

    if run_mode == "TEST":
        tester.run_test()
    elif run_mode == "BATCH":
        tester.run_monte_carlo(iterations=iterations)

if __name__ == "__main__":
    random.seed(42)
    run()

