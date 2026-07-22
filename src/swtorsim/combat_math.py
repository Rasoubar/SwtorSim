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
    4140: {"stat_name": "Mastery Stat"},  # I blame the devs, I made up my own id for this one
    155: {"stat_name": "Power Stat"},
    156: {"stat_name": "Critical Stat"},
    64:{ "stat_name": "Base Cooldown Modifier"},
    154:{"stat_name": "Accuracy"},
    422:{"stat_name": "Ability Base Charges"},
    48:{"stat:name": "Armor Rating"}
}
def calculate_hit(caster, target, action_data):
    """Calculates the hit value of an action from a caster to a targe. Returns value and whether it was a crit"""

    #pre-extract damage_type, attack_type and action_tags to not be doing same thing multiple times
    attack_type = action_data["attack_type"]
    if attack_type in (1, 2):
        damage_type = 1
    else:
        damage_type = action_data["damage_type"]
    action_tags = action_data.get("tags", [])

    #calculate damage calculation modifiers
    modifiers = handle_modifiers(caster, target, action_tags)

    #calculate base damage from caster stats and action_data
    base_damage = calculate_base_damage(caster,action_data, attack_type)

    post_mit_damage = handle_mitigation(caster, target, base_damage, modifiers, damage_type)

    post_mod_damage = post_mit_damage * modifiers['total_multiplier']

    post_crit_damage, is_crit = calculate_crit(caster, post_mod_damage, modifiers)

    return int(post_crit_damage), is_crit

def handle_modifiers(caster, target, action_tags):
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
    handle_caster_buffs(caster, target, action_tags, buckets, modifiers)
    handle_target_debuffs(target, action_tags, buckets, modifiers)

    #consume relevant charges. (this will be changed as it doesn't reflect the actual mechanism in the game)
    consume_charges(caster, target, action_tags)

    for bucket_value in buckets.values():
        modifiers['total_multiplier'] *= (1.0 + bucket_value)

    return modifiers

def handle_caster_buffs(caster, target, action_tags, buckets, modifiers):
    """ Alters modifiers dict according to buffs on caster."""
    for buff in caster.effects.values():
        if buff.id not in EFFECTS:
            continue
        if buff.consumable_charges is not None and buff.consumable_charges <= 0:
            continue
        if buff.required_tags is not None and not any(tag in action_tags for tag in buff.required_tags):
            continue
        if buff.target_hp_threshold is not None and target.hp_ratio > buff.target_hp_threshold:
            continue

        alter_modifier(buff,modifiers,buckets)

def handle_target_debuffs(target, action_tags, buckets, modifiers):
    """ Alters modifiers dict according to debuffs on target."""
    for debuff in target.effects.values():
        if debuff.id not in EFFECTS:
            continue
        if debuff.required_tags is not None and not any(tag in action_tags for tag in debuff.required_tags):
            continue
        alter_modifier(debuff,modifiers,buckets)

def alter_modifier(effect, modifiers, buckets):
    """Handles the individual modifier modification fors both buffs and debuffs"""
    meta = EFFECTS[effect.id]

    """get the buff value when different number of stacks on the buff give different values,
       is needed because it's not implemented so that it is always linear.
       Works for now but might need changes for other classes, JSONs too."""
    if effect.stack_values:
        stack_index = max(0, min(effect.charges - 1, len(effect.stack_values) - 1))
        total_buff_value = effect.stack_values[stack_index]
    else:
        multiplier = effect.charges if effect.max_charges is not None else 1
        total_buff_value = effect.value * multiplier

    stat_name = meta["stat_name"]
    if stat_name == "Damage Modifier":
        bucket = meta["modifier_bucket"]
        buckets[bucket] = buckets.get(bucket, 0.0) + total_buff_value
    elif stat_name == "Critical Chance":
        modifiers['bonus_crit_chance'] += total_buff_value
    elif stat_name == "Critical Damage":
        modifiers['bonus_crit_modifier'] += total_buff_value

def consume_charges(caster, target, action_tags):
    """Alters charge value according to use. Will be gone on next version as doesn't follow game logic."""
    caster_expired_buffs = []

    # Consume Caster Buffs
    for effect_id, buff in list(caster.effects.items()):
        if buff.id not in EFFECTS:
            continue
        if buff.required_tags is not None and not any(tag in action_tags for tag in buff.required_tags):
            continue
        if buff.target_hp_threshold is not None and target.hp_ratio > buff.target_hp_threshold:
            continue

        if buff.consumable_charges is not None and buff.id != 68:  # temporary exemption preserved
            buff.consumable_charges -= 1
            if buff.consumable_charges <= 0:
                caster_expired_buffs.append(effect_id)
    caster.cleanup_expired_effects(caster_expired_buffs)

    # Consume Target Debuffs
    for effect_id, buff in list(target.effects.items()):
        if buff.id not in EFFECTS:
            continue
        if buff.required_tags is not None and not any(tag in action_tags for tag in buff.required_tags):
            continue
        if buff.consumable_charges is not None:
            buff.consumable_charges -= 1
            if buff.consumable_charges <= 0:
                del target.effects[effect_id]

def calculate_base_damage(caster, action_data, attack_type):
    """ Calculates base damage from caster and action data. Returns damage value."""
    shp_min = action_data["shp_min"]
    shp_max = action_data["shp_max"]
    coeff = action_data["coeff"]
    standard_health = caster.stats["Standard_health"]
    if attack_type in (3, 4): # for when damage is force/tech
        damage_bonus = caster.stats["F_Bonus_Damage"]
        ability_damage_min = (coeff * damage_bonus) + (shp_min * standard_health)
        ability_damage_max = (coeff * damage_bonus) + (shp_max * standard_health)
    elif attack_type in (1, 2): # for when damage is melee/ranged
        amp = action_data["amp"]
        damage_bonus = caster.stats["M_Bonus_Damage"]
        if action_data["hand"] == "off":
            off_hand_min = caster.stats["Off_hand_min"]
            off_hand_max = caster.stats["Off_hand_max"]
            ability_damage_min = ((amp + 1) * off_hand_min * 0.3)
            ability_damage_max = ((amp + 1) * off_hand_max * 0.3)
        else:
            main_hand_min = caster.stats["Main_hand_min"]
            main_hand_max = caster.stats["Main_hand_max"]
            ability_damage_min = ((amp + 1) * main_hand_min) + (coeff * damage_bonus) + (shp_min * standard_health)
            ability_damage_max = ((amp + 1) * main_hand_max) + (coeff * damage_bonus) + (shp_max * standard_health)

    else:
        raise ValueError(f'Action had no valid attack_type')
    ability_damage = random.randint(int(ability_damage_min), int(ability_damage_max))

    return ability_damage

def handle_mitigation(caster, target, ability_damage, modifiers, damage_type):
    """Determines if applicable, if so calculates and applies mitigation to damage value. Returns new damage value"""
    if damage_type in (1, 2):
        armor = target.stats.get("armor", 17225)
        total_armor_pen = caster.stats.get("Armor Penetration", 0.0)
        print(f'ARMOR PEN IS {total_armor_pen}')
        effective_armor = armor * (1.0 - total_armor_pen)
        armor_dr = effective_armor / (effective_armor + 32000)
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