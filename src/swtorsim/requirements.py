import random
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from entities import Player, Dummy

def _to_list(val: Any) -> list:
    """Helper to convert single string/item conditions into an iterable list."""
    return [val] if isinstance(val, str) else val

def check_target_hp(conditions, caster: "Player", target: "Dummy", **_kwargs) -> bool:
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

def check_caster_buff(conditions: Any, caster: "Player", _target: "Dummy", **_kwargs) -> bool:
    return any(caster.has_effect(b) for b in _to_list(conditions))

def check_target_debuff(conditions: Any, _caster: "Player", target: "Dummy", **_kwargs) -> bool:
    return any(target.has_effect(d) for d in _to_list(conditions))

def inverse_check_target_debuff(conditions: Any, caster: "Player", target: "Dummy", **kwargs) -> bool:
    return not check_target_debuff(conditions, caster, target, **kwargs)

def check_caster_energy_above(threshold: int, caster: "Player", _target: "Dummy", **_kwargs) -> bool:
    return caster.resource.current_value >= threshold

def check_caster_energy_below(threshold: int, caster: "Player", _target: "Dummy", **_kwargs) -> bool:
    return caster.resource.current_value < threshold

def check_proc_cooldown_above(data: dict, caster: "Player", _target: "Dummy", sim, **_kwargs) -> bool:
    name = data["name"]
    if caster.has_effect(name):
        return False

    current_time = sim.current_time if sim is not None else 0.0
    remaining_cooldown = 0.0
    proc = getattr(caster, "procs", {}).get(name)
    if proc is not None and hasattr(proc, "next_possible_proc"):
        remaining_cooldown = max(0.0, proc.next_possible_proc - current_time)
    else:
        for eff in getattr(caster, "effects", {}).values():
            if getattr(eff, "is_expired", False):
                continue
            if getattr(eff, "name", None) == name and any("lockout" in t for t in getattr(eff, "tags", ())):
                if getattr(eff, "expires_at", None) is not None:
                    remaining_cooldown = max(remaining_cooldown, eff.expires_at - current_time)

    return remaining_cooldown > data["value"]

def check_target_hp_above(threshold: float, _caster: "Player", target: "Dummy", **_kwargs) -> bool:
    return target.hp_ratio > threshold

def check_caster_does_not_have_buff(conditions: Any, caster: "Player", _target: "Dummy", **_kwargs) -> bool:
    buff_list = [conditions] if isinstance(conditions, str) else conditions
    has_any_buff = any(caster.has_effect(b) for b in buff_list)
    return not has_any_buff

def check_ability_cooldown_under(data: dict, caster: "Player", _target: "Dummy", sim, **_kwargs) -> bool:
    cooldown = caster.cooldowns.get(data["name"], 0)
    remaining_cooldown = cooldown - sim.current_time

    return remaining_cooldown < data["value"]


def compare_values(actual: float, comparison: str, expected: float) -> bool:
    """Evaluates comparison operators used in extracted game data and rotation rules."""
    if comparison in ("lte", "<="):
        return actual <= expected
    elif comparison in ("gte", ">="):
        return actual >= expected
    elif comparison in ("lt", "<"):
        return actual < expected
    elif comparison in ("gt", ">"):
        return actual > expected
    elif comparison in ("eq", "==", "="):
        return actual == expected
    return True


def entity_has_effect(entity, tags: list[str] | None = None, ability_spec: str | None = None, count: int = 1) -> bool:
    """Checks whether an entity has an active effect or dot matching tags or an ability spec."""
    if not entity:
        return False

    effects = getattr(entity, "effects", {})
    tags_set = set(tags) if tags else set()

    for eff in effects.values():
        eff_tags = set(getattr(eff, "tags", []) or getattr(eff, "required_tags", []) or [])
        eff_name = getattr(eff, "name", "") or getattr(eff, "effect_name", "")
        eff_fqn = getattr(eff, "fqn", "") or getattr(eff, "source_ability", "")
        stacks = getattr(eff, "stacks", None) or getattr(eff, "charges", 1) or 1

        matches = False
        if tags_set and (tags_set & eff_tags):
            matches = True
        if ability_spec and ability_spec in (eff_fqn, eff_name):
            matches = True

        if matches and stacks >= count:
            return True

    # Also check active dots on dummy targets
    dots = getattr(entity, "dots", {})
    for dot_name, dot in dots.items():
        if ability_spec and ability_spec == dot_name:
            return True
        dot_tags = set(getattr(dot, "tags", []) or [])
        if tags_set and (tags_set & dot_tags):
            return True

    return False


def get_entity_effect_stacks(entity, tags: list[str] | None = None, ability_spec: str | None = None) -> int:
    """Returns the current stack/charge count of an active effect or dot matching tags or ability spec."""
    if not entity:
        return 0

    effects = getattr(entity, "effects", {})
    tags_set = set(tags) if tags else set()

    best_stacks = 0
    found = False

    for eff in effects.values():
        if getattr(eff, "is_expired", False):
            continue
        eff_tags = set(getattr(eff, "tags", []) or getattr(eff, "required_tags", []) or [])
        eff_name = getattr(eff, "name", "") or getattr(eff, "effect_name", "")
        eff_fqn = getattr(eff, "fqn", "") or getattr(eff, "source_ability", "")

        matches = False
        if tags_set and (tags_set & eff_tags):
            matches = True
        if ability_spec and ability_spec in (eff_fqn, eff_name):
            matches = True

        if matches:
            st = int(getattr(eff, "stacks", None) or getattr(eff, "charges", 1) or 1)
            best_stacks = max(best_stacks, st)
            found = True

    # Also check active dots on dummy targets
    dots = getattr(entity, "dots", {})
    for dot_name, dot in dots.items():
        if getattr(dot, "is_expired", False):
            continue
        if ability_spec and ability_spec == dot_name:
            st = int(getattr(dot, "stacks", 1) or 1)
            best_stacks = max(best_stacks, st)
            found = True
        dot_tags = set(getattr(dot, "tags", []) or [])
        if tags_set and (tags_set & dot_tags):
            st = int(getattr(dot, "stacks", 1) or 1)
            best_stacks = max(best_stacks, st)
            found = True

    if found:
        return best_stacks
    return 0


def get_caster_buff_stacks(caster: "Player", buff_name: str | None = None, tags: list[str] | None = None) -> int:
    """Returns the current stack count of an active buff on the caster.

    Resolution order:
      1. Tag or ability specification match via get_entity_effect_stacks (takes highest stack across active instances).
      2. Direct lookup by key in caster.effects.
      3. Case-insensitive / normalized name or FQN match across active effects.
    Returns 0 if the effect is not active or expired.
    """
    if not caster or not hasattr(caster, "effects"):
        return 0

    best_stacks = 0
    found = False

    stacks = get_entity_effect_stacks(caster, tags=tags, ability_spec=buff_name)
    if stacks > 0:
        best_stacks = max(best_stacks, stacks)
        found = True

    if buff_name and buff_name in caster.effects:
        eff = caster.effects[buff_name]
        if not getattr(eff, "is_expired", False):
            st = int(getattr(eff, "stacks", None) or getattr(eff, "charges", 1) or 1)
            best_stacks = max(best_stacks, st)
            found = True

    if buff_name:
        target_norm = buff_name.strip().lower().replace("_", " ")
        for eff_key, eff in caster.effects.items():
            if getattr(eff, "is_expired", False):
                continue
            eff_name = getattr(eff, "name", "") or getattr(eff, "effect_name", "") or eff_key
            eff_fqn = getattr(eff, "fqn", "") or getattr(eff, "source_ability", "")
            if (
                target_norm == str(eff_name).strip().lower().replace("_", " ")
                or target_norm == str(eff_fqn).strip().lower().replace("_", " ")
                or target_norm == str(eff_key).strip().lower().replace("_", " ")
            ):
                st = int(getattr(eff, "stacks", None) or getattr(eff, "charges", 1) or 1)
                best_stacks = max(best_stacks, st)
                found = True

    return best_stacks if found else 0


def check_caster_buff_stacks(data: Any, caster: "Player", _target: "Dummy", **_kwargs) -> bool:
    """Validator for rotation rules checking a buff's stack count on the caster.

    Supported rule shapes in rotation configs:
      - dict:
          {"name": "Recklessness", "stacks": 2}
          {"name": "Recklessness", "count": 2, "comparison": "gte"}
          {"buff": "Recklessness", "stacks": 1, "comparison": "eq"}
          {"name": "Static Charge", "value": 3, "operator": ">="}
          {"tags": ["tag.abl.charges"], "stacks": 3}
      - list/tuple:
          ["Recklessness", 2]          (defaults to comparison >= 2)
          ["Recklessness", 2, "gte"]   (or 'eq', '==', '<=', etc.)
    """
    if isinstance(data, (list, tuple)):
        name = data[0] if len(data) > 0 else None
        expected_stacks = float(data[1]) if len(data) > 1 else 1.0
        comparison = data[2] if len(data) > 2 else "gte"
        tags = None
    elif isinstance(data, dict):
        name = data.get("name") or data.get("buff") or data.get("ability_spec")
        expected_stacks = float(data.get("stacks", data.get("count", data.get("value", data.get("charges", 1)))))
        comparison = data.get("comparison", data.get("operator", "gte"))
        tags = data.get("tags")
    else:
        return False

    actual_stacks = get_caster_buff_stacks(caster, buff_name=name, tags=tags)
    return compare_values(actual_stacks, comparison, expected_stacks)


def check_target_debuff_stacks(data: Any, _caster: "Player", target: "Dummy", **_kwargs) -> bool:
    """Validator for rotation rules checking a debuff or DoT stack count on the target."""
    if isinstance(data, (list, tuple)):
        name = data[0] if len(data) > 0 else None
        expected_stacks = float(data[1]) if len(data) > 1 else 1.0
        comparison = data[2] if len(data) > 2 else "gte"
        tags = None
    elif isinstance(data, dict):
        name = data.get("name") or data.get("debuff") or data.get("ability_spec")
        expected_stacks = float(data.get("stacks", data.get("count", data.get("value", 1))))
        comparison = data.get("comparison", data.get("operator", "gte"))
        tags = data.get("tags")
    else:
        return False

    actual_stacks = get_entity_effect_stacks(target, tags=tags, ability_spec=name)
    return compare_values(actual_stacks, comparison, expected_stacks)


CONDITION_REGISTRY = {
    "target_hp_below_pct": check_target_hp,
    "target_has_debuff": check_target_debuff,
    "caster_has_buff": check_caster_buff,
    "target_doesnt_have_debuff": inverse_check_target_debuff,
    "caster_energy_above": check_caster_energy_above,
    "caster_energy_below": check_caster_energy_below,
    "target_hp_above_pct": check_target_hp_above,
    "proc_cooldown_above": check_proc_cooldown_above,
    "caster_does_not_have_buff": check_caster_does_not_have_buff,
    "ability_cooldown_under": check_ability_cooldown_under,
    "caster_buff_stacks": check_caster_buff_stacks,
    "caster_has_buff_stacks": check_caster_buff_stacks,
    "caster_buff_charges": check_caster_buff_stacks,
    "target_debuff_stacks": check_target_debuff_stacks,
    "target_has_debuff_stacks": check_target_debuff_stacks,
}


def evaluate_single_extracted_condition(item: dict, caster: "Player", target: "Dummy", sim=None, context=None) -> bool:
    """Evaluates an individual atomic condition record from an extracted condition list."""
    cond_type = item.get("type")
    actor_str = item.get("actor")

    if actor_str == "target":
        actor = target
    elif actor_str == "caster":
        actor = caster
    elif actor_str == "trigger_target" and context and "target" in context:
        actor = context["target"]
    elif actor_str == "trigger_caster" and context and "caster" in context:
        actor = context["caster"]
    else:
        if cond_type == "is_creature_type" and target is not None and target is not caster:
            actor = target
        else:
            actor = caster

    res = True

    if cond_type == "has_ability":
        spec = item.get("ability_spec")
        comparison = item.get("comparison", "gte")
        expected_rank = item.get("ints", {}).get("rank", 1)
        has_it = False
        target_entity = actor if actor is not None else caster
        if hasattr(target_entity, "passive_blueprints") and spec in target_entity.passive_blueprints:
            has_it = True
        elif hasattr(target_entity, "passive_db") and spec in target_entity.passive_db:
            has_it = True
        elif hasattr(target_entity, "ability_db"):
            if spec in target_entity.ability_db or (isinstance(spec, str) and spec.lower().replace(" ", "_") in target_entity.ability_db):
                has_it = True
            elif isinstance(spec, str):
                from src.swtorsim.settings import is_stem_matching_enabled
                if is_stem_matching_enabled():
                    base_stem = spec.split(".")[-1]
                    if any(getattr(a, "fqn", "").endswith(f".{base_stem}_plus") for a in target_entity.ability_db.values()):
                        has_it = True
        if not has_it:
            res = False
        else:
            actual_rank = 1
            res = compare_values(actual_rank, comparison, expected_rank)

    elif cond_type == "has_effect":
        tags = item.get("tags")
        spec = item.get("ability_spec")
        count = item.get("count", 1)
        res = entity_has_effect(actor, tags=tags, ability_spec=spec, count=count)

    elif cond_type == "if_toughness":
        expected = item.get("ints", {}).get("toughness", 3)
        comparison = item.get("comparison", "lte")
        actual = getattr(actor, "toughness", 5 if getattr(actor, "max_hp", 0) > 0 else 1)
        res = compare_values(actual, comparison, expected)

    elif cond_type == "if_health":
        floats = item.get("floats", {})
        threshold = floats.get("health_percent", 0.0)
        comparison = item.get("comparison", "lte")
        actual_hp_pct = getattr(actor, "hp_ratio", 1.0) * 100.0
        res = compare_values(actual_hp_pct, comparison, threshold)

    elif cond_type == "has_specified_resource_amount":
        floats = item.get("floats", {})
        threshold = floats.get("resource_amount", 0.0)
        comparison = item.get("comparison", "gte")
        actual = getattr(getattr(actor, "resource", None), "current_value", 0.0)
        res = compare_values(actual, comparison, threshold)

    elif cond_type == "has_ability_stack_charge":
        spec = item.get("ability_spec")
        comparison = item.get("comparison", "gte")
        amount = item.get("floats", {}).get("amount", 1.0)
        actual = 0
        if hasattr(caster, "ability_db") and spec in caster.ability_db:
            actual = getattr(caster.ability_db[spec], "charges", 0)
        res = compare_values(actual, comparison, amount)

    elif cond_type == "is_player":
        res = bool(getattr(actor, "is_player", False))

    elif cond_type == "is_not_player":
        res = not bool(getattr(actor, "is_player", False))

    elif cond_type == "if_primary_target":
        res = True

    elif cond_type == "random_chance":
        chance = item.get("floats", {}).get("chance", 1.0)
        res = random.random() <= chance

    elif cond_type == "immune_by_resolve":
        # Target dummies/bosses have resolve immunity
        res = bool(getattr(actor, "immune_by_resolve", False))

    elif cond_type == "if_spell_hit":
        res = True

    elif cond_type in ("is_party_member", "is_friend"):
        res = (actor is caster)

    elif cond_type == "has_melee_weapon":
        res = getattr(actor, "stats", {}).get("Main_hand_max", 0) > 0

    elif cond_type == "is_dual_wielding":
        res = getattr(actor, "stats", {}).get("Off_hand_max", 0) > 0

    elif cond_type == "is_not_dual_wielding":
        res = getattr(actor, "stats", {}).get("Off_hand_max", 0) <= 0

    elif cond_type == "has_effect_at_stack_charge_count":
        tags = item.get("tags")
        spec = item.get("ability_spec")
        comparison = item.get("comparison", "eq")
        expected_count = int(item.get("count", 1))
        actual_stacks = get_entity_effect_stacks(actor, tags=tags, ability_spec=spec)
        res = compare_values(actual_stacks, comparison, expected_count)

    elif cond_type == "if_stack_charge":
        expected_count = int(item.get("count", 1))
        actual_stacks = 1
        if context:
            if "stack_multiplier" in context:
                actual_stacks = int(context["stack_multiplier"])
            elif "current_stacks" in context:
                actual_stacks = int(context["current_stacks"])
            elif "stacks" in context:
                actual_stacks = int(context["stacks"])
            elif "charges" in context:
                actual_stacks = int(context["charges"])
            elif "active_effect" in context and hasattr(context["active_effect"], "stacks"):
                actual_stacks = int(getattr(context["active_effect"], "stacks", 1))
        res = (actual_stacks == expected_count)

    elif cond_type == "is_target_caster":
        effective_target = context.get("target") if context and "target" in context else target
        res = (effective_target is caster)

    elif cond_type == "is_casting":
        active_channel = getattr(actor, "active_channel", None)
        active_cast = getattr(actor, "active_cast", None)
        is_busy = (active_channel is not None) or (active_cast is not None) or getattr(actor, "is_channeling", False)
        
        spec = item.get("ability_spec")
        if spec and is_busy:
            active_bp = getattr(active_channel, "ability", None) or getattr(active_cast, "ability", None)
            active_fqn = getattr(active_bp, "fqn", "")
            res = (spec == active_fqn)
        else:
            res = is_busy

    elif cond_type == "is_in_combat":
        res = getattr(actor, "in_combat", True)

    elif cond_type == "is_not_in_combat":
        res = not getattr(actor, "in_combat", False)

    elif cond_type == "is_discipline":
        res = True

    elif cond_type == "passes_conditional":
        # In SWTOR, this evaluates world/encounter rules (e.g. cnd.global.is_in_flashpoint_operation).
        # Resolution order: execution context -> sim instance -> actor/caster instance -> global setting.
        if context and "in_flashpoint_operation" in context:
            res = bool(context["in_flashpoint_operation"])
        elif sim is not None and hasattr(sim, "in_flashpoint_operation"):
            res = bool(getattr(sim, "in_flashpoint_operation"))
        elif actor is not None and hasattr(actor, "in_flashpoint_operation"):
            res = bool(getattr(actor, "in_flashpoint_operation"))
        elif caster is not None and hasattr(caster, "in_flashpoint_operation"):
            res = bool(getattr(caster, "in_flashpoint_operation"))
        else:
            from src.swtorsim.settings import is_in_flashpoint_operation
            res = is_in_flashpoint_operation()

    elif cond_type == "is_companion":
        res = False

    elif cond_type == "is_in_cover":
        res = bool(getattr(actor, "is_in_cover", False))

    elif cond_type == "is_not_in_cover":
        res = not bool(getattr(actor, "is_in_cover", False))

    elif cond_type == "if_caster_positioning":
        # In SWTOR, requires the caster to be positioned behind the target (rear 180-degree arc).
        # In simulation / parsing, default to True unless explicitly disabled on caster or context.
        if context and "is_behind_target" in context:
            res = bool(context["is_behind_target"])
        elif hasattr(caster, "is_behind_target"):
            res = bool(getattr(caster, "is_behind_target"))
        elif hasattr(caster, "behind_target"):
            res = bool(getattr(caster, "behind_target"))
        elif getattr(caster, "position", None) is not None:
            res = (getattr(caster, "position") == "behind")
        else:
            res = True

    elif cond_type == "is_class":
        # Character base class validation.
        # Checks whether the actor is a player character with a class, or matches a specific class if provided.
        expected_class = (
            item.get("class_name")
            or item.get("strings", {}).get("class")
            or item.get("ints", {}).get("class_id")
            or item.get("ints", {}).get("class")
        )
        if expected_class:
            actual_class = (
                getattr(actor, "character_class", None)
                or getattr(actor, "class_name", None)
                or getattr(actor, "base_class", None)
            )
            res = (str(actual_class).lower() == str(expected_class).lower())
        else:
            res = hasattr(actor, "ability_db") or bool(getattr(actor, "character_class", None))

    elif cond_type == "is_creature_type":
        # Target creature type check (e.g. droid = 3 vs organic = 1 / humanoid, player character = 4).
        expected_type = item.get("ints", {}).get("creature_type")
        if getattr(actor, "is_droid", False):
            actual_type = 3
        elif getattr(actor, "is_player", False):
            actual_type = 4
        else:
            actual_type = getattr(actor, "creature_type", 1)
        if expected_type is not None:
            res = (actual_type == int(expected_type))
        else:
            res = True

    elif cond_type == "if_weapon_mode":
        # Evaluates weapon attack mode (1 = single/primary, 2 = dual-wield/secondary).
        expected_mode = item.get("ints", {}).get("mode", 1)
        if context and "weapon_mode" in context:
            actual_mode = context["weapon_mode"]
        elif hasattr(actor, "weapon_mode"):
            actual_mode = getattr(actor, "weapon_mode")
        elif getattr(actor, "stats", {}).get("Off_hand_max", 0) > 0:
            actual_mode = 2
        elif getattr(actor, "stats", {}).get("Main_hand_max", 0) > 0:
            actual_mode = 1
        else:
            actual_mode = 0
        res = (actual_mode == int(expected_mode))

    elif cond_type == "if_faction":
        # Evaluates character faction (e.g. 'empire'/'imperial' vs 'republic').
        expected_faction = (
            item.get("strings", {}).get("factions")
            or item.get("faction")
            or item.get("strings", {}).get("faction")
        )
        actual_faction = (
            context.get("faction") if (context and "faction" in context)
            else getattr(actor, "faction", "empire")
        )
        if expected_faction:
            res = str(expected_faction).lower() in str(actual_faction).lower()
        else:
            res = bool(actual_faction)

    elif cond_type in ("is_stealthed", "is_not_stealthed"):
        # Evaluates whether the actor is stealthed or not.
        is_stealthed = (
            getattr(actor, "is_stealthed", False)
            or entity_has_effect(actor, tags=["tag.abl.stealth", "tag.abl.utility.stealth"], ability_spec="stealth")
        )
        res = bool(is_stealthed) if cond_type == "is_stealthed" else not is_stealthed

    elif cond_type == "is_mounted":
        # Evaluates whether the actor is currently mounted on a vehicle.
        if context and "is_mounted" in context:
            res = bool(context["is_mounted"])
        else:
            res = bool(getattr(actor, "is_mounted", False))

    elif cond_type == "if_result":
        # Evaluates combat hit/action result (e.g. previous action succeeded and did not miss).
        if context and "result" in context:
            res = bool(context["result"])
        elif context and "is_hit" in context:
            res = bool(context["is_hit"])
        elif context and "missed" in context:
            res = not bool(context["missed"])
        else:
            res = True

    else:
        # Fallback for unmodeled visual/flavor conditions
        res = True

    if item.get("negated", False):
        res = not res

    return res


def evaluate_logic(logic_node: dict, results_by_id: dict[str, bool]) -> bool:
    """Recursively evaluates boolean logic trees (and/or/condition reference)."""
    if not logic_node:
        return True
    if "condition" in logic_node:
        return results_by_id.get(logic_node["condition"], True)

    op = logic_node.get("op")
    operands = logic_node.get("operands", [])
    if op == "and":
        return all(evaluate_logic(child, results_by_id) for child in operands)
    elif op == "or":
        return any(evaluate_logic(child, results_by_id) for child in operands)
    return True


def evaluate_extracted_conditions(conditions: dict[str, Any], caster: "Player", target: "Dummy", sim=None, context=None) -> bool:
    """Evaluates an extracted condition structure containing a 'list' and 'logic' tree."""
    cond_list = conditions.get("list") or []
    logic_tree = conditions.get("logic") or {}

    results_by_id = {}
    for item in cond_list:
        cond_id = item.get("id")
        if cond_id:
            results_by_id[cond_id] = evaluate_single_extracted_condition(
                item, caster, target, sim=sim, context=context
            )

    return evaluate_logic(logic_tree, results_by_id)


def validate_all(requirements: dict[str, Any], caster: "Player", target: "Dummy", sim = None, context = None) -> bool:
    """Validates conditions, supporting both extracted AST structures and legacy rotation rules."""
    if not requirements:
        return True

    # 1. Extracted AST condition schema: {"list": [...], "logic": {...}}
    if isinstance(requirements, dict) and "list" in requirements and "logic" in requirements:
        return evaluate_extracted_conditions(requirements, caster, target, sim=sim, context=context)

    # 2. Legacy flat dictionary format (used by rotation.py priority rules)
    for key, value in requirements.items():
        validator_func = CONDITION_REGISTRY.get(key)
        if validator_func:
            if not validator_func(value, caster, target, sim=sim):
                return False
        else:
            raise KeyError(
                f"\n This requirement doesn't exist/isn't implemented: '{key}'\n"
                f"Please check your ability/proc JSON configuration files.\n"
                f"Implemented requirements are: {list(CONDITION_REGISTRY.keys())}\n"
                f"Contact me if you think yours should be here too")
    return True
