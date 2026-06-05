import random
EFFECTS = {
    79: {"stat_name": "Damage Modifier", "modifier_bucket": "normal_percentage"},
    386: {"stat_name": "Damage Modifier", "modifier_bucket": "normal_percentage"},
    220: {"stat_name": "Damage Modifier", "modifier_bucket": "sub_30"},
    133: {"stat_name": "Critical Chance", "modifier_bucket": "crit"},
    46: {"stat_name": "Damage Modifier", "modifier_bucket": "unknown_percentage"}
}
def calculate_hit(caster, target, action_data) -> tuple[int, bool]:
    attack_type = action_data["attack type"] #1 = melee, 2 = ranged, 3 = force, 4 = tech
    if attack_type in (1,2):
        damage_type = 1

    else:
        damage_type = action_data["damage type"] #1 = kinetic, 2 = energy, 3 = elemental, 4 = internal

    buckets = {}
    bonus_crit_chance = 0
    bonus_crit_modifier = 0
    bonus_armor_pen = 0
    target_armor_debuff = 0

    for effect_id, buff in caster.effects.items():
        if effect_id in EFFECTS:
            meta = EFFECTS[effect_id]
            if meta["stat_name"] == "Damage Modifier":
                bucket = meta["modifier_bucket"]
                buckets[bucket] = buckets.get(bucket, 0.0) + buff.get("value", 0.0)
            elif meta["stat_name"] == "Critical Chance":
                bonus_crit_chance += buff.get("value", 0.0)
            elif meta["stat_name"] == "Critical Damage":
                bonus_crit_modifier += buff.get("value", 0.0)
            elif meta["stat_name"] == "Armor Penetration":
                bonus_armor_pen += buff.get("value", 0.0)

    for effect_id, buff in target.debuffs.items():
        if effect_id in EFFECTS:
            meta = EFFECTS[effect_id]
            if meta["stat_name"] == "Damage Modifier":
                bucket = meta["modifier_bucket"]
                buckets[bucket] = buckets.get(bucket, 0.0) + buff.get("value", 0.0)
            elif meta["stat_name"] == "Armor Debuff":
                target_armor_debuff += buff.get("value", 0.0)

    total_multiplier = 1.0
    for bucket_value in buckets.values():
        total_multiplier *= (1 + bucket_value)

    shp_min = action_data["shp_min"]
    shp_max = action_data["shp_max"]
    amp = action_data["amp"] #amount modifier percent
    coeff = action_data["coeff"]
    main_hand_min = caster.stats["main_hand_min"]
    main_hand_max = caster.stats["main_hand_max"]
    off_hand_min = caster.stats["off_hand_min"]
    off_hand_max = caster.stats["off_hand_max"]
    damage_bonus = caster.stats["damage_bonus"]
    standard_health = caster.stats["standard_health"]

    ability_damage_min = ((amp + 1) * main_hand_min) + ((amp + 1) * off_hand_min) + (coeff * damage_bonus) + (shp_min * standard_health)
    ability_damage_max = ((amp + 1) * main_hand_max) + ((amp + 1) * off_hand_max) + (coeff * damage_bonus) + (shp_max * standard_health)
    ability_damage = random.randint(int(ability_damage_min), int(ability_damage_max)) * total_multiplier

    if damage_type in (1,2):
        armor = target.stats.get("armor", 17225) * (1.0 - target_armor_debuff)
        total_armor_pen = caster.stats.get("base_armor_penetration", 0.0) + bonus_armor_pen
        effective_armor = armor * (1.0 - total_armor_pen)

        armor_dr = effective_armor / (effective_armor + 32000)
        ability_damage *= (1 - armor_dr)

    crit_chance = caster.stats.get("crit_chance", 0.05) + bonus_crit_chance
    crit_multiplier = caster.stats.get("crit_multiplier", 1.5) + bonus_crit_modifier
    is_crit = random.random() < crit_chance
    if is_crit:
        return int(ability_damage * crit_multiplier), True
    return int(ability_damage), False



