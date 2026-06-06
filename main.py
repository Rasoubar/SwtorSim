import random
from engine import Simulation
from entities import Player, Target
from abilities import Ability
from events import CastAttemptEvent

# Pin the random seed so the damage and crit output is deterministic for testing
random.seed(42)

# 1. Initialize your actual simulation timeline
sim = Simulation()

# 2. Create your actual entities
player = Player("Sith Assassin")
dummy = Target("Training Dummy", hp=150000)

# Set baseline stats on your real player object so your math has numbers to calculate
player.base_stats.update({
    "Main_hand_min": 500,
    "Main_hand_max": 600,
    "F_Bonus_Damage": 1500,
    "Standard_health": 18000,
    "Critical Chance": 0.10,
    "Critical Modifier": 1.5
})
player.recalculate_stats()

# 3. Create raw dictionary configurations matching your JSON database schema
recklessness_config = {
    "name": "Recklessness",
    "cooldown": 60.0,
    "triggers_gcd": False,
    "energy_cost": 0.0,
    "actions": [{
        "action_type": "buff",
        "duration": 12.0,
        "id": 133,
        "effect_name": "Recklessness",
        "stat_name": "Critical Chance",
        "value": 0.60,
        "consumable_charges": 2,  # Your code inside entities.py automatically maps this to consumable_charges
        "affected_by_cdr": False
    }]
}

shock_config = {
    "name": "Shock",
    "cooldown": 0.0,
    "triggers_gcd": True,
    "base_gcd": 1.5,
    "energy_cost": 20.0,
    "actions": [{
        "action_type": "direct_hit",
        "delay": 0.0,
        "attack type": 3,   # Force Attack
        "damage type": 1,   # Kinetic Damage
        "coeff": 2.5,
        "amp": 0.1,
        "shp_min": 0.05,
        "shp_max": 0.05
    },{
        "action_type": "direct_hit",
        "delay": 0.3,
        "attack type": 3,   # Force Attack
        "damage type": 1,   # Kinetic Damage
        "coeff": 4.5,
        "amp": 0.1,
        "shp_min": 0.05,
        "shp_max": 0.05
    }]
}

# Instantiate your real Ability items
recklessness = Ability(recklessness_config)
shock = Ability(shock_config)

# 4. Load events onto your actual Simulation heapq timeline
sim.schedule_relative(0.0, CastAttemptEvent(player, dummy, recklessness))
sim.schedule_relative(0.1, CastAttemptEvent(player, dummy, shock))       # Hit 1: Consumes charge 1 (High crit chance)
sim.schedule_relative(1.6, CastAttemptEvent(player, dummy, shock))       # Hit 2: Consumes charge 2 (High crit chance -> Auto-pops)
sim.schedule_relative(3.1, CastAttemptEvent(player, dummy, shock))       # Hit 3: Buff is gone (Normal baseline crit chance)

print("=" * 60)
print("   LAUNCHING TIMELINE RUN USING YOUR NATIVE ARCHITECTURE")
print("=" * 60)

# Run the heap engine queue for 10 simulation seconds
sim.run_timed(10.0)

print("\n" + "=" * 60)
print(f"Final Active Player Buff Inventory: {list(player.effects.keys())}")
print("=" * 60)