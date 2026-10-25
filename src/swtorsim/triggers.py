# src/swtorsim/triggers.py
import random


_LIFECYCLE_TRIGGERS = frozenset({
    "on_apply",
    "on_refresh",
    "on_tick",
    "on_stack_charge_increased",
    "on_stack_charge_decreased",
})


class TriggerManager:
    def __init__(self):
        # Maps event_name -> list of compiled trigger dicts
        self._listeners = {}

    def subscribe(self, owner_id, ability, branch, caster, target, effect_key=None, effect_tags=None):
        """Registers every event-bus trigger rule defined on a branch independently."""
        for raw_trigger in getattr(branch, "triggers", []):
            event = raw_trigger.get("trigger")
            if not event or event in _LIFECYCLE_TRIGGERS:
                continue

            intervals = raw_trigger.get("intervals") or {}
            min_interval = float(intervals.get("interval_61", 0.0) or 0.0)

            entry = {
                "owner_id": owner_id,
                "effect_key": effect_key,
                "ability": ability,
                "branch": branch,
                "caster": caster,
                "target": target,
                # Pre-compile lists to frozensets once at registration time
                "tags": frozenset(raw_trigger.get("tags") or []),
                "excluded_tags": frozenset(raw_trigger.get("excluded_tags") or []),
                "ints": raw_trigger.get("ints") or {},
                "eff_results": frozenset(raw_trigger.get("effResults") or []),
                "proc_chance": (raw_trigger.get("floats") or {}).get("proc_chance_percent"),
                "min_interval": min_interval,
                "next_allowed_time": 0.0,
                "effect_tags": frozenset(effect_tags or ()),
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
            # 0. Internal cooldown / rate limit on trigger
            if sub["min_interval"] > 0.0 and sim.current_time < sub["next_allowed_time"]:
                continue

            # 1. Fast reject on excluded tags
            if sub["excluded_tags"] and (event_tags & sub["excluded_tags"]):
                continue

            # 2. Required tags check (OR match)
            if sub["tags"] and not (event_tags & sub["tags"]):
                continue

            # 3. Result filter (e.g. effResultCrit)
            if "effResultCrit" in sub["eff_results"] and not context.get("is_crit", False):
                continue

            # 4. Match on integer / spec flags
            ints = sub["ints"]
            if ints:
                spec_val = ints.get("ability_spec")
                if spec_val and spec_val != 0 and spec_val != "0":
                    ctx_spec = str(context.get("ability_spec") or "")
                    base_stem = str(spec_val).split(".")[-1]
                    if ctx_spec != str(spec_val) and not ctx_spec.endswith(f".{base_stem}_plus"):
                        continue

                dmg_type = ints.get("damage_type")
                if dmg_type and dmg_type not in (0, 5):
                    if context.get("damage_type") not in (None, dmg_type):
                        continue

                req_spell_type = ints.get("spell_type")
                if req_spell_type:
                    ctx_spell_type = context.get("spell_type")
                    if ctx_spell_type is not None and ctx_spell_type != req_spell_type:
                        continue

                req_weapon_mode = ints.get("weapon_mode")
                if req_weapon_mode and req_weapon_mode != 1:
                    if context.get("weapon_mode") != req_weapon_mode:
                        continue

            # 5. Proc chance check
            proc_chance = sub["proc_chance"]
            if proc_chance is not None and proc_chance < 100.0:
                if random.random() * 100.0 > proc_chance:
                    continue

            branch_ctx = {
                **context,
                "owner_id": sub["owner_id"],
                "owner_effect_key": sub["effect_key"],
                "owner_entity": sub["target"],
                "effect_tags": set(context.get("effect_tags") or ()) | set(sub.get("effect_tags") or ()),
            }
            ran = sub["ability"].execute_branch(
                sim,
                sub["branch"],
                sub["caster"],
                sub["target"],
                context=branch_ctx,
            )
            if ran:
                if sub["min_interval"] > 0.0:
                    sub["next_allowed_time"] = sim.current_time + sub["min_interval"]
