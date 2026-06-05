from typing import TYPE_CHECKING #yellow warnings annoy me
from combat_math import calculate_hit, EFFECTS

if TYPE_CHECKING:
    from entities import Player, Target
    from abilities import Ability

class Event:
    def __init__(self, name="EventName"):
        self.name = name

    def resolve(self,sim):
        print(f"[{sim.current_time:.2f}s] Executing: {self.name}")

    def __lt__(self,other): #prevent crash if 2 events to happen at same time
        return False

class DamageHit(Event):
    def __init__(self, source: "Player", target: "Target", action_data: dict, ability_name: str):
        super().__init__(f"{ability_name} Hit")
        self.source = source
        self.target = target
        self.action_data = action_data
        self.ability_name = ability_name

    def resolve(self, sim):
        final_damage, is_crit = calculate_hit(self.source, self.target, self.action_data)

        crit_string = " (CRITICAL!)" if is_crit else ""
        self.target.hp -= final_damage
        print(f"[{sim.current_time:.2f}s] {self.ability_name} deals {final_damage} {crit_string} damage to {self.target.name} (HP: {self.target.hp})")

class CastAttemptEvent(Event):
    def __init__(self, player: "Player", target: "Target", ability: "Ability"):
        super().__init__(f"Cast Attempt: {ability.name}")
        self.player = player
        self.target = target
        self.ability = ability

    def resolve(self, sim):
        self.ability.cast(self.player, self.target, sim)


class PlayerReady(Event):

    def __init__(self, player: "Player", target: "Target"):
        super().__init__("Player Ready")
        self.player = player
        self.target = target

    def resolve(self, sim):
        acted = self.player.rotation.evaluate(self.player, self.target, sim)

        if acted:
            sim.schedule_absolute(self.player.next_gcd, self)
        else:
            sim.schedule_relative(0.1, self)

class BuffExpire(Event):
    def __init__(self, player: "Player", buff_name: str, instance_ref: dict):
        super().__init__(f"{buff_name} Expired")
        self.player = player
        self.buff_name = buff_name
        self.instance_ref = instance_ref

    def resolve(self, sim):
        if self.player.effects.get(self.buff_name) is self.instance_ref:
            del self.player.effects[self.buff_name]
            effect_id = self.instance_ref.get("id")
            print(f"[{sim.current_time:.2f}s] Buff expired: {self.buff_name}")
            if effect_id in EFFECTS:
                stat_name = EFFECTS[effect_id]["stat_name"]
                if stat_name in {"Mastery Stat", "Power Stat", "Bonus Damage", "Crit Stat"}:
                    self.player.recalculate_stats()

class DebuffExpire(Event):
    def __init__(self, target: "Target", debuff_name: str, instance_ref: dict):
        super().__init__(f"{debuff_name} Expired")
        self.target = target
        self.debuff_name = debuff_name
        self.instance_ref = instance_ref

    def resolve(self, sim):
        if self.target.debuffs.get(self.debuff_name) is self.instance_ref:

            del self.target.debuffs[self.debuff_name]
            print(f"[{sim.current_time:.2f}s] Debuff expired: {self.debuff_name} on {self.target.name}")


class DotTick(Event):
    def __init__(self, source: "Player", target: "Target", instance_ref: dict):
        super().__init__(f"DoT Tick: {instance_ref['name']}")
        self.source = source
        self.target = target
        self.instance_ref = instance_ref

    def resolve(self, sim):
        dot_name = self.instance_ref["name"]

        if self.target.dots.get(dot_name) is not self.instance_ref:
            return  #if it was overwritten we ignore

        hit = DamageHit(source=self.source, target=self.target, action_data = self.instance_ref["action_data"], ability_name= dot_name)
        hit.resolve(sim)

        self.instance_ref["ticks_remaining"] -= 1
        if self.instance_ref["ticks_remaining"] > 0:
            next_tick_time = sim.current_time + self.instance_ref["interval"]
            sim.schedule_absolute(next_tick_time, self)