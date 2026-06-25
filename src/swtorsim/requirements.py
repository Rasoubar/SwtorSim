from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from entities import Player, Target

def check_target_hp(conditions, caster: "Player", target: "Target",**kwargs) -> bool:
    if isinstance(conditions, dict):
        threshold = conditions.get("pct", 0.3)
        bypass_buffs = conditions.get("bypass_if_buff_active", None)
    else:
        threshold = conditions
        bypass_buffs = None
    if target.hp_ratio <= threshold:
        return True
    if bypass_buffs and check_caster_buff(bypass_buffs, caster, target):
        return True
    return False

def check_caster_buff(conditions: Any, caster: "Player", target: "Target",**kwargs) -> bool:
    buff_list = [conditions] if isinstance(conditions, str) else conditions
    return any(caster.has_buff(b) for b in buff_list)

def check_target_debuff(conditions: Any, caster: "Player", target: "Target",**kwargs) -> bool:
    debuff_list = [conditions] if isinstance(conditions, str) else conditions
    return any(target.has_debuff(d) for d in debuff_list)

def check_exact_dot_amount(conditions: int, caster: "Player", target: "Target",**kwargs) -> bool:
    return target.count_active_dots == conditions

def check_has_any_dot(conditions: bool, caster: "Player", target: "Target",**kwargs) -> bool:
    return (target.count_active_dots > 0) is conditions

def inverse_check_target_debuff(conditions: Any, caster: "Player", target: "Target", **kwargs) -> bool:
    return not check_target_debuff(conditions, caster, target, **kwargs)

def has_specific_dot(conditions: Any, caster: "Player", target: "Target",**kwargs) -> bool:
    dot_list = [conditions] if isinstance(conditions, str) else conditions
    return any(target.has_dot(d) for d in dot_list)

def check_caster_energy_above(threshold: int, caster: "Player", target: "Target",**kwargs) -> bool:
    return caster.resource.current_value >= threshold

def check_dot_absent(dot_name: str, caster: "Player", target: "Target", **kwargs) -> bool:
    return dot_name not in target.dots

def check_caster_energy_below(threshold: int, caster: "Player", target: "Target", **kwargs) -> bool:
    return caster.resource.current_value < threshold

def check_proc_cooldown_above(data: dict, caster: "Player", target: "Target",sim) -> bool:
    proc = caster.procs.get(data["name"])
    remaining_cooldown = proc.next_possible_proc - sim.current_time

    return remaining_cooldown > data["value"]

def check_target_hp_above(threshold: float, caster: "Player", target: "Target", **kwargs) -> bool:
    return target.hp_ratio > threshold


def check_caster_does_not_have_buff(conditions: Any, caster: "Player", target: "Target", **kwargs) -> bool:
    buff_list = [conditions] if isinstance(conditions, str) else conditions
    has_any_buff = any(caster.has_buff(b) for b in buff_list)
    return not has_any_buff

CONDITION_REGISTRY = {
    "target_hp_below_pct": check_target_hp,
    "target_has_debuff": check_target_debuff,
    "caster_has_buff": check_caster_buff,
    "exact_dot_amount": check_exact_dot_amount,
    "has_dot": check_has_any_dot,
    "target_doesnt_have_debuff": inverse_check_target_debuff,
    "has_specific_dot": has_specific_dot,
    "caster_energy_above": check_caster_energy_above,
    "caster_energy_below": check_caster_energy_below,
    "dot_absent": check_dot_absent,
    "target_hp_above_pct": check_target_hp_above,
    "proc_cooldown_above": check_proc_cooldown_above,
    "caster_does_not_have_buff": check_caster_does_not_have_buff
}

def validate_all(requirements: dict[str, Any], caster: "Player", target: "Target", sim = None) -> bool:
    if not requirements:
        return True
    for key, value in requirements.items():
        validator_func = CONDITION_REGISTRY.get(key)
        if validator_func:
            if not validator_func(value, caster, target,sim=sim):
                return False
        else:
            raise KeyError(
                f"\n This requirement doesn't exist/isn't implemented: '{key}'\n"
                f"Please check your ability/proc JSON configuration files.\n"
                f"Implemented requirements are: {list(CONDITION_REGISTRY.keys())}\n"
                f"Contact me if you think yours should be here too")
    return True

