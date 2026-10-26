import random
from typing import Any, Optional

from src.swtorsim.combat_curves import armor_constants

def calculate_hit(caster, target, action_data):
    """Calculates the hit value of an action from a caster to a targe. Returns value and whether it was a crit"""

    #pre-extract damage_type, attack_type and action_tags to not be doing same thing multiple times
    attack_type = action_data.get("attack_type", 1)
    damage_type = action_data.get("damage_type")
    if damage_type is None:
        # Fallback when blueprint omits damage_type:
        # Lightsabers and blasters deal Energy (2); other attacks default to Kinetic (1).
        # Both Kinetic (1) and Energy (2) are mitigated by armor in handle_mitigation.
        damage_type = 2 if attack_type in (1, 2) else 1

    action_data["resolved_attack_type"] = attack_type
    action_data["resolved_damage_type"] = damage_type

    #calculate damage calculation modifiers
    modifiers = handle_modifiers(caster, target, action_data, damage_type=damage_type)

    #calculate base damage from caster stats and action_data
    base_damage = calculate_base_damage(caster, action_data, attack_type, modifiers=modifiers)

    post_mit_damage = handle_mitigation(caster, target, base_damage, damage_type, modifiers)

    post_mod_damage = post_mit_damage * modifiers['total_multiplier']

    post_crit_damage, is_crit = calculate_crit(caster, post_mod_damage, modifiers)

    return int(post_crit_damage), is_crit

def handle_modifiers(caster, target, action_data, damage_type=None):
    """Determines numeric modifiers to the hit. Both direct and that affect mitigation. Returns Modifiers dict"""

    """buckets are needed to handle buffs/debuffs that will affect total_multiplier in different ways.
    buffs that are additive with each other go on the same bucket, after all the buffs are sorted into the buckets,
    the buckets are multiplied to give the total_multiplier final value."""
    buckets = {}
    modifiers = {
        'bonus_crit_chance': 0.0,
        'bonus_crit_modifier': 0.0,
        'bonus_armor_pen': 0.0,
        'base_weapon_damage_modifier': 0.0,

        'total_multiplier': 1.0
    }

    #modify the modifiers with applicable target and caster buffs/debuffs
    action_tags = frozenset(action_data.get("tags") or ())
    ability_fqn = action_data.get("ability_fqn")
    attack_type = action_data.get("attack_type", 1)
    if damage_type is None:
        damage_type = action_data.get("resolved_damage_type") or action_data.get("damage_type", 1)

    handle_caster_buffs(caster, target, action_tags, ability_fqn, attack_type, damage_type, buckets, modifiers)
    handle_target_debuffs(target, action_tags, ability_fqn, attack_type, damage_type, buckets, modifiers, caster=caster)

    for bucket_value in buckets.values():
        modifiers['total_multiplier'] *= (1.0 + bucket_value)

    return modifiers

# Multiplicative Damage Buckets
BUCKET_NORMAL = "normal_percentage"
BUCKET_EXECUTE = "sub_30"
BUCKET_CHANNEL = "channel_scaling"
BUCKET_DAMAGE_TYPE = "damage_type_scaling"
BUCKET_TAG = "tag_scaling"
BUCKET_TARGET_STATE = "target_state"

_CASTER_DAMAGE_DISPATCH = {
    # 1. Base / General Damage Done (Additive with base pool & vulnerabilities)
    "STAT_cbt_damage_done_modifier_percentage": (BUCKET_NORMAL, None),
    "79": (BUCKET_NORMAL, None),
    "STAT_cbt_damage_done_modifier_fixed": (BUCKET_NORMAL, None),
    "78": (BUCKET_NORMAL, None),
    "386": (BUCKET_NORMAL, None),
    "384": (BUCKET_NORMAL, None),
    "370": (BUCKET_NORMAL, None),
    "376": (BUCKET_NORMAL, None),
    "46": (BUCKET_NORMAL, None),

    # 2. Low-Health Execute (sub-30)
    "STAT_cbt_damage_done_if_target_health_low_modifier_percentage": (
        BUCKET_EXECUTE,
        lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: getattr(target, "hp_ratio", 1.0) <= 0.30,
    ),
    "220": (
        BUCKET_EXECUTE,
        lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: getattr(target, "hp_ratio", 1.0) <= 0.30,
    ),

    # 3. Channel (Attack Type) Damage Dealt
    "stat_cbt_damage_dealt_scale_channel_melee_modifier_percentage": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m),
    "stat_cbt_damage_dealt_scale_channel_melee": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m),
    "stat_cbt_damage_dealt_scale_channel_melee_modifier_fixed": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m),
    "408": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m),
    "407": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m),

    "stat_cbt_damage_dealt_scale_channel_ranged_modifier_percentage": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_r),
    "stat_cbt_damage_dealt_scale_channel_ranged": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_r),
    "stat_cbt_damage_dealt_scale_channel_ranged_modifier_fixed": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_r),
    "406": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_r),
    "405": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_r),

    "stat_cbt_damage_dealt_scale_channel_force_modifier_percentage": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),
    "stat_cbt_damage_dealt_scale_channel_force": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),
    "409": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),
    "stat_cbt_force_damage_dealt_modifier": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),
    "stat_cbt_damage_dealt_scale_channel_force_modifier_fixed": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),
    "410": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),
    "451": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),

    "stat_cbt_damage_dealt_scale_channel_tech_modifier_percentage": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),
    "stat_cbt_damage_dealt_scale_channel_tech": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),
    "411": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),
    "stat_cbt_tech_damage_dealt_modifier": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),
    "stat_cbt_damage_dealt_scale_channel_tech_modifier_fixed": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),
    "412": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),
    "449": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),

    "stat_cbt_damage_dealt_scale_channel_weapon_modifier": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m or is_r),
    "462": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m or is_r),
    "stat_cbt_weapon_damage_dealt_modifier": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m or is_r),
    "450": (BUCKET_CHANNEL, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m or is_r),

    # 4. Damage Type Specific Dealt Modifiers
    "stat_cbt_damage_dealt_scale_type_kinetic_modifier_percentage": (BUCKET_DAMAGE_TYPE, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 1),
    "397": (BUCKET_DAMAGE_TYPE, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 1),
    "stat_cbt_damage_dealt_scale_type_energy_modifier_percentage": (BUCKET_DAMAGE_TYPE, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 2),
    "395": (BUCKET_DAMAGE_TYPE, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 2),
    "stat_cbt_damage_dealt_scale_type_elemental_modifier_percentage": (BUCKET_DAMAGE_TYPE, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 3),
    "393": (BUCKET_DAMAGE_TYPE, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 3),
    "stat_cbt_damage_dealt_scale_type_internal_modifier_percentage": (BUCKET_DAMAGE_TYPE, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 4),
    "399": (BUCKET_DAMAGE_TYPE, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 4),

    # 5. Tag-Specific Dealt Modifiers (AoE, DoT)
    "stat_cbt_damage_dealt_scale_tag_aoe_modifier": (BUCKET_TAG, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _hit_is_aoe(tags)),
    "464": (BUCKET_TAG, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _hit_is_aoe(tags)),
    "stat_cbt_aoe_damage_dealt_modifier": (BUCKET_TAG, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _hit_is_aoe(tags)),
    "454": (BUCKET_TAG, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _hit_is_aoe(tags)),
    "stat_cbt_damage_dealt_scale_tag_dot_modifier": (BUCKET_TAG, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: any("dot" in str(t).lower() or "periodic" in str(t).lower() for t in tags)),
    "466": (BUCKET_TAG, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: any("dot" in str(t).lower() or "periodic" in str(t).lower() for t in tags)),

    # 6. Target-State Conditional Damage Modifiers
    "STAT_cbt_damage_done_if_target_bleeding_modifier_percentage": (BUCKET_TARGET_STATE, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _entity_has_tag(target, "bleed")),
    "221": (BUCKET_TARGET_STATE, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _entity_has_tag(target, "bleed")),
    "STAT_cbt_damage_done_if_target_on_fire_modifier_percentage": (BUCKET_TARGET_STATE, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _entity_has_tag(target, "burn") or _entity_has_tag(target, "fire")),
    "250": (BUCKET_TARGET_STATE, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _entity_has_tag(target, "burn") or _entity_has_tag(target, "fire")),
    "STAT_cbt_damage_done_if_target_accuracy_reduced_modifier_percentage": (BUCKET_TARGET_STATE, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _entity_has_tag(target, "accuracy_reduced")),
    "389": (BUCKET_TARGET_STATE, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _entity_has_tag(target, "accuracy_reduced")),
    "STAT_cbt_dual_wield_damage_done_modifier_percentage": (BUCKET_TARGET_STATE, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: getattr(caster, "stats", {}).get("Off_hand_max", 0.0) > 0),
    "127": (BUCKET_TARGET_STATE, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: getattr(caster, "stats", {}).get("Off_hand_max", 0.0) > 0),
}

_CRIT_CHANCE_DISPATCH = {
    "STAT_cbt_force_critical_chance": lambda is_m, is_r, is_f, is_t: is_f,
    "133": lambda is_m, is_r, is_f, is_t: is_f,
    "STAT_cbt_melee_critical_chance": lambda is_m, is_r, is_f, is_t: is_m,
    "116": lambda is_m, is_r, is_f, is_t: is_m,
    "STAT_cbt_ranged_critical_chance": lambda is_m, is_r, is_f, is_t: is_r,
    "122": lambda is_m, is_r, is_f, is_t: is_r,
    "STAT_cbt_tech_critical_chance": lambda is_m, is_r, is_f, is_t: is_t,
    "135": lambda is_m, is_r, is_f, is_t: is_t,
    "Critical Chance": lambda is_m, is_r, is_f, is_t: True,
}

_CRIT_DAMAGE_DISPATCH = {
    "STAT_cbt_force_critical_damage": lambda is_m, is_r, is_f, is_t: is_f,
    "134": lambda is_m, is_r, is_f, is_t: is_f,
    "STAT_cbt_melee_critical_damage": lambda is_m, is_r, is_f, is_t: is_m,
    "117": lambda is_m, is_r, is_f, is_t: is_m,
    "STAT_cbt_ranged_critical_damage": lambda is_m, is_r, is_f, is_t: is_r,
    "123": lambda is_m, is_r, is_f, is_t: is_r,
    "STAT_cbt_tech_critical_damage": lambda is_m, is_r, is_f, is_t: is_t,
    "136": lambda is_m, is_r, is_f, is_t: is_t,
    "Critical Damage": lambda is_m, is_r, is_f, is_t: True,
}

_SKIP_BASE_STATS = frozenset({
    "STAT_att_mastery", "414", "4140",
    "STAT_rtg_attack_power", "155", "STAT_att_power",
    "STAT_rtg_crit", "156",
    "STAT_rtg_alacrity", "Alacrity Rating", "STAT_rtg_spell_haste", "255",
    "STAT_rtg_accuracy", "154", "Accuracy",
    "STAT_cbt_melee_accuracy", "114",
    "STAT_cbt_ranged_accuracy", "120",
    "STAT_cbt_force_accuracy", "232",
    "STAT_cbt_tech_accuracy", "233",
    "STAT_cbtAccuracy", "11",
    "STAT_cbt_melee_damage_bonus", "26",
    "STAT_cbt_ranged_damage_bonus", "25",
    "STAT_cbt_force_damage_bonus", "129",
    "STAT_cbt_tech_damage_bonus", "130",
    "STAT_cbt_damage_bonus",
    "STAT_att_endurance",
    "STAT_cbtStealthEffectiveLevel",
})


def handle_caster_buffs(caster, target, action_tags, ability_fqn, attack_type, damage_type, buckets, modifiers):
    """ Alters modifiers dict according to active effects and buffs on caster."""
    is_melee = attack_type in (1, "melee", "Melee")
    is_ranged = attack_type in (2, "ranged", "Ranged")
    is_force = attack_type in (3, "force", "Force")
    is_tech = attack_type in (4, "tech", "Tech")

    for buff in caster.effects.values():
        if getattr(buff, "is_expired", False):
            continue

        getter = getattr(buff, "get_effective_modifiers", None)
        eff_mods = getter() if getter is not None else getattr(buff, "modifiers", [])
        if not eff_mods:
            continue

        for mod in eff_mods:
            stat = str(mod.stat)
            val = float(mod.value)

            # Skip untargeted character base stats that were already processed in recalculate_stats
            if not mod.targets and stat in _SKIP_BASE_STATS:
                continue

            # Check conditional tag requirement on target or caster
            cond_tag = getattr(mod, "conditional_tag", None)
            if cond_tag:
                require_owner = getattr(mod, "require_owner", False)
                actor = getattr(mod, "actor", None)

                def _entity_has_cond_tag(ent):
                    if ent is None:
                        return False
                    for e in getattr(ent, "effects", {}).values():
                        if getattr(e, "is_expired", False):
                            continue
                        if cond_tag in getattr(e, "tags", ()):
                            if require_owner and caster is not None:
                                c_ref = getattr(e, "caster_ref", None)
                                if c_ref is not None and c_ref is not caster:
                                    continue
                            return True
                    return False

                if actor == 3:  # Target
                    has_tag = _entity_has_cond_tag(target)
                elif actor == 1:  # Caster
                    has_tag = _entity_has_cond_tag(caster)
                else:  # Unspecified: check target then caster
                    has_tag = _entity_has_cond_tag(target) or _entity_has_cond_tag(caster)

                if not has_tag:
                    continue

            # Check ability FQN / tags matching
            if not mod.applies_to(ability_fqn=ability_fqn, ability_tags=action_tags):
                continue

            # 1. Damage Multiplier Buckets (Table Dispatch)
            entry = _CASTER_DAMAGE_DISPATCH.get(stat)
            if entry is not None:
                bucket_key, filter_fn = entry
                if filter_fn is None or filter_fn(target, is_melee, is_ranged, is_force, is_tech, damage_type, action_tags, caster):
                    buckets[bucket_key] = buckets.get(bucket_key, 0.0) + val
                continue

            # 2. Critical Chance Modifiers (Table Dispatch)
            crit_fn = _CRIT_CHANCE_DISPATCH.get(stat)
            if crit_fn is not None:
                if crit_fn(is_melee, is_ranged, is_force, is_tech):
                    modifiers['bonus_crit_chance'] += val
                continue

            # 3. Critical Damage Modifiers (Table Dispatch)
            surge_fn = _CRIT_DAMAGE_DISPATCH.get(stat)
            if surge_fn is not None:
                if surge_fn(is_melee, is_ranged, is_force, is_tech):
                    modifiers['bonus_crit_modifier'] += val
                continue

            # 4. Armor Penetration
            if stat in ("STAT_cbt_armor_penetration", "166"):
                modifiers['bonus_armor_pen'] += val
                continue

            # 5. Base Weapon Damage Modifier
            if stat in ("STAT_cbt_base_weapon_damage_modifier_percentage", "413"):
                modifiers['base_weapon_damage_modifier'] = modifiers.get('base_weapon_damage_modifier', 0.0) + val
                continue

_ATTACK_TYPE_CHANNELS = {
    1: "melee",
    2: "ranged",
    3: "force",
    4: "tech",
}

_DAMAGE_TYPE_NAMES = {
    1: "kinetic",
    2: "energy",
    3: "elemental",
    4: "internal",
}


def _channel_for_hit(tags, attack_type):
    return _ATTACK_TYPE_CHANNELS.get(attack_type)


def _hit_is_aoe(tags) -> bool:
    return any(str(tag).endswith("is_aoe") or str(tag).endswith("aoe_ability") for tag in tags)


def _entity_has_tag(entity, tag_substr: str) -> bool:
    """Checks if entity has any active, unexpired effect containing tag_substr in its tags."""
    if entity is None:
        return False
    effects = getattr(entity, "effects", None)
    if not effects:
        return False
    substr = tag_substr.lower()
    for eff in effects.values():
        if getattr(eff, "is_expired", False):
            continue
        for t in getattr(eff, "tags", ()) or ():
            if substr in str(t).lower():
                return True
    return False


def handle_target_debuffs(target, action_tags, ability_fqn, attack_type, damage_type, buckets, modifiers, caster=None):
    """ Alters modifiers dict according to active debuffs on target."""
    channel = _channel_for_hit(action_tags, attack_type)
    type_name = _DAMAGE_TYPE_NAMES.get(damage_type)
    aoe = _hit_is_aoe(action_tags)
    is_melee = attack_type in (1, "melee", "Melee")
    is_ranged = attack_type in (2, "ranged", "Ranged")
    is_force = attack_type in (3, "force", "Force")
    is_tech = attack_type in (4, "tech", "Tech")

    for debuff in target.effects.values():
        if getattr(debuff, "is_expired", False):
            continue

        getter = getattr(debuff, "get_effective_modifiers", None)
        eff_mods = getter() if getter is not None else getattr(debuff, "modifiers", [])
        if not eff_mods:
            continue

        for mod in eff_mods:
            stat = str(mod.stat)
            val = float(mod.value)

            # Skip target armor debuffs (handled by Dummy/entity armor recalculation)
            if stat == "STAT_rtg_armor":
                continue

            # Conditional tag check
            cond_tag = getattr(mod, "conditional_tag", None)
            if cond_tag:
                require_owner = getattr(mod, "require_owner", False)
                actor = getattr(mod, "actor", None)

                def _entity_has_cond_tag_debuff(ent):
                    if ent is None:
                        return False
                    for e in getattr(ent, "effects", {}).values():
                        if getattr(e, "is_expired", False):
                            continue
                        if cond_tag in getattr(e, "tags", ()):
                            if require_owner and caster is not None:
                                c_ref = getattr(e, "caster_ref", None)
                                if c_ref is not None and c_ref is not caster:
                                    continue
                            return True
                    return False

                if actor == 3:
                    has_tag = _entity_has_cond_tag_debuff(target)
                elif actor == 1:
                    has_tag = _entity_has_cond_tag_debuff(caster)
                else:
                    has_tag = _entity_has_cond_tag_debuff(target) or _entity_has_cond_tag_debuff(caster)

                if not has_tag:
                    continue

            stat_lower = stat.lower()

            # 1. Channel vulnerabilities (Melee, Ranged, Force, Tech, Weapon)
            matched = False
            if is_force and stat in (
                "stat_cbt_damage_taken_scale_channel_force_modifier_percentage", "386",
                "stat_cbt_force_damage_taken_modifier", "456",
            ):
                matched = True
            elif is_tech and stat in (
                "stat_cbt_damage_taken_scale_channel_tech_modifier_percentage", "388",
                "stat_cbt_tech_damage_taken_modifier", "459",
            ):
                matched = True
            elif is_melee and stat in (
                "stat_cbt_damage_taken_scale_channel_melee_modifier_percentage", "384",
                "stat_cbt_damage_taken_scale_channel_weapon_modifier", "463",
                "stat_cbt_weapon_damage_taken_modifier", "458",
            ):
                matched = True
            elif is_ranged and stat in (
                "stat_cbt_damage_taken_scale_channel_ranged_modifier_percentage", "382",
                "stat_cbt_damage_taken_scale_channel_weapon_modifier", "463",
                "stat_cbt_weapon_damage_taken_modifier", "458",
            ):
                matched = True

            if matched:
                buckets["normal_percentage"] = buckets.get("normal_percentage", 0.0) + val
                continue

            # 2. Damage type vulnerabilities (Kinetic, Energy, Elemental, Internal)
            if "damage_taken_scale_type_" in stat_lower or stat in (
                "369", "370", "371", "372", "373", "374", "375", "376"
            ):
                matched = False
                if type_name and f"type_{type_name}_" in stat_lower:
                    matched = True
                elif damage_type == 1 and (
                    stat in ("stat_cbt_damage_taken_scale_type_kinetic_modifier_percentage", "374")
                    or "type_kinetic_" in stat_lower
                ):
                    matched = True
                elif damage_type == 2 and (
                    stat in ("stat_cbt_damage_taken_scale_type_energy_modifier_percentage", "372")
                    or "type_energy_" in stat_lower
                ):
                    matched = True
                elif damage_type == 3 and (
                    stat in ("stat_cbt_damage_taken_scale_type_elemental_modifier_percentage", "370")
                    or "type_elemental_" in stat_lower
                ):
                    matched = True
                elif damage_type == 4 and (
                    stat in ("stat_cbt_damage_taken_scale_type_internal_modifier_percentage", "376")
                    or "type_internal_" in stat_lower
                ):
                    matched = True

                if matched:
                    buckets["normal_percentage"] = buckets.get("normal_percentage", 0.0) + val
                continue

            # 3. Tag-specific vulnerabilities (AoE, DoT)
            if stat in ("stat_cbt_damage_taken_scale_tag_aoe_modifier", "465", "stat_cbt_aoe_damage_taken_modifier", "460") or "tag_aoe_" in stat_lower:
                if aoe:
                    buckets["normal_percentage"] = buckets.get("normal_percentage", 0.0) + val
                continue

            if stat in ("stat_cbt_damage_taken_scale_tag_dot_modifier", "467") or "tag_dot_" in stat_lower:
                if any("dot" in str(t).lower() or "periodic" in str(t).lower() for t in action_tags):
                    buckets["normal_percentage"] = buckets.get("normal_percentage", 0.0) + val
                continue

            # 4. General damage received percentage
            if stat in ("STAT_cbt_damage_received_modifier_percentage", "46"):
                if not mod.targets or mod.applies_to(ability_fqn=ability_fqn, ability_tags=action_tags) or (aoe and any(str(tt).endswith("is_aoe") for tt in mod.targets)):
                    buckets["normal_percentage"] = buckets.get("normal_percentage", 0.0) + val
                continue

            elif stat in ("STAT_cbt_damage_received_if_target_stunned_modifier_percentage", "223"):
                if _entity_has_tag(target, "stun") or _entity_has_tag(target, "incapacitate"):
                    buckets["normal_percentage"] = buckets.get("normal_percentage", 0.0) + val
                continue

            # 5. Critical Chance on Target
            if not mod.applies_to(ability_fqn=ability_fqn, ability_tags=action_tags):
                continue

            if stat in ("STAT_cbt_force_critical_chance", "133"):
                if is_force:
                    modifiers['bonus_crit_chance'] += val
            elif stat in ("STAT_cbt_melee_critical_chance", "116"):
                if is_melee:
                    modifiers['bonus_crit_chance'] += val
            elif stat in ("STAT_cbt_ranged_critical_chance", "122"):
                if is_ranged:
                    modifiers['bonus_crit_chance'] += val
            elif stat in ("STAT_cbt_tech_critical_chance", "135"):
                if is_tech:
                    modifiers['bonus_crit_chance'] += val
            elif stat == "Critical Chance":
                modifiers['bonus_crit_chance'] += val

def damage_taken_multiplier(target, tags, attack_type, damage_type) -> float:
    """Legacy helper for target vulnerability scaling (now handled in handle_target_debuffs)."""
    channel = _channel_for_hit(tags, attack_type)
    type_name = _DAMAGE_TYPE_NAMES.get(damage_type)
    tag_set = frozenset(tags)
    aoe = _hit_is_aoe(tags)
    bonus = 0.0

    for effect in target.effects.values():
        getter = getattr(effect, "get_effective_modifiers", None)
        if getter is None:
            continue
        for modifier in getter():
            stat = modifier.stat
            stat_lower = stat.lower()
            if "damage_taken_scale_channel_" in stat_lower:
                if channel and f"channel_{channel}_" in stat_lower:
                    bonus += modifier.value
                continue
            if "damage_taken_scale_type_" in stat_lower:
                if type_name and f"type_{type_name}_" in stat_lower:
                    bonus += modifier.value
                continue
            if stat == "STAT_rtg_armor" or not modifier.targets:
                continue
            if modifier.applies_to(ability_tags=tag_set):
                bonus += modifier.value
            elif aoe and any(str(target_tag).endswith("is_aoe") for target_tag in modifier.targets):
                bonus += modifier.value

    return 1.0 + bonus


def calculate_base_damage(caster, action_data, attack_type, modifiers=None):
    """ Calculates base damage from caster and action data. Returns damage value."""
    shp_min = action_data["shp_min"]
    shp_max = action_data["shp_max"]
    coeff = action_data["coeff"]
    standard_health = caster.stats["Standard_health"]
    if attack_type == 3:  # Force
        damage_bonus = caster.stats.get("F_Bonus_Damage", 0.0) or caster.stats.get("T_Bonus_Damage", 0.0)
        ability_damage_min = (coeff * damage_bonus) + (shp_min * standard_health)
        ability_damage_max = (coeff * damage_bonus) + (shp_max * standard_health)
    elif attack_type == 4:  # Tech
        damage_bonus = caster.stats.get("T_Bonus_Damage", 0.0) or caster.stats.get("F_Bonus_Damage", 0.0)
        ability_damage_min = (coeff * damage_bonus) + (shp_min * standard_health)
        ability_damage_max = (coeff * damage_bonus) + (shp_max * standard_health)
    elif attack_type in (1, 2):  # Melee (1) / Ranged (2)
        amp = action_data["amp"]
        if attack_type == 2:
            damage_bonus = caster.stats.get("R_Bonus_Damage", 0.0) or caster.stats.get("M_Bonus_Damage", 0.0)
        else:
            damage_bonus = caster.stats.get("M_Bonus_Damage", 0.0)
        # Base weapon damage modifier (STAT_cbt_base_weapon_damage_modifier_percentage / 413)
        weapon_mod = 0.0
        if modifiers is not None and "base_weapon_damage_modifier" in modifiers:
            weapon_mod = modifiers["base_weapon_damage_modifier"]
        elif caster is not None and hasattr(caster, "effects"):
            ability_fqn = action_data.get("ability_fqn")
            action_tags = frozenset(action_data.get("tags") or ())
            for eff in caster.effects.values():
                if getattr(eff, "is_expired", False):
                    continue
                getter = getattr(eff, "get_effective_modifiers", None)
                eff_mods = getter() if getter is not None else getattr(eff, "modifiers", [])
                for mod in eff_mods:
                    if str(mod.stat) in ("STAT_cbt_base_weapon_damage_modifier_percentage", "413"):
                        if not mod.targets or mod.applies_to(ability_fqn=ability_fqn, ability_tags=action_tags):
                            weapon_mod += float(mod.value)

        weapon_multiplier = max(0.0, 1.0 + weapon_mod)

        if action_data.get("hand") == "off":
            weapon_min = caster.stats.get("Off_hand_min", 0.0) * 0.3 * weapon_multiplier
            weapon_max = caster.stats.get("Off_hand_max", 0.0) * 0.3 * weapon_multiplier
        else:
            weapon_min = caster.stats.get("Main_hand_min", 0.0) * weapon_multiplier
            weapon_max = caster.stats.get("Main_hand_max", 0.0) * weapon_multiplier
        ability_damage_min = ((amp + 1) * weapon_min) + (coeff * damage_bonus) + (shp_min * standard_health)
        ability_damage_max = ((amp + 1) * weapon_max) + (coeff * damage_bonus) + (shp_max * standard_health)

    else:
        raise ValueError(f'Action had no valid attack_type')
    ability_damage = random.randint(int(ability_damage_min), int(ability_damage_max))

    return ability_damage

def handle_mitigation(caster, target, ability_damage, damage_type, modifiers=None):
    """Determines if applicable, if so calculates and applies mitigation to damage value. Returns new damage value"""
    if damage_type in (1, 2):
        armor = target.stats.get("Armor", 17225)
        bonus_pen = (modifiers.get('bonus_armor_pen', 0.0) if modifiers else 0.0)
        total_armor_pen = min(1.0, caster.stats.get("Armor Penetration", 0.0) + bonus_pen)
        effective_armor = max(0.0, armor * (1.0 - total_armor_pen))
        multiplier, additive = armor_constants(caster.level)
        armor_dr = effective_armor / (effective_armor + multiplier * caster.level + additive)
        ability_damage *= (1.0 - armor_dr)
    return ability_damage

def calculate_crit(caster, damage, modifiers):
    """Determines if it's crit, if so calculates new damage. Returns damage value and whether it was crit."""
    crit_chance = caster.stats.get("Critical Chance", 0.05) + modifiers['bonus_crit_chance']
    is_crit = random.random() < crit_chance
    if is_crit:
        extra_crit_multiplier = max(1,crit_chance) #if crit chance passes 100% it affects multiplier damage
        crit_multiplier = 1 + (caster.stats.get("Critical Modifier", 0.5) + modifiers['bonus_crit_modifier']) * extra_crit_multiplier
        damage *= crit_multiplier
    return damage, is_crit

def accuracy_roll(
    source,
    hand: str = "main",
    attack_type: Any = 1,
    ability_fqn: Optional[str] = None,
    action_tags: frozenset = frozenset(),
    target: Any = None,
) -> bool:
    """Determines if hit/ability meets the accuracy roll against target defense/resistance.

    Supports channel-specific accuracy stats:
      - STAT_cbt_melee_accuracy (114)
      - STAT_cbt_ranged_accuracy (120)
      - STAT_cbt_force_accuracy (232)
      - STAT_cbt_tech_accuracy (233)
      - STAT_cbtAccuracy (11)
      - STAT_cbt_dual_wield_accuracy_modifier_fixed (126)
    And channel-specific defense stats on target:
      - STAT_cbt_melee_defense (115)
      - STAT_cbt_ranged_defense (121)
      - STAT_cbt_force_defense (234)
      - STAT_cbt_tech_defense (235)
    """
    is_melee = attack_type in (1, "melee", "Melee")
    is_ranged = attack_type in (2, "ranged", "Ranged")
    is_force = attack_type in (3, "force", "Force")
    is_tech = attack_type in (4, "tech", "Tech")

    stats = getattr(source, "stats", {}) or {}
    main_acc = stats.get("Main Accuracy") or stats.get("Accuracy") or 1.0
    if is_melee:
        base_acc = stats.get("Melee Accuracy") or main_acc
    elif is_ranged:
        base_acc = stats.get("Ranged Accuracy") or main_acc
    elif is_force:
        base_acc = stats.get("Force Accuracy") or main_acc
    elif is_tech:
        base_acc = stats.get("Tech Accuracy") or main_acc
    else:
        base_acc = main_acc

    if hand == "off" and (is_melee or is_ranged):
        main_acc = stats.get("Main Accuracy", 1.0)
        off_acc = stats.get("Off Accuracy", 0.67)
        base_acc -= max(0.0, main_acc - off_acc)

    # Base target defense / resistance
    target_stats = getattr(target, "stats", {}) or {} if target else {}
    if is_force or is_tech:
        def_chance = float(target_stats.get("Resistance", 0.0))
    else:
        def_chance = float(target_stats.get("Defense", 0.10))

    bonus_accuracy = 0.0
    effects = getattr(source, "effects", None)
    if effects:
        for eff in effects.values():
            if getattr(eff, "is_expired", False):
                continue
            getter = getattr(eff, "get_effective_modifiers", None)
            eff_mods = getter() if getter is not None else getattr(eff, "modifiers", [])
            for mod in eff_mods or ():
                stat = str(mod.stat)
                val = float(mod.value)

                # Skip untargeted general accuracy rating (already processed in recalculate_stats)
                if not mod.targets and stat in ("STAT_rtg_accuracy", "154", "Accuracy"):
                    continue

                cond_tag = getattr(mod, "conditional_tag", None)
                if cond_tag:
                    require_owner = getattr(mod, "require_owner", False)
                    actor = getattr(mod, "actor", None)

                    def _acc_check_ent(ent):
                        if ent is None:
                            return False
                        for e in getattr(ent, "effects", {}).values():
                            if getattr(e, "is_expired", False):
                                continue
                            if cond_tag in getattr(e, "tags", ()):
                                if require_owner and source is not None:
                                    c_ref = getattr(e, "caster_ref", None)
                                    if c_ref is not None and c_ref is not source:
                                        continue
                                return True
                        return False

                    if actor == 3:
                        has_tag = _acc_check_ent(target)
                    elif actor == 1:
                        has_tag = _acc_check_ent(source)
                    else:
                        has_tag = _acc_check_ent(target) or _acc_check_ent(source)

                    if not has_tag:
                        continue

                if not mod.applies_to(ability_fqn=ability_fqn, ability_tags=action_tags):
                    continue

                if is_melee and stat in ("STAT_cbt_melee_accuracy", "114"):
                    bonus_accuracy += val
                elif is_ranged and stat in ("STAT_cbt_ranged_accuracy", "120"):
                    bonus_accuracy += val
                elif is_force and stat in ("STAT_cbt_force_accuracy", "232"):
                    bonus_accuracy += val
                elif is_tech and stat in ("STAT_cbt_tech_accuracy", "233"):
                    bonus_accuracy += val
                elif stat in ("STAT_cbtAccuracy", "11"):
                    bonus_accuracy += val
                elif stat in ("STAT_cbt_dual_wield_accuracy_modifier_fixed", "126"):
                    if hand == "off" or getattr(source, "stats", {}).get("Off_hand_max", 0.0) > 0:
                        bonus_accuracy += val

    bonus_defense = 0.0
    target_effects = getattr(target, "effects", None) if target else None
    if target_effects:
        for eff in target_effects.values():
            if getattr(eff, "is_expired", False):
                continue
            getter = getattr(eff, "get_effective_modifiers", None)
            eff_mods = getter() if getter is not None else getattr(eff, "modifiers", [])
            for mod in eff_mods or ():
                stat = str(mod.stat)
                val = float(mod.value)
                if is_melee and stat in ("STAT_cbt_melee_defense", "115"):
                    bonus_defense += val
                elif is_ranged and stat in ("STAT_cbt_ranged_defense", "121"):
                    bonus_defense += val
                elif is_force and stat in ("STAT_cbt_force_defense", "234"):
                    bonus_defense += val
                elif is_tech and stat in ("STAT_cbt_tech_defense", "235"):
                    bonus_defense += val

    effective_acc = base_acc + bonus_accuracy
    effective_def = def_chance + bonus_defense
    hit_chance = effective_acc - effective_def

    if hit_chance >= 1.0:
        return True
    if hit_chance <= 0.0:
        print("MISSED")
        return False

    if random.random() > hit_chance:
        print("MISSED")
        return False
    return True


def calc_dr(rating: float, cap: float, k_factor: float, level: int) -> float:
    """Percentage from a rating: Cap * [1 - (1 - 0.01 / Cap) ** ((1 / divisor) * (Rating / Level))]."""
    if not rating:
        return 0.0

    base_ratio = 1.0 - (0.01 / cap)
    decay_exponent = (1.0 / k_factor) * (rating / level)
    return cap * (1.0 - (base_ratio ** decay_exponent))