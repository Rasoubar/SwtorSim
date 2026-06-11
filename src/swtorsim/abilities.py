import random
from src.swtorsim.events import DamageHit, BuffExpire, DebuffExpire, DotTick, ResourceGainEvent
from src.swtorsim.entities import ActiveDot, Player, Target
from src.swtorsim.requirements import validate_all


def execute_single_action(sim, caster, target, action: dict, source_name: str):
    if not validate_all(action.get("conditions", {}), caster, target):
        return
    if "chance" in action and random.random() > action["chance"]:
        return
    action_type = action.get("action_type")
    delay = action.get("delay", 0.0)

    if action_type == "damage":
        _handle_damage_action(sim, caster, target, action, source_name, delay)
    elif action_type == "dot":
        _handle_dot_action(sim, caster, target, action, source_name)
    elif action_type == "buff":
        _handle_buff_action(sim, caster, action, source_name, sim.current_time)
    elif action_type == "debuff":
        _handle_debuff_action(sim, target, action, source_name, sim.current_time)
    elif action_type == "resource_gain":
        _handle_resource_gain_action(sim, caster, action, delay)
    elif action_type == "cooldown_mod":
        _handle_cooldown_modification(sim, caster, action)



def _handle_damage_action(sim, caster, target, action, source_name, delay):
    hit_event = DamageHit(caster, target, action, source_name)
    sim.schedule_relative(delay, hit_event)


def _handle_dot_action(sim, caster, target, action, source_name):
    scaled_interval = caster.scale_time_modifier(action["interval"])
    dot_instance = ActiveDot(
        name=source_name,
        interval=scaled_interval,
        ticks_remaining=action["total_ticks"],
        action_data=action
    )
    target.dots[source_name] = dot_instance

    if action.get("instant_tick", False):
        tick_delay = action.get("instant_tick_delay", 0.0)
        for sub_action in dot_instance.choose_action(caster, target):
            instant_hit = DamageHit(caster, target, sub_action, source_name)
            sim.schedule_relative(tick_delay, instant_hit)

    sim.schedule_relative(scaled_interval, DotTick(caster, target, dot_instance))


def _handle_buff_action(sim, caster, action, source_name, current_time):
    buff_key, buff_instance, duration = caster.apply_buff(action, source_name, current_time)

    sim.schedule_relative(duration, BuffExpire(caster, buff_key, buff_instance))


def _handle_debuff_action(sim, target, action, source_name, current_time):
    debuff_key, debuff_instance, duration = target.apply_debuff(action, source_name, current_time)
    sim.schedule_relative(duration, DebuffExpire(target, debuff_key, debuff_instance))


def _handle_resource_gain_action(sim, caster, action, delay):
    regen = action.get("value", 0.0)
    sim.schedule_relative(delay, ResourceGainEvent(caster, regen))


def _handle_cooldown_modification(sim, caster, action):
    cooldown_dict = getattr(caster, "cooldowns", {})
    player_db = getattr(caster, "abilities_db", {})
    if not (cooldown_dict and player_db and "target_tags" in action):
        return
    reset_tags = set(action["target_tags"])
    is_reset = action.get("reset", False)
    for cd_key in list(cooldown_dict.keys()):
        if cooldown_dict[cd_key] <= sim.current_time: #clean the ones gone
            del cooldown_dict[cd_key]
            continue
        ability_data = player_db.get(cd_key.upper()) #I'll change JSON a bit to get rid of this upper(), eventually
        ability_tags = getattr(ability_data, 'tags', []) if ability_data else []
        if reset_tags & set(ability_tags):
            if is_reset:
                del cooldown_dict[cd_key]
                print(f"   >> [COOLDOWN] {cd_key} has been completely RESET!")
            else:
                reduction = action.get("value", 0.0)
                new_cd = max(sim.current_time, cooldown_dict[cd_key] - reduction)
                cooldown_dict[cd_key] = new_cd
                if cooldown_dict[cd_key] <= sim.current_time:
                    del cooldown_dict[cd_key]
class Ability:
    def __init__(self, config: dict):
        self.name = config["name"]
        self.cooldown = config.get("cooldown",0.0)
        self.triggers_gcd = config.get("triggers_gcd", True)
        self.base_gcd = config.get("base_gcd", 1.5)
        self.actions = config.get ("actions", [])
        self.energy_cost = config.get("energy_cost", 0.0)
        self.tags=config.get("tags",[])
        self.conditions = config.get("conditions", {})

    def can_cast(self, caster: "Player", target: "Target", sim) -> bool:
        if self.triggers_gcd and sim.current_time < caster.next_gcd:
            return False
        if sim.current_time < caster.cooldowns.get(self.name, 0.0):
            return False
        modified_cost = caster.calculate_resource_cost(self.name, self.energy_cost, apply = False)
        if not caster.resource.can_afford(modified_cost): #considered caching this. didn't do it to keep code cleaner
            return False
        return validate_all(self.conditions, caster, target) #validates conditions

    def apply_cooldown_locks(self, caster, sim):
        if self.triggers_gcd:
            caster.next_gcd = sim.current_time + caster.calculate_gcd(self.base_gcd)
        if self.cooldown > 0.0:
            caster.cooldowns[self.name] = sim.current_time + caster.calculate_cooldown(self.cooldown)

    def cast(self, caster, target, sim) -> bool:
        if not self.can_cast(caster, target, sim):
            return False
        final_spend = caster.calculate_resource_cost(self.name, self.energy_cost, apply = True)
        caster.resource.spend(final_spend)
        print(f"[{sim.current_time:.2f}s] {caster.name} casts {self.name}")
        self.apply_cooldown_locks(caster, sim)
        for action in self.actions:
            execute_single_action(sim, caster, target, action, self.name)
        return True
