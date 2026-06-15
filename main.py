from src.swtorsim.config_load import load_abilities_from_json, load_passives_from_json, load_permanent_buffs_from_json
from src.swtorsim.batch import ParallelBatchRunner

HYBRID_ROTATION_CONFIG = [
    {"type": "fixed", "ability_id": "eradicate"},
    {"type": "fixed", "ability_id": "creeping_terror"},
    {"type": "fixed", "ability_id": "discharge"},
    {"type": "fixed", "ability_id": "leeching_strike"},
    {"type": "fixed", "ability_id": "eradicate"},
    {
        "type": "priority_block",
        "name": "Reck+DF+MPRIO1 Window 1",
        "pool": [
            {"ability_id": "recklessness", "rules": []},
            {"ability_id": "death_field", "rules": [{"type": "buff_active", "name": "Recklessness"}]},
            {"ability_id": "saber_strike", "rules": [{"type": "energy_level", "operator": "<", "value": 35}]},
            {"ability_id": "assassinate", "rules": []},
            {"ability_id": "leeching_strike", "rules": []},
            {"ability_id": "thrash", "rules": []},
            {"ability_id": "saber_strike", "rules": []}
        ]
    },
    {
        "type": "priority_block",
        "name": "Reck+DF+MPRIO1 Window 2",
        "pool": [
            {"ability_id": "recklessness", "rules": []},
            {"ability_id": "death_field", "rules": [{"type": "buff_active", "name": "Recklessness"}]},
            {"ability_id": "saber_strike", "rules": [{"type": "energy_level", "operator": "<", "value": 35}]},
            {"ability_id": "assassinate", "rules": []},
            {"ability_id": "leeching_strike", "rules": []},
            {"ability_id": "thrash", "rules": []},
            {"ability_id": "saber_strike", "rules": []}
        ]
    },
    {
        "type": "priority_block",
        "name": "Reck+DF+MPRIO1 Window 3",
        "pool": [
            {"ability_id": "recklessness", "rules": []},
            {"ability_id": "death_field", "rules": [{"type": "proc_active", "name": "Recklessness"}]},
            {"ability_id": "saber_strike", "rules": [{"type": "energy_level", "operator": "<", "value": 35}]},
            {"ability_id": "assassinate", "rules": []},
            {"ability_id": "leeching_strike", "rules": []},
            {"ability_id": "thrash", "rules": []},
            {"ability_id": "saber_strike", "rules": []}
        ]
    },
    {
        "type": "priority_block",
        "name": "MPRIO 2 Window",
        "pool": [
            {"ability_id": "leeching_strike", "rules": []},
            {"ability_id": "saber_strike", "rules": [{"type": "energy_level", "operator": "<", "value": 35}]},
            {"ability_id": "assassinate", "rules": []},
            {"ability_id": "thrash", "rules": []},
            {"ability_id": "saber_strike", "rules": []},
        ]
    },
    {"type": "fixed", "ability_id": "eradicate"},
    {
        "type": "priority_block",
        "name": "MPRIO 1 Window A",
        "pool": [
            {"ability_id": "saber_strike", "rules": [{"type": "energy_level", "operator": "<", "value": 30}]},
            {"ability_id": "assassinate", "rules": []},
            {"ability_id": "leeching_strike", "rules": []},
            {"ability_id": "thrash", "rules": []},
            {"ability_id": "saber_strike", "rules": []}
        ]
    },
    {
        "type": "priority_block",
        "name": "MPRIO 1 Window B",
        "pool": [
            {"ability_id": "saber_strike", "rules": [{"type": "energy_level", "operator": "<", "value": 30}]},
            {"ability_id": "assassinate", "rules": []},
            {"ability_id": "leeching_strike", "rules": []},
            {"ability_id": "thrash", "rules": []},
            {"ability_id": "saber_strike", "rules": []}
        ]
    },
    {
        "type": "priority_block",
        "name": "MPRIO 3 Window",
        "pool": [
            {"ability_id": "saber_strike", "rules": [{"type": "energy_level", "operator": "<", "value": 60}]},
            {"ability_id": "assassinate", "rules": []},
            {"ability_id": "leeching_strike", "rules": []},
            {"ability_id": "thrash", "rules": []},
            {"ability_id": "saber_strike", "rules": []}
        ]
    }
]

MY_CUSTOM_CHARACTER_STATS = {
    "class_name": "Assassin",
    "stats": {
        "Mastery": 16834,
        "Power": 14503,
        "Force Power": 9332,
        "Critical Rating": 3758,
        "Alacrity Rating": 2218,
        "Main_hand_min": 2513,
        "Main_hand_max": 3769,
        "Standard_health": 19335
    }
}

if __name__ == "__main__":
    abilities_db = load_abilities_from_json("data/Assassin/Hatred/Abilities/Abilities.json")
    procs_db = load_passives_from_json("data/Assassin/Hatred/Procs/BaseAssassinProcs+MasteryPowerRelics.json")
    buffs_db = load_permanent_buffs_from_json("data/Assassin/Hatred/Buffs/PermanentBuffs.json")

    runner = ParallelBatchRunner(
        rotation_config=HYBRID_ROTATION_CONFIG,
        stats_config=MY_CUSTOM_CHARACTER_STATS,
        abilities_db=abilities_db,
        procs_db=procs_db,
        buffs_db=buffs_db
    )

    runner.run_monte_carlo(iterations=1000, duration=10000.0, dummy_hp=200000000)