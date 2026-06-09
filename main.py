import os
import json
from engine import Simulation
from entities import Player, Target
from events import Event, CastAttemptEvent
from config_load import load_abilities_from_json, load_passives_from_json, load_permanent_buffs_from_json

# 🟢 ENGINE SAFETY BRIDGE: Monkeypatch 'abilities' to process and trace cooldown_mod live
import abilities

original_execute_action = abilities.execute_single_action


def patched_execute_single_action(sim, caster, target, action, source_name):
    action_type = action.get("action_type")

    if action_type == "cooldown_mod":
        target_ability = action["ability_name"]
        is_reset = action.get("reset", False)
        val = action.get("value", 0.0)

        print(
            f"⏱️  [{sim.current_time:.2f}s] Cooldown Modifier triggered by '{source_name}' for target: {target_ability} (Full Reset: {is_reset})")

        # Determine your player instance's active cooldown tracking dictionary layout
        cd_dict = None
        for attr in ['abilities_cooldown_map', 'cooldowns', 'cooldown_ends']:
            if hasattr(caster, attr):
                cd_dict = getattr(caster, attr)
                break

        if cd_dict is not None:
            if is_reset:
                cd_dict[target_ability] = 0.0
                print(f"   ↳ [System Check] {target_ability} cooldown cleared back to 0.0s!")
            else:
                if target_ability in cd_dict:
                    cd_dict[target_ability] = max(0.0, cd_dict[target_ability] - val)
                    print(
                        f"   ↳ [System Check] Reduced {target_ability} cooldown by {val}s. New remaining: {cd_dict[target_ability]}s")

    # Pass along to standard engine execution rules for buff/damage packages
    original_execute_action(sim, caster, target, action, source_name)


# Overwrite the global handler module with our validation trace
abilities.execute_single_action = patched_execute_single_action


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


def run_recklessness_cooldown_test():
    print("=== Starting Isolated Recklessness Cooldown Reset Logic Test ===")

    # 1. Initialize simulation context and standard player attributes
    sim = Simulation()
    player = Player("Assassin")
    target = Target("Target Dummy", hp=200000)

    # Configure baseline combat statistics
    p_stats = player.base_stats
    p_stats["Mastery"] = 12400
    p_stats["Power"] = 6200
    p_stats["Force Power"] = 4900
    p_stats["Critical Rating"] = 3258
    p_stats["Alacrity Rating"] = 2684
    p_stats["Main_hand_min"] = 1840
    p_stats["Main_hand_max"] = 2460
    p_stats["Standard_health"] = 2325
    player.recalculate_stats()

    # 2. Load JSON Database nodes
    json_path_abilities = os.path.join("data", "HatredAssassinAbilities.json")
    abilities_db = load_abilities_from_json(json_path_abilities)

    json_path_procs = os.path.join("data", "BaseAssassinProcs.json")
    player.procs = load_passives_from_json(json_path_procs)

    perm_buffs_path = os.path.join("data", "AssassinBasePermanentBuffs.json")
    player.effects = load_permanent_buffs_from_json(perm_buffs_path)

    player.recalculate_stats()

    # 3. Schedule the explicit step verification sequence
    recklessness_ability = abilities_db['RECKLESSNESS']
    leeching = abilities_db['ERADICATE']

    # At 1.00s: Force target skills onto cooldown
    sim.schedule_absolute(1.0, ForceMockCooldownsEvent(player))
    sim.schedule_absolute(2.0, CastAttemptEvent(player, target, leeching))
    # At 3.00s: Activate Recklessness to trigger structural changes
    sim.schedule_absolute(3.0, CastAttemptEvent(player, target, recklessness_ability))
    sim.schedule_absolute(4.0, CastAttemptEvent(player, target, leeching))

    # 4. Spin up the timeline loop
    sim.run_timed(duration=12.0)


if __name__ == "__main__":
    run_recklessness_cooldown_test()