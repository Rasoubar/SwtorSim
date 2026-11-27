"""Read-only snapshot of a simulation at one moment: resource, GCD, cooldowns, charges, effects, ICDs, stats.

Nothing here changes the simulation. Times are measured from ``at`` (the moment asked for), so "remaining" means
remaining at that moment even when the last processed event was slightly earlier.
"""

from __future__ import annotations

import math
from typing import Any


def _round(value, digits=3):
    if value is None:
        return None
    if isinstance(value, float) and math.isinf(value):
        return None  # permanent: JSON has no infinity
    return round(float(value), digits)


def _effects(entity, label: str, at: float) -> list[dict[str, Any]]:
    out = []
    for key, eff in entity.effects.items():
        if getattr(eff, "is_expired", False):
            continue
        remaining = eff.time_remaining(at) if hasattr(eff, "time_remaining") else None
        out.append({
            "entity": label,
            "key": str(key),
            "name": getattr(eff, "name", str(key)),
            "stacks": getattr(eff, "stacks", 1),
            "max_stacks": getattr(eff, "max_stacks", 1),
            "remaining": _round(remaining),
            "permanent": remaining is None or math.isinf(remaining),
            "passive": bool(getattr(eff, "is_passive", False)),
            "tags": sorted(str(t) for t in (getattr(eff, "tags", ()) or ()))[:8],
        })
    return out


def snapshot(sim, at: float) -> dict[str, Any]:
    """Returns the state the player, target and trigger manager are in, as plain JSON-ready data."""
    player = sim.incoming_attack_victim
    target = sim.incoming_attack_attacker
    seen = set()
    abilities = []
    for ability in player.ability_db.values():
        if id(ability) in seen:  # the database lists each ability under its fqn and its name
            continue
        seen.add(id(ability))
        ready_in = max(0.0, player.cooldowns.get(ability.name, 0.0) - at)
        has_charges = bool(getattr(ability, "has_charges", False))
        recharge_in = None
        if has_charges and getattr(ability, "recharge_target_time", None) is not None:
            recharge_in = max(0.0, ability.recharge_target_time - at)
        # A charge-based ability can cast while it has a charge; others when their cooldown is over.
        ready = (ability.charges or 0) >= 1 if has_charges else ready_in <= 1e-4
        abilities.append({
            "name": ability.name,
            "ready": bool(ready),
            "ready_in": _round(ready_in),
            "charges": ability.charges if has_charges else None,
            "max_charges": ability.max_charges if has_charges else None,
            "recharge_in": _round(recharge_in),
            "cooldown": _round(getattr(ability, "cooldown", None)),
            "on_gcd": bool(getattr(ability, "triggers_gcd", False)),
        })
    abilities.sort(key=lambda a: a["name"].lower())

    icds = []
    for event, entries in sim.triggers._listeners.items():
        for sub in entries:
            remaining = sub["next_allowed_time"] - at
            if remaining > 1e-9:
                icds.append({"source": getattr(sub["ability"], "name", None), "event": event, "remaining": _round(remaining)})
    icds.sort(key=lambda i: -i["remaining"])

    resource = player.resource
    stats = {k: _round(v, 5) for k, v in sorted(player.stats.items()) if isinstance(v, (int, float))}
    return {
        "at": _round(at, 6),
        "last_event_at": _round(sim.current_time, 6),
        "gcd_remaining": _round(max(0.0, player.next_gcd - at)),
        "resource": {
            "type": type(resource).__name__,
            "current": _round(getattr(resource, "current", None), 2),
            "max": _round(getattr(resource, "max_value", None), 2),
        },
        "casting": getattr(player.active_cast, "ability_name", None) if player.active_cast is not None else None,
        "channeling": getattr(player.active_channel, "ability_name", None) if player.active_channel is not None else None,
        "target": {"hp": _round(target.hp, 0), "max_hp": _round(getattr(target, "max_hp", None), 0)},
        "abilities": abilities,
        "effects": _effects(player, "Player", at) + _effects(target, "Target", at),
        "icds": icds,
        "stats": stats,
    }

def _adj(value, elapsed):
    """A time-left value as it would be ``elapsed`` seconds later with nothing happening (never below 0)."""
    return None if value is None else max(0.0, value - elapsed)


def diff_snapshots(before: dict, after: dict, elapsed: float = 0.0, eps: float = 1e-3) -> dict[str, Any]:
    """What changed between two ``snapshot`` results taken ``elapsed`` seconds apart.

    Time-left values in ``before`` are first aged by ``elapsed``, so a cooldown that simply ran down is not a change;
    a time left that is longer than it should be means the effect or cooldown was refreshed or started again.
    """
    def ability_view(a, aged):
        return {
            "ready": a["ready"], "charges": a["charges"],
            "ready_in": _adj(a["ready_in"], elapsed) if aged else a["ready_in"],
            "recharge_in": _adj(a["recharge_in"], elapsed) if aged else a["recharge_in"],
        }

    def differs(x, y):
        return (x is None) != (y is None) or (x is not None and abs(x - y) > eps)

    before_abilities = {a["name"]: a for a in before["abilities"]}
    abilities = []
    for a in after["abilities"]:
        old = before_abilities.get(a["name"])
        if old is None:
            continue
        was, now = ability_view(old, True), ability_view(a, False)
        if was["ready"] != now["ready"] or was["charges"] != now["charges"] or differs(was["ready_in"], now["ready_in"]) \
                or differs(was["recharge_in"], now["recharge_in"]):
            abilities.append({"name": a["name"], "before": ability_view(old, False), "after": now})

    key = lambda e: (e["entity"], e["key"])
    old_effects, new_effects = {key(e): e for e in before["effects"]}, {key(e): e for e in after["effects"]}
    added = [e for k, e in new_effects.items() if k not in old_effects]
    removed = [e for k, e in old_effects.items() if k not in new_effects]
    changed = []
    for k, e in new_effects.items():
        old = old_effects.get(k)
        if old is None:
            continue
        refreshed = (not e["permanent"] and e["remaining"] is not None and old["remaining"] is not None
                     and e["remaining"] > _adj(old["remaining"], elapsed) + eps)
        if e["stacks"] != old["stacks"] or refreshed:
            changed.append({"entity": e["entity"], "name": e["name"], "stacks_before": old["stacks"], "stacks_after": e["stacks"],
                            "max_stacks": e["max_stacks"], "remaining_after": e["remaining"], "refreshed": bool(refreshed)})

    def icd_map(snap):
        out = {}
        for i in snap["icds"]:
            k = (i["source"], i["event"])
            out[k] = max(out.get(k, 0.0), i["remaining"])
        return out

    old_icds, new_icds = icd_map(before), icd_map(after)
    icds = [{"source": k[0], "event": k[1], "remaining": r, "restarted": k in old_icds}
            for k, r in new_icds.items() if k not in old_icds or r > _adj(old_icds[k], elapsed) + eps]

    stats = [{"stat": k, "before": before["stats"].get(k), "after": v}
             for k, v in after["stats"].items() if before["stats"].get(k) is not None and abs(v - before["stats"][k]) > 1e-9]

    def pair(a, b):
        return {"before": a, "after": b}

    return {
        "elapsed": _round(elapsed, 3),
        "resource": {**pair(before["resource"]["current"], after["resource"]["current"]), "type": after["resource"]["type"],
                     "delta": _round((after["resource"]["current"] or 0) - (before["resource"]["current"] or 0), 2)},
        "gcd": pair(_adj(before["gcd_remaining"], elapsed), after["gcd_remaining"]),
        "target_hp": {**pair(before["target"]["hp"], after["target"]["hp"]),
                      "delta": _round((after["target"]["hp"] or 0) - (before["target"]["hp"] or 0), 0)},
        "casting": pair(before["casting"], after["casting"]),
        "channeling": pair(before["channeling"], after["channeling"]),
        "abilities": abilities,
        "effects": {"added": added, "removed": removed, "changed": changed},
        "icds": icds,
        "stats": stats,
    }
