import random
#EFFECTS = {
#    79: {"stat_name": "Damage Modifier", "modifier_bucket": "normal_percentage"},
#    386: {"stat_name": "Damage Modifier", "modifier_bucket": "normal_percentage"},
#    220: {"stat_name": "Damage Modifier", "modifier_bucket": "sub_30"},
#    133: {"stat_name": "Critical Chance", "modifier_bucket": "crit"},
#    46: {"stat_name": "Damage Modifier", "modifier_bucket": "unknown_percentage"}
#}


EFFECTS = {
    0:{"stat_name": "PlaceHolder"},
    79: {"stat_name": "Damage Modifier", "modifier_bucket": "normal_percentage"},
    386: {"stat_name": "Damage Modifier", "modifier_bucket": "normal_percentage"},
    220: {"stat_name": "Damage Modifier", "modifier_bucket": "sub_30"},
    133: {"stat_name": "Critical Chance"},
    46: {"stat_name": "Damage Modifier", "modifier_bucket": "unknown_percentage"},
    68:{"stat_name": "cost_reduction_flat"},
    166:{"stat_name": "Armor Penetration"},
    # for testing for now, will check actual ids later
    500: {"stat_name": "Mastery Stat"},
    600: {"stat_name": "Power Stat"}
}
def calculate_hit(caster, target, action_data) -> tuple[int, bool]:
    attack_type = action_data["attack_type"] #1 = melee, 2 = ranged, 3 = force, 4 = tech
    action_tags = action_data.get("tags", [])
    if attack_type in (1,2):
        damage_type = 1
    else:
        damage_type = action_data["damage_type"] #1 = kinetic, 2 = energy, 3 = elemental, 4 = internal


    buckets = {}
    bonus_crit_chance = 0
    bonus_crit_modifier = 0
    bonus_armor_pen = 0
    target_armor_debuff = 0

    caster_expired_buffs = []
    for effect_id, buff in list(caster.effects.items()):
        if buff.id in EFFECTS:
            meta = EFFECTS[buff.id]
            if buff.consumable_charges is not None and buff.consumable_charges <= 0: #can remove this
                continue
            if buff.required_tags is not None:
                if not any(tag in action_tags for tag in buff.required_tags):
                    continue
            if buff.target_hp_threshold is not None and target.hp_ratio > buff.target_hp_threshold:
                continue
            multiplier = buff.charges if buff.max_charges is not None else 1
            if meta["stat_name"] == "Damage Modifier":
                bucket = meta["modifier_bucket"]
                buckets[bucket] = buckets.get(bucket, 0.0) + (buff.value * multiplier)
            elif meta["stat_name"] == "Critical Chance":
                bonus_crit_chance += (buff.value * multiplier)
            elif meta["stat_name"] == "Critical Damage":
                bonus_crit_modifier += (buff.value * multiplier)
            elif meta["stat_name"] == "Armor Penetration":
                bonus_armor_pen += (buff.value * multiplier)
            if buff.consumable_charges is not None:
                buff.consumable_charges -= 1
                if buff.consumable_charges <= 0:
                    caster_expired_buffs.append(effect_id)

    for effect_id, buff in list(target.debuffs.items()):
        if buff.id in EFFECTS:
            meta = EFFECTS[buff.id]
            multiplier = buff.charges if buff.max_charges is not None else 1
            if meta["stat_name"] == "Damage Modifier":
                bucket = meta["modifier_bucket"]
                buckets[bucket] = buckets.get(bucket, 0.0) + (buff.value * multiplier)
            elif meta["stat_name"] == "Armor Debuff":
                target_armor_debuff += (buff.value * multiplier)
            if buff.consumable_charges is not None:
                print(f"📉 [Stack Trigger] '{buff.effect_name}' triggered via hit from {caster.name}. "
                      f"Consumable Stacks: {buff.consumable_charges} -> {buff.consumable_charges - 1}")
                buff.consumable_charges -= 1
                if buff.consumable_charges <= 0:
                    del target.debuffs[effect_id]

    total_multiplier = 1.0
    for bucket_value in buckets.values():
        total_multiplier *= (1 + bucket_value)

    shp_min = action_data["shp_min"]
    shp_max = action_data["shp_max"]
    amp = action_data["amp"] #amount modifier percent
    coeff = action_data["coeff"]
    main_hand_min = caster.stats["Main_hand_min"]
    main_hand_max = caster.stats["Main_hand_max"]
    off_hand_min = caster.stats["Off_hand_min"]
    off_hand_max = caster.stats["Off_hand_max"]
    standard_health = caster.stats["Standard_health"]
    total_armor_pen = 0
    if attack_type in (1,2):
        damage_bonus = caster.stats["M_Bonus_Damage"]
    else:
        damage_bonus = caster.stats["F_Bonus_Damage"]

    print(total_multiplier)
    print(bonus_crit_chance)
    ability_damage_min = ((amp ) * main_hand_min) + ((amp) * off_hand_min) + (coeff * damage_bonus) + (shp_min * standard_health)
    ability_damage_max = ((amp ) * main_hand_max) + ((amp) * off_hand_max) + (coeff * damage_bonus) + (shp_max * standard_health)
    ability_damage = random.randint(int(ability_damage_min), int(ability_damage_max)) * total_multiplier


    if damage_type in (1,2):
        armor = target.stats.get("armor", 17225) * (1.0 - target_armor_debuff)
        total_armor_pen = caster.stats.get("Armor Penetration", 0.0) + bonus_armor_pen
        effective_armor = armor * (1.0 - total_armor_pen)

        armor_dr = effective_armor / (effective_armor + 32000)
        ability_damage *= (1 - armor_dr)

    crit_chance = caster.stats.get("Critical Chance", 0.05) + bonus_crit_chance
    crit_multiplier = caster.stats.get("Critical Modifier", 1.5) + bonus_crit_modifier
    is_crit = random.random() < crit_chance
    caster.cleanup_expired_effects(caster_expired_buffs) #idk any buff where this will matter, but i dont know much
    if is_crit:
        return int(ability_damage * crit_multiplier), True
    return int(ability_damage), False




