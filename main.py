# main.py
import events
import abilities
from engine import Simulation
from entities import Player, Target
from abilities import Ability
from rotation import PriorityRotation
from events import PlayerReady

# =====================================================================
# AUTOMATIC DEBUG INTERCEPTORS (MONKEY PATCHES)
# =====================================================================
orig_cast = abilities.Ability.cast
def debug_cast(self, caster, target, sim):
    res = orig_cast(self, caster, target, sim)
    if res:
        crit = caster.get_stat('Critical Chance') * 100
        crit1 = caster.get_stat('Critical Modifier') * 100
        print(f"   [STAT CHECK] After Cast -> Live Crit Chance: {crit:.1f}% Live Crit Mod: {crit1:.1f}| Active Buffs: {list(caster.effects.keys())}")
    return res
abilities.Ability.cast = debug_cast

orig_hit = events.DamageHit.resolve
def debug_hit(self, sim):
    crit = self.source.get_stat('Critical Chance') * 100
    print(f"   [STAT CHECK] Before Damage Roll -> Live Crit Chance: {crit:.1f}% | Active Buffs: {list(self.source.effects.keys())}")
    orig_hit(self, sim)
events.DamageHit.resolve = debug_hit

orig_expire = events.BuffExpire.resolve
def debug_expire(self, sim):
    orig_expire(self, sim)
    crit = self.player.get_stat('Critical Chance') * 100
    print(f"   [STAT CHECK] After Expiration -> Live Crit Chance: {crit:.1f}% | Active Buffs: {list(self.player.effects.keys())}")
events.BuffExpire.resolve = debug_expire
# =====================================================================

def run_integration_test():
    sim = Simulation()
    player = Player("Mage Tester")
    boss = Target("Target Dummy", hp=50000)

    # Initialize baseline stats
    player.stats["Cooldown Reduction"] = 0.15
    player.stats["Critical Chance"] = 0.10
    player.stats["Critical Modifier"] = 2.0

    # Test ability configurations
    supernova_config = {
        "name": "Supernova",
        "cooldown": 12.0,
        "base_gcd": 1.5,
        "effects": [
            {
                "type": "direct_hit",
                "value": 1000
            },
            {
                "type": "buff",
                "effect_name": "Supernova_Crit_Chance_Buff",
                "stat_name": "Critical Chance",
                "value": 0.90,
                "duration": 3.0
            },
            {
                "type": "buff",
                "effect_name": "Supernova_Crit_Multiplier_Buff",
                "stat_name": "Critical Modified",
                "value": 0.50,
                "duration": 3.0
            }
        ]
    }

    scorch_config = {
        "name": "Scorch",
        "effects": [{"type": "direct_hit", "value": 300, "delay": 0.0}]
    }

    supernova = Ability(supernova_config)
    scorch = Ability(scorch_config)
    player.rotation = PriorityRotation([supernova, scorch])

    print("--- Starting Timeline Test ---")
    sim.schedule_absolute(0.00, PlayerReady(player, boss))
    sim.run_timed(duration=6.0)

if __name__ == "__main__":
    run_integration_test()