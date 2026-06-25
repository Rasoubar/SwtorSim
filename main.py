from src.swtorsim.config_load import load_abilities_from_json, load_passives_from_json, load_permanent_buffs_from_json, optional_choices, load_rotation_from_json
from src.swtorsim.batch import ParallelBatchRunner
from src.swtorsim.tester import SingleTester


Rotation = load_rotation_from_json("data/Assassin/Hatred/Rotations/BasicMaliPS.json")

MY_CUSTOM_CHARACTER_STATS = {
    "class_name": "Assassin",
    "stats": {
        "Mastery": 16570,
        "Power": 14394,
        "Force Power": 9332,
        "Critical Rating": 4029,
        "Alacrity Rating": 2218,
        "Main_hand_min": 2513,
        "Main_hand_max": 3769,
        "Standard_health": 19335,
        "Accuracy Rating": 2824
    }
}

if __name__ == "__main__":
    #base
    abilities_db = load_abilities_from_json("data/Assassin/Hatred/Abilities/Abilities.json")
    buffs_db = load_permanent_buffs_from_json("data/Assassin/Hatred/Buffs/PermanentBuffs.json")
    procs_db = load_passives_from_json("data/Assassin/Hatred/Procs/BaseProcs.json")
    #options
    optional = {"relics": "data/Assassin/Hatred/Choices/Relics.json",
                "tree": "data/Assassin/Hatred/Choices/Tree.json",
                "tactical": "data/Assassin/Hatred/Choices/Tacticals.json",
                "implants": "data/Assassin/Hatred/Choices/Implants.json"}
    choices = optional_choices(optional)
    print(f'choices are {choices}')
    abilities_db.update(choices[0])
    buffs_db.update(choices[1])
    procs_db.update(choices[2])


    # --- TOGGLE THIS TO SWITCH MODES ---
    RUN_MODE = "TEST"  # Change to "BATCH" for full simulation
    # -----------------------------------

    if RUN_MODE == "TEST":
        tester = SingleTester(
            rotation_config=Rotation,
            stats_config=MY_CUSTOM_CHARACTER_STATS,
            abilities_db=abilities_db,
            procs_db=procs_db,
            buffs_db=buffs_db
        )
        # Running for 5 minutes (300 seconds) is usually enough for a rotation check
        tester.run_test(duration=1000.0, dummy_hp=10000000)

    elif RUN_MODE == "BATCH":
        runner = ParallelBatchRunner(
            rotation_config=Rotation,
            stats_config=MY_CUSTOM_CHARACTER_STATS,
            abilities_db=abilities_db,
            procs_db=procs_db,
            buffs_db=buffs_db
        )
        runner.run_monte_carlo(iterations=10000, duration=10000.0, dummy_hp=10000000)