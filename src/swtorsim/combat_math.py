"""Core SWTOR combat math: base damage, mitigation, verified empirical damage buckets, accuracy, and critical hits."""

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

    if action_data.get("record_audit"):
        action_data["_audit"] = {
            "base_damage": round(base_damage, 2),
            "post_mit_damage": round(post_mit_damage, 2),
            "post_mod_damage": round(post_mod_damage, 2),
            "total_multiplier": round(modifiers.get('total_multiplier', 1.0), 4),
            "buckets": {k: round(v, 4) for k, v in modifiers.get('_buckets', {}).items()} if '_buckets' in modifiers else {},
            "bonus_crit_chance": round(modifiers.get('bonus_crit_chance', 0.0), 4),
            "bonus_crit_modifier": round(modifiers.get('bonus_crit_modifier', 0.0), 4),
            "bonus_armor_pen": round(modifiers.get('bonus_armor_pen', 0.0), 4),
        }

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
        'dual_wield_damage_modifier': 0.0,

        'total_multiplier': 1.0
    }

    #modify the modifiers with applicable target and caster buffs/debuffs
    action_tags = frozenset(action_data.get("tags") or ())
    ability_fqn = action_data.get("ability_fqn")
    attack_type = action_data.get("attack_type", 1)
    hand = action_data.get("hand", "main")
    if damage_type is None:
        damage_type = action_data.get("resolved_damage_type") or action_data.get("damage_type", 1)

    handle_caster_buffs(caster, target, action_tags, ability_fqn, attack_type, damage_type, buckets, modifiers, hand=hand)
    handle_target_debuffs(target, action_tags, ability_fqn, attack_type, damage_type, buckets, modifiers, caster=caster)

    if action_data.get("record_audit"):
        modifiers['_buckets'] = {k: 1.0 + v for k, v in buckets.items()}
    for bucket_value in buckets.values():
        modifiers['total_multiplier'] *= (1.0 + bucket_value)

    return modifiers


def _add_to_bucket(buckets: dict, bucket_key: Optional[str], val: float, stat_identifier: str = "", context_desc: str = ""):
    """Adds a modifier value to its assigned bucket. Raises RuntimeError if unpredicted/unassigned."""
    if not bucket_key:
        raise RuntimeError(
            f"[FATAL: UNPREDICTED DAMAGE MODIFIER] Stat '{stat_identifier}' (value: {val}) "
            f"encountered in {context_desc} has no verified bucket assignment! "
            f"Empirically verify its bucketing layer before running simulations."
        )
    buckets[bucket_key] = buckets.get(bucket_key, 0.0) + val


# Verified Multiplicative Damage Buckets
BUCKET_1 = "bucket_1"  # Test 1: STAT_cbt_damage_done_modifier_percentage (79), Test 2: Vulnerable (386), Assailable (376), Test 6: Beat Down (384), Test 8: Assailable Elemental (370), Susceptible (388), Test 9: Marked (382), Test 11: Caster Channel Dealt Scale Melee (407), Test 13: Caster Type Dealt Scale Energy/Kinetic (395, 397), Test 15: Caster Channel Dealt Scale Force (409)
BUCKET_2 = "bucket_2"  # Test 3: Target damage received percentage / Overwhelmed AoE vulnerability (46)
BUCKET_3 = "bucket_3"  # Test 4: Low-health execute (220 Inevitable Demise)
BUCKET_4 = "bucket_4"  # Test 7: Target state accuracy reduced conditional (389 Torment)
BUCKET_5 = "bucket_5"  # Test 12 & 14: Target state bleeding (221 Bloodbath / Blood Tracker)
BUCKET_6 = "bucket_6"  # Test 16: Target state on fire / burning (250 Burning Storm)

# 1. Caster Offensive Damage Dispatch Table: (bucket_key, filter_fn)
# Governs outgoing damage-done / damage-dealt buffs on the attacker (caster.effects).
# Strictly ordered by numeric GOM Stat ID.
_CASTER_DAMAGE_DISPATCH = {
    # Stat 78: STAT_cbt_damage_done_modifier_fixed (Verified no-op in percentage bucketing; Test 17: Pull and Pummel)
    "78": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: False),
    "STAT_cbt_damage_done_modifier_fixed": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: False),

    # Stat 79: STAT_cbt_damage_done_modifier_percentage (Base / General Damage Done; Test 1)
    "79": (BUCKET_1, None),
    "STAT_cbt_damage_done_modifier_percentage": (BUCKET_1, None),

    # Stat 220: STAT_cbt_damage_done_if_target_health_low_modifier_percentage (Execute sub-30%; Test 4)
    "220": (
        BUCKET_3,
        lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: getattr(target, "hp_ratio", 1.0) <= 0.30,
    ),
    "STAT_cbt_damage_done_if_target_health_low_modifier_percentage": (
        BUCKET_3,
        lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: getattr(target, "hp_ratio", 1.0) <= 0.30,
    ),

    # Stat 221: STAT_cbt_damage_done_if_target_bleeding_modifier_percentage (Conditional Bleeding; Test 12 & 14)
    "221": (
        BUCKET_5,
        lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _entity_has_tag(target, "bleed"),
    ),
    "STAT_cbt_damage_done_if_target_bleeding_modifier_percentage": (
        BUCKET_5,
        lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _entity_has_tag(target, "bleed"),
    ),

    # Stat 222: STAT_cbt_damage_done_if_target_stunned_modifier_percentage
    "222": (
        None,
        lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _entity_has_tag(target, "stun") or _entity_has_tag(target, "incapacitate"),
    ),
    "STAT_cbt_damage_done_if_target_stunned_modifier_percentage": (
        None,
        lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _entity_has_tag(target, "stun") or _entity_has_tag(target, "incapacitate"),
    ),

    # Stat 250: STAT_cbt_damage_done_if_target_on_fire_modifier_percentage (Conditional Burning/Fire; Test 16)
    "250": (
        BUCKET_6,
        lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _entity_has_tag(target, "burn") or _entity_has_tag(target, "fire"),
    ),
    "STAT_cbt_damage_done_if_target_on_fire_modifier_percentage": (
        BUCKET_6,
        lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _entity_has_tag(target, "burn") or _entity_has_tag(target, "fire"),
    ),

    # Stat 389: STAT_cbt_damage_done_if_target_accuracy_reduced_modifier_percentage (Conditional Accuracy Reduced; Test 7)
    "389": (
        BUCKET_4,
        lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _entity_has_tag(target, "accuracy_reduced"),
    ),
    "STAT_cbt_damage_done_if_target_accuracy_reduced_modifier_percentage": (
        BUCKET_4,
        lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _entity_has_tag(target, "accuracy_reduced"),
    ),

    # Stat 393: stat_cbt_damage_dealt_scale_type_elemental_modifier_percentage
    "393": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 3),
    "stat_cbt_damage_dealt_scale_type_elemental_modifier_percentage": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 3),

    # Stat 395: stat_cbt_damage_dealt_scale_type_energy_modifier_percentage (Energy Type Dealt; Test 13)
    "395": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 2),
    "stat_cbt_damage_dealt_scale_type_energy_modifier_percentage": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 2),

    # Stat 397: stat_cbt_damage_dealt_scale_type_kinetic_modifier_percentage (Kinetic Type Dealt; Test 13)
    "397": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 1),
    "stat_cbt_damage_dealt_scale_type_kinetic_modifier_percentage": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 1),

    # Stat 399: stat_cbt_damage_dealt_scale_type_internal_modifier_percentage
    "399": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 4),
    "stat_cbt_damage_dealt_scale_type_internal_modifier_percentage": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 4),

    # Stat 405: stat_cbt_damage_dealt_scale_channel_ranged_modifier_percentage
    "405": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_r),
    "stat_cbt_damage_dealt_scale_channel_ranged_modifier_percentage": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_r),
    "stat_cbt_damage_dealt_scale_channel_ranged": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_r),

    # Stat 406: stat_cbt_damage_dealt_scale_channel_ranged_modifier_fixed
    "406": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_r),
    "stat_cbt_damage_dealt_scale_channel_ranged_modifier_fixed": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_r),

    # Stat 407: stat_cbt_damage_dealt_scale_channel_melee_modifier_percentage (Melee Channel Dealt; Test 11)
    "407": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m),
    "stat_cbt_damage_dealt_scale_channel_melee_modifier_percentage": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m),
    "stat_cbt_damage_dealt_scale_channel_melee": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m),

    # Stat 408: stat_cbt_damage_dealt_scale_channel_melee_modifier_fixed
    "408": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m),
    "stat_cbt_damage_dealt_scale_channel_melee_modifier_fixed": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m),

    # Stat 409: stat_cbt_damage_dealt_scale_channel_force_modifier_percentage (Force Channel Dealt; Test 15)
    "409": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),
    "stat_cbt_damage_dealt_scale_channel_force_modifier_percentage": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),
    "stat_cbt_damage_dealt_scale_channel_force": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),

    # Stat 410: stat_cbt_damage_dealt_scale_channel_force_modifier_fixed
    "410": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),
    "stat_cbt_damage_dealt_scale_channel_force_modifier_fixed": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),

    # Stat 411: stat_cbt_damage_dealt_scale_channel_tech_modifier_percentage
    "411": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),
    "stat_cbt_damage_dealt_scale_channel_tech_modifier_percentage": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),
    "stat_cbt_damage_dealt_scale_channel_tech": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),

    # Stat 412: stat_cbt_damage_dealt_scale_channel_tech_modifier_fixed
    "412": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),
    "stat_cbt_damage_dealt_scale_channel_tech_modifier_fixed": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),

    # Stat 449: stat_cbt_tech_damage_dealt_modifier
    "449": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),
    "stat_cbt_tech_damage_dealt_modifier": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),

    # Stat 450: stat_cbt_weapon_damage_dealt_modifier
    "450": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m or is_r),
    "stat_cbt_weapon_damage_dealt_modifier": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m or is_r),

    # Stat 451: stat_cbt_force_damage_dealt_modifier
    "451": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),
    "stat_cbt_force_damage_dealt_modifier": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),

    # Stat 454: stat_cbt_aoe_damage_dealt_modifier
    "454": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _hit_is_aoe(tags)),
    "stat_cbt_aoe_damage_dealt_modifier": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _hit_is_aoe(tags)),

    # Stat 462: stat_cbt_damage_dealt_scale_channel_weapon_modifier
    "462": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m or is_r),
    "stat_cbt_damage_dealt_scale_channel_weapon_modifier": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m or is_r),

    # Stat 464: stat_cbt_damage_dealt_scale_tag_aoe_modifier
    "464": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _hit_is_aoe(tags)),
    "stat_cbt_damage_dealt_scale_tag_aoe_modifier": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _hit_is_aoe(tags)),

    # Stat 466: stat_cbt_damage_dealt_scale_tag_dot_modifier
    "466": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: any("dot" in str(t).lower() or "periodic" in str(t).lower() for t in tags)),
    "stat_cbt_damage_dealt_scale_tag_dot_modifier": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: any("dot" in str(t).lower() or "periodic" in str(t).lower() for t in tags)),
}

# 2. Target Vulnerability Damage Dispatch Table: (bucket_key, filter_fn)
# Governs incoming damage-received / damage-taken debuffs on the victim (target.effects).
# Strictly ordered by numeric GOM Stat ID.
_TARGET_DAMAGE_DISPATCH = {
    # Stat 46: STAT_cbt_damage_received_modifier_percentage (Damage Received / Overwhelmed AoE; Test 3)
    "46": (BUCKET_2, None),
    "STAT_cbt_damage_received_modifier_percentage": (BUCKET_2, None),

    # Stat 47: STAT_cbt_damage_received_modifier_fixed
    "47": (None, None),
    "STAT_cbt_damage_received_modifier_fixed": (None, None),

    # Stat 223: STAT_cbt_damage_received_if_target_stunned_modifier_percentage
    "223": (
        None,
        lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _entity_has_tag(target, "stun") or _entity_has_tag(target, "incapacitate"),
    ),
    "STAT_cbt_damage_received_if_target_stunned_modifier_percentage": (
        None,
        lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _entity_has_tag(target, "stun") or _entity_has_tag(target, "incapacitate"),
    ),

    # Stat 369: stat_cbt_damage_taken_scale_type_elemental_modifier_fixed
    "369": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 3),
    "stat_cbt_damage_taken_scale_type_elemental_modifier_fixed": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 3),

    # Stat 370: stat_cbt_damage_taken_scale_type_elemental_modifier_percentage (Assailable Elemental; Test 8)
    "370": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 3),
    "stat_cbt_damage_taken_scale_type_elemental_modifier_percentage": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 3),

    # Stat 371: stat_cbt_damage_taken_scale_type_energy_modifier_fixed
    "371": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 2),
    "stat_cbt_damage_taken_scale_type_energy_modifier_fixed": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 2),

    # Stat 372: stat_cbt_damage_taken_scale_type_energy_modifier_percentage
    "372": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 2),
    "stat_cbt_damage_taken_scale_type_energy_modifier_percentage": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 2),

    # Stat 373: stat_cbt_damage_taken_scale_type_kinetic_modifier_fixed
    "373": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 1),
    "stat_cbt_damage_taken_scale_type_kinetic_modifier_fixed": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 1),

    # Stat 374: stat_cbt_damage_taken_scale_type_kinetic_modifier_percentage
    "374": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 1),
    "stat_cbt_damage_taken_scale_type_kinetic_modifier_percentage": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 1),

    # Stat 375: stat_cbt_damage_taken_scale_type_internal_modifier_fixed
    "375": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 4),
    "stat_cbt_damage_taken_scale_type_internal_modifier_fixed": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 4),

    # Stat 376: stat_cbt_damage_taken_scale_type_internal_modifier_percentage (Assailable Internal; Test 2)
    "376": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 4),
    "stat_cbt_damage_taken_scale_type_internal_modifier_percentage": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: dmg_type == 4),

    # Stat 381: stat_cbt_damage_taken_scale_channel_ranged_modifier_fixed
    "381": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_r),
    "stat_cbt_damage_taken_scale_channel_ranged_modifier_fixed": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_r),

    # Stat 382: stat_cbt_damage_taken_scale_channel_ranged_modifier_percentage (Marked Ranged; Test 9)
    "382": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_r),
    "stat_cbt_damage_taken_scale_channel_ranged_modifier_percentage": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_r),

    # Stat 383: stat_cbt_damage_taken_scale_channel_melee_modifier_fixed
    "383": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m),
    "stat_cbt_damage_taken_scale_channel_melee_modifier_fixed": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m),

    # Stat 384: stat_cbt_damage_taken_scale_channel_melee_modifier_percentage (Beat Down Melee; Test 6)
    "384": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m),
    "stat_cbt_damage_taken_scale_channel_melee_modifier_percentage": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m),

    # Stat 385: stat_cbt_damage_taken_scale_channel_force_modifier_fixed
    "385": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),
    "stat_cbt_damage_taken_scale_channel_force_modifier_fixed": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),

    # Stat 386: stat_cbt_damage_taken_scale_channel_force_modifier_percentage (Vulnerable Force; Test 2)
    "386": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),
    "stat_cbt_damage_taken_scale_channel_force_modifier_percentage": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),

    # Stat 387: stat_cbt_damage_taken_scale_channel_tech_modifier_fixed
    "387": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),
    "stat_cbt_damage_taken_scale_channel_tech_modifier_fixed": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),

    # Stat 388: stat_cbt_damage_taken_scale_channel_tech_modifier_percentage (Susceptible Tech; Test 8)
    "388": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),
    "stat_cbt_damage_taken_scale_channel_tech_modifier_percentage": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),

    # Stat 456: stat_cbt_force_damage_taken_modifier
    "456": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),
    "stat_cbt_force_damage_taken_modifier": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_f),

    # Stat 457: stat_cbt_dot_amount_taken_modifier
    "457": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: any("dot" in str(t).lower() or "periodic" in str(t).lower() for t in tags)),
    "stat_cbt_dot_amount_taken_modifier": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: any("dot" in str(t).lower() or "periodic" in str(t).lower() for t in tags)),

    # Stat 458: stat_cbt_weapon_damage_taken_modifier
    "458": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m or is_r),
    "stat_cbt_weapon_damage_taken_modifier": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m or is_r),

    # Stat 459: stat_cbt_tech_damage_taken_modifier
    "459": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),
    "stat_cbt_tech_damage_taken_modifier": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_t),

    # Stat 460: stat_cbt_aoe_damage_taken_modifier
    "460": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _hit_is_aoe(tags)),
    "stat_cbt_aoe_damage_taken_modifier": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _hit_is_aoe(tags)),

    # Stat 463: stat_cbt_damage_taken_scale_channel_weapon_modifier
    "463": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m or is_r),
    "stat_cbt_damage_taken_scale_channel_weapon_modifier": (BUCKET_1, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: is_m or is_r),

    # Stat 465: stat_cbt_damage_taken_scale_tag_aoe_modifier
    "465": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _hit_is_aoe(tags)),
    "stat_cbt_damage_taken_scale_tag_aoe_modifier": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: _hit_is_aoe(tags)),

    # Stat 467: stat_cbt_damage_taken_scale_tag_dot_modifier
    "467": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: any("dot" in str(t).lower() or "periodic" in str(t).lower() for t in tags)),
    "stat_cbt_damage_taken_scale_tag_dot_modifier": (None, lambda target, is_m, is_r, is_f, is_t, dmg_type, tags, caster: any("dot" in str(t).lower() or "periodic" in str(t).lower() for t in tags)),
}

# 3. Critical Chance Dispatch Table
# Strictly ordered by numeric GOM Stat ID.
_CRIT_CHANCE_DISPATCH = {
    # Stat 116: Melee Critical Chance
    "116": lambda is_m, is_r, is_f, is_t: is_m,
    "STAT_cbt_melee_critical_chance": lambda is_m, is_r, is_f, is_t: is_m,

    # Stat 122: Ranged Critical Chance
    "122": lambda is_m, is_r, is_f, is_t: is_r,
    "STAT_cbt_ranged_critical_chance": lambda is_m, is_r, is_f, is_t: is_r,

    # Stat 133: Force Critical Chance
    "133": lambda is_m, is_r, is_f, is_t: is_f,
    "STAT_cbt_force_critical_chance": lambda is_m, is_r, is_f, is_t: is_f,

    # Stat 135: Tech Critical Chance
    "135": lambda is_m, is_r, is_f, is_t: is_t,
    "STAT_cbt_tech_critical_chance": lambda is_m, is_r, is_f, is_t: is_t,

    # Generic Critical Chance
    "Critical Chance": lambda is_m, is_r, is_f, is_t: True,
}

# 4. Critical Damage Dispatch Table
# Strictly ordered by numeric GOM Stat ID.
_CRIT_DAMAGE_DISPATCH = {
    # Stat 117: Melee Critical Damage
    "117": lambda is_m, is_r, is_f, is_t: is_m,
    "STAT_cbt_melee_critical_damage": lambda is_m, is_r, is_f, is_t: is_m,

    # Stat 123: Ranged Critical Damage
    "123": lambda is_m, is_r, is_f, is_t: is_r,
    "STAT_cbt_ranged_critical_damage": lambda is_m, is_r, is_f, is_t: is_r,

    # Stat 134: Force Critical Damage
    "134": lambda is_m, is_r, is_f, is_t: is_f,
    "STAT_cbt_force_critical_damage": lambda is_m, is_r, is_f, is_t: is_f,

    # Stat 136: Tech Critical Damage
    "136": lambda is_m, is_r, is_f, is_t: is_t,
    "STAT_cbt_tech_critical_damage": lambda is_m, is_r, is_f, is_t: is_t,

    # Generic Critical Damage
    "Critical Damage": lambda is_m, is_r, is_f, is_t: True,
}

_SKIP_BASE_STATS = frozenset({
    "STAT_att_mastery", "414", "4140",
    "STAT_rtg_attack_power", "155", "STAT_att_power",
    "STAT_rtg_crit", "156", "STAT_rtg_critical_chance",
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
    "STAT_cbt_armor_penetration", "166",
    "STAT_att_endurance",
    "STAT_cbt_tech_energy_max", "9",
    "STAT_cbt_force_force_max", "10",
    "STAT_cbtStealthEffectiveLevel",
})


def handle_caster_buffs(caster, target, action_tags, ability_fqn, attack_type, damage_type, buckets, modifiers, hand: str = "main"):
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
                    _add_to_bucket(buckets, bucket_key, val, stat_identifier=stat, context_desc=f"Caster Buff '{buff.name}'")
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

            # 6. Dual Wield Damage Done Modifier (Stat 127) - modifies off-hand weapon damage scalar (0.30 + val)
            if stat in ("STAT_cbt_dual_wield_damage_done_modifier_percentage", "127"):
                if hand == "off":
                    modifiers['dual_wield_damage_modifier'] = modifiers.get('dual_wield_damage_modifier', 0.0) + val
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
    """Maps an numeric attack_type (1..4) to its canonical channel name ('melee', 'ranged', 'force', 'tech')."""
    return _ATTACK_TYPE_CHANNELS.get(attack_type)


def _hit_is_aoe(tags) -> bool:
    """Returns True if any tag on the hit marks it as an Area-of-Effect (AoE) ability."""
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
            if stat in ("STAT_rtg_armor", "48"):
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

            # Check ability FQN / tags matching (including AoE tag equivalence for Overwhelmed)
            if not (
                not mod.targets
                or mod.applies_to(ability_fqn=ability_fqn, ability_tags=action_tags)
                or (aoe and any(str(tt).endswith("is_aoe") for tt in mod.targets))
            ):
                continue

            # 1. Target Damage Vulnerability Buckets (Table Dispatch)
            entry = _TARGET_DAMAGE_DISPATCH.get(stat)
            if entry is not None:
                bucket_key, filter_fn = entry
                if filter_fn is None or filter_fn(target, is_melee, is_ranged, is_force, is_tech, damage_type, action_tags, caster):
                    _add_to_bucket(buckets, bucket_key, val, stat_identifier=stat, context_desc=f"Target Debuff '{debuff.name}'")
                continue

            # 2. Target Critical Chance Modifiers (Table Dispatch)
            crit_fn = _CRIT_CHANCE_DISPATCH.get(stat)
            if crit_fn is not None:
                if crit_fn(is_melee, is_ranged, is_force, is_tech):
                    modifiers['bonus_crit_chance'] += val
                continue


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
            dual_wield_mod = 0.0
            if modifiers is not None and "dual_wield_damage_modifier" in modifiers:
                dual_wield_mod = modifiers["dual_wield_damage_modifier"]
            elif caster is not None and hasattr(caster, "effects"):
                for eff in caster.effects.values():
                    if getattr(eff, "is_expired", False):
                        continue
                    getter = getattr(eff, "get_effective_modifiers", None)
                    eff_mods = getter() if getter is not None else getattr(eff, "modifiers", [])
                    for mod in eff_mods:
                        if str(mod.stat) in ("STAT_cbt_dual_wield_damage_done_modifier_percentage", "127"):
                            dual_wield_mod += float(mod.value)
            offhand_ratio = 0.30 + dual_wield_mod
            weapon_min = caster.stats.get("Off_hand_min", 0.0) * offhand_ratio * weapon_multiplier
            weapon_max = caster.stats.get("Off_hand_max", 0.0) * offhand_ratio * weapon_multiplier
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
    """
    is_melee = attack_type in (1, "melee", "Melee")
    is_ranged = attack_type in (2, "ranged", "Ranged")
    is_force = attack_type in (3, "force", "Force")
    is_tech = attack_type in (4, "tech", "Tech")

    if hand == "off":
        base_acc = source.stats.get("Off Accuracy", 0.67)
    elif is_force:
        base_acc = source.stats.get("Force Accuracy", source.stats.get("Main Accuracy", 1.0))
    elif is_tech:
        base_acc = source.stats.get("Tech Accuracy", source.stats.get("Main Accuracy", 1.0))
    elif is_ranged:
        base_acc = source.stats.get("Ranged Accuracy", source.stats.get("Main Accuracy", 1.0))
    else:
        base_acc = source.stats.get("Melee Accuracy", source.stats.get("Main Accuracy", 1.0))

    if target is not None and hasattr(target, "stats"):
        if is_force or is_tech:
            def_chance = target.stats.get("Resistance", target.stats.get("Defense Chance", 0.10))
        else:
            def_chance = target.stats.get("Defense Chance", 0.10)
    else:
        def_chance = 0.10

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

                if not mod.targets and stat in _SKIP_BASE_STATS:
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
                    if hand == "off":
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
