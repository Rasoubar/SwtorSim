import random

EFFECTS = {
    0: {"stat_name": "PlaceHolder"},
    79: {"stat_name": "Damage Modifier", "modifier_bucket": "normal_percentage"},
    386: {"stat_name": "Damage Modifier", "modifier_bucket": "normal_percentage"},
    220: {"stat_name": "Damage Modifier", "modifier_bucket": "sub_30"},
    116: {"stat_name": "Critical Chance"},
    117: {"stat_name": "Critical Damage"},
    134: {"stat_name": "Critical Damage"},
    133: {"stat_name": "Critical Chance"},
    46: {"stat_name": "Damage Modifier", "modifier_bucket": "unknown_percentage"},
    68: {"stat_name": "cost_reduction_flat"},
    166: {"stat_name": "Armor Penetration"},
    26: {"stat_name": "Bonus Damage"},
    414: {"stat_name": "Mastery PCT"},
    4140: {"stat_name": "Mastery Stat"},  # i blame the devs, I made up my own id for this one
    155: {"stat_name": "Power Stat"},
    156: {"stat_name": "Critical Stat"},
    64:{ "stat_name": "Base Cooldown Modifier"},
    154:{"stat_name": "Accuracy"},
    422:{"stat_name": "Ability Base Charges"}
}


def get_modifiers(caster, target, action_tags):
    buckets = {}

    modifiers = {'bonus_crit_chance': 0.0,
                 'bonus_crit_modifier': 0.0,
                 'bonus_armor_pen': 0.0,
                 'target_armor_debuff': 0.0,
                 'total_multiplier': 1.0}

    caster_expired_buffs = []

    for effect_id, buff in list(caster.effects.items()):
        if buff.id in EFFECTS:
            meta = EFFECTS[buff.id]
            if buff.consumable_charges is not None and buff.consumable_charges <= 0:  # can remove this
                continue
            if buff.required_tags is not None:
                if not any(tag in action_tags for tag in buff.required_tags):
                    continue
            if buff.target_hp_threshold is not None and target.hp_ratio > buff.target_hp_threshold:
                continue
            if buff.stack_values:
                stack_index = min(buff.charges - 1, len(buff.stack_values) - 1)
                total_buff_value = buff.stack_values[stack_index]
            else:
                multiplier = buff.charges if buff.max_charges is not None else 1
                total_buff_value = buff.value * multiplier
            if meta["stat_name"] == "Damage Modifier":
                bucket = meta["modifier_bucket"]
                buckets[bucket] = buckets.get(bucket, 0.0) + total_buff_value
            elif meta["stat_name"] == "Critical Chance":
                modifiers['bonus_crit_chance'] += total_buff_value
            elif meta["stat_name"] == "Critical Damage":
                modifiers['bonus_crit_modifier'] += total_buff_value
            elif meta["stat_name"] == "Armor Penetration":
                modifiers['bonus_armor_pen'] += total_buff_value
            if buff.consumable_charges is not None and buff.id != 68: #temporary
                buff.consumable_charges -= 1
                if buff.consumable_charges <= 0:
                    caster_expired_buffs.append(effect_id)

    caster.cleanup_expired_effects(caster_expired_buffs)

    for effect_id, buff in list(target.debuffs.items()):
        if buff.id in EFFECTS:
            meta = EFFECTS[buff.id]
            multiplier = buff.charges if buff.max_charges is not None else 1
            if buff.required_tags is not None:
                if not any(tag in action_tags for tag in buff.required_tags):
                    continue
            if meta["stat_name"] == "Damage Modifier":
                bucket = meta["modifier_bucket"]
                buckets[bucket] = buckets.get(bucket, 0.0) + (buff.value * multiplier)
            elif meta["stat_name"] == "Armor Debuff":
                modifiers['target_armor_debuff'] += (buff.value * multiplier)
            if buff.consumable_charges is not None:
                buff.consumable_charges -= 1
                if buff.consumable_charges <= 0:
                    del target.debuffs[effect_id]
    for bucket_value in buckets.values():
        modifiers['total_multiplier'] *= (1 + bucket_value)
    return modifiers


def calculate_hit(caster, target, action_data):
    print(f'TARGET DOTS NAMES: {target.dots}')
    attack_type = action_data["attack_type"]  # 1 = melee, 2 = ranged, 3 = force, 4 = tech
    action_tags = action_data.get("tags", [])
    if attack_type in (1, 2):
        damage_type = 1
    else:
        damage_type = action_data["damage_type"]  # 1 = kinetic, 2 = energy, 3 = elemental, 4 = internal

    modifiers = get_modifiers(caster, target, action_tags)

    shp_min = action_data["shp_min"]
    shp_max = action_data["shp_max"]
    coeff = action_data["coeff"]
    standard_health = caster.stats["Standard_health"]
    if attack_type in (3, 4):
        damage_bonus = caster.stats["F_Bonus_Damage"]
        ability_damage_min = (coeff * damage_bonus) + (shp_min * standard_health)
        ability_damage_max = (coeff * damage_bonus) + (shp_max * standard_health)
    elif attack_type in (1, 2):
        amp = action_data["amp"]
        damage_bonus = caster.stats["M_Bonus_Damage"]
        if action_data["hand"] == "off":
            off_hand_min = caster.stats["Off_hand_min"]
            off_hand_max = caster.stats["Off_hand_max"]
            ability_damage_min =((amp + 1) * off_hand_min * 0.3)
            ability_damage_max =((amp + 1) * off_hand_max * 0.3)
        else:
            main_hand_min = caster.stats["Main_hand_min"]
            main_hand_max = caster.stats["Main_hand_max"]
            ability_damage_min = ((amp + 1) * main_hand_min) + (coeff * damage_bonus) + (shp_min * standard_health)
            ability_damage_max = ((amp + 1) * main_hand_max) + (coeff * damage_bonus) + (shp_max * standard_health)

    else:
        raise ValueError(f'Action had no valid attack_type')
    ability_damage = random.randint(int(ability_damage_min), int(ability_damage_max))
    if damage_type in (1, 2):
        armor = target.stats.get("armor", 17225) * (1.0 - modifiers['target_armor_debuff'])
        total_armor_pen = caster.stats.get("Armor Penetration", 0.0) + modifiers['bonus_armor_pen']
        effective_armor = armor * (1.0 - total_armor_pen)
        armor_dr = effective_armor / (effective_armor + 32000)
        ability_damage *= (1.0 - armor_dr)
    ability_damage *= modifiers['total_multiplier']
    crit_chance = caster.stats.get("Critical Chance", 0.05) + modifiers['bonus_crit_chance']
    extra_crit_multiplier = 1
    if crit_chance > 1:
        extra_crit_multiplier = crit_chance - 1
    crit_multiplier = 1 + (caster.stats.get("Critical Modifier", 0.5) + modifiers['bonus_crit_modifier']) * extra_crit_multiplier
    is_crit = random.random() < crit_chance
    if is_crit:
        ability_damage *= crit_multiplier
    return int(ability_damage), is_crit

