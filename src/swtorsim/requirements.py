from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from entities import Player, Target

def check_target_hp(conditions, caster: "Player", target: "Target") -> bool:
    if isinstance(conditions, dict):
        threshold = conditions.get("pct", 1.0)
        bypass_buffs = conditions.get("bypass_if_buff_active", None)
    else:
        threshold = conditions
        bypass_buffs = None
    if target.hp_ratio <= threshold:
        return True
    if bypass_buffs and check_caster_buff(bypass_buffs, caster, target):
        return True
    return False

def check_caster_buff(conditions: Any, caster: "Player", target: "Target") -> bool:
    buff_list = [conditions] if isinstance(conditions, str) else conditions
    return any(caster.has_buff(b) for b in buff_list)

def check_target_debuff(conditions: Any, caster: "Player", target: "Target") -> bool:
    debuff_list = [conditions] if isinstance(conditions, str) else conditions
    return any(target.has_debuff(d) for d in debuff_list)

def check_exact_dot_amount(conditions: int, caster: "Player", target: "Target") -> bool:
    return target.count_active_dots == conditions

def check_has_any_dot(conditions: bool, caster: "Player", target: "Target") -> bool:
    return (target.count_active_dots > 0) is conditions

def inverse_check_target_debuff(conditions: Any, caster: "Player", target: "Target") -> bool:
    return not check_target_debuff(conditions, caster, target)

def has_specific_dot(conditions: Any, caster: "Player", target: "Target") -> bool:
    dot_list = [conditions] if isinstance(conditions, str) else conditions
    return any(target.has_dot(d) for d in dot_list)

CONDITION_REGISTRY = {
    "target_hp_below_pct": check_target_hp,
    "target_has_debuff": check_target_debuff,
    "caster_has_buff": check_caster_buff,
    "exact_dot_amount": check_exact_dot_amount,
    "has_dot": check_has_any_dot,
    "target_doesnt_have_debuff": inverse_check_target_debuff,
    "has_specific_dot": has_specific_dot
}

def validate_all(requirements: dict[str, Any], caster: "Player", target: "Target") -> bool:
    if not requirements:
        return True
    for key, value in requirements.items():
        validator_func = CONDITION_REGISTRY.get(key)
        if validator_func:
            if not validator_func(value, caster, target):
                return False
        else:
            raise KeyError(
                f"\n This requirement doesn't exist/isn't implemented: '{key}'\n"
                f"Please check your ability/proc JSON configuration files.\n"
                f"Implemented requirements are: {list(CONDITION_REGISTRY.keys())}\n"
                f"Contact me if you think yours should be here too")
    return True

