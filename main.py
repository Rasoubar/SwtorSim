import os
from engine import Simulation
from entities import Player, Target
from events import PlayerReady
from config_load import load_abilities_from_json, load_passives_from_json, load_permanent_buffs_from_json
from rotation import PriorityRotation


def run_integration_test():
    print("--- Starting Integrated Architecture Test (JSON Data Load) ---")

    # 1. Initialize simulation context
    sim = Simulation()
    player = Player("Assassin")
    target = Target("Target Dummy", hp=50000)

    # Configure baseline stats matching your Title Case stat keys
    p_stats = player.base_stats
    p_stats["Mastery"] = 12400
    p_stats["Power"] = 6200
    p_stats["Force Power"] = 4900  # Extracted from Level 80 weapon item hilts
    p_stats["Critical Rating"] = 3258  # Hits optimal Surge threshold allocations
    p_stats["Alacrity Rating"] = 2684  # Reaches the 1.4-second global cooldown breakpoint!
    p_stats["Main_hand_min"] = 1840
    p_stats["Main_hand_max"] = 2460
    p_stats["Standard_health"] = 2325
    player.recalculate_stats()

    # 2. Dynamically load spells from your external configuration layout
    json_path_abilities = os.path.join("data", "HatredAssassinAbilities.json")
    abilities_db = load_abilities_from_json(json_path_abilities)
    json_path_procs = os.path.join("data", "BaseAssassinProcs.json")
    player.procs = load_passives_from_json(json_path_procs)
    perm_buffs_path = os.path.join("data", "AssassinBasePermanentBuffs.json")
    player.effects = load_permanent_buffs_from_json(perm_buffs_path)
    # 3. Form your automated rotation list using the loaded instances
    rotation_sequence = [
        abilities_db["THRASH"],
    ]
    player.recalculate_stats()
    player.rotation = PriorityRotation(rotation_sequence)
    # 4. Prime the simulation conveyor belt and run the timeline
    sim.schedule_absolute(0.0, PlayerReady(player, target))
    sim.run_timed(duration=6.0)


if __name__ == "__main__":
    run_integration_test()