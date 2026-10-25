import math
from typing import Any, Optional
from src.swtorsim.resources import create_resource_pool
from collections import defaultdict #performance choice
from src.swtorsim.combat_curves import (
    ACCURACY_RATING,
    ALACRITY_RATING,
    CRITICAL_CHANCE_TARGET,
    CRITICAL_DAMAGE_TARGET,
    CRITICAL_RATING,
    MASTERY,
    derived_stat,
)
from src.swtorsim.combat_math import EFFECTS, calc_dr
from src.swtorsim.effects import ActiveEffect


class Entity:
    """Base class for combat entities managing active effects and stat recalculation triggers."""
    RECALCULATE_STATS = set()
    def __init__(self, name: str):
        self.name = name
        self.effects = {}
        self.stats = {}

    def apply_effect(self, sim, ability, effect, caster=None): #can be improved on the refresh
        """Applies or refreshes an extracted ActiveEffect, calculates expiration, and triggers stat updates if needed."""
        current_time = sim.current_time if sim is not None else 0.0
        base_duration = float(getattr(effect, "duration", 0.0) or 0.0)
        ignore_alacrity = bool(getattr(effect, "eff_ignore_alacrity", True))

        if base_duration > 0.0 and not ignore_alacrity and caster is not None:
            duration = caster.scale_time_modifier(base_duration)
        else:
            duration = base_duration

        is_passive = bool(getattr(effect, "is_passive", False))
        expires_at = (current_time + duration) if (duration > 0.0 and not is_passive) else None

        effect_instance = ActiveEffect.from_effect(
            ability=ability,
            effect=effect,
            current_time=current_time,
            expires_at=expires_at,
            caster=caster or self,
            target=self,
            sim=sim,
        )
        raw_effect_name = getattr(effect, "name", None)
        effect_key = (
            raw_effect_name
            if raw_effect_name
            else f"{effect_instance.name or effect_instance.fqn}:{effect_instance.number}"
        )

        base_tick = float(getattr(effect, "tick_interval", 0.0) or 0.0)
        if base_tick > 0.0 and base_duration > 0.0:
            total_ticks = max(1, int(round(base_duration / base_tick)))
            scaled_tick = duration / total_ticks
        else:
            total_ticks = 0
            scaled_tick = None

        effect_instance.caster_ref = caster
        effect_instance.tick_interval = scaled_tick
        effect_instance.total_ticks = total_ticks
        effect_instance.ticks_remaining = total_ticks

        existing = self.effects.get(effect_key)
        if existing is not None and not getattr(existing, "is_expired", False):
            if effect_instance.scales_with_stacks:
                effect_instance.stacks = min(
                    effect_instance.max_stacks,
                    getattr(existing, "stacks", 1) + 1,
                )
            else:
                effect_instance.stacks = max(
                    getattr(existing, "stacks", 1),
                    getattr(effect_instance, "initial_stacks", 1),
                )
            if existing.expires_at is not None and expires_at is not None:
                effect_instance.expires_at = max(existing.expires_at, expires_at)

        owner_id = f"{id(self)}:{effect_key}"
        effect_instance.owner_id = owner_id
        self.effects[effect_key] = effect_instance
        self.consider_recalculation(effect_instance)

        if sim is not None:
            self._sim_ref = sim
            if hasattr(sim, "triggers") and ability is not None:
                sim.triggers.unsubscribe(owner_id)
                effect_tags = (
                    effect.get("tags", ())
                    if isinstance(effect, dict)
                    else getattr(effect, "tags", ())
                )
                for branch in getattr(effect, "branches", ()) or ():
                    sim.triggers.subscribe(
                        owner_id,
                        ability,
                        branch,
                        caster or self,
                        self,
                        effect_key=effect_key,
                        effect_tags=effect_tags,
                    )

            if total_ticks > 0 and scaled_tick is not None:
                from src.swtorsim.events import DotTick
                sim.schedule_absolute(
                    current_time + scaled_tick,
                    DotTick(caster, self, effect_instance, effect_key=effect_key),
                )
            elif effect_instance.expires_at is not None:
                from src.swtorsim.events import EffectExpire
                sim.schedule_absolute(
                    effect_instance.expires_at,
                    EffectExpire(self, effect_key, effect_instance),
                )

        return effect_key, effect_instance, duration

    @staticmethod
    def _determine_charges(existing_effect, incoming_charges: int) -> int:
        """Caps charges at max_charges if defined, otherwise uses incoming charges."""
        if existing_effect and existing_effect.max_charges is not None:
            return min(existing_effect.max_charges, existing_effect.charges + incoming_charges)
        return incoming_charges

    @staticmethod
    def _determine_duration(existing_effect, extra_duration, current_time):
        """Calculates expiration time for an active effect."""
        new_expires_at = current_time + extra_duration
        if existing_effect and existing_effect.expires_at is not None:
            return max(existing_effect.expires_at, new_expires_at)
        return new_expires_at

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
        if getattr(effect_instance, "modifiers", None):
            self.recalculate_stats()
            return
        effect_id = getattr(effect_instance, "id", None)
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
        sim_ref = getattr(self, "_sim_ref", None)
        for r_id in expired_keys:
            popped_effect = self.effects.pop(r_id, None)
            if popped_effect is None:
                continue
            if hasattr(popped_effect, "is_expired"):
                popped_effect.is_expired = True
            owner_id = getattr(popped_effect, "owner_id", None)
            if owner_id and sim_ref is not None and hasattr(sim_ref, "triggers"):
                sim_ref.triggers.unsubscribe(owner_id)
            if getattr(popped_effect, "modifiers", None):
                needs_stat_recalc = True
            elif getattr(popped_effect, "id", None) in EFFECTS:
                if EFFECTS[popped_effect.id]["stat_name"] in self.RECALCULATE_STATS:
                    needs_stat_recalc = True
        if needs_stat_recalc:
            self.recalculate_stats()

    def has_effect(self, effect_name):
        """Returns bool on whether effect is present in entity"""
        direct = self.effects.get(effect_name)
        if direct is not None and not getattr(direct, "is_expired", False):
            return True
        for eff in self.effects.values():
            if getattr(eff, "is_expired", False) or getattr(eff, "is_passive", False):
                continue
            if any("lockout" in t for t in getattr(eff, "tags", ())):
                continue
            if getattr(eff, "name", None) == effect_name:
                return True
        return False


class Player(Entity):
    """Represents a player character and all that entails."""
    RECALCULATE_STATS = {"Mastery Stat", "Power Stat", "Bonus Damage", "Critical Stat", "Accuracy", "Armor Penetration", "Alacrity Rating", "Mastery PCT"}

    def __init__(self, name: str, abilities: dict = None, passives: dict = None, resource: str = "Force"):
        super().__init__(name)
        self.next_gcd = 0.0
        self.cooldowns = {}
        self.procs = {}
        self.passive_blueprints = passives or {}
        self.passive_db = {}
        self.ability_db = self.build_ability_db(abilities or {})
        self.level = 85
        self.rotation = None
        self.toughness = 1
        self.resource = create_resource_pool(
            pool_type=resource
        )
        self.base_stats = {
            "Alacrity": 0.0,
            "Critical Chance": 0.0,
            "Critical Modifier": 0.0,
            "Critical Rating": 0.0,
            "Accuracy Rating": 0.0,
            "Main Accuracy": 0.0,
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

    @staticmethod
    def build_ability_db(abilities: dict) -> dict:
        """Indexes abilities by both their FQN and their normalized name (e.g. 'thrash')."""
        ability_db = {}
        for key, abl in abilities.items():
            # Store primary key (FQN or original string)
            ability_db[key] = abl
            # Store normalized key
            ability_db[key.lower().replace(" ", "_")] = abl
            # Store normalized human-readable name if available
            if hasattr(abl, "name"):
                ability_db[abl.name.lower().replace(" ", "_")] = abl
        return ability_db

    def calculate_gcd(self, base_gcd: float = 1.5) -> float:
        """Calculates GCD duration scaled by Alacrity, rounded up to the nearest tenth of a second as ingame"""
        gcd = self.scale_time_modifier(base_gcd)
        scaled_gcd = math.ceil(gcd * 10) / 10
        return scaled_gcd

    def calculate_cooldown(self, base_cooldown: float, ability: Any = None) -> float:
        """Calculates ability cooldown after flat/percentage modifiers and scaled by current Alacrity CDR."""
        flat_mod = 0.0
        pct_mod = 1.0

        if ability is not None:
            if isinstance(ability, str):
                abl_obj = getattr(self, "ability_db", {}).get(ability) or getattr(self, "ability_db", {}).get(ability.lower().replace(" ", "_"))
                abl_fqn = getattr(abl_obj, "fqn", ability)
                abl_tags = getattr(abl_obj, "tags", frozenset()) or frozenset()
            else:
                abl_fqn = getattr(ability, "fqn", None)
                abl_tags = getattr(ability, "tags", frozenset()) or frozenset()

            for effect in self.effects.values():
                if getattr(effect, "is_expired", False):
                    continue
                for mod in _effect_modifiers(effect):
                    if str(mod.stat) in ("64", "STAT_abl_time_cooldown"):
                        if mod.applies_to(ability_fqn=abl_fqn, ability_tags=abl_tags):
                            if abs(mod.value) <= 1.0:
                                pct_mod += mod.value
                            else:
                                flat_mod += mod.value

        adjusted_base = max(0.0, (base_cooldown * pct_mod) + flat_mod)
        cdr = self.stats.get("Alacrity", 0.0)
        cooldown = adjusted_base / (1.0 + cdr)
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
            if getattr(effect, "is_expired", False):
                continue
            effect_id = getattr(effect, "id", None)
            if effect_id in EFFECTS:
                multiplier = effect.charges if getattr(effect, "max_charges", None) is not None else 1
                stat_name = EFFECTS[effect_id]["stat_name"]
                bonuses[stat_name] += effect.value * multiplier
            for modifier in _effect_modifiers(effect):
                if modifier.targets:
                    continue  # Ability-specific modifiers are evaluated during calculate_hit
                stat = str(modifier.stat)
                val = float(modifier.value)
                if stat in ("STAT_att_mastery", "414", "4140"):
                    if abs(val) <= 1.0:
                        bonuses["Mastery PCT"] += val
                    else:
                        bonuses["Mastery Stat"] += val
                elif stat in ("STAT_rtg_attack_power", "155", "STAT_att_power"):
                    bonuses["Power Stat"] += val
                elif stat in ("STAT_rtg_crit", "156"):
                    bonuses["Critical Stat"] += val
                elif stat in ("STAT_rtg_alacrity", "Alacrity Rating"):
                    bonuses["Alacrity Rating"] += val
                elif stat in ("STAT_rtg_accuracy", "154", "Accuracy"):
                    bonuses["Accuracy"] += val
                elif stat in ("STAT_cbt_armor_penetration", "166"):
                    bonuses["Armor Penetration"] += val
                elif stat == "STAT_cbt_melee_damage_bonus":
                    bonuses["M_Bonus_Damage_PCT"] += val
                elif stat == "STAT_cbt_force_damage_bonus":
                    bonuses["F_Bonus_Damage_PCT"] += val
                elif stat in ("STAT_cbt_damage_bonus", "26"):
                    bonuses["Bonus Damage"] += val

        #independent stats
        temp_stats["Mastery"] = (temp_stats["Mastery"] + bonuses["Mastery Stat"]) * (1 + bonuses["Mastery PCT"])
        temp_stats["Power"] += bonuses["Power Stat"]
        temp_stats["Critical Rating"] += bonuses["Critical Stat"]
        temp_stats["Alacrity Rating"] += bonuses["Alacrity Rating"]
        temp_stats["Armor Penetration"] += bonuses["Armor Penetration"]

        #bonus damage
        base_bonus_damage = (temp_stats["Mastery"] * 0.20) + (temp_stats["Power"] * 0.23)
        m_damage_bonus_multiplier = 1 + bonuses["Bonus Damage"] + bonuses["M_Bonus_Damage_PCT"]
        f_damage_bonus_multiplier = 1 + bonuses["Bonus Damage"] + bonuses["F_Bonus_Damage_PCT"]
        temp_stats["M_Bonus_Damage"] = base_bonus_damage * m_damage_bonus_multiplier
        temp_stats["F_Bonus_Damage"] = (base_bonus_damage + (temp_stats["Force Power"] * 0.23)) * f_damage_bonus_multiplier

        #diminishing returns
        alacrity_divisor, alacrity_cap = derived_stat(ALACRITY_RATING, self.level)
        accuracy_divisor, accuracy_cap = derived_stat(ACCURACY_RATING, self.level)
        crit_chance_divisor, crit_chance_cap = derived_stat(
            CRITICAL_RATING, self.level, CRITICAL_CHANCE_TARGET
        )
        crit_damage_divisor, crit_damage_cap = derived_stat(
            CRITICAL_RATING, self.level, CRITICAL_DAMAGE_TARGET
        )
        mastery_divisor, mastery_cap = derived_stat(
            MASTERY, self.level, CRITICAL_CHANCE_TARGET
        )
        temp_stats["Alacrity"] = calc_dr(
            temp_stats["Alacrity Rating"], alacrity_cap, alacrity_divisor, self.level
        )
        acc_base = calc_dr(
            temp_stats["Accuracy Rating"], accuracy_cap, accuracy_divisor, self.level
        )
        critical_chance = calc_dr(
            temp_stats["Critical Rating"], crit_chance_cap, crit_chance_divisor, self.level
        )
        critical_damage = calc_dr(
            temp_stats["Critical Rating"], crit_damage_cap, crit_damage_divisor, self.level
        )
        mastery_cc = calc_dr(
            temp_stats["Mastery"], mastery_cap, mastery_divisor, self.level
        )

        #dependant statts
        temp_stats["Critical Chance"] = 0.05 + critical_chance + mastery_cc
        temp_stats["Critical Modifier"] = 0.5 + critical_damage
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
        abl_obj = self.ability_db.get(ability_name) or self.ability_db.get(target_ability)
        abl_fqn = getattr(abl_obj, "fqn", None)
        abl_tags = getattr(abl_obj, "tags", frozenset()) or frozenset()

        for effect in self.effects.values():
            if getattr(effect, "is_expired", False):
                continue
            for mod in _effect_modifiers(effect):
                if mod.stat in ("68", "STAT_abl_cost_force", "STAT_abl_cost_energy"):
                    matched = mod.applies_to(abl_fqn, abl_tags)
                    if not matched and abl_fqn:
                        for t in mod.targets:
                            stem = str(t).split(".")[-1]
                            if stem and abl_fqn.endswith(f".{stem}_plus"):
                                matched = True
                                break
                    if matched:
                        if abs(mod.value) <= 1.0:
                            pct_modifiers += mod.value
                        else:
                            flat_reductions += mod.value

            effect_id = getattr(effect, "id", None)
            if effect_id not in EFFECTS:
                continue
            meta = EFFECTS[effect_id]
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


def _effect_modifiers(effect):
    getter = getattr(effect, "get_effective_modifiers", None)
    if getter is None:
        return ()
    return getter()


class Dummy(Entity):
    """Represents a dummy and all it entails."""
    RECALCULATE_STATS = {"Armor Rating"}
    def __init__(self, name: str, hp: int):
        super().__init__(name)
        self.max_hp = hp
        self.hp = hp
        self.toughness = 5
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
            effect_id = getattr(effect, "id", None)
            if effect_id in EFFECTS:
                multiplier = effect.charges if effect.max_charges is not None else 1
                stat_name = EFFECTS[effect_id]["stat_name"]
                if stat_name == "Armor Rating":
                    armor_rating_change += effect.value * multiplier
            for modifier in _effect_modifiers(effect):
                if modifier.stat == "STAT_rtg_armor":
                    armor_rating_change += modifier.value
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
