import random
from src.swtorsim.cli import (
    select_discipline_path,
    select_stats_path,
    select_rotation_path,
    load_discipline_fqns,
    prompt_optional_choices,
    prompt_run_mode,
)
from src.swtorsim.config_load import (
    load_complete_loadout,
    load_rotation_from_json,
    load_character_stats_from_json,
    load_permanent_effects_from_json,
)
from src.swtorsim.tester import Tester


def run():
    run_mode, iterations = prompt_run_mode()

    # 1. Selection prompts
    class_name, spec_name, spec_path = select_discipline_path()
    stats_path = select_stats_path()
    rotation_path = select_rotation_path(spec_name)

    # 2. Select baseline abilities and skill tree talents
    discipline_fqns = load_discipline_fqns(spec_path)

    # 3. Select tactical, implants, and relics
    selected_gear_fqns, selected_relic_paths = prompt_optional_choices(class_name)
    all_selected_fqns = discipline_fqns + selected_gear_fqns

    # 4. Load blueprints, stats, rotation, and debuffs
    loadout_blueprints = load_complete_loadout(all_selected_fqns, selected_relic_paths)
    stats_config = load_character_stats_from_json(class_name, stats_path)
    rotation_config = load_rotation_from_json(rotation_path)
    debuff_module = load_permanent_effects_from_json("data/DebuffModule.json")

    # 5. Initialize and run tester
    tester = Tester(
        rotation_config=rotation_config,
        stats_config=stats_config,
        loadout_blueprints=loadout_blueprints,
        duration=1000,
        dummy_hp=10000000,
        debuff_module=debuff_module,
    )

    if run_mode == "TEST":
        tester.run_test()
    elif run_mode == "BATCH":
        tester.run_monte_carlo(iterations=iterations)


if __name__ == "__main__":
    random.seed(42)
    run()