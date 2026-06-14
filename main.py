from src.swtorsim.engine import Simulation
from src.swtorsim.entities import Player, Target
from src.swtorsim.events import ResourceTick, PlayerReady
from src.swtorsim.config_load import load_abilities_from_json, load_passives_from_json, load_permanent_buffs_from_json
from src.swtorsim.rotation import Rotation
from src.swtorsim.requirements import validate_all

from src.swtorsim.config_load import load_abilities_from_json, load_passives_from_json, load_permanent_buffs_from_json
from src.swtorsim.rotation import Rotation
from src.swtorsim.requirements import validate_all

def run_test():
    # 1. Load data and initialize simulation
    abilities_db = load_abilities_from_json("data/Assassin/Hatred/Abilities/Abilities.json")
    sim = Simulation(abilities_db)
    player = Player("Assassin")
    target = Target("Target Dummy", hp=2000000)

    # 2. Assign base player stats
    p_stats = player.base_stats
    p_stats["Mastery"] = 16834
    p_stats["Power"] = 14503
    p_stats["Force Power"] = 9332
    p_stats["Critical Rating"] = 3758
    p_stats["Alacrity Rating"] = 2218
    p_stats["Main_hand_min"] = 2513
    p_stats["Main_hand_max"] = 3769
    p_stats["Standard_health"] = 19335
    player.recalculate_stats()

    # 3. Load passives and permanent buffs
    player.procs = load_passives_from_json("data/Assassin/Hatred/Procs/BaseAssassinProcs+MasteryPowerRelics.json")
    player.effects = load_permanent_buffs_from_json("data/Assassin/Hatred/Buffs/PermanentBuffs.json")
    player.recalculate_stats()

    # 4. Process baseline permanent cooldown modifications
    for effect_id, effect in player.effects.items():
        if effect.id == 64 and effect.required_tags is not None:
            for ability in sim.ability_db.values():
                if any(tag in ability.tags for tag in effect.required_tags):
                    ability.cooldown -= effect.value

    # 5. Define your complete repeating hybrid rotation configuration
    hybrid_rotation_config = [
        # --- The Fixed Opener Chain ---
        {"type": "fixed", "ability_id": "eradicate"},
        {"type": "fixed", "ability_id": "creeping_terror"},
        {"type": "fixed", "ability_id": "discharge"},
        {"type": "fixed", "ability_id": "leeching_strike"},
        {"type": "fixed", "ability_id": "eradicate"},

        # --- Step 6: Master Block Window 1 ---
        {
            "type": "priority_block",
            "name": "Reck+DF+MPRIO1 Window 1",
            "pool": [
                {"ability_id": "recklessness", "rules": []},
                {
                    "ability_id": "death_field",
                    "rules": [{"type": "buff_active", "name": "Recklessness"}]
                },
                {"ability_id": "saber_strike", "rules": [{"type": "energy_level", "operator": "<", "value": 35}]},
                {"ability_id": "assassinate", "rules": []},
                {"ability_id": "leeching_strike", "rules": []},
                {"ability_id": "thrash", "rules": []},
                {"ability_id": "saber_strike", "rules": []}
            ]
        },

        # --- Step 7: Master Block Window 2 ---
        {
            "type": "priority_block",
            "name": "Reck+DF+MPRIO1 Window 2",
            "pool": [
                {"ability_id": "recklessness", "rules": []},
                {
                    "ability_id": "death_field",
                    "rules": [{"type": "buff_active", "name": "Recklessness"}]
                },
                {"ability_id": "saber_strike", "rules": [{"type": "energy_level", "operator": "<", "value": 35}]},
                {"ability_id": "assassinate", "rules": []},
                {"ability_id": "leeching_strike", "rules": []},
                {"ability_id": "thrash", "rules": []},
                {"ability_id": "saber_strike", "rules": []}
            ]
        },

        # --- Step 8: Master Block Window 3 ---
        {
            "type": "priority_block",
            "name": "Reck+DF+MPRIO1 Window 3",
            "pool": [
                {"ability_id": "recklessness", "rules": []},
                {
                    "ability_id": "death_field",
                    "rules": [{"type": "proc_active", "name": "Recklessness"}]  # <-- Added rule
                },
                {"ability_id": "saber_strike", "rules": [{"type": "energy_level", "operator": "<", "value": 35}]},
                {"ability_id": "assassinate", "rules": []},
                {"ability_id": "leeching_strike", "rules": []},
                {"ability_id": "thrash", "rules": []},
                {"ability_id": "saber_strike", "rules": []}
            ]
        },

        # --- MPRIO 2 ---
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

        # --- Return to Fixed Transition ---
        {"type": "fixed", "ability_id": "eradicate"},

        # --- MPRIO 1 (Back-to-Back Windows) ---
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

        # --- MPRIO 3 ---
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

    # 6. Instantiate the manager WITH loop=True so it repeats for the full duration
    player.rotation = Rotation(name="Hatred Meta Loop", steps_config=hybrid_rotation_config, loop=True)

    # 7. Run the timeline loop
    sim.schedule_absolute(0.0, PlayerReady(player, target))
    sim.schedule_absolute(1.0, ResourceTick(player))
    sim.run_timed(duration=90.0, target=target)

if __name__ == "__main__":
    run_test()