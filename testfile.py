from src.swtorsim.entities import Player, Target
from src.swtorsim.events import DamageHit
from src.swtorsim.combat_math import EFFECTS


# --- MOCK SIMULATOR ENV ---
# Gives the event exactly what it needs to resolve without crashing
class MockTracker:
    def log_damage(self, ability_name, final_damage, is_crit, target, current_time):
        # We don't need to save the logs for this test, we just need it to not crash
        pass


class TestSim:
    def __init__(self):
        self.current_time = 0.0
        self.ability_db = {}
        self.tracker = MockTracker()

    def schedule_relative(self, delay, event):
        pass

    def schedule_absolute(self, time, event):
        pass


# --- THE REAL TEST ---
def run_real_damage_test():
    print("--- FIRING REAL DAMAGE EVENTS ---")
    sim = TestSim()

    # 1. Initialize real entities
    player = Player("Test_Assassin")
    target = Target("Operations Dummy", 1000000)

    # Make sure we have a baseline stat so the damage has something to scale off
    player.base_stats["Mastery"] = 10000
    player.base_stats["Accuracy"] = 10000
    player.recalculate_stats()

    # 2. Inject the test buff into your real EFFECTS database
    TEST_BUFF_ID = 9999
    # Note: If your combat_math uses a specific bucket name for Surging Charge,
    # it will dynamically pick it up here from the meta dict.
    EFFECTS[TEST_BUFF_ID] = {
        "stat_name": "Damage Modifier",
        "modifier_bucket": "surging_charge_bucket"
    }

    # 3. Define the Buff Action (Non-Linear)
    tactical_action = {
        "id": TEST_BUFF_ID,
        "effect_name": "Surging Charge",
        "duration": 999.0,
        "max_charges": 3,
        "value": 0.0,
        "stack_values": [0.0, 1.0, 5.0],  # 0%, 100%, 200%
    }

    # 4. Define a standard Damage Action (e.g., Discharge)
    discharge_action = {
        "action_type": "damage",
        "attack_type": 3,  # Force
        "damage_type": 2,  # Energy
        "hand": "main",
        "coeff": 1.5,  # Standard scaling
        "amp": 0.0,
        "shp_min": 1000.0,  # Base damage
        "shp_max": 1000.0
    }

    # 5. Fire the attack with 1, 2, and 3 stacks
    for stacks in [0, 1, 2, 3]:
        # Apply the stacks to the real player
        tactical_action["charges"] = stacks
        player.apply_buff(tactical_action, "Test_Source", sim.current_time)

        print(f"\n--- HITTING TARGET WITH {stacks} STACK(S) ---")

        # Create the real DamageHit event
        hit_event = DamageHit(player, target, discharge_action, "Discharge")

        # Fire it using your engine's actual resolve method
        hit_event.resolve(sim)


if __name__ == "__main__":
    run_real_damage_test()