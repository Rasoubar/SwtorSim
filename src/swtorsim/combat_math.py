import random

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
    base_damage = calculate_base_damage(caster, action_data, attack_type)

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

def handle_caster_buffs(caster, target, action_tags, ability_fqn, attack_type, damage_type, buckets, modifiers):
    """ Alters modifiers dict according to active effects and buffs on caster."""
    is_melee = attack_type == 1
    is_ranged = attack_type == 2
    is_force = attack_type == 3
    is_tech = attack_type == 4

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
            if not mod.targets and stat in (
                "STAT_att_mastery", "414", "4140",
                "STAT_rtg_attack_power", "155", "STAT_att_power",
                "STAT_rtg_crit", "156",
                "STAT_rtg_alacrity", "Alacrity Rating",
                "STAT_rtg_accuracy", "154", "Accuracy",
                "STAT_cbt_melee_damage_bonus", "115",
                "STAT_cbt_ranged_damage_bonus", "128",
                "STAT_cbt_force_damage_bonus", "132",
                "STAT_cbt_tech_damage_bonus", "130",
                "STAT_cbt_damage_bonus",
                "STAT_att_endurance",
                "STAT_cbtStealthEffectiveLevel",
            ):
                continue

            # Check conditional tag requirement on target or caster
            cond_tag = getattr(mod, "conditional_tag", None)
            if cond_tag:
                has_tag = any(
                    cond_tag in getattr(e, "tags", ())
                    for e in getattr(target, "effects", {}).values()
                    if not getattr(e, "is_expired", False)
                ) or any(
                    cond_tag in getattr(e, "tags", ())
                    for e in getattr(caster, "effects", {}).values()
                    if not getattr(e, "is_expired", False)
                )
                if not has_tag:
                    continue

            # Check ability FQN / tags matching
            if not mod.applies_to(ability_fqn=ability_fqn, ability_tags=action_tags):
                continue

            # 1. Damage Done Percentage Modifiers
            if stat in ("STAT_cbt_damage_done_modifier_percentage", "79", "386", "384", "370", "376", "46"):
                buckets["normal_percentage"] = buckets.get("normal_percentage", 0.0) + val

            elif stat in ("STAT_cbt_damage_done_if_target_health_low_modifier_percentage", "220"):
                if getattr(target, "hp_ratio", 1.0) <= 0.30:
                    buckets["sub_30"] = buckets.get("sub_30", 0.0) + val

            elif stat in ("stat_cbt_damage_dealt_scale_channel_melee_modifier_percentage", "stat_cbt_damage_dealt_scale_channel_melee"):
                if is_melee:
                    buckets["normal_percentage"] = buckets.get("normal_percentage", 0.0) + val

            elif stat in ("stat_cbt_damage_dealt_scale_channel_ranged_modifier_percentage", "stat_cbt_damage_dealt_scale_channel_ranged"):
                if is_ranged:
                    buckets["normal_percentage"] = buckets.get("normal_percentage", 0.0) + val

            elif stat in ("stat_cbt_damage_dealt_scale_channel_force_modifier_percentage", "stat_cbt_damage_dealt_scale_channel_force"):
                if is_force:
                    buckets["normal_percentage"] = buckets.get("normal_percentage", 0.0) + val

            elif stat in ("stat_cbt_damage_dealt_scale_channel_tech_modifier_percentage", "stat_cbt_damage_dealt_scale_channel_tech"):
                if is_tech:
                    buckets["normal_percentage"] = buckets.get("normal_percentage", 0.0) + val

            # 2. Critical Chance Modifiers
            elif stat in ("STAT_cbt_force_critical_chance", "133"):
                if is_force:
                    modifiers['bonus_crit_chance'] += val

            elif stat in ("STAT_cbt_melee_critical_chance", "116"):
                if is_melee:
                    modifiers['bonus_crit_chance'] += val

            elif stat in ("STAT_cbt_ranged_critical_chance", "118"):
                if is_ranged:
                    modifiers['bonus_crit_chance'] += val

            elif stat in ("STAT_cbt_tech_critical_chance", "135"):
                if is_tech:
                    modifiers['bonus_crit_chance'] += val

            elif stat == "Critical Chance":
                modifiers['bonus_crit_chance'] += val

            # 3. Critical Damage Modifiers
            elif stat in ("STAT_cbt_force_critical_damage", "134"):
                if is_force:
                    modifiers['bonus_crit_modifier'] += val

            elif stat in ("STAT_cbt_melee_critical_damage", "117"):
                if is_melee:
                    modifiers['bonus_crit_modifier'] += val

            elif stat in ("STAT_cbt_ranged_critical_damage",):
                if is_ranged:
                    modifiers['bonus_crit_modifier'] += val

            elif stat in ("STAT_cbt_tech_critical_damage",):
                if is_tech:
                    modifiers['bonus_crit_modifier'] += val

            elif stat == "Critical Damage":
                modifiers['bonus_crit_modifier'] += val

            # 4. Armor Penetration
            elif stat in ("STAT_cbt_armor_penetration", "166"):
                modifiers['bonus_armor_pen'] += val

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


def handle_target_debuffs(target, action_tags, ability_fqn, attack_type, damage_type, buckets, modifiers, caster=None):
    """ Alters modifiers dict according to active debuffs on target."""
    channel = _channel_for_hit(action_tags, attack_type)
    type_name = _DAMAGE_TYPE_NAMES.get(damage_type)
    aoe = _hit_is_aoe(action_tags)
    is_melee = attack_type == 1
    is_ranged = attack_type == 2
    is_force = attack_type == 3
    is_tech = attack_type == 4

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
                has_tag = any(
                    cond_tag in getattr(e, "tags", ())
                    for e in getattr(target, "effects", {}).values()
                    if not getattr(e, "is_expired", False)
                ) or (caster is not None and any(
                    cond_tag in getattr(e, "tags", ())
                    for e in getattr(caster, "effects", {}).values()
                    if not getattr(e, "is_expired", False)
                ))
                if not has_tag:
                    continue

            stat_lower = stat.lower()

            # 1. Channel vulnerabilities (Melee, Ranged, Force, Tech, Weapon)
            if "damage_taken_scale_channel_" in stat_lower or stat in (
                "381", "382", "383", "384", "385", "386", "387", "388", "463"
            ):
                matched = False
                if channel and f"channel_{channel}_" in stat_lower:
                    matched = True
                elif is_melee and (
                    stat in ("stat_cbt_damage_taken_scale_channel_melee_modifier_percentage", "384")
                    or "channel_melee_" in stat_lower
                    or stat in ("stat_cbt_damage_taken_scale_channel_weapon_modifier", "463")
                    or "channel_weapon_" in stat_lower
                ):
                    matched = True
                elif is_ranged and (
                    stat in ("stat_cbt_damage_taken_scale_channel_ranged_modifier_percentage", "382")
                    or "channel_ranged_" in stat_lower
                    or stat in ("stat_cbt_damage_taken_scale_channel_weapon_modifier", "463")
                    or "channel_weapon_" in stat_lower
                ):
                    matched = True
                elif is_force and (
                    stat in ("stat_cbt_damage_taken_scale_channel_force_modifier_percentage", "386")
                    or "channel_force_" in stat_lower
                ):
                    matched = True
                elif is_tech and (
                    stat in ("stat_cbt_damage_taken_scale_channel_tech_modifier_percentage", "388")
                    or "channel_tech_" in stat_lower
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
            if stat in ("stat_cbt_damage_taken_scale_tag_aoe_modifier", "465") or "tag_aoe_" in stat_lower:
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

            # 5. Critical Chance on Target
            if not mod.applies_to(ability_fqn=ability_fqn, ability_tags=action_tags):
                continue

            if stat in ("STAT_cbt_force_critical_chance", "133"):
                if is_force:
                    modifiers['bonus_crit_chance'] += val
            elif stat in ("STAT_cbt_melee_critical_chance", "116"):
                if is_melee:
                    modifiers['bonus_crit_chance'] += val
            elif stat in ("STAT_cbt_ranged_critical_chance", "118"):
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


def calculate_base_damage(caster, action_data, attack_type):
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
        if action_data.get("hand") == "off":
            weapon_min = caster.stats.get("Off_hand_min", 0.0) * 0.3
            weapon_max = caster.stats.get("Off_hand_max", 0.0) * 0.3
        else:
            weapon_min = caster.stats.get("Main_hand_min", 0.0)
            weapon_max = caster.stats.get("Main_hand_max", 0.0)
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

def accuracy_roll(source, hand):
    """Determines if hit/ability meets the accuracy roll."""
    def_chance = 0.1
    if hand == "main":
        acc = source.stats.get("Main Accuracy")
    elif hand == "off":
        acc = source.stats.get("Off Accuracy")
    else:
        acc = source.stats.get("Main Accuracy")
    if random.random() + def_chance > acc:
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