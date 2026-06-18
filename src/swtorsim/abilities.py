import random
from src.swtorsim.events import DamageHit, BuffExpire, DebuffExpire, DotTick, ResourceGainEvent, ChannelTickEvent
from src.swtorsim.entities import ActiveDot, Player, Target, ActiveChannel
from src.swtorsim.requirements import validate_all


def execute_single_action(sim, caster, target, action: dict, source_name: str):
    if not validate_all(action.get("conditions", {}), caster, target):
        return
    if "chance" in action and random.random() > action["chance"]:
        return
    action_type = action.get("action_type")
    delay = action.get("delay", 0.0)

    if action_type == "damage":
        handle_damage_action(sim, caster, target, action, source_name, delay)
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
    elif action_type =="grant_charge":
        handle_restore_charge(sim, caster, action)



def handle_damage_action(sim, caster, target, action, source_name, delay):
    hit_event = DamageHit(caster, target, action, source_name)
    sim.schedule_relative(delay, hit_event)


def handle_dot_action(sim, caster, target, action, source_name):
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


def handle_channel_action(sim, caster, target, action_data: dict, source_name: str):

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
    buff_key, buff_instance, duration = caster.apply_buff(action, source_name, current_time)

    sim.schedule_relative(duration, BuffExpire(caster, buff_key, buff_instance))


def handle_debuff_action(sim, target, action, source_name, current_time):
    debuff_key, debuff_instance, duration = target.apply_debuff(action, source_name, current_time)
    sim.schedule_relative(duration, DebuffExpire(target, debuff_key, debuff_instance))


def handle_resource_gain_action(sim, caster, action, delay):
    regen = action.get("value", 0.0)
    sim.schedule_relative(delay, ResourceGainEvent(caster, regen))


def handle_cooldown_modification(sim, caster, action):
    cooldown_dict = getattr(caster, "cooldowns", {})
    ability_db = sim.ability_db
    if not (cooldown_dict and ability_db and "target_tags" in action):
        return
    reset_tags = set(action["target_tags"])
    is_reset = action.get("reset", False)
    for cd_key in list(cooldown_dict.keys()):
        if cooldown_dict[cd_key] <= sim.current_time: #clean the ones gone
            del cooldown_dict[cd_key]
            continue
        ability_data = ability_db.get(cd_key.lower().replace(" ", "_")) #I'll change JSON a bit to get rid of this string manipulation. eventually
        ability_tags = getattr(ability_data, 'tags', []) if ability_data else []
        if reset_tags & set(ability_tags):
            if is_reset:
                del cooldown_dict[cd_key]
            else:
                reduction = action.get("value", 0.0)
                new_cd = max(sim.current_time, cooldown_dict[cd_key] - reduction)
                cooldown_dict[cd_key] = new_cd
                if cooldown_dict[cd_key] <= sim.current_time:
                    del cooldown_dict[cd_key]


def handle_restore_charge(sim, caster, action):
    target_ability_name = action.get("target_ability")
    amount = action.get("amount", 1)
    if target_ability_name in caster.abilities_db:
        ability = caster.abilities_db[target_ability_name]
        ability.add_charge(amount)


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
        if getattr(caster, "active_channel", None) is not None:
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
        caster.next_gcd = sim.current_time
        if self.triggers_gcd:
            caster.next_gcd += caster.calculate_gcd(self.base_gcd)
        if self.has_charges:
            if self.charges == self.max_charges:
                self.last_charge_time = sim.current_time
            self.charges -= 1
        elif self.cooldown > 0.0:
            caster.cooldowns[self.name] = sim.current_time + caster.calculate_cooldown(self.cooldown)

    def cast(self, caster, target, sim) -> bool:
        if not self.can_cast(caster, target, sim):
            return False
        if getattr(caster, "active_channel", None) is not None:
            print(f"[{sim.current_time:.3f}] {caster.class_name} interrupted channel to cast {self.name}!")
            caster.active_channel = None
            caster.is_channeling = False
        final_spend = caster.calculate_resource_cost(self.name, self.energy_cost, apply = True)
        print(f'final spend: {final_spend}')
        print(f'caster.resource.current_value: {caster.resource.current_value}')
        caster.resource.spend(final_spend)
        print(f'caster.resource.current_value: {caster.resource.current_value}')
        print(f"[{sim.current_time:.2f}s] {caster.name} casts {self.name}")
        self.apply_cooldown_locks(caster, sim)
        self.evaluate_on_cast_procs(caster, target, sim)
        for action in self.actions:
            execute_single_action(sim, caster, target, action, self.name)
        return True

    def evaluate_on_cast_procs(self, caster, target, sim):
        for proc in caster.procs.values():
            if proc.trigger != "on_cast":
                continue
            if proc.required_tags:
                if not any(tag in self.tags for tag in proc.required_tags):
                    continue
            if sim.current_time < proc.next_possible_proc:
                continue
            print("made it 3x")
            if random.random() < proc.chance:
                current_icd = caster.scale_time_modifier(proc.icd) if proc.affected_by_cdr else proc.icd
                proc.next_possible_proc = sim.current_time + current_icd
                for action in proc.actions:
                    print(proc.actions)
                    execute_single_action(sim, caster, target, action, proc.name)