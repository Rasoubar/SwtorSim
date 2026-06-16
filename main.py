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
            {"ability_id": "recklessness", "rules": {}},
            {"ability_id": "saber_strike", "rules": {"caster_energy_below": 35}},
            {"ability_id": "assassinate", "rules": {}},
            {"ability_id": "leeching_strike", "rules": {}},
            {"ability_id": "thrash", "rules": {}},
            {"ability_id": "saber_strike", "rules": {}}
        ]
    },
    {
        "type": "priority_block",
        "name": "Reck+DF+MPRIO1 Window 2",
        "pool": [
            {"ability_id": "recklessness", "rules": {}},
            {"ability_id": "death_field", "rules": {"caster_has_buff": "Recklessness"}},
            {"ability_id": "saber_strike", "rules": {"caster_energy_below": 35}},
            {"ability_id": "assassinate", "rules": {}},
            {"ability_id": "leeching_strike", "rules": {}},
            {"ability_id": "thrash", "rules": {}},
            {"ability_id": "saber_strike", "rules": {}}
        ]
    },
    {
        "type": "optional",
        "ability_id": "phantom_stride",
        "rules": {
            "target_hp_above_pct": 0.30,
            "proc_cooldown_above": {"name": "Bloodletting", "value": 0.5},
            "caster_does_not_have_buff": "Bloodletting"
        }
    },
    {
        "type": "priority_block",
        "name": "Reck+DF+MPRIO1 Window 3",
        "pool": [
            {"ability_id": "recklessness", "rules": {}},
            {"ability_id": "death_field", "rules":{}},
            {"ability_id": "saber_strike", "rules": {"caster_energy_below": 35}},
            {"ability_id": "assassinate", "rules": {}},
            {"ability_id": "leeching_strike", "rules": {}},
            {"ability_id": "thrash", "rules": {}},
            {"ability_id": "saber_strike", "rules": {}}
        ]
    },
    {
        "type": "optional",
        "ability_id": "phantom_stride",
        "rules": {
            "target_hp_above_pct": 0.30,
            "proc_cooldown_above": {"name": "Bloodletting", "value": 6.0},
            "caster_does_not_have_buff": "Bloodletting"
        }
    },
    {
        "type": "priority_block",
        "name": "MPRIO 2 Window",
        "pool": [
            {"ability_id": "leeching_strike", "rules": {}},
            {"ability_id": "saber_strike", "rules": {"caster_energy_below": 35}},
            {"ability_id": "assassinate", "rules": {}},
            {"ability_id": "thrash", "rules": {}},
            {"ability_id": "saber_strike", "rules": {}},
        ]
    },
    {
        "type": "optional",
        "ability_id": "phantom_stride",
        "rules": {
            "target_hp_above_pct": 0.30,
            "proc_cooldown_above": {"name": "Bloodletting", "value": 4.0},
            "caster_does_not_have_buff": "Bloodletting"
        }
    },
    {
        "type": "priority_block",
        "name": "Eradicate_block",
        "pool": [
            {"ability_id": "eradicate", "rules": {}},
            {"ability_id": "saber_strike", "rules": {"caster_energy_below": 35}},
            {"ability_id": "assassinate", "rules": {}},
            {"ability_id": "thrash", "rules": {}},
            {"ability_id": "saber_strike", "rules": {}},
        ]
    },
    {
        "type": "optional",
        "ability_id": "phantom_stride",
        "rules": {
            "target_hp_above_pct": 0.30,
            "proc_cooldown_above": {"name": "Bloodletting", "value": 0.3},
            "caster_does_not_have_buff": "Bloodletting"
        }
    },
    {
        "type": "priority_block",
        "name": "MPRIO 1 Window A",
        "pool": [
            {"ability_id": "saber_strike", "rules": {"caster_energy_below": 30}},
            {"ability_id": "assassinate", "rules": {}},
            {"ability_id": "leeching_strike", "rules": {}},
            {"ability_id": "thrash", "rules": {}},
            {"ability_id": "saber_strike", "rules": {}}
        ]
    },
    {
        "type": "optional",
        "ability_id": "phantom_stride",
        "rules": {
            "target_hp_above_pct": 0.30,
            "proc_cooldown_above": {"name": "Bloodletting", "value": 4.0},
            "caster_does_not_have_buff": "Bloodletting"
        }
    },
    {
        "type": "priority_block",
        "name": "MPRIO 1 Window B",
        "pool": [
            {"ability_id": "saber_strike", "rules": {"caster_energy_below": 30}},
            {"ability_id": "assassinate", "rules": {}},
            {"ability_id": "leeching_strike", "rules": {}},
            {"ability_id": "thrash", "rules": {}},
            {"ability_id": "saber_strike", "rules": {}}
        ]
    },
    {
        "type": "priority_block",
        "name": "MPRIO 3 Window",
        "pool": [
            {"ability_id": "saber_strike", "rules": {"caster_energy_below": 60}},
            {"ability_id": "assassinate", "rules": {}},
            {"ability_id": "leeching_strike", "rules": {}},
            {"ability_id": "thrash", "rules": {}},
            {"ability_id": "saber_strike", "rules": {}}
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
    runner.run_monte_carlo(iterations=1000, duration=10000.0, dummy_hp=10000000)