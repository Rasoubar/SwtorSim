"""Records the hits that miss, for the simulator's combat log and the debugger, without touching the engine files.

The engine decides a miss inside ``combat_math.accuracy_roll`` and the caller (``abilities.handle_damage_action``) simply
skips the hit, so nothing remembers it. ``log_misses`` swaps in, for the length of a ``with`` block, a thin wrapper around
the real ``accuracy_roll`` that calls it once, unchanged (the same random draw, the same answer), and reports each False.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Mapping


def ability_name(blueprints: Mapping[str, Any] | None, fqn: str | None) -> str:
    """Display name of an ability or effect source from its fqn (the loadout's blueprint name, else the fqn's tail)."""
    if not fqn:
        return "Unknown"
    name = getattr(blueprints.get(fqn), "name", None) if blueprints else None
    return str(name).strip() if name else fqn.split(".")[-1].replace("_", " ").title()


@contextmanager
def log_misses(sim: Any, blueprints: Mapping[str, Any] | None, on_miss: Callable[[dict], None]):
    """While active, calls ``on_miss(record)`` for every accuracy roll that fails.

    ``record`` has ``time`` (simulation clock), ``fqn``, ``ability``, ``hand``, ``attack_type`` and ``target``.
    """
    import src.swtorsim.abilities as abilities

    original = abilities.accuracy_roll

    def accuracy_roll_logging_misses(source, hand="main", attack_type=1, ability_fqn=None, action_tags=frozenset(), target=None):
        hit = original(source, hand=hand, attack_type=attack_type, ability_fqn=ability_fqn,
                       action_tags=action_tags, target=target)
        if not hit:
            on_miss({
                "time": float(sim.current_time), "fqn": ability_fqn, "ability": ability_name(blueprints, ability_fqn),
                "hand": hand, "attack_type": attack_type, "target": getattr(target, "name", ""),
            })
        return hit

    abilities.accuracy_roll = accuracy_roll_logging_misses
    try:
        yield
    finally:
        abilities.accuracy_roll = original
