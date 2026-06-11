import os
from engine import Simulation
from entities import Player, Target
from events import Event, CastAttemptEvent, ResourceTick, PlayerReady
from config_load import load_abilities_from_json, load_passives_from_json, load_permanent_buffs_from_json
from rotation import FixedRotation

def run_test():

    sim = Simulation()
    player = Player("Assassin")
    target = Target("Target Dummy", hp=1000000)

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

    json_path_abilities = os.path.join("data", "HatredAssassinAbilities.json")
    player.abilities_db = load_abilities_from_json(json_path_abilities)
    json_path_procs = os.path.join("data", "BaseAssassinProcs.json")
    player.procs = load_passives_from_json(json_path_procs)
    perm_buffs_path = os.path.join("data", "AssassinBasePermanentBuffs.json")
    player.effects = load_permanent_buffs_from_json(perm_buffs_path)

    player.recalculate_stats()
    abilities = {
        key.lower().replace(" ", "_"): val
        for key, val in player.abilities_db.items()
    }

    rotation = [abilities['eradicate'],abilities['creeping_terror'],abilities['discharge'],abilities['leeching_strike'],abilities['eradicate'],abilities['recklessness'],abilities['death_field'],
            abilities['leeching_strike'],abilities['eradicate'],abilities['thrash'],abilities['thrash'],abilities['thrash']]
    player.rotation = FixedRotation(rotation)

    sim.schedule_absolute(0.0, PlayerReady(player, target))
    sim.schedule_absolute(1.0, ResourceTick(player))

    sim.run_timed(duration=30.0)


if __name__ == "__main__":
    run_test()