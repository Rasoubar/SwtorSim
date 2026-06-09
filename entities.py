import math
from combat_math import EFFECTS

class ActiveDot:
    __slots__ = ['name', 'interval', 'ticks_remaining', 'action_data']

    def __init__(self, name, interval, ticks_remaining, action_data):
        self.name = name
        self.interval = interval
        self.ticks_remaining = ticks_remaining
        self.action_data = action_data


class ActiveBuff:
    __slots__ = [
        'id', 'effect_name', 'stat_name', 'value', 'expires_at', 'source_ability', 'required_tags', 'charges', 'consumable_charges',
        'max_charges', 'proc_data', 'last_proc_at','target_hp_threshold']

    def __init__(self, id_num, effect_name, stat_name, value, expires_at, source_ability,
                 required_tags=None, charges=None, consumable_charges=None, max_charges = None, target_hp_threshold = None):
        self.id = id_num
        self.effect_name = effect_name
        self.stat_name = stat_name
        self.value = value
        self.expires_at = expires_at
        self.source_ability = source_ability
        self.required_tags = required_tags
        self.charges = charges
        self.consumable_charges = consumable_charges
        self.max_charges = max_charges
        self.target_hp_threshold = target_hp_threshold

class ProcData:
    __slots__ = ['name','action','chance','icd','next_possible_proc','trigger','required_tag','affected_by_cdr']

    def __init__(self, name: str, trigger: str, action: dict,
                 required_tag: str = None, chance: float = 1.0, icd: float = 0.0, affected_by_cdr = False):
        self.name = name
        self.trigger = trigger
        self.required_tag = required_tag
        self.chance = chance
        self.icd = icd
        self.action = action
        self.next_possible_proc = 0.0
        self.affected_by_cdr = affected_by_cdr

class Actor:
    def __init__(self, name: str):
        self.name = name

class Player(Actor):
    def __init__(self, name: str):
        super().__init__(name)
        self.next_gcd = 0.0
        self.cooldowns= {}
        self.effects = {}
        self.procs = {}
        self.rotation = None
        self.resource = ResourcePool(pool_type="Force", max_value=100.0, base_regen=8.0)
        self.base_stats = {
            "Alacrity": 0.0,
            "Critical Chance": 0.0,
            "Critical Modifier": 0.0,
            "Critical Rating": 0.0,
            "Mastery": 0.0,
            "Power": 0.0,
            "Force Power": 0.0,
            "M_Bonus_Damage": 0.0,
            "Alacrity Rating": 0.0,
            "F_Bonus_Damage": 0.0,
            "Main_hand_min": 0.0,
            "Main_hand_max": 0.0,
            "Off_hand_min": 0.0,
            "Off_hand_max": 0.0,
            "Standard_health": 0.0,
            "Armor Penetration": 0.0
        }
        self.stats = self.base_stats.copy()

    def calculate_gcd(self, base_gcd: float = 1.5) -> float:
        gcd = self.scale_time_modifier(base_gcd)
        scaled_gcd = math.ceil(gcd * 10) / 10
        return scaled_gcd

    def calculate_cooldown(self, base_cooldown: float) -> float:
        cdr = self.stats.get("Alacrity", 0.0)
        cooldown = base_cooldown / (1.0 + cdr)
        scaled_cooldown = math.ceil(cooldown * 10) / 10
        return round(scaled_cooldown, 2)

    def get_stat(self, stat_name: str) -> float:
        base_value = self.stats.get(stat_name, 0.0)
        modifier = 0.0
        for effect in self.effects.values():
            if effect.stat_name == stat_name:
                multiplier = effect.charges if effect.max_charges is not None else 1
                modifier += effect.value * multiplier
        return base_value + modifier

    def scale_time_modifier(self, base_time: float) -> float:
        cdr = self.stats.get("Alacrity",0.0)
        return base_time / (1.0 + cdr)

    def apply_buff(self, action: dict, source_name: str, current_time): #can be improved on the refresh

        from combat_math import EFFECTS
        try:
            action_id = action.get("id")
            extracted_stat = EFFECTS[action_id]["stat_name"]
        except (KeyError, TypeError) as e:
            print(f"🚨 CONFIGURATION CRASH in apply_buff via [{source_name}]")
            print(f"👉 Action ID {action.get('id')} is completely missing from the EFFECTS database!")
            raise e
        duration = action["duration"]
        if action.get("affected_by_cdr", False):
            duration = self.scale_time_modifier(duration)

        buff_key = action.get("effect_name", f"{source_name}_{action['stat_name']}")
        expiration_timestamp = current_time + duration

        existing_buff = self.effects.get(buff_key)

        if existing_buff:
            existing_buff.expires_at = expiration_timestamp
            if existing_buff.max_charges is not None:
                current_charges = min(existing_buff.max_charges, existing_buff.charges + 1) #WATCH
            elif "charges" in action:
                current_charges = action["charges"]
            else: #it was this or action.get("charges"), this faster
                current_charges = existing_buff.charges
        else:
            current_charges = action.get("charges", 1)

        raw_tags = action.get("required_tags")
        if raw_tags is not None:
            tags_set = set(raw_tags) if isinstance(raw_tags, (list, tuple, set)) else {raw_tags}
        else:
            tags_set = None

        buff_instance = ActiveBuff(
            id_num=action.get("id"),
            effect_name=buff_key,
            stat_name=extracted_stat,
            value=action["value"],
            expires_at=expiration_timestamp,
            source_ability=source_name,
            required_tags=tags_set,
            charges= current_charges,
            consumable_charges=action.get("consumable_charges"),
            max_charges=action.get("max_charges"),
            target_hp_threshold=action.get("target_hp_threshold")
        )

        self.effects[buff_key] = buff_instance

        effect_id = buff_instance.id
        if effect_id in EFFECTS:
            stat_name = EFFECTS[effect_id]["stat_name"]
            if stat_name in {"Mastery Stat", "Power Stat", "Bonus Damage", "Critical Stat"}:
                self.recalculate_stats()

        return buff_key, buff_instance, duration
    def recalculate_stats(self): #because relics hate me

        temp_stats = self.base_stats.copy()
        bonus_mastery = 0
        bonus_power = 0
        bonus_critical_rating = 0
        bonus_alacrity_rating = 0
        damage_bonus_multiplier = 1
        for buff in self.effects.values():
            effect_id = buff.id
            if effect_id in EFFECTS:
                multiplier = buff.charges if buff.max_charges is not None else 1
                stat_name = EFFECTS[effect_id]["stat_name"]
                if stat_name == "Mastery Stat":
                    bonus_mastery += buff.value * 1.05
                elif stat_name == "Power Stat":
                    bonus_power += buff.value
                elif stat_name == "Critical Stat":
                    bonus_critical_rating += buff.value
                elif stat_name == "Alacrity Rating":
                    bonus_alacrity_rating += buff.value
                elif stat_name == "Bonus Damage":
                    damage_bonus_multiplier += (buff.value * multiplier)

        temp_stats["Mastery"]  = temp_stats["Mastery"] + bonus_mastery
        temp_stats["Power"] = temp_stats["Power"] + bonus_power
        temp_stats["Critical Rating"] = temp_stats["Critical Rating"] + bonus_critical_rating
        temp_stats["Alacrity Rating"] = temp_stats["Alacrity Rating"] + bonus_alacrity_rating

        temp_stats["M_Bonus_Damage"] = ((temp_stats["Mastery"] * 0.20) + (temp_stats["Power"] * 0.23)) * damage_bonus_multiplier
        temp_stats["F_Bonus_Damage"] = ((temp_stats["Mastery"] * 0.20) + (temp_stats["Power"] * 0.23) + (temp_stats["Force Power"]*0.23)) * damage_bonus_multiplier

        critical_cc = 0.3 * (1 - (1 - (0.01 / 0.3)) ** ((1 / 2.41) * temp_stats["Critical Rating"] / 80))
        mastery_cc = 0.2 * (1 - (1 - (0.01 / 0.2)) ** ((1 / 12.93) * (temp_stats["Mastery"] / 80)))
        temp_stats["Critical Chance"] = 0.05 + critical_cc + mastery_cc
        temp_stats["Critical Modifier"] = 1.5 + critical_cc
        temp_stats["Alacrity"] = 0.3 * (1 - (1 - (0.01 / 0.3)) ** ((1 / 3.2) * (temp_stats["Alacrity Rating"] / 80)))
        self.stats = temp_stats

    def calculate_resource_cost(self, ability_name: str, base_cost: float) -> float:
        if base_cost <= 0.0:
            return 0.0
        pct_modifiers = 1.0
        flat_reductions = 0.0
        for effect in self.effects.values():
            if effect.stat_name == "cost_reduction_pct":
                target_ability = getattr(effect, "unique_ability", None)
                if target_ability is None or target_ability == ability_name:
                    pct_modifiers -= effect.value
            elif effect.stat_name == "cost_reduction_flat":
                target_ability = getattr(effect, "unique_ability", None)
                if target_ability is None or target_ability == ability_name:
                    flat_reductions += effect.value
        final_cost = (base_cost * pct_modifiers) - flat_reductions
        return max(0.0, final_cost) #safeguard tbh

    def has_buff(self, buff_name):
        return buff_name in self.effects

    def cleanup_expired_effects(self, expired_keys: list):
        if not expired_keys:
            return

        needs_stat_recalc = False
        for r_id in expired_keys:
            popped_buff = self.effects.pop(r_id, None)
            if popped_buff and popped_buff.id in EFFECTS:
                if EFFECTS[popped_buff.id]["stat_name"] in {"Mastery Stat", "Power Stat", "Bonus Damage", "Critical Stat"}:
                    needs_stat_recalc = True

        if needs_stat_recalc:
            self.recalculate_stats()
class Target(Actor):
    def __init__(self, name: str, hp: int):
        super().__init__(name)
        self.max_hp = hp
        self.hp = hp
        self.dots = {}
        self.debuffs = {}
        self.stats = {
            "armor" : 17225
        }

    def apply_debuff(self, action: dict, source_name: str, current_time: float) -> tuple[str, "ActiveBuff", float]:

        from combat_math import EFFECTS
        try:
            action_id = action.get("id")
            extracted_stat = EFFECTS[action_id]["stat_name"]
        except (KeyError, TypeError) as e:
            print(f"🚨 CONFIGURATION CRASH in apply_debuff via [{source_name}]")
            print(f"👉 Action ID {action.get('id')} is completely missing from the EFFECTS database!")
            raise e
        duration = action["duration"]
        debuff_key = action.get("effect_name", f"{source_name}_{action['stat_name']}")
        expiration_timestamp = current_time + duration

        existing_debuff = self.debuffs.get(debuff_key)
        if existing_debuff:
            if existing_debuff.max_charges is not None:
                current_charges = min(existing_debuff.max_charges, existing_debuff.charges + 1)
            elif "charges" in action:
                current_charges = action["charges"]
            else:
                current_charges = existing_debuff.charges
        else:
            current_charges = 1 if "max_charges" in action else action.get("charges")

        raw_att = action.get("required_att_type")
        att_set = set(raw_att) if isinstance(raw_att, (list, tuple, set)) else ({raw_att} if raw_att is not None else None)

        raw_dmg = action.get("required_dmg_type")
        dmg_set = set(raw_dmg) if isinstance(raw_dmg, (list, tuple, set)) else ({raw_dmg} if raw_dmg is not None else None)

        raw_tags = action.get("required_tags")
        tags_set = set(raw_tags) if isinstance(raw_tags, (list, tuple, set)) else ({raw_tags} if raw_tags is not None else None)

        debuff_instance = ActiveBuff(
            id_num=action.get("id"),
            effect_name=debuff_key,
            stat_name=extracted_stat,
            value=action.get("value", 0.0),
            expires_at=expiration_timestamp,
            source_ability=source_name,
            required_tags=tags_set,
            charges=current_charges,
            consumable_charges=action.get("consumable_charges"),
            max_charges=action.get("max_charges"),
            target_hp_threshold=action.get("target_hp_threshold")
        )
        self.debuffs[debuff_key] = debuff_instance

        effect_id = debuff_instance.id
        if effect_id in EFFECTS:
            stat_name = EFFECTS[effect_id]["stat_name"]
            if stat_name in {"Mastery Stat", "Power Stat", "Bonus Damage", "Critical Stat", "Armor Penetration"}:
                if hasattr(self, "recalculate_stats"):
                    self.recalculate_stats()

        return debuff_key, debuff_instance, duration

    def has_debuff(self, effect_name:str) -> bool:
        return effect_name in self.debuffs

    def has_dot(self, dot_name: str) -> bool:
        return dot_name in self.dots

    @property
    def count_active_dots(self): #fuck you leeching strike
        return len(self.dots.keys())

    @property
    def hp_ratio(self) -> float:
        return self.hp / self.max_hp if self.max_hp > 0 else 1.0

class ResourcePool:
    def __init__(self, pool_type: str = "Force", max_value: float = 100.0, base_regen: float = 8.0):
        self.pool_type = pool_type
        self.max_value = max_value
        self.current_value = max_value
        self.base_regen = base_regen

    def can_afford(self, amount: float) -> bool:
        if self.pool_type == "Heat":
            return self.current_value + amount <= self.max_value
        else:
            return self.current_value >= amount

    def spend(self, amount: float) -> bool:
        if self.pool_type == "Heat":
            if self.current_value + amount > self.max_value:
                return False
            self.current_value += amount
            return True
        else:
            if self.current_value < amount:
                return False
            self.current_value -= amount
            return True

    def generate(self, amount: float):
        if self.pool_type == "Heat":
            self.current_value = max(0.0, self.current_value - amount)
        else:
            self.current_value = min(self.max_value, self.current_value + amount)

    def tick_passive_regen(self, delta_time: float, alacrity_modifier: float = 1.0):
        actual_regen_rate = self.base_regen * alacrity_modifier
        self.generate(actual_regen_rate * delta_time)