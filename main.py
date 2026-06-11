import os
import json
from engine import Simulation
from entities import Player, Target
from events import Event, CastAttemptEvent, ResourceTick
from config_load import load_abilities_from_json, load_passives_from_json, load_permanent_buffs_from_json

# 🟢 ENGINE SAFETY BRIDGE: Monkeypatch 'abilities' to process and trace cooldown_mod live
import abilities

# 🟢 CUSTOM TEST EVENT: Forces targeted skills onto a simulated cooldown timeline state
class ForceMockCooldownsEvent(Event):
    def __init__(self, player: "Player"):
        super().__init__("Test Framework: Simulate Skill Use Cooldowns")
        self.player = player

    def resolve(self, sim):
        cd_dict = None
        for attr in ['abilities_cooldown_map', 'cooldowns', 'cooldown_ends']:
            if hasattr(self.player, attr):
                cd_dict = getattr(self.player, attr)
                break

        # If your Player class doesn't initialize a dictionary yet, we instantiate one here
        if cd_dict is None:
            self.player.abilities_cooldown_map = {}
            cd_dict = self.player.abilities_cooldown_map

        print(
            f"\n💥 [{sim.current_time:.2f}s] Forcing ASSASSINATE, LEECHING STRIKE, and ERADICATE onto active cooldown states...")
        cd_dict["ASSASSINATE"] = sim.current_time + 12.0
        cd_dict["LEECHING STRIKE"] = sim.current_time + 15.0
        cd_dict["ERADICATE"] = sim.current_time + 10.0

        print(f"   ↳ Current status: Assassinate (12s), Leeching Strike (15s), Eradicate (10s)\n")


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
    sim.schedule_absolute(0.0, CastAttemptEvent(player, target, abilities['creeping_terror']))
    sim.schedule_absolute(1.4, CastAttemptEvent(player, target, abilities['discharge']))
    sim.schedule_absolute(2.8, CastAttemptEvent(player, target, abilities['leeching_strike']))
    sim.schedule_absolute(  4.2, CastAttemptEvent(player, target, abilities['eradicate']))
    sim.schedule_absolute(5.6, CastAttemptEvent(player, target, abilities['recklessness']))
    sim.schedule_absolute(5.6, CastAttemptEvent(player, target, abilities['death_field']))
    sim.schedule_absolute(7.0, CastAttemptEvent(player, target, abilities['leeching_strike']))
    sim.schedule_absolute(8.4, CastAttemptEvent(player, target, abilities['assassinate']))
    sim.schedule_absolute(9.8, CastAttemptEvent(player, target, abilities['eradicate']))
    sim.schedule_absolute(11.2, CastAttemptEvent(player, target, abilities['thrash']))
    sim.schedule_absolute(12.6, CastAttemptEvent(player, target, abilities['thrash']))
    sim.schedule_absolute(14.0, CastAttemptEvent(player, target, abilities['thrash']))

    sim.schedule_absolute(1.0, ResourceTick(player))

    sim.run_timed(duration=30.0)


if __name__ == "__main__":
    run_test()