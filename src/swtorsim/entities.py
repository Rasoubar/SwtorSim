import math
from collections import defaultdict #performance choice
from src.swtorsim.combat_math import EFFECTS, calc_dr
from src.swtorsim.effects import ActiveEffect
from src.swtorsim.resources import ResourcePool


class Entity:
    """Base class for combat entities managing active effects and stat recalculation triggers."""
    RECALCULATE_STATS = set()
    def __init__(self, name: str):
        self.name = name
        self.effects = {}
        self.stats = {}

    def apply_effect(self, action: dict, source_name: str, current_time): #can be improved on the refresh
        """Applies or refreshes an active effect, calculates expiration, and triggers stat updates if needed."""
        extracted_stat = self._get_stat_name(action.get("id"), source_name)

        duration = self.scale_time_modifier(action["duration"]) if action.get("affected_by_cdr") else action["duration"]
        expiration_timestamp = current_time + duration

        effect_key = action.get("effect_name", extracted_stat)

        current_charges = self._determine_charges(self.effects.get(effect_key), action.get("charges", 1))

        effect_instance = ActiveEffect.from_action(
            action=action,
            stat_name=extracted_stat,
            effect_key=effect_key,
            charges=current_charges,
            expires_at=expiration_timestamp,
            source_name=source_name
        )

        self.effects[effect_key] = effect_instance

        self.consider_recalculation(effect_instance)

        return effect_key, effect_instance, duration

    @staticmethod
    def _determine_charges(existing_effect, incoming_charges: int) -> int:
        """Caps charges at max_charges if defined, otherwise uses incoming charges."""
        if existing_effect and existing_effect.max_charges is not None:
            return min(existing_effect.max_charges, existing_effect.charges + incoming_charges)
        return incoming_charges

    @staticmethod
    def _get_stat_name(action_id, source_name: str) -> str:
        """Looks up target stat in EFFECTS database, crashing explicitly if config is missing."""
        try:
            return EFFECTS[action_id]["stat_name"]
        except (KeyError, TypeError) as e:
            print(f" CONFIGURATION CRASH in apply_effect via [{source_name}]")
            print(f" Action ID {action_id} is completely missing from the EFFECTS database!")
            raise e

    def scale_time_modifier(self, base_time: float) -> float:
        """Scales time durations (override in Player for Alacrity)."""
        return base_time

    def consider_recalculation(self, effect_instance):
        """Triggers recalculate_stats() only if the applied effect modifies a relevant stat."""
        effect_id = effect_instance.id
        if effect_id in EFFECTS:
            stat_name = EFFECTS[effect_id]["stat_name"]
            if stat_name in self.RECALCULATE_STATS:
                self.recalculate_stats()

    def recalculate_stats(self):
        """Override in subclasses to perform entity-specific stat math."""
        pass

    def cleanup_expired_effects(self, expired_keys: list):
        """Removes expired effects and triggers stat recalculation if any affected stats."""
        if not expired_keys:
            return
        needs_stat_recalc = False
        for r_id in expired_keys:
            popped_effect = self.effects.pop(r_id, None)
            if popped_effect and popped_effect.id in EFFECTS:
                if EFFECTS[popped_effect.id]["stat_name"] in self.RECALCULATE_STATS:
                    needs_stat_recalc = True
        if needs_stat_recalc:
            self.recalculate_stats()
            print(f'Effects active:{self.effects}')

    def has_effect(self, effect_name):
        """Returns bool on whether effect is present in entity"""
        return effect_name in self.effects


class Player(Entity):
    """Represents a player character and all that entails."""
    RECALCULATE_STATS = {"Mastery Stat", "Power Stat", "Bonus Damage", "Critical Stat", "Accuracy", "Armor Penetration", "Alacrity Rating", "Mastery PCT"}
    def __init__(self, name: str):
        super().__init__(name)
        self.next_gcd = 0.0
        self.cooldowns= {}
        self.procs = {}
        self.rotation = None
        self.resource = ResourcePool(pool_type="Force", max_value=100.0, base_regen=8.0)
        self.base_stats = {
            "Alacrity": 0.0,
            "Critical Chance": 0.0,
            "Critical Modifier": 0.0,
            "Critical Rating": 0.0,
            "Accuracy Rating":0.0,
            "Main Accuracy":0.0,
            "Off Accuracy": 0.0,
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
        """Calculates GCD duration scaled by Alacrity, rounded up to the nearest tenth of a second as ingame"""
        gcd = self.scale_time_modifier(base_gcd)
        scaled_gcd = math.ceil(gcd * 10) / 10
        return scaled_gcd

    def calculate_cooldown(self, base_cooldown: float) -> float:
        """Calculates ability cooldown scaled by current Alacrity CDR."""
        cdr = self.stats.get("Alacrity", 0.0)
        cooldown = base_cooldown / (1.0 + cdr)
        scaled_cooldown = math.ceil(cooldown * 10) / 10
        return round(scaled_cooldown, 2)

    def scale_time_modifier(self, base_time: float) -> float:
        """Scales a base time duration using current Alacrity CDR."""
        cdr = self.stats.get("Alacrity",0.0)
        return base_time / (1.0 + cdr)

    def recalculate_stats(self):  # because relics hate me
        """Recalculates a character's stats using its effects."""
        temp_stats = self.base_stats.copy()

        bonuses = defaultdict(float)
        for effect in self.effects.values():
            effect_id = effect.id
            if effect_id in EFFECTS:
                multiplier = effect.charges if effect.max_charges is not None else 1
                stat_name = EFFECTS[effect_id]["stat_name"]
                bonuses[stat_name] += effect.value * multiplier

        #independent stats
        temp_stats["Mastery"] = (temp_stats["Mastery"] + bonuses["Mastery Stat"]) * (1 + bonuses["Mastery PCT"])
        temp_stats["Power"] += bonuses["Power Stat"]
        temp_stats["Critical Rating"] += bonuses["Critical Stat"]
        temp_stats["Alacrity Rating"] += bonuses["Alacrity Rating"]
        temp_stats["Armor Penetration"] += bonuses["Armor Penetration"]

        #bonus damage
        damage_bonus_multiplier = 1 + bonuses["Bonus Damage"]
        base_bonus_damage = (temp_stats["Mastery"] * 0.20) + (temp_stats["Power"] * 0.23)
        temp_stats["M_Bonus_Damage"] = base_bonus_damage * damage_bonus_multiplier
        temp_stats["F_Bonus_Damage"] = (base_bonus_damage + (temp_stats["Force Power"] * 0.23)) * damage_bonus_multiplier

        #diminishing returns
        temp_stats["Alacrity"] = calc_dr(temp_stats["Alacrity Rating"], cap=0.3, k_factor=3.2)
        acc_base = calc_dr(temp_stats["Accuracy Rating"], cap=0.3, k_factor=3.2)
        critical_cc = calc_dr(temp_stats["Critical Rating"], cap=0.3, k_factor=2.41)
        mastery_cc = calc_dr(temp_stats["Mastery"], cap=0.2, k_factor=12.93)

        #dependant statts
        temp_stats["Critical Chance"] = 0.05 + critical_cc + mastery_cc
        temp_stats["Critical Modifier"] = 0.5 + critical_cc
        temp_stats["Main Accuracy"] = 1 + acc_base + bonuses["Accuracy"]
        temp_stats["Off Accuracy"] = 0.67 + acc_base + bonuses["Accuracy"]

        self.stats = temp_stats

    def calculate_resource_cost(self, ability_name: str, base_cost: float, apply = False) -> float:
        """Calculates resource cost after percentage/flat reductions and optionally consumes buff charges."""
        if base_cost <= 0.0:
            return 0.0

        pct_modifiers = 1.0
        flat_reductions = 0.0
        effects_to_clear = []
        target_ability = ability_name.lower().replace(" ", "_")

        for effect in self.effects.values():
            meta = EFFECTS[effect.id]
            stat_name = meta['stat_name']

            if stat_name not in ("cost_reduction_pct", "cost_reduction_flat"):
                continue

            effect_tags = getattr(effect, "required_tags", [])
            if effect_tags and target_ability not in effect_tags:
                continue

            if stat_name == "cost_reduction_pct":
                pct_modifiers -= effect.value
            elif stat_name == "cost_reduction_flat":
                flat_reductions += effect.value

            if apply and effect.consume_charge():
                effects_to_clear.append(effect.effect_name)

        if effects_to_clear:
            self.cleanup_expired_effects(effects_to_clear)

        final_cost = (base_cost * pct_modifiers) + flat_reductions
        return max(0.0, final_cost) #safeguard tbh

class Dummy(Entity):
    """Represents a dummy and all it entails."""
    RECALCULATE_STATS = {"Armor Rating"}
    def __init__(self, name: str, hp: int):
        super().__init__(name)
        self.max_hp = hp
        self.hp = hp
        self.dots = {}
        self.base_stats = {
            "Armor" : 17225
        }
        self.stats = self.base_stats.copy()

    def recalculate_stats(self):
        """Recalculates the dummy's armor."""
        temp_stats = self.base_stats.copy()
        armor_rating_change = 0
        for effect in self.effects.values():
            effect_id = effect.id
            if effect_id in EFFECTS:
                multiplier = effect.charges if effect.max_charges is not None else 1
                stat_name = EFFECTS[effect_id]["stat_name"]
                if stat_name == "Armor Rating":
                    armor_rating_change += effect.value * multiplier
        temp_stats["Armor"] *= (1+armor_rating_change)
        self.stats = temp_stats


    def has_dot(self, dot_name: str) -> bool:
        """Returns whether a dot is present in the dummy or not."""
        return dot_name in self.dots

    @property
    def count_active_dots(self): #fuck you leeching strike
        """Returns the number of active dots present in the dummy. Likely useless in the near future."""
        if self.dots is None:
            return 0
        return len(self.dots)

    @property
    def hp_ratio(self) -> float:
        """Calculates the meaning of life. Evidently."""
        return self.hp / self.max_hp if self.max_hp > 0 else 1.0

