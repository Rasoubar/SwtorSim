# src/swtorsim/triggers.py
import random


class TriggerManager:
    def __init__(self):
        # Maps event_name -> list of compiled trigger dicts
        self._listeners = {}

    def subscribe(self, owner_id, ability, branch, caster, target):
        """Registers every trigger rule defined on a branch independently."""
        for raw_trigger in getattr(branch, "triggers", []):
            event = raw_trigger.get("trigger")
            if not event:
                continue

            entry = {
                "owner_id": owner_id,
                "ability": ability,
                "branch": branch,
                "caster": caster,
                "target": target,
                # Pre-compile lists to frozensets once at registration time
                "tags": frozenset(raw_trigger.get("tags") or []),
                "excluded_tags": frozenset(raw_trigger.get("excluded_tags") or []),
                "ints": raw_trigger.get("ints") or {},
                "proc_chance": (raw_trigger.get("floats") or {}).get("proc_chance_percent"),
            }
            self._listeners.setdefault(event, []).append(entry)

    def unsubscribe(self, owner_id):
        """Removes all triggers tied to a specific effect or passive instance."""
        for event, entries in self._listeners.items():
            self._listeners[event] = [sub for sub in entries if sub["owner_id"] != owner_id]

    def dispatch(self, event_name: str, sim, context: dict):
        """Filters incoming combat events and delegates execution to the ability."""
        entries = self._listeners.get(event_name)
        if not entries:
            return

        event_tags = frozenset(context.get("tags") or [])

        # Snapshot the list to allow cascading actions/triggers during iteration
        for sub in list(entries):
            # 1. Fast reject on excluded tags
            if sub["excluded_tags"] and (event_tags & sub["excluded_tags"]):
                continue

            # 2. Required tags check (OR match)
            if sub["tags"] and not (event_tags & sub["tags"]):
                continue

            # 3. Exact match on integer flags (damage_type, weapon_mode, spell_type)
            ints = sub["ints"]
            if ints and any(context.get(k) != v for k, v in ints.items()):
                continue

            # 4. Proc chance check
            proc_chance = sub["proc_chance"]
            if proc_chance is not None and proc_chance < 100.0:
                if random.random() * 100.0 > proc_chance:
                    continue

            # Hand execution directly back to the Ability method
            sub["ability"].execute_branch(
                sim,
                sub["branch"],
                sub["caster"],
                sub["target"],
                context=context
            )