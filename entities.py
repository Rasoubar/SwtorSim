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
    __slots__ = ['id', 'effect_name', 'stat_name', 'value', 'expires_at', 'source_ability']

    def __init__(self, id_num, effect_name, stat_name, value, expires_at, source_ability):
        self.id = id_num
        self.effect_name = effect_name
        self.stat_name = stat_name
        self.value = value
        self.expires_at = expires_at
        self.source_ability = source_ability



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
            if effect.get("stat_name") == stat_name:
                modifier += effect.get("value", 0.0)
        return base_value + modifier

    def scale_time_modifier(self, base_time: float) -> float:
        cdr = self.get_stat("Cooldown Reduction")
        return base_time / (1.0 + cdr)

    def apply_buff(self, action: dict, source_name: str, current_time) -> tuple[str, dict, float, bool]:

        duration = action["duration"]
        if action.get("affected_by_cdr", False):
            duration = self.scale_time_modifier(duration)

        buff_key = action.get("effect_name", f"{source_name}_{action['stat_name']}")
        expiration_timestamp = current_time + duration
        existing_buff = self.effects.get(buff_key)
        if existing_buff:
            existing_buff["expires_at"] = expiration_timestamp
            return buff_key, existing_buff, duration, False

        buff_instance = action.copy()
        buff_instance["source_ability"] = source_name
        buff_instance["expires_at"] = expiration_timestamp

        self.effects[buff_key] = buff_instance


        effect_id = buff_instance.get("id")
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
        for buff_key, buff in self.effects.items():
            effect_id = buff.get("id")
            if effect_id in EFFECTS:
                stat_name = EFFECTS[effect_id]["stat_name"]
                if stat_name == "Mastery Stat":
                    bonus_mastery += buff.get("value", 0) * 1.05
                elif stat_name == "Power Stat":
                    bonus_power += buff.get("value", 0)
                elif stat_name == "Bonus Damage":
                    damage_bonus_multiplier += buff.get("value", 0)

        temp_stats["Mastery"]  = temp_stats["Mastery"] + bonus_mastery
        temp_stats["Power"] = temp_stats["Power"] + bonus_power

        temp_stats["M_Damage_Bonus"] = ((temp_stats["Mastery"] * 0.20) + (temp_stats["Power"] * 0.23)) * damage_bonus_multiplier
        temp_stats["F_Damage_Bonus"] = ((temp_stats["Mastery"] * 0.20) + (temp_stats["Power"] * 0.23) + (temp_stats["Force Power"]*0.23)) * damage_bonus_multiplier

        critical_cc = 0.3 * (1 - (1 - (0.01 / 0.3)) ** ((1 / 2.41) * temp_stats["Critical Rating"] / 80))
        mastery_cc = 0.2 * (1 - (1 - (0.01 / 0.2)) ** ((1 / 12.93) * (temp_stats["Mastery"] / 80)))
        temp_stats["Critical Chance"] = 0.05 + critical_cc + mastery_cc
        self.stats = temp_stats


class Target(Actor):
    def __init__(self, name: str, hp: int):
        super().__init__(name)
        self.hp = hp
        self.dots = {}
        self.debuffs = {}
        self.stats = {
            "armor" : 17225
        }

    def apply_debuff(self, action: dict, source_name: str) -> tuple[str, dict, float]:
        duration = action["duration"]
        debuff_key = action.get("effect_name", f"{source_name}_{action['stat_name']}")
        debuff_instance = action.copy()
        debuff_instance["source_ability"] = source_name
        self.debuffs[debuff_key] = debuff_instance
        return debuff_key, debuff_instance, duration