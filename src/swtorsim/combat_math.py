import random

from src.swtorsim.combat_curves import armor_constants

EFFECTS = {
    0: {"stat_name": "PlaceHolder"},
    79: {"stat_name": "Damage Modifier", "modifier_bucket": "normal_percentage"},
    386: {"stat_name": "Damage Modifier", "modifier_bucket": "normal_percentage"},
    384: {"stat_name": "Damage Modifier", "modifier_bucket": "normal_percentage"},
    370: {"stat_name": "Damage Modifier", "modifier_bucket": "normal_percentage"},
    376: {"stat_name": "Damage Modifier", "modifier_bucket": "normal_percentage"},
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
    48:{"stat_name": "Armor Rating"}
}
def calculate_hit(caster, target, action_data):
    """Calculates the hit value of an action from a caster to a targe. Returns value and whether it was a crit"""

    #pre-extract damage_type, attack_type and action_tags to not be doing same thing multiple times
    attack_type = action_data["attack_type"]
    if attack_type in (1, 2):
        damage_type = 1
    else:
        damage_type = action_data["damage_type"]

    #calculate damage calculation modifiers
    modifiers = handle_modifiers(caster, target, action_data)

    #calculate base damage from caster stats and action_data
    base_damage = calculate_base_damage(caster,action_data, attack_type)

    post_mit_damage = handle_mitigation(caster, target, base_damage, damage_type, modifiers)

    tags = action_data.get("tags") or []
    taken = damage_taken_multiplier(target, tags, attack_type, damage_type)
    post_mod_damage = post_mit_damage * modifiers['total_multiplier'] * taken

    post_crit_damage, is_crit = calculate_crit(caster, post_mod_damage, modifiers)

    return int(post_crit_damage), is_crit

def handle_modifiers(caster, target, action_data):
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
    damage_type = action_data.get("damage_type", 1)

    handle_caster_buffs(caster, target, action_tags, ability_fqn, attack_type, damage_type, buckets, modifiers)
    handle_target_debuffs(target, action_tags, ability_fqn, attack_type, damage_type, buckets, modifiers)

    #consume relevant charges. (this will be changed as it doesn't reflect the actual mechanism in the game)
    consume_charges(caster, target, action_tags)

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

        # Legacy effect compatibility
        effect_id = getattr(buff, "id", None)
        if effect_id in EFFECTS:
            if getattr(buff, "consumable_charges", None) is not None and buff.consumable_charges <= 0:
                continue
            if getattr(buff, "required_tags", None) is not None and not any(tag in action_tags for tag in buff.required_tags):
                continue
            if getattr(buff, "target_hp_threshold", None) is not None and getattr(target, "hp_ratio", 1.0) > buff.target_hp_threshold:
                continue
            if getattr(buff, "required_damage_type", None) is not None and buff.required_damage_type != damage_type:
                continue
            alter_modifier(buff, modifiers, buckets)
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
                "STAT_cbt_melee_damage_bonus",
                "STAT_cbt_force_damage_bonus",
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

            elif stat == "stat_cbt_damage_dealt_scale_channel_melee_modifier_percentage":
                if is_melee:
                    buckets["normal_percentage"] = buckets.get("normal_percentage", 0.0) + val

            elif stat == "stat_cbt_damage_dealt_scale_channel_force_modifier_percentage":
                if is_force:
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

def handle_target_debuffs(target, action_tags, ability_fqn, attack_type, damage_type, buckets, modifiers):
    """ Alters modifiers dict according to active debuffs on target."""
    for debuff in target.effects.values():
        if getattr(debuff, "is_expired", False):
            continue

        # Legacy debuff compatibility
        effect_id = getattr(debuff, "id", None)
        if effect_id in EFFECTS:
            if getattr(debuff, "required_tags", None) is not None and not any(tag in action_tags for tag in debuff.required_tags):
                continue
            if getattr(debuff, "required_damage_type", None) is not None and debuff.required_damage_type != damage_type:
                continue
            alter_modifier(debuff, modifiers, buckets)
            continue

        getter = getattr(debuff, "get_effective_modifiers", None)
        eff_mods = getter() if getter is not None else getattr(debuff, "modifiers", [])
        if not eff_mods:
            continue

        is_melee = attack_type == 1
        is_ranged = attack_type == 2
        is_force = attack_type == 3
        is_tech = attack_type == 4
        for mod in eff_mods:
            if not mod.applies_to(ability_fqn=ability_fqn, ability_tags=action_tags):
                continue
            stat = str(mod.stat)
            val = float(mod.value)
            if stat == "STAT_cbt_damage_received_modifier_percentage":
                buckets["target_vuln"] = buckets.get("target_vuln", 0.0) + val
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
    target_expired_debuffs = []

    # Consume Caster Buffs
    for effect_id, buff in list(caster.effects.items()):
        if getattr(buff, "id", None) not in EFFECTS:
            continue
        if buff.required_tags is not None and not any(tag in action_tags for tag in buff.required_tags):
            continue
        if buff.target_hp_threshold is not None and target.hp_ratio > buff.target_hp_threshold:
            continue
        if buff.id != 68 and buff.consume_charge(): #this will be changed once proper expiration is implemented
            caster_expired_buffs.append(effect_id)
    caster.cleanup_expired_effects(caster_expired_buffs)

    # Consume Target Debuffs
    for effect_key, buff in list(target.effects.items()):
        if getattr(buff, "id", None) not in EFFECTS:
            continue
        if buff.required_tags and not any(tag in action_tags for tag in buff.required_tags):
            continue
        if buff.consume_charge():
            target_expired_debuffs.append(effect_key)

    target.cleanup_expired_effects(target_expired_debuffs)

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


def damage_taken_multiplier(target, tags, attack_type, damage_type) -> float:
    """Scales damage by parsed target modifiers such as the training dummy armor debuff."""
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
            if "damage_taken_scale_channel_" in stat:
                if channel and f"channel_{channel}_" in stat:
                    bonus += modifier.value
                continue
            if "damage_taken_scale_type_" in stat:
                if type_name and f"type_{type_name}_" in stat:
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