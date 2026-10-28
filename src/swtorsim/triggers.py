# src/swtorsim/triggers.py
import random


_LIFECYCLE_TRIGGERS = frozenset({
    "on_apply",
    "on_refresh",
    "on_tick",
    "on_stack_charge_increased",
    "on_stack_charge_decreased",
})

_TARGET_MATCH_TRIGGERS = frozenset({
    "on_damage_taken",
    "on_pre_damage_taken",
    "on_healing_taken",
    "on_pre_healing_taken",
    "on_death",
    "on_pre_death",
    "on_effect_received",
})

_CASTER_MATCH_TRIGGERS = frozenset({
    "on_damage_dealt",
    "on_pre_damage_dealt",
    "on_healing_dealt",
    "on_pre_healing_dealt",
    "on_kill",
    "on_effect_applied",
    "on_ability_activate",
    "on_ability_activated",
    "on_channeling_ended",
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
                "bools": raw_trigger.get("bools") or {},
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
            caster = sub["caster"]
            abl = sub["ability"]
            abl_fqn = getattr(abl, "fqn", None)
            all_sub_tags = set(sub["tags"]) | set(sub.get("effect_tags") or ())
            frozen_sub_tags = frozenset(all_sub_tags)

            # Fast reject if actor context does not match subscriber role
            if event_name in _TARGET_MATCH_TRIGGERS:
                ctx_target = context.get("target")
                sub_target = sub.get("target")
                if ctx_target is not None and sub_target is not None and ctx_target != sub_target:
                    continue

            if event_name in _CASTER_MATCH_TRIGGERS:
                ctx_caster = context.get("caster")
                sub_caster = sub.get("caster")
                if ctx_caster is not None and sub_caster is not None and ctx_caster != sub_caster:
                    continue

            # 0. Internal cooldown / rate limit on trigger (STAT_eff_trigger_rate_limit_modifier_fixed / 229)
            base_min_interval = sub["min_interval"]
            rate_limit_mod = 0.0
            if hasattr(caster, "effects"):
                for eff in caster.effects.values():
                    if getattr(eff, "is_expired", False):
                        continue
                    getter = getattr(eff, "get_effective_modifiers", None)
                    eff_mods = getter() if getter is not None else getattr(eff, "modifiers", [])
                    for mod in eff_mods:
                        if str(mod.stat) in ("229", "STAT_eff_trigger_rate_limit_modifier_fixed"):
                            if mod.applies_to(ability_fqn=abl_fqn, ability_tags=frozen_sub_tags):
                                rate_limit_mod += float(mod.value)

            effective_interval = max(0.0, base_min_interval + rate_limit_mod)
            if effective_interval > 0.0 and sim.current_time < sub["next_allowed_time"]:
                continue

            # 1. Fast reject on excluded tags
            if sub["excluded_tags"] and (event_tags & sub["excluded_tags"]):
                continue

            # 1b. Fast reject on boolean flags (e.g. is_successful on channel completion)
            bools = sub.get("bools") or {}
            if "is_successful" in bools and "is_successful" in context:
                if bools["is_successful"] != context["is_successful"]:
                    continue
            if "include_effect_refreshes" in bools and not bools["include_effect_refreshes"]:
                if context.get("include_effect_refreshes", False):
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
                    from src.swtorsim.settings import is_stem_matching_enabled
                    matches_spec = (ctx_spec == str(spec_val))
                    if not matches_spec and is_stem_matching_enabled() and ctx_spec.endswith(f".{base_stem}_plus"):
                        matches_spec = True
                    if not matches_spec:
                        continue

                dmg_type = ints.get("damage_type")
                if dmg_type and dmg_type not in (0, 5):
                    if context.get("damage_type") not in (None, dmg_type):
                        continue

                req_spell_type = ints.get("spell_type")
                if req_spell_type and req_spell_type != 1:
                    ctx_spell_type = context.get("spell_type")
                    if ctx_spell_type is not None and ctx_spell_type != req_spell_type:
                        continue

                req_weapon_mode = ints.get("weapon_mode")
                if req_weapon_mode and req_weapon_mode != 1:
                    if context.get("weapon_mode") != req_weapon_mode:
                        continue

            # 5. Proc chance check (STAT_eff_trigger_proc_chance_percent_modifier_fixed / 228)
            proc_chance = sub["proc_chance"]
            if proc_chance is not None:
                bonus_proc = 0.0
                if hasattr(caster, "effects"):
                    for eff in caster.effects.values():
                        if getattr(eff, "is_expired", False):
                            continue
                        getter = getattr(eff, "get_effective_modifiers", None)
                        eff_mods = getter() if getter is not None else getattr(eff, "modifiers", [])
                        for mod in eff_mods:
                            if str(mod.stat) in ("228", "STAT_eff_trigger_proc_chance_percent_modifier_fixed"):
                                if mod.applies_to(ability_fqn=abl_fqn, ability_tags=frozen_sub_tags):
                                    val = float(mod.value)
                                    if abs(val) <= 1.0:
                                        bonus_proc += val * 100.0
                                    else:
                                        bonus_proc += val

                effective_proc = min(100.0, max(0.0, proc_chance + bonus_proc))
                if effective_proc < 100.0:
                    if random.random() * 100.0 > effective_proc:
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
                if effective_interval > 0.0:
                    sub["next_allowed_time"] = sim.current_time + effective_interval
