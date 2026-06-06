from events import DamageHit, DotTick, BuffExpire, DebuffExpire, ResourceGainEvent
from entities import ActiveDot, Target, Player, ResourcePool
import random

class Ability:
    def __init__(self, config: dict):
        self.name = config["name"]
        self.cooldown = config.get("cooldown",0.0)
        self.triggers_gcd = config.get("triggers_gcd", True)
        self.base_gcd = config.get("base_gcd", 1.5)
        self.actions = config.get ("actions", [])
        self.energy_cost = config.get("energy_cost", 0.0)

    def can_cast(self, caster: "Player", target: "Target", sim) -> bool:
        if self.triggers_gcd and sim.current_time < caster.next_gcd:
            return False
        if sim.current_time < caster.cooldowns.get(self.name, 0.0):
            return False
        if not caster.resource.can_afford(self.energy_cost):
            return False
        restrictions = getattr(self, "restrictions", {})
        if not restrictions:
            return True
        if "target_hp_below_pct" in restrictions:
            if target.hp_percentage > restrictions["target_hp_below_pct"]: #will deal with this, dw
                return False
        if "target_has_debuff" in restrictions:
            if not target.has_debuff(restrictions["target_has_debuff"]):
                return False
        if "caster_requires_buff" in restrictions:
            if not caster.has_buff(restrictions["caster_requires_buff"]):
                return False
        return True


    def apply_cooldown_locks(self, caster, sim):
        if self.triggers_gcd:
            caster.next_gcd = sim.current_time + caster.calculate_gcd(self.base_gcd)
        if self.cooldown > 0.0:
            caster.cooldowns[self.name] = sim.current_time + caster.calculate_cooldown(self.cooldown)

    def cast(self, caster, target, sim) -> bool:
        if not self.can_cast(caster, target, sim):
            return False
        caster.resource.spend(self.energy_cost)

        print(f"[{sim.current_time:.2f}s] {caster.name} casts {self.name}")
        self.apply_cooldown_locks(caster, sim)
        for action in self.actions: #do all the things the ability commands
            if not is_action_valid(action, target, caster):
                continue

            if "chance" in action and random.random() > action["chance"]:
                continue

            action_type = action.get("action_type")
            delay = action.get("delay", 0.0)
            if action_type == "direct_hit": #we schedule it to hit after the delay
                hit_event = DamageHit(caster, target, action, self.name)
                sim.schedule_relative(delay, hit_event)
            elif action_type == "dot":
                scaled_interval = caster.scale_time_modifier(action["interval"])
                existing_dot = target.dots.get(self.name)

                if existing_dot:
                    existing_dot.ticks_remaining = action["total_ticks"]
                    existing_dot.interval = scaled_interval
                    existing_dot.action_data = action

                    if action.get("instant_tick", False):
                        tick_delay = action.get("instant_tick_delay", 0.0)
                        instant_hit = DamageHit(caster, target, action, f"{self.name} (Instant Refresh)")
                        sim.schedule_relative(tick_delay, instant_hit)
                        existing_dot.ticks_remaining -= 1
                else:
                    dot_instance = ActiveDot(
                        name=self.name,
                        interval=scaled_interval,
                        ticks_remaining=action["total_ticks"],
                        action_data=action
                    )
                    target.dots[self.name] = dot_instance

                    if action.get("instant_tick", False):
                        tick_delay = action.get("instant_tick_delay", 0.0)
                        instant_hit = DamageHit(caster, target, action, self.name)
                        sim.schedule_relative(tick_delay, instant_hit)
                        dot_instance.ticks_remaining -= 1

                    sim.schedule_relative(scaled_interval, DotTick(caster, target, dot_instance))
            elif action_type == "buff":
                buff_key, buff_instance, duration, is_fresh = caster.apply_buff(action, self.name, sim.current_time)
                if is_fresh:
                    sim.schedule_relative(duration, BuffExpire(caster, buff_key, buff_instance))
            elif action_type == "debuff":
                debuff_key, debuff_instance, duration, is_fresh = target.apply_debuff(action, self.name)
                if is_fresh:
                    sim.schedule_relative(duration, DebuffExpire(target, debuff_key, debuff_instance))
            elif action_type == "resource_gain":
                regen = action.get("value", 0.0)
                sim.schedule_relative(delay, ResourceGainEvent(caster, regen))


        return True


def is_action_valid(action_data, target, caster):
    conditions = action_data.get("conditions", {})
    if not conditions:
        return True

    if "exact_dot_amount" in conditions:
        actual_count = target.count_active_dots
        required_count = conditions.get("required_count", 0)
        if actual_count != required_count:
            return False
    if "has_dot" in conditions:
        actual_count = target.count_active_dots
        if actual_count == 0:
            return False
    if "has_debuff" in conditions:
        return target.has_debuff(conditions["has_debuff"])
    if "has_buff" in conditions:
        return caster.has_buff(conditions["has_buff"])
    if "does_not_have_debuff" in conditions:
        return not target.has_debuff(conditions["does_not_have_debuff"])
    return True
