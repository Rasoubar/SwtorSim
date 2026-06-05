from events import DamageHit, DotTick, BuffExpire, DebuffExpire

class Ability:
    def __init__(self, config: dict):
        self.name = config["name"]
        self.cooldown = config.get("cooldown",0.0)
        self.triggers_gcd = config.get("triggers_gcd", True)
        self.base_gcd = config.get("base_gcd", 1.5)
        self.actions = config.get ("effects", [])

    def can_cast(self, caster, sim) -> bool:
        if self.triggers_gcd and sim.current_time < caster.next_gcd:
            return False
        if sim.current_time < caster.cooldowns.get(self.name, 0.0):
            return False
        return True

    def apply_cooldown_locks(self, caster, sim):
        if self.triggers_gcd:
            caster.next_gcd = sim.current_time + caster.calculate_gcd(self.base_gcd)
        if self.cooldown > 0.0:
            caster.cooldowns[self.name] = sim.current_time + caster.calculate_cooldown(self.cooldown)

    def cast(self, caster, target, sim) -> bool:
        if not self.can_cast(caster, sim):
            return False

        print(f"[{sim.current_time:.2f}s] {caster.name} casts {self.name}")
        self.apply_cooldown_locks(caster, sim)

        for action in self.actions: #do all the things the ability commands
            action_type = action.get("type")
            delay = action.get("delay", 0.0)
            if action_type == "direct_hit": #we schedule it to hit after the delay
                hit_event = DamageHit(caster, target, action, self.name)
                sim.schedule_relative(delay, hit_event)
            elif action_type == "dot":
                scaled_interval = caster.scale_time_modifier(action["interval"])
                dot_instance = {
                    "name": self.name,
                    "interval": scaled_interval,
                    "ticks_remaining": action["total_ticks"],
                    "action data": action
                }
                target.dots[self.name] = dot_instance
                if action.get("instant_tick", False):
                    instant_hit = DamageHit(caster, target, action["value"], self.name)
                    instant_hit.resolve(sim)
                    dot_instance["ticks_remaining"] -= 1
                sim.schedule_relative(action["interval"], DotTick(caster, target, dot_instance)) #interval will be affected by alacrity too
            elif action_type == "buff":
                buff_key, buff_instance, duration = caster.apply_buff(action, self.name)
                sim.schedule_relative(duration, BuffExpire(caster, buff_key, buff_instance))
            elif action_type == "debuff":
                debuff_key, debuff_instance, duration = target.apply_debuff(action, self.name)
                sim.schedule_relative(duration, DebuffExpire(target, debuff_key, debuff_instance))

        return True
