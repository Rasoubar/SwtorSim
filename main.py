import random
from src.swtorsim.cli import select_loadout_paths, prompt_optional_choices, prompt_run_mode
from src.swtorsim.config_load import load_rotation_from_json, build_complete_loadout
from src.swtorsim.tester import Tester


def run():
    """Interactively prompts for loadout choices, loads databases, and executes simulation test mode."""

    run_mode, iterations = prompt_run_mode()

    # 1. Prompt user for class/spec/build/rotation selections
    base_dir, stats_config, rotation_path = select_loadout_paths()

    # 2. Prompt user for optional gear/tree choices (relics, tacticals, tree, implants)
    raw_opt_abilities, raw_opt_buffs, raw_opt_procs = prompt_optional_choices(base_dir)


    # 3. Load rotation and build full database loadout
    rotation_config = load_rotation_from_json(rotation_path)
    abilities_db, procs_db, buffs_db = build_complete_loadout(
        base_dir, raw_opt_abilities, raw_opt_buffs, raw_opt_procs
    )

    # 4. Initialize and run tester

    tester = Tester(
        rotation_config=rotation_config,
        stats_config=stats_config,
        abilities_db=abilities_db,
        procs_db=procs_db,
        buffs_db=buffs_db,
        duration=1000,
        dummy_hp=10000000
    )

    if run_mode == "TEST":
        tester.run_test()
    elif run_mode == "BATCH":
        tester.run_monte_carlo(iterations=iterations)

if __name__ == "__main__":
    # Fixed seed applied at entry point for reproducible test runs
    random.seed(42)
    run()