"""Condition and requirement evaluators for rotation steps, ability activations, and effect branches."""

import random
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from entities import Player, Dummy

def _to_list(val: Any) -> list:
    """Helper to convert single string/item conditions into an iterable list."""
    return [val] if isinstance(val, str) else val

def check_target_hp_pct(conditions, caster: "Player", target: "Dummy", **_kwargs) -> bool:
    """True when target HP ratio matches ``comparison`` (default <=) against ``pct``.

    An optional ``bypass_if_buff_active`` still makes the rule true on its own.
    """
    if isinstance(conditions, dict):
        threshold = conditions.get("pct", 0.3)
        comparison = conditions.get("comparison", conditions.get("operator", "lte"))
        bypass_buffs = conditions.get("bypass_if_buff_active", None)
    else:
        threshold = conditions
        comparison = "lte"
        bypass_buffs = None
    if compare_values(target.hp_ratio, comparison, threshold):
        return True
    if bypass_buffs and check_caster_buff(bypass_buffs, caster, target):
        return True
    return False

def check_target_hp(conditions, caster: "Player", target: "Dummy", **_kwargs) -> bool:
    """Legacy key: target HP ratio is at or below the threshold, or an execute-bypass buff is active."""
    if isinstance(conditions, dict):
        forced = dict(conditions)
        forced["comparison"] = "lte"
        return check_target_hp_pct(forced, caster, target)
    return check_target_hp_pct(conditions, caster, target)

def check_caster_buff(conditions: Any, caster: "Player", _target: "Dummy", **_kwargs) -> bool:
    """Returns True if the caster has any of the specified active buffs."""
    return any(caster.has_effect(b) for b in _to_list(conditions))

def check_target_debuff(conditions: Any, _caster: "Player", target: "Dummy", **_kwargs) -> bool:
    """Returns True if the target has any of the specified active debuffs."""
    return any(target.has_effect(d) for d in _to_list(conditions))

def inverse_check_target_debuff(conditions: Any, caster: "Player", target: "Dummy", **kwargs) -> bool:
    """Returns True if the target does NOT have any of the specified debuffs."""
    return not check_target_debuff(conditions, caster, target, **kwargs)

def check_caster_energy(data, caster: "Player", _target: "Dummy", **_kwargs) -> bool:
    """True when the caster's primary resource matches ``comparison`` (default >=) against ``value``."""
    if isinstance(data, dict):
        threshold = data.get("value", data.get("threshold", 0))
        comparison = data.get("comparison", data.get("operator", "gte"))
    else:
        threshold = data
        comparison = "gte"
    return compare_values(caster.resource.current_value, comparison, threshold)

def check_caster_energy_above(threshold: int, caster: "Player", _target: "Dummy", **_kwargs) -> bool:
    """Legacy key: the caster's current primary resource is at or above ``threshold``."""
    return compare_values(caster.resource.current_value, "gte", threshold)

def check_caster_energy_below(threshold: int, caster: "Player", _target: "Dummy", **_kwargs) -> bool:
    """Legacy key: the caster's current primary resource is strictly below ``threshold``."""
    return compare_values(caster.resource.current_value, "lt", threshold)

def _proc_remaining_seconds(name: str, caster: "Player", sim) -> float | None:
    """Remaining proc ICD or lockout. None means the proc buff is active, so the rule is false."""
    if caster.has_effect(name):
        return None

    current_time = sim.current_time if sim is not None else 0.0
    remaining_cooldown = 0.0

    proc_info = getattr(caster, "proc_registry", {}).get(name)
    if proc_info is not None:
        kind = proc_info.get("kind")
        if kind == "lockout_effect":
            target_eff_name = proc_info.get("effect_name", name)
            for eff in getattr(caster, "effects", {}).values():
                if getattr(eff, "is_expired", False):
                    continue
                if getattr(eff, "name", None) == target_eff_name and any("lockout" in t for t in getattr(eff, "tags", ())):
                    if getattr(eff, "expires_at", None) is not None:
                        remaining_cooldown = max(remaining_cooldown, eff.expires_at - current_time)
            return remaining_cooldown
        elif kind == "trigger_icd":
            if sim is not None and hasattr(sim, "triggers"):
                source_fqn = proc_info.get("source_fqn", "")
                remaining_cooldown = sim.triggers.get_remaining_icd(source_fqn, current_time, caster=caster)
            return remaining_cooldown

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

    return remaining_cooldown

def check_proc_cooldown(data: dict, caster: "Player", _target: "Dummy", sim, **_kwargs) -> bool:
    """True when the named proc buff is inactive and its remaining ICD matches ``comparison`` (default >)."""
    remaining = _proc_remaining_seconds(data["name"], caster, sim)
    if remaining is None:
        return False
    comparison = data.get("comparison", data.get("operator", "gt"))
    return compare_values(remaining, comparison, data["value"])

def check_proc_cooldown_above(data: dict, caster: "Player", _target: "Dummy", sim, **_kwargs) -> bool:
    """Legacy key: the named proc is inactive and its remaining ICD is strictly above ``data['value']``."""
    remaining = _proc_remaining_seconds(data["name"], caster, sim)
    if remaining is None:
        return False
    return compare_values(remaining, "gt", data["value"])

def check_target_hp_above(threshold: float, _caster: "Player", target: "Dummy", **_kwargs) -> bool:
    """Legacy key: the target's HP ratio is strictly above ``threshold``."""
    return compare_values(target.hp_ratio, "gt", threshold)

def check_caster_does_not_have_buff(conditions: Any, caster: "Player", _target: "Dummy", **_kwargs) -> bool:
    """Returns True if the caster does not have any of the specified buffs active."""
    buff_list = [conditions] if isinstance(conditions, str) else conditions
    has_any_buff = any(caster.has_effect(b) for b in buff_list)
    return not has_any_buff

def _ability_for_cooldown_rule(caster, name: str):
    """Resolves a rotation cooldown name to an ability, using the same keys as ``Player.build_ability_db``."""
    ability_db = getattr(caster, "ability_db", None) or {}
    if not isinstance(name, str) or not ability_db:
        return None
    ability = ability_db.get(name)
    if ability is None:
        ability = ability_db.get(name.lower().replace(" ", "_"))
    return ability


def remaining_ability_cooldown(name: str, caster, sim) -> float:
    """Seconds until ``name`` can be cast again.

    A normal ability stores its ready time in ``caster.cooldowns`` under the display name.
    A charge ability does not: spending the last charge records ``recharge_target_time`` on the
    ability and leaves the cooldown map empty. A charge still in hand does not block the cast.
    """
    now = float(sim.current_time)
    cooldowns = getattr(caster, "cooldowns", None) or {}
    ready_at = float(cooldowns.get(name, 0) or 0)

    ability = _ability_for_cooldown_rule(caster, name)
    if ability is not None:
        stored_name = getattr(ability, "name", None)
        if stored_name and stored_name != name:
            ready_at = max(ready_at, float(cooldowns.get(stored_name, 0) or 0))
        if getattr(ability, "has_charges", False):
            charges = getattr(ability, "charges", None)
            if charges is not None and charges < 1:
                recharge_at = getattr(ability, "recharge_target_time", None)
                if recharge_at is not None:
                    ready_at = max(ready_at, float(recharge_at))
    return ready_at - now


def check_ability_cooldown(data: dict, caster: "Player", _target: "Dummy", sim, **_kwargs) -> bool:
    """True when the remaining cooldown of ``data['name']`` matches ``comparison`` (default <) against ``value``."""
    comparison = data.get("comparison", data.get("operator", "lt"))
    return compare_values(remaining_ability_cooldown(data["name"], caster, sim), comparison, data["value"])

def check_ability_cooldown_under(data: dict, caster: "Player", _target: "Dummy", sim, **_kwargs) -> bool:
    """Legacy key: the remaining cooldown of ``data['name']`` is strictly below ``data['value']`` seconds."""
    return compare_values(remaining_ability_cooldown(data["name"], caster, sim), "lt", data["value"])

def check_ability_cooldown_above(data: dict, caster: "Player", _target: "Dummy", sim, **_kwargs) -> bool:
    """Legacy key: the remaining cooldown of ``data['name']`` is strictly above ``data['value']`` seconds."""
    return compare_values(remaining_ability_cooldown(data["name"], caster, sim), "gt", data["value"])


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


def _applied_by(eff, source) -> bool:
    """True when `source` is None (any applier) or the effect was applied by `source`.
    An effect with no recorded applier (`caster_ref` None) still counts."""
    if source is None:
        return True
    applier = getattr(eff, "caster_ref", None)
    return applier is None or applier is source


def _condition_source(item: dict, caster):
    """Applier an effect condition is restricted to: the caster for `from_actor: caster`, else None
    (other `from_actor` values, e.g. `actor_1` / `target`, are not restricted)."""
    return caster if item.get("from_actor") == "caster" else None


def entity_has_effect(entity, tags: list[str] | None = None, ability_spec: str | None = None, count: int = 1,
                      source=None) -> bool:
    """Checks whether an entity has an active effect or dot matching tags or an ability spec.

    `count` is the combined stack total across all matching active effects and dots, so one
    effect with 3 stacks and three separate effects sharing a tag (e.g. three DoTs tagged
    sinister_succor_dot) both satisfy count=3. `source` limits active effects to those applied
    by that entity (`from_actor: caster`).
    """
    if not entity:
        return False

    effects = getattr(entity, "effects", {})
    tags_set = set(tags) if tags else set()
    total = 0

    for eff in effects.values():
        if getattr(eff, "is_expired", False):
            continue
        if not _applied_by(eff, source):
            continue
        eff_tags = set(getattr(eff, "tags", []) or getattr(eff, "required_tags", []) or [])
        eff_name = getattr(eff, "name", "") or getattr(eff, "effect_name", "")
        eff_fqn = getattr(eff, "fqn", "") or getattr(eff, "source_ability", "")
        stacks = getattr(eff, "stacks", None) or getattr(eff, "charges", 1) or 1

        matches = False
        if tags_set and (tags_set & eff_tags):
            matches = True
        if ability_spec and ability_spec in (eff_fqn, eff_name):
            matches = True

        if matches:
            total += stacks
            if total >= count:
                return True

    # Also check active dots on dummy targets
    dots = getattr(entity, "dots", {})
    for dot_name, dot in dots.items():
        dot_stacks = getattr(dot, "stacks", None) or 1
        if ability_spec and ability_spec == dot_name:
            total += dot_stacks
        else:
            dot_tags = set(getattr(dot, "tags", []) or [])
            if tags_set and (tags_set & dot_tags):
                total += dot_stacks
        if total >= count:
            return True

    return False


def get_entity_effect_stacks(entity, tags: list[str] | None = None, ability_spec: str | None = None,
                             source=None) -> int:
    """Returns the current stack/charge count of an active effect or dot matching tags or ability spec.
    `source` limits active effects to those applied by that entity (`from_actor: caster`)."""
    if not entity:
        return 0

    effects = getattr(entity, "effects", {})
    tags_set = set(tags) if tags else set()

    best_stacks = 0
    found = False

    for eff in effects.values():
        if getattr(eff, "is_expired", False):
            continue
        if not _applied_by(eff, source):
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
    elif isinstance(data, str):
        name, expected_stacks, comparison, tags = data, 1.0, "gte", None  # bare name: at least one stack
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
    elif isinstance(data, str):
        name, expected_stacks, comparison, tags = data, 1.0, "gte", None  # bare name: at least one stack
    else:
        return False

    # Same name lookup as the caster buff rule (exact key / name / FQN, then case- and underscore-insensitive).
    actual_stacks = get_caster_buff_stacks(target, buff_name=name, tags=tags)
    return compare_values(actual_stacks, comparison, expected_stacks)


def _effect_name_matches(eff, key, name: str) -> bool:
    """True when ``name`` is this effect's key, display name, or FQN (case- and underscore-insensitive)."""
    if not name:
        return False
    if key == name:
        return True
    target_norm = name.strip().lower().replace("_", " ")
    eff_name = getattr(eff, "name", "") or getattr(eff, "effect_name", "") or key
    eff_fqn = getattr(eff, "fqn", "") or getattr(eff, "source_ability", "")
    return target_norm in {
        str(eff_name).strip().lower().replace("_", " "),
        str(eff_fqn).strip().lower().replace("_", " "),
        str(key).strip().lower().replace("_", " "),
    }


def _seconds_left(eff, now: float) -> float:
    """Remaining seconds. A permanent effect (no expiry) is infinite."""
    if hasattr(eff, "time_remaining"):
        return float(eff.time_remaining(now))
    expires_at = getattr(eff, "expires_at", None)
    if expires_at is None:
        return float("inf")
    return max(0.0, float(expires_at) - now)


def effect_time_remaining(entity, name: str, sim) -> float:
    """Longest remaining seconds of a matching active effect.

    An effect that is not active counts as 0, so a "less than" refresh rule is true when it is missing.
    Expired effects, passives, and lockouts are ignored. A permanent effect has infinite time left.
    When several copies match, the longest remaining time is the one that is still up.
    """
    if not entity or not name:
        return 0.0
    now = float(sim.current_time) if sim is not None else 0.0
    best: float | None = None

    def consider(eff, key) -> None:
        nonlocal best
        if getattr(eff, "is_expired", False) or getattr(eff, "is_passive", False):
            return
        tags = getattr(eff, "tags", ()) or ()
        if any("lockout" in t for t in tags):
            return
        if not _effect_name_matches(eff, key, name):
            return
        remaining = _seconds_left(eff, now)
        best = remaining if best is None else max(best, remaining)

    for key, eff in (getattr(entity, "effects", {}) or {}).items():
        consider(eff, key)
    for key, eff in (getattr(entity, "dots", {}) or {}).items():
        consider(eff, key)
    return 0.0 if best is None else best


def _remaining_rule_parts(data: Any) -> tuple[str, float, str] | None:
    """``(name, seconds, comparison)`` from a duration rule. Comparison defaults to ``lt``."""
    if not isinstance(data, dict):
        return None
    name = data.get("name") or data.get("buff") or data.get("debuff") or ""
    seconds = float(data.get("value", data.get("seconds", 0)))
    comparison = data.get("comparison", data.get("operator", "lt"))
    return str(name), seconds, comparison


def check_caster_buff_remaining(data: Any, caster: "Player", _target: "Dummy", sim=None, **_kwargs) -> bool:
    """True when the named caster buff's remaining seconds match ``comparison`` (default <) against ``value``.

    A buff that is not active has 0 seconds left.
    """
    parts = _remaining_rule_parts(data)
    if parts is None or not parts[0]:
        return False
    name, seconds, comparison = parts
    return compare_values(effect_time_remaining(caster, name, sim), comparison, seconds)


def check_target_debuff_remaining(data: Any, _caster: "Player", target: "Dummy", sim=None, **_kwargs) -> bool:
    """True when the named target debuff or DoT's remaining seconds match ``comparison`` (default <) against ``value``.

    A debuff that is not active has 0 seconds left.
    """
    parts = _remaining_rule_parts(data)
    if parts is None or not parts[0]:
        return False
    name, seconds, comparison = parts
    return compare_values(effect_time_remaining(target, name, sim), comparison, seconds)


CONDITION_REGISTRY = {
    "target_hp_below_pct": check_target_hp,
    "target_hp_pct": check_target_hp_pct,
    "target_has_debuff": check_target_debuff,
    "caster_has_buff": check_caster_buff,
    "target_doesnt_have_debuff": inverse_check_target_debuff,
    "caster_energy": check_caster_energy,
    "caster_energy_above": check_caster_energy_above,
    "caster_energy_below": check_caster_energy_below,
    "target_hp_above_pct": check_target_hp_above,
    "proc_cooldown": check_proc_cooldown,
    "proc_cooldown_above": check_proc_cooldown_above,
    "caster_does_not_have_buff": check_caster_does_not_have_buff,
    "ability_cooldown": check_ability_cooldown,
    "ability_cooldown_under": check_ability_cooldown_under,
    "ability_cooldown_above": check_ability_cooldown_above,
    "caster_buff_stacks": check_caster_buff_stacks,
    "caster_buff_remaining": check_caster_buff_remaining,
    "target_debuff_stacks": check_target_debuff_stacks,
    "target_debuff_remaining": check_target_debuff_remaining,
}


def _find_ability(entity, spec):
    """Returns the Ability ``spec`` on ``entity.ability_db`` (exact key, normalized name, or `_plus` stem when
    stem matching is enabled), else None."""
    db = getattr(entity, "ability_db", None)
    if not db or not isinstance(spec, str):
        return None
    if spec in db:
        return db[spec]
    norm = spec.lower().replace(" ", "_")
    if norm in db:
        return db[norm]
    from src.swtorsim.settings import is_stem_matching_enabled
    if is_stem_matching_enabled():
        base_stem = spec.split(".")[-1]
        for abl in db.values():
            if getattr(abl, "fqn", "").endswith(f".{base_stem}_plus"):
                return abl
    return None


def owner_effect_stacks(context) -> int | None:
    """Live stacks of the effect that owns the branch (``owner_entity.effects[owner_effect_key]``),
    or None when the context names no owner effect. Exact key only: a raw dict lookup, so an effect
    that just dropped to 0 stacks (flagged expired, not yet cleaned up) still answers."""
    if not context:
        return None
    effects = getattr(context.get("owner_entity"), "effects", None)
    key = context.get("owner_effect_key")
    if effects is None or not key:
        return None
    eff = dict.get(effects, key)
    return None if eff is None else getattr(eff, "stacks", None)


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
    elif actor_str == "actor_4":
        # GOM actor 4 is the enemy the ability acts on (DoTs/debuffs "from_actor: caster", execute-range HP checks).
        # Branches whose target_overrides redirect `target` to the caster still need the real enemy here, so
        # prefer the trigger's enemy target, then a non-caster `target`, then the caster's current target.
        enemy = (context or {}).get("enemy_target")
        if enemy is None and target is not None and target is not caster:
            enemy = target
        if enemy is None:
            enemy = getattr(caster, "current_target", None)
        actor = enemy if enemy is not None else (target if target is not None else caster)
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
        res = entity_has_effect(actor, tags=tags, ability_spec=spec, count=count,
                                source=_condition_source(item, caster))

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
        resource = getattr(actor, "resource", None)
        actual = getattr(resource, "current_value", 0.0)
        # Game data states resource thresholds as resource AVAILABLE; HeatPool stores heat BUILT UP,
        # so convert to remaining capacity (gte 6 -> heat <= 94, lte 60 -> heat >= 40).
        if str(getattr(resource, "pool_type", "")).lower() == "heat":
            actual = getattr(resource, "max_value", 100.0) - actual
        res = compare_values(actual, comparison, threshold)

    elif cond_type == "has_ability_stack_charge":
        spec = item.get("ability_spec")
        comparison = item.get("comparison", "gte")
        amount = item.get("floats", {}).get("amount", 1.0)
        # The named actor's ability first; extracted self-effects often name "target" while the sim passes the
        # enemy, so fall back to the caster's own ability like before.
        abl = _find_ability(actor, spec)
        if abl is None and actor is not caster:
            abl = _find_ability(caster, spec)
        actual = getattr(abl, "charges", None) if abl is not None else None
        res = compare_values(actual if actual is not None else 0, comparison, amount)  # None = not a charge ability

    elif cond_type == "is_player":
        res = bool(getattr(actor, "is_player", False))

    elif cond_type == "is_not_player":
        res = not bool(getattr(actor, "is_player", False))

    elif cond_type == "if_primary_target":
        res = True

    elif cond_type == "random_chance":
        floats = item.get("floats", {})
        if "percent_chance" in floats:
            chance = floats["percent_chance"] / 100.0  # extractor field is a percent (10.0 = 10%)
        else:
            chance = floats.get("chance", 1.0)
        res = random.random() < chance

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
        actual_stacks = get_entity_effect_stacks(actor, tags=tags, ability_spec=spec,
                                                 source=_condition_source(item, caster))
        res = compare_values(actual_stacks, comparison, expected_count)

    elif cond_type == "if_stack_charge":
        expected_count = int(item.get("count", 1))
        # The stack charge of the effect this branch belongs to. The context's stack_multiplier is 1 for an
        # effect whose stacks do not scale damage (trigger manager, DoT tick), so it is only the fallback.
        actual_stacks = owner_effect_stacks(context)
        if actual_stacks is None:
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
        res = (int(actual_stacks) == expected_count)

    elif cond_type == "is_target_caster":
        effective_target = target if target is not None else ((context or {}).get("target"))
        res = (effective_target is caster)

    elif cond_type == "is_casting":
        active_channel = getattr(actor, "active_channel", None)
        active_cast = getattr(actor, "active_cast", None)
        is_busy = (active_channel is not None) or (active_cast is not None) or getattr(actor, "is_channeling", False)
        
        spec = item.get("ability_spec")
        if spec and is_busy:
            # A channel wraps its ability (ActiveChannel.ability); a timed cast is the Ability itself.
            active_bp = getattr(active_channel, "ability", None) or getattr(active_cast, "ability", None) or active_cast
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

    elif cond_type == "not_has_effect":
        res = not entity_has_effect(
            actor, tags=item.get("tags"), ability_spec=item.get("ability_spec"), count=item.get("count", 1),
            source=_condition_source(item, caster),
        )

    elif cond_type == "is_dead":
        res = getattr(actor, "hp", 1) <= 0

    elif cond_type == "has_pending_revive":
        res = False  # the sim has no revive mechanic, so no revive is ever pending

    elif cond_type == "is_area":
        res = False  # the sim fight is never inside one of the named game areas

    elif cond_type in ("is_object", "if_not_weapon_type"):
        res = True  # unmodeled: no placeable objects or weapon-type restrictions in the sim

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
