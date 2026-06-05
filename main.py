# main.py
import events
import abilities
from engine import Simulation
from entities import Player, Target
from abilities import Ability
from rotation import PriorityRotation
from events import PlayerReady

# =====================================================================
# ENHANCED AUTOMATIC DEBUG INTERCEPTORS (MONKEY PATCHES)
# =====================================================================
orig_cast = abilities.Ability.cast


def debug_cast(self, caster, target, sim):
    res = orig_cast(self, caster, target, sim)
    if res:
        crit = caster.get_stat('Critical Chance') * 100
        mastery = caster.stats.get('Mastery', 0)
        power = caster.stats.get('Power', 0)

        # Pull active tracking names
        active_buffs = list(caster.effects.keys())
        active_dots = [f"{name}(Ticks:{data['ticks_remaining']})" for name, data in target.dots.items()]

        print(f"   [SHEET SNAPSHOT] Live Stats -> Mastery: {mastery:.0f} | Power: {power:.0f} | Crit: {crit:.1f}%")
        print(f"   [ENTITY STATE]  Active Buffs: {active_buffs} | Active DoTs: {active_dots}")
    return res


abilities.Ability.cast = debug_cast

orig_hit = events.DamageHit.resolve


def debug_hit(self, sim):
    orig_hit(self, sim)


events.DamageHit.resolve = debug_hit

orig_expire = events.BuffExpire.resolve


def debug_expire(self, sim):
    was_active = self.buff_name in self.player.effects
    orig_expire(self, sim)
    is_active_now = self.buff_name in self.player.effects

    if was_active and not is_active_now:
        crit = self.player.get_stat('Critical Chance') * 100
        mastery = self.player.stats.get('Mastery', 0)
        power = self.player.stats.get('Power', 0)
        active_buffs = list(self.player.effects.keys())

        print(f"   [SHEET SNAPSHOT] Post-Expiration -> Mastery: {mastery:.0f} | Power: {power:.0f} | Crit: {crit:.1f}%")
        print(f"   [ENTITY STATE]  Remaining Active Buffs: {active_buffs}")


events.BuffExpire.resolve = debug_expire


# =====================================================================

def run_proc_expiration_test():
    sim = Simulation()
    player = Player("Mage Tester")
    boss = Target("Boss Enemy", hp=500000)

    # Initialize pristine baseline gear statistics
    player.base_stats["Cooldown Reduction"] = 0.15  # 15% Alacrity/CDR
    player.base_stats["Critical Rating"] = 800.0
    player.base_stats["Mastery"] = 2500.0
    player.base_stats["Power"] = 1200.0
    player.base_stats["Force Power"] = 1000.0

    player.base_stats["Main_hand_min"] = 400.0
    player.base_stats["Main_hand_max"] = 600.0
    player.base_stats["Off_hand_min"] = 0.0
    player.base_stats["Off_hand_max"] = 0.0
    player.base_stats["Standard_health"] = 15000.0

    player.base_stats["Critical Modifier"] = 1.50
    player.base_stats["Base_Armor_Penetration"] = 0.0

    player.recalculate_stats()

    supernova_config = {
        "name": "Supernova",
        "cooldown": 20.0,  # <-- Change this from 0.0 to 20.0!
        "base_gcd": 1.5,
        "effects": [
            {
                "type": "direct_hit",
                "attack type": 3,
                "damage type": 3,
                "amp": 0.2, "coeff": 2.5, "shp_min": 0.05, "shp_max": 0.05
            },
            {
                "id": 500,
                "type": "buff",
                "effect_name": "Supernova_Mastery_Proc",
                "stat_name": "Mastery Stat",
                "value": 1000.0,
                "duration": 4.0  # Lasts 4 seconds baseline (3.40s with alacrity)
            }
        ]
    }

    # Include Scorch too so we can monitor active DoTs and active Buffs simultaneously
    scorch_config = {
        "name": "Scorch",
        "cooldown": 20.0,  # High cooldown so it only casts once as an opener
        "base_gcd": 1.5,
        "effects": [
            {
                "type": "dot",
                "attack type": 4,
                "damage type": 4,
                "amp": 0.0, "coeff": 0.6, "shp_min": 0.02, "shp_max": 0.02,
                "interval": 2.0, "total_ticks": 3,
                "instant_tick": True, "instant_tick_delay": 0.2
            }
        ]
    }

    # Supernova will get spammed after Scorch applies its DoT
    player.rotation = PriorityRotation([
        Ability(scorch_config),
        Ability(supernova_config)
    ])

    print("--- Starting Extended Lifecycle State Test ---")
    sim.schedule_absolute(0.00, PlayerReady(player, boss))

    # EXTENDED RUN: 11 seconds guarantees we see the final 9.00s drop-off
    sim.run_timed(duration=11.0)


if __name__ == "__main__":
    run_proc_expiration_test()