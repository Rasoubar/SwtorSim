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
    # 1. Expand slots to explicitly carry our 4 filtering dimensions
    __slots__ = [
        'id', 'effect_name', 'stat_name', 'value', 'expires_at', 'source_ability',
        'unique_ability', 'required_att_type', 'required_dmg_type', 'required_tags', 'charges', 'consumable_charges'
    ]

    def __init__(self, id_num, effect_name, stat_name, value, expires_at, source_ability,
                 unique_ability=None, required_att_type=None, required_dmg_type=None,
                 required_tags=None, charges=None, consumable_charges=None):
        self.id = id_num
        self.effect_name = effect_name
        self.stat_name = stat_name
        self.value = value
        self.expires_at = expires_at
        self.source_ability = source_ability
        self.unique_ability = unique_ability  # String or None, ability it applies to
        self.required_att_type = required_att_type  # Set of ints or None
        self.required_dmg_type = required_dmg_type  # Set of ints or None
        self.required_tags = required_tags  # Set of strings or None
        self.charges = charges  # Integer or None
        self.consumable_charges = consumable_charges



class Actor:
    def __init__(self, name: str):
        self.name = name

class Player(Actor):
    def __init__(self, name: str):
        super().__init__(name)
        self.next_gcd = 0.0
        self.cooldowns= {}
        self.effects = {}
        self.rotation = None
        self.resource = ResourcePool(pool_type="Force", max_value=100.0, base_regen=8.0)
        self.base_stats = {
            "Cooldown Reduction": 0.0,
            "Critical Chance": 0.0,
            "Critical Modifier": 0.0,
            "Critical Rating": 0.0,
            "Mastery": 0.0,
            "Power": 0.0,
            "Force Power": 0.0,
            "M_Bonus_Damage": 0.0,
            "Alacrity" : 0.0,
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
        cdr = self.stats.get("Cooldown Reduction", 0.0)
        cooldown = base_cooldown / (1.0 + cdr)
        scaled_cooldown = math.ceil(cooldown * 10) / 10
        return round(scaled_cooldown, 2)

    def get_stat(self, stat_name: str) -> float:
        base_value = self.stats.get(stat_name, 0.0)
        modifier = 0.0
        for effect in self.effects.values():
            if effect.stat_name == stat_name:
                modifier += effect.value
        return base_value + modifier

    def scale_time_modifier(self, base_time: float) -> float:
        cdr = self.stats.get("Cooldown Reduction",0.0)
        return base_time / (1.0 + cdr)

    def apply_buff(self, action: dict, source_name: str, current_time) -> tuple[str, dict, float, bool]:

        duration = action["duration"]
        if action.get("affected_by_cdr", False):
            duration = self.scale_time_modifier(duration)

        buff_key = action.get("effect_name", f"{source_name}_{action['stat_name']}")
        expiration_timestamp = current_time + duration

        existing_buff = self.effects.get(buff_key)

        if existing_buff:
            existing_buff.expires_at = expiration_timestamp
            if "charges" in action:
                existing_buff.charges = action["charges"]
            return buff_key, existing_buff, duration, False

        raw_att = action.get("required_att_type")
        if raw_att is not None:
            att_set = set(raw_att) if isinstance(raw_att, (list, tuple, set)) else {raw_att}
        else:
            att_set = None

        raw_dmg = action.get("required_dmg_type")
        if raw_dmg is not None:
            dmg_set = set(raw_dmg) if isinstance(raw_dmg, (list, tuple, set)) else {raw_dmg}
        else:
            dmg_set = None

        raw_tags = action.get("required_tags")
        if raw_tags is not None:
            tags_set = set(raw_tags) if isinstance(raw_tags, (list, tuple, set)) else {raw_tags}
        else:
            tags_set = None

        buff_instance = ActiveBuff(
            id_num=action.get("id"),
            effect_name=buff_key,
            stat_name=action.get("stat_name"),
            value=action["value"],
            expires_at=expiration_timestamp,
            source_ability=source_name,
            unique_ability=action.get("unique_ability"),  # Stays a string/None
            required_att_type=att_set,  # Guaranteed Set or None
            required_dmg_type=dmg_set,  # Guaranteed Set or None
            required_tags=tags_set,  # Guaranteed Set or None
            charges=action.get("charges"),
            consumable_charges=action.get("consumable_charges")
        )

        self.effects[buff_key] = buff_instance

        effect_id = buff_instance.id
        if effect_id in EFFECTS:
            stat_name = EFFECTS[effect_id]["stat_name"]
            if stat_name in {"Mastery Stat", "Power Stat", "Bonus Damage", "Crit Stat"}:
                self.recalculate_stats()

        return buff_key, buff_instance, duration, True

    def recalculate_stats(self): #because relics hate me

        temp_stats = self.base_stats.copy()
        bonus_mastery = 0
        bonus_power = 0
        damage_bonus_multiplier = 1
        for buff in self.effects.values():
            effect_id = buff.id
            if effect_id in EFFECTS:
                stat_name = EFFECTS[effect_id]["stat_name"]
                if stat_name == "Mastery Stat":
                    bonus_mastery += buff.value * 1.05
                elif stat_name == "Power Stat":
                    bonus_power += buff.value
                elif stat_name == "Bonus Damage":
                    damage_bonus_multiplier += buff.value

        temp_stats["Mastery"]  = temp_stats["Mastery"] + bonus_mastery
        temp_stats["Power"] = temp_stats["Power"] + bonus_power

        temp_stats["M_Damage_Bonus"] = ((temp_stats["Mastery"] * 0.20) + (temp_stats["Power"] * 0.23)) * damage_bonus_multiplier
        temp_stats["F_Damage_Bonus"] = ((temp_stats["Mastery"] * 0.20) + (temp_stats["Power"] * 0.23) + (temp_stats["Force Power"]*0.23)) * damage_bonus_multiplier

        critical_cc = 0.3 * (1 - (1 - (0.01 / 0.3)) ** ((1 / 2.41) * temp_stats["Critical Rating"] / 80))
        mastery_cc = 0.2 * (1 - (1 - (0.01 / 0.2)) ** ((1 / 12.93) * (temp_stats["Mastery"] / 80)))
        temp_stats["Critical Chance"] = 0.05 + critical_cc + mastery_cc
        self.stats = temp_stats

    def has_buff(self, buff_name):
        return buff_name in self.effects
class Target(Actor):
    def __init__(self, name: str, hp: int):
        super().__init__(name)
        self.hp = hp
        self.dots = {}
        self.debuffs = {}
        self.stats = {
            "armor" : 17225
        }

    def apply_debuff(self, action: dict, source_name: str, current_time: float) -> tuple[str, ActiveBuff, float, bool]:
        duration = action["duration"]
        debuff_key = action.get("effect_name", f"{source_name}_{action['stat_name']}")
        expiration_timestamp = current_time + duration

        existing_debuff = self.debuffs.get(debuff_key)
        if existing_debuff:
            existing_debuff.expires_at = expiration_timestamp
            if "charges" in action:
                existing_debuff.charges = action["charges"]
            return debuff_key, existing_debuff, duration, False

        debuff_instance = ActiveBuff( #same shit, buffs on me and debuffs on enemy
            id_num=action.get("id"),
            effect_name=debuff_key,
            stat_name=action.get("stat_name"),
            value=action.get("value", 0.0),
            expires_at=expiration_timestamp,
            source_ability=source_name,
            charges=action.get("charges")
        )
        self.debuffs[debuff_key] = debuff_instance
        return debuff_key, debuff_instance, duration, True

    def has_debuff(self, effect_name:str) -> bool:
        return effect_name in self.debuffs

    def has_dot(self, dot_name: str) -> bool:
        return dot_name in self.dots

    @property
    def count_active_dots(self): #fuck you leeching strike
        return len(self.dots.keys())

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