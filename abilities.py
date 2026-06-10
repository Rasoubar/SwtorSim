import random
from events import DamageHit, BuffExpire, DebuffExpire, DotTick, ResourceGainEvent
from entities import ActiveDot, Player, Target
from requirements import validate_all


def execute_single_action(sim, caster, target, action: dict, source_name: str): #this function is ugly. I'll get to it eventually.
    if not is_action_valid(action, target, caster):
        return
    if "chance" in action and random.random() > action["chance"]:
        return
    action_type = action.get("action_type")
    delay = action.get("delay", 0.0)
    if action_type == "damage":
        hit_event = DamageHit(caster, target, action, source_name)
        sim.schedule_relative(delay, hit_event)
    elif action_type == "dot":
        scaled_interval = caster.scale_time_modifier(action["interval"])
        dot_instance = ActiveDot(
            name=source_name,
            interval=scaled_interval,
            ticks_remaining=action["total_ticks"],
            action_data=action)
        target.dots[source_name] = dot_instance
        if action.get("instant_tick", False):
            tick_delay = action.get("instant_tick_delay", 0.0)
            valid_instant_actions=dot_instance.choose_action(caster, target)
            for sub_action in valid_instant_actions:
                print(sub_action)
                instant_hit = DamageHit(caster, target, sub_action, source_name)
                sim.schedule_relative(tick_delay, instant_hit)
        sim.schedule_relative(scaled_interval, DotTick(caster, target, dot_instance))
    elif action_type == "buff":
        buff_key, buff_instance, duration = caster.apply_buff(action, source_name, sim.current_time)
        sim.schedule_relative(duration, BuffExpire(caster, buff_key, buff_instance))
    elif action_type == "debuff":
        debuff_key, debuff_instance, duration = target.apply_debuff(action, source_name, sim.current_time)
        sim.schedule_relative(duration, DebuffExpire(target, debuff_key, debuff_instance))
    elif action_type == "resource_gain":
        regen = action.get("value", 0.0)
        sim.schedule_relative(delay, ResourceGainEvent(caster, regen)) #vent heat exists, this prepares for it. doing the imediate ones a microsend later should not have impact
        print(f'gained {regen:.2f} force')
    elif action_type == "cooldown_mod":
        is_reset = action.get("reset", False)
        cooldown_dict = getattr(caster, "cooldowns", None)
        player_db = getattr(caster, "abilities_db", None)

        print(action["target_tags"])
        print(cooldown_dict)
        print(player_db)
        if cooldown_dict and player_db and "target_tags" in action:
            reset_tags = set(action["target_tags"])
            for cooldown in list(cooldown_dict.keys()):
                if cooldown_dict[cooldown] <= sim.current_time:
                    del cooldown_dict[cooldown]
                    continue
                target_ability = cooldown_dict.get(cooldown)
                if target_ability:
                    ability_tags = getattr(player_db[cooldown.upper()], 'tags', []) #this is all a bit over the knee. it's late
                    if reset_tags & set(ability_tags):
                        current_cd_timestamp = cooldown_dict[cooldown]
                        if current_cd_timestamp > sim.current_time:
                            if is_reset:
                                del cooldown_dict[cooldown]
                                print(f"   >> [COOLDOWN] {cooldown} cooldown has been completely RESET via tags!")
                            else:
                                reduction = action.get("value", 0.0)
                                new_cd = max(sim.current_time, current_cd_timestamp - reduction)
                                cooldown_dict[cooldown] = new_cd
                                remaining = new_cd - sim.current_time
                                print(
                                    f"   >> [COOLDOWN] {cooldown} cooldown reduced by {reduction}s. (Remaining: {remaining:.2f}s)")
                                if cooldown_dict[cooldown] <= sim.current_time:
                                    del cooldown_dict[cooldown]

class Ability:
    def __init__(self, config: dict):
        self.name = config["name"]
        self.cooldown = config.get("cooldown",0.0)
        self.triggers_gcd = config.get("triggers_gcd", True)
        self.base_gcd = config.get("base_gcd", 1.5)
        self.actions = config.get ("actions", [])
        self.energy_cost = config.get("energy_cost", 0.0)
        self._calculated_cost = None
        self.tags=config.get("tags",[])
        self.restrictions = config.get("restrictions", {})

    def can_cast(self, caster: "Player", target: "Target", sim) -> bool:
        if self.triggers_gcd and sim.current_time < caster.next_gcd:
            return False
        if sim.current_time < caster.cooldowns.get(self.name, 0.0):
            return False
        modified_cost = caster.calculate_resource_cost(self.name, self.energy_cost)
        if not caster.resource.can_afford(modified_cost):
            self._calculated_cost = modified_cost
            return False

        return validate_all(self.restrictions, caster,target)


    def apply_cooldown_locks(self, caster, sim):
        if self.triggers_gcd:
            caster.next_gcd = sim.current_time + caster.calculate_gcd(self.base_gcd)
        if self.cooldown > 0.0:
            caster.cooldowns[self.name] = sim.current_time + caster.calculate_cooldown(self.cooldown)

    def cast(self, caster, target, sim) -> bool:
        if not self.can_cast(caster, target, sim):
            return False
        if getattr(self, "_calculated_cost", None) is not None:
            final_spend = self._calculated_cost
        else:
            final_spend = caster.calculate_resource_cost(self.name, self.energy_cost)
            if caster.resource.can_afford(final_spend):
                self._calculated_cost = final_spend
            else:
                return False
        caster.resource.spend(final_spend)
        self._calculated_cost = None
        print(f"[{sim.current_time:.2f}s] {caster.name} casts {self.name}")
        self.apply_cooldown_locks(caster, sim)
        for action in self.actions: #do all the things the ability commands
            execute_single_action(sim, caster, target, action, self.name)
        print(caster.resource.current_value)
        return True


def is_action_valid(action_data, target, caster):
    conditions = action_data.get("conditions", {})
    if not conditions:
        return True
    return validate_all(conditions, caster, target)
