import json
import os
from src.swtorsim.config_load import (
    load_abilities_from_json,
    load_passives_from_json,
    load_permanent_buffs_from_json,
    optional_choices,
    load_rotation_from_json,
)
from src.swtorsim.batch import ParallelBatchRunner
from src.swtorsim.tester import SingleTester


def get_dynamic_loadout():
    print("=== SWTOR Combat Simulator Environment Setup ===")
    data_root = "data"

    print(f"\n📂 Available Classes inside '{data_root}':")
    class_options = sorted([
        d for d in os.listdir(data_root)
        if os.path.isdir(os.path.join(data_root, d))
    ])
    for idx, name in enumerate(class_options, 1):
        print(f"  [{idx}] {name}")

    class_idx = int(input("Select Class Number: ").strip()) - 1
    class_name = class_options[class_idx]

    class_dir = os.path.join(data_root, class_name)
    print(f"\n📂 Available Specializations inside '{class_name}':")
    spec_options = sorted([
        d for d in os.listdir(class_dir)
        if os.path.isdir(os.path.join(class_dir, d))
    ])
    for idx, name in enumerate(spec_options, 1):
        print(f"  [{idx}] {name}")

    spec_idx = int(input("Select Specialization Number: ").strip()) - 1
    spec_name = spec_options[spec_idx]

    base_dir = f"data/{class_name}/{spec_name}"


    builds_dir = f"{base_dir}/PlayerBuilds"
    print(f"\n📂 Available Stat Profiles in '{builds_dir}':")
    stat_options = sorted([f for f in os.listdir(builds_dir) if f.endswith(".json")])
    for idx, f_name in enumerate(stat_options, 1):
        print(f"  [{idx}] {f_name}")

    stat_idx = int(input("Select Stats Profile Number: ").strip()) - 1
    stats_choice = stat_options[stat_idx]
    stats_path = f"{builds_dir}/{stats_choice}"

    with open(stats_path, "r", encoding="utf-8") as f:
        stats_data = json.load(f)

    my_custom_character_stats = {
        "class_name": class_name,
        "stats": stats_data
    }

    rotations_dir = f"{base_dir}/Rotations"
    print(f"\n📂 Available Rotations in '{rotations_dir}':")
    rotation_options = sorted([f for f in os.listdir(rotations_dir) if f.endswith(".json")])
    for idx, f_name in enumerate(rotation_options, 1):
        print(f"  [{idx}] {f_name}")

    rot_idx = int(input("Select Rotation Sequence Number: ").strip()) - 1
    rotation_file = rotation_options[rot_idx]
    rotation_path = f"{rotations_dir}/{rotation_file}"
    rotation_config = load_rotation_from_json(rotation_path)

    abilities_db = load_abilities_from_json(f"{base_dir}/Abilities.json")
    buffs_db = load_permanent_buffs_from_json(f"{base_dir}/PermanentBuffs.json")
    procs_db = load_passives_from_json(f"{base_dir}/BaseProcs.json")

    optional_paths = {
        "relics": f"{base_dir}/choices/relics.json",
        "tree": f"{base_dir}/choices/tree.json",
        "tactical": f"{base_dir}/choices/tacticals.json",
        "implants": f"{base_dir}/choices/implants.json"
    }

    # 7. Run interactive choices drafting loops
    choices = optional_choices(optional_paths)
    print(f"choices are {choices}")

    # 8. Merge selected modifications directly into active databases
    abilities_db.update(choices[0])
    buffs_db.update(choices[1])
    procs_db.update(choices[2])

    return rotation_config, my_custom_character_stats, abilities_db, procs_db, buffs_db


if __name__ == "__main__":
    # Dynamically resolve paths and harvest complete dataset at startup
    Rotation, MY_CUSTOM_CHARACTER_STATS, abilities_db, procs_db, buffs_db = get_dynamic_loadout()

    # --- TOGGLE THIS TO SWITCH MODES ---
    RUN_MODE = "BATCH"  # Change to "BATCH" for full simulation
    # -----------------------------------

    if RUN_MODE == "TEST":
        tester = SingleTester(
            rotation_config=Rotation,
            stats_config=MY_CUSTOM_CHARACTER_STATS,
            abilities_db=abilities_db,
            procs_db=procs_db,
            buffs_db=buffs_db
        )
        tester.run_test(duration=1000.0, dummy_hp=10000000)

    elif RUN_MODE == "BATCH":
        runner = ParallelBatchRunner(
            rotation_config=Rotation,
            stats_config=MY_CUSTOM_CHARACTER_STATS,
            abilities_db=abilities_db,
            procs_db=procs_db,
            buffs_db=buffs_db
        )
        runner.run_monte_carlo(iterations=5000, duration=300.0, dummy_hp=10000000)