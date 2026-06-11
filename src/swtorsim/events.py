from typing import TYPE_CHECKING #yellow warnings annoy me
from src.swtorsim.combat_math import calculate_hit, EFFECTS
import random
from src.swtorsim.requirements import validate_all

if TYPE_CHECKING:
    from src.swtorsim.entities import Player, Target, ActiveDot, ActiveBuff
    from abilities import Ability


class Event:
    def __init__(self, name="EventName"):
        self.name = name

    def resolve(self,sim):
        print(f"[{sim.current_time:.2f}s] Executing: {self.name}")

    def __lt__(self,other): #prevent crash if 2 events to happen at same time, which i expect wil happen
        return False

class ApplyDamageLandEvent(Event): #bro why did I put this here
    def __init__(self, source, target, final_damage, is_crit, ability_name):
        super().__init__()
        self.source = source
        self.target = target
        self.final_damage = final_damage
        self.is_crit = is_crit
        self.ability_name = ability_name

    def resolve(self, sim):
        crit_string = " (CRITICAL!)" if self.is_crit else ""
        self.target.hp -= self.final_damage
        print(f"[{sim.current_time:.2f}s] {self.ability_name} deals {self.final_damage}{crit_string} damage to {self.target.name} (HP: {self.target.hp})")

class DamageHit(Event):
    def __init__(self, source: "Player", target: "Target", action_data: dict, ability_name: str):
        super().__init__(f"{ability_name} Hit")
        self.source = source
        self.target = target
        self.action_data = action_data
        self.ability_name = ability_name

    def resolve(self, sim):
        final_damage, is_crit = calculate_hit(self.source, self.target, self.action_data)
        tags = self.action_data.get("tags", [])
        impact_delay = self.action_data.get("impact_delay", 0.0)
        if impact_delay > 0.0:
            sim.schedule_relative(impact_delay, ApplyDamageLandEvent(
                self.source, self.target, final_damage, is_crit, self.ability_name
            ))
        else:
            instant_land = ApplyDamageLandEvent(self.source, self.target, final_damage, is_crit, self.ability_name)
            instant_land.resolve(sim)
        self.evaluate_on_hit_procs(sim, is_crit, tags)

    def evaluate_on_hit_procs(self, sim, is_crit: bool, tags):
        for proc in self.source.procs.values():
            if not self._proc_can_trigger(proc, sim, is_crit, tags):
                continue
            self._trigger_proc_effects(proc, sim)

    def _proc_can_trigger(self, proc, sim, is_crit: bool, tags) -> bool:
        if sim.current_time < proc.next_possible_proc:
            return False
        if proc.trigger == "crit" and not is_crit:
            return False
        if proc.required_tag and proc.required_tag not in tags:
            return False
        if not validate_all(proc.conditions, self.source, self.target):
            return False
        if random.random() > proc.chance:
            return False
        return True

    def _trigger_proc_effects(self, proc, sim):
        current_icd = self.source.scale_time_modifier(proc.icd) if proc.affected_by_cdr else proc.icd
        proc.next_possible_proc = sim.current_time + current_icd
        for action in proc.actions:
            action_conditions = action.get("conditions", {})
            if not validate_all(action_conditions, self.source, self.target):
                continue
            if action.get("action_type") == "damage" and action.get("delay", 0.0) == 0.0:
                instant_hit = DamageHit(self.source, self.target, action, proc.name)
                instant_hit.resolve(sim)
            else:
                from src.swtorsim.abilities import execute_single_action
                execute_single_action(sim, self.source, self.target, action, proc.name)

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
    def __init__(self, player: "Player", buff_name: str, instance_ref: "ActiveBuff"):
        super().__init__(f"{buff_name} Expired")
        self.player = player
        self.buff_name = buff_name
        self.instance_ref = instance_ref

    def resolve(self, sim):
        active_buff = self.player.effects.get(self.buff_name)
        if active_buff is not self.instance_ref: #crash protection
            return
        if sim.current_time < active_buff.expires_at: #refresh
            time_remaining = active_buff.expires_at - sim.current_time
            sim.schedule_relative(time_remaining, self)
            return
        self.player.effects.pop(self.buff_name, None)
        print(f"[{sim.current_time:.2f}s] Buff expired and cleared: {self.buff_name}") #should change the print probly, in case it wasn't there.
        effect_id = active_buff.id
        if effect_id in EFFECTS:
            stat_name = EFFECTS[effect_id]["stat_name"]
            if stat_name in {"Mastery Stat", "Power Stat", "Bonus Damage", "Critical Stat"}:
                self.player.recalculate_stats()


class DebuffExpire(Event):
    def __init__(self, target: "Target", debuff_name: str, instance_ref: "ActiveBuff"):
        super().__init__(f"{debuff_name} Expired")
        self.target = target
        self.debuff_name = debuff_name
        self.instance_ref = instance_ref

    def resolve(self, sim):
        active_debuff = self.target.debuffs.get(self.debuff_name)
        if active_debuff is not self.instance_ref:
            return
        if sim.current_time < active_debuff.expires_at:
            time_remaining = active_debuff.expires_at - sim.current_time
            sim.schedule_relative(time_remaining, self)
            return
        self.target.debuffs.pop(self.debuff_name, None)
        print(f"[{sim.current_time:.2f}s] Debuff expired and cleared: {self.debuff_name} on {self.target.name}")


class DotTick(Event):
    def __init__(self, source: "Player", target: "Target", instance_ref: "ActiveDot"):
        super().__init__(f"DoT Tick: {instance_ref.name}")
        self.source = source
        self.target = target
        self.instance_ref = instance_ref

    def resolve(self, sim):
        dot_name = self.instance_ref.name

        #This was useful before I updated dot aplication logic. It might be useful in an unlikely future. Nevermind it's useful
        if self.target.dots.get(dot_name) is not self.instance_ref: #this should never evaluate to True with the updated dot aplication logic. Nop, still makes sense afterall.
            active_dot = self.target.dots.get(dot_name)
            if active_dot and active_dot.ticks_remaining <= 0:
               del self.target.dots[dot_name]
               print(f"[{sim.current_time:.2f}s] Cleaned up zombie data for: {dot_name}")
            return

        valid_actions = self.instance_ref.choose_action(self.source, self.target)
        for action in valid_actions:
            hit = DamageHit(source=self.source, target=self.target, action_data = action, ability_name= dot_name)
            hit.resolve(sim)
            self.instance_ref.ticks_remaining -= 1
        print(f" [Dot Tracking] {dot_name} action executed. Ticks remaining: {self.instance_ref.ticks_remaining}")
        if self.instance_ref.ticks_remaining > 0:
            next_tick_time = sim.current_time + self.instance_ref.interval
            sim.schedule_absolute(next_tick_time, self)
        else:
            del self.target.dots[dot_name]
            print(f"[{sim.current_time:.2f}s] DoT expired and cleared: {dot_name}")



class ResourceTick(Event):
    def __init__(self, player: "Player", interval: float = 1.0): #keeping interval because i dont know how shit is, dont wanna assume it's every second
        super().__init__(f"Resource Passive Tick")
        self.player = player
        self.interval = interval

    def resolve(self, sim):
        alacrity_pct = self.player.stats.get("Alacrity", 0.0)
        alacrity_mod = 1.0 + alacrity_pct
        print(f'[{sim.current_time:.2f}s] Passive force regen, now at: {self.player.resource.current_value} force.')
        self.player.resource.tick_passive_regen(self.interval, alacrity_mod) #generate
        sim.schedule_relative(self.interval, self) #schedule next

class ResourceGainEvent(Event):
    def __init__(self, player, amount):
        super().__init__("Resource Gain")
        self.player = player
        self.amount = amount

    def resolve(self, sim):
        self.player.resource.generate(self.amount)
        print(f'[{sim.current_time:.2f}s] gained {self.amount} {self.player.resource.pool_type}')


class RotationDecisionLoop(Event):
    def __init__(self, rotation, player, target):
        super().__init__("Rotation Decision Loop")
        self.rotation = rotation
        self.player = player
        self.target = target

    def resolve(self, sim):
        did_cast = self.rotation.evaluate(self.player, self.target, sim)
        if did_cast:
            sim.schedule_absolute(self.player.next_gcd, self)
        else:
            sim.schedule_relative(0.10, self)