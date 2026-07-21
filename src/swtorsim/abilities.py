import random
from src.swtorsim.events import DamageHit, BuffExpire, DebuffExpire, DotTick, ResourceGainEvent, ChannelTickEvent
from src.swtorsim.combat_math import accuracy_roll
from src.swtorsim.entities import Player, Target
from src.swtorsim.effects import ActiveDot, ActiveChannel
from src.swtorsim.requirements import validate_all


def execute_single_action(sim, caster, target, action: dict, source_name: str):
    """Calls the appropriate function for the action type"""
    if not validate_all(action.get("conditions", {}), caster, target, sim=sim):
        return False
    if "chance" in action and random.random() > action["chance"]:
        return False
    action_type = action.get("action_type")
    delay = action.get("delay", 0.0)
    if action_type == "damage":
        return handle_damage_action(sim, caster, target, action, source_name, delay)
    elif action_type == "dot":
        handle_dot_action(sim, caster, target, action, source_name)
    elif action_type == "channel":
        handle_channel_action(sim, caster, target, action, source_name)
    elif action_type == "buff":
        handle_buff_action(sim, caster, action, source_name, sim.current_time)
    elif action_type == "debuff":
        handle_debuff_action(sim, target, action, source_name, sim.current_time)
    elif action_type == "resource_gain":
        handle_resource_gain_action(sim, caster, action, delay)
    elif action_type == "cooldown_mod":
        handle_cooldown_modification(sim, caster, action)
    elif action_type == "grant_charge":
        handle_restore_charge(sim, caster, action)
    elif action_type == "buff_remove":
        handle_buff_remove_action(sim, caster, action)
    else:
        raise ValueError(
            f"CRITICAL ENGINE ERROR: Unrecognized action_type '{action_type}' "
            f"triggered by '{source_name}'. Please check your JSON blueprints."
        )
    return True


def handle_damage_action(sim, caster, target, action, source_name, delay):
    """Rolls accuracy then schedules or executes the hit"""
    if not accuracy_roll(caster, action.get("hand", "main")):
        return False
    hit_event = DamageHit(caster, target, action, source_name)
    if delay > 0.0:
        sim.schedule_relative(delay, hit_event)
    else:
        hit_event.resolve(sim)
    return True


def handle_dot_action(sim, caster, target, action, source_name):
    """Calculates how often the dot ticks, creates the dots, channels the 1st tick"""
    scaled_interval = caster.scale_time_modifier(action["interval"])
    dot_instance = ActiveDot(
        name=source_name,
        interval=scaled_interval,
        ticks_remaining=action["total_ticks"],
        action_data=action
    )
    target.dots[source_name] = dot_instance
    sim.schedule_relative(scaled_interval, DotTick(caster, target, dot_instance))


def handle_channel_action(sim, caster, target, action_data: dict, source_name: str):
    """Flags the caster as channeling, creates the channel instance, and schedules the first tick"""
    caster.is_channeling = True

    tick_interval = action_data.get("tick_interval", 3.0)
    total_ticks = action_data.get("channel_ticks", 4)
    tick_cost = action_data.get("tick_cost", 0.0)

    new_channel = ActiveChannel(source_name, action_data, total_ticks, tick_interval, tick_cost)
    caster.active_channel = new_channel
    print(f"[{sim.current_time:.3f}] {caster.name} started channeling {source_name}.")

    first_tick_time = sim.current_time

    sim.schedule_absolute(first_tick_time, ChannelTickEvent(caster, target, new_channel))


def handle_buff_action(sim, caster, action, source_name, current_time):
    """Applies the buff to the caster and schedules it's expiration"""
    buff_key, buff_instance, duration = caster.apply_buff(action, source_name, current_time)
    sim.schedule_relative(duration, BuffExpire(caster, buff_key, buff_instance))


def handle_debuff_action(sim, target, action, source_name, current_time):
    """Applies the debuff to the target and schedules it's expiration"""
    debuff_key, debuff_instance, duration = target.apply_debuff(action, source_name, current_time)
    sim.schedule_relative(duration, DebuffExpire(target, debuff_key, debuff_instance))


def handle_resource_gain_action(sim, caster, action, delay):
    """Schedules or executes the resource gain event"""
    regen = action.get("value", 0.0)
    gain_event = ResourceGainEvent(caster, regen)
    if delay > 0.0:
        sim.schedule_relative(delay, gain_event)
    else:
        gain_event.resolve(sim)

def handle_cooldown_modification(sim, caster, action):
    """Applies cooldown reductions or resets to targeted abilities"""
    cooldown_dict = getattr(caster, "cooldowns", {})
    ability_db = sim.ability_db
    if not (cooldown_dict and ability_db and "target_tags" in action):
        return
    reset_tags = frozenset(action["target_tags"])
    is_reset = action.get("reset", False)
    for cd_key in list(cooldown_dict.keys()):
        if cooldown_dict[cd_key] <= sim.current_time: #clean the ones gone
            del cooldown_dict[cd_key]
            continue
        ability_data = ability_db.get(cd_key.lower().replace(" ", "_")) #I'll change JSON a bit to get rid of this string manipulation. eventually
        ability_tags = getattr(ability_data, 'tags', frozenset()) if ability_data else frozenset()
        if reset_tags & ability_tags:
            if is_reset:
                del cooldown_dict[cd_key]
            else:
                reduction = action.get("value", 0.0)
                new_cd = max(sim.current_time, cooldown_dict[cd_key] - reduction)
                cooldown_dict[cd_key] = new_cd
                if cooldown_dict[cd_key] <= sim.current_time:
                    del cooldown_dict[cd_key]


def handle_restore_charge(sim, _caster, action): #might want to change so that the ability_db is on the player
    """Restores a charge to the target ability"""
    target_ability_name = action.get("target_ability")
    amount = action.get("amount", 1)
    if target_ability_name in sim.ability_db:
        ability = sim.ability_db[target_ability_name]
        ability.add_charge(amount)

def handle_buff_remove_action(sim, caster, action):
    """Removes a buff from the caster"""
    effect_name = action.get("effect_name")
    if effect_name and caster.has_buff(effect_name):
        caster.cleanup_expired_effects([effect_name])
        print(f"[{sim.current_time:.3f}] {caster.name} consumed/removed buff: {effect_name}")


class Ability:
    """Represents """
    def __init__(self, config: dict):
        self.name = config["name"]
        self.cooldown = config.get("cooldown",0.0)
        self.triggers_gcd = config.get("triggers_gcd", True)
        self.base_gcd = config.get("base_gcd", 1.5)
        self.actions = config.get ("actions", [])
        self.energy_cost = config.get("energy_cost", 0.0)
        self.tags = frozenset(config.get("tags", []))
        self.conditions = config.get("conditions", {})
        self.has_charges = config.get("max_charges", 0) > 0
        if self.has_charges:
            self.max_charges = config.get("max_charges",1)
            self.charges = self.max_charges
            self.recharge_time = config.get("recharge_time", self.cooldown)
            self.last_charge_time = 0.0

    def update_charges(self, caster, sim):
        if  self.recharge_time <= 0:
            return
        if self.charges < self.max_charges:
            time_elapsed = sim.current_time - self.last_charge_time
            actual_recharge_time = caster.calculate_cooldown(self.recharge_time)
            charges_gained = int(time_elapsed // actual_recharge_time)
            if charges_gained > 0:
                self.charges = min(self.max_charges, self.charges + charges_gained)
                self.last_charge_time += charges_gained * actual_recharge_time

    def add_charge(self, amount=1):
        self.charges = min(self.max_charges, self.charges + amount)

    def can_cast(self, caster: "Player", target: "Target", sim) -> bool:
        if self.triggers_gcd and sim.current_time < caster.next_gcd: #redundant right now, possibly will catch bugs
            return False

        if getattr(caster, "active_channel", None) is not None: #to improve when channel clipping is implemented
            return False

        if self.has_charges:
            self.update_charges(caster,sim)
            if self.charges < 1:
                return False

        if sim.current_time < caster.cooldowns.get(self.name, 0.0):
            return False

        modified_cost = caster.calculate_resource_cost(self.name, self.energy_cost, apply = False)

        if not caster.resource.can_afford(modified_cost): #I had a more eficient aproach to this. Like this rn, will change
            return False

        return validate_all(self.conditions, caster, target) #validates conditions

    def apply_cooldown_locks(self, caster, sim):
        #fuck floating points but i dont wanna go integer
        caster.next_gcd = round(sim.current_time, 4)
        if self.triggers_gcd:
            caster.next_gcd = round(sim.current_time + caster.calculate_gcd(self.base_gcd), 4)
        if self.has_charges:
            if self.charges == self.max_charges:
                self.last_charge_time = round(sim.current_time, 4)
            self.charges -= 1
        elif self.cooldown > 0.0:
            caster.cooldowns[self.name] = round(sim.current_time + caster.calculate_cooldown(self.cooldown), 4)

    def cast(self, caster, target, sim) -> bool:
        if not self.can_cast(caster, target, sim):
            return False

        if getattr(caster, "active_channel", None) is not None:
            print(f"[{sim.current_time:.3f}] {caster.class_name} interrupted channel to cast {self.name}!")
            caster.active_channel = None
            caster.is_channeling = False

        final_spend = caster.calculate_resource_cost(self.name, self.energy_cost, apply = True)
        caster.resource.spend(final_spend)
        print(f"[{sim.current_time:.2f}s] {caster.name} casts {self.name}")
        self.apply_cooldown_locks(caster, sim)
        self.evaluate_on_cast_procs(caster, target, sim)

        for action in self.actions:
            success = execute_single_action(sim, caster, target, action, self.name)
            if success and "on_success_actions" in action:
                for child_action in action["on_success_actions"]:
                    execute_single_action(sim, caster, target, child_action, self.name)
        return True

    def evaluate_on_cast_procs(self, caster, target, sim):
        for proc in caster.procs.values():
            if proc.trigger != "cast":
                continue
            if proc.required_tags and not (proc.required_tags & self.tags):
                continue
            if sim.current_time < proc.next_possible_proc:
                continue
            print(f'On cast proc {proc.name} triggered.')
            if random.random() < proc.chance:
                current_icd = caster.scale_time_modifier(proc.icd) if proc.affected_by_cdr else proc.icd
                proc.next_possible_proc = round(sim.current_time + current_icd,4)
                for action in proc.actions:
                    execute_single_action(sim, caster, target, action, proc.name)