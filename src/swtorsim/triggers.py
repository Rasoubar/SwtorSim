"""Event-bus trigger subscription, filtering, rate-limiting (ICD), and dispatch engine."""

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


_RATE_LIMIT_STATS = frozenset({"229", "STAT_eff_trigger_rate_limit_modifier_fixed"})
_PROC_CHANCE_STATS = frozenset({"228", "STAT_eff_trigger_proc_chance_percent_modifier_fixed"})


def _collect_trigger_mods(caster):
    """Returns the caster's active (rate-limit, proc-chance) trigger modifiers, in effect order."""
    rate_limit_mods = []
    proc_chance_mods = []
    if hasattr(caster, "effects"):
        for eff in caster.effects.values():
            if getattr(eff, "is_expired", False):
                continue
            getter = getattr(eff, "get_effective_modifiers", None)
            eff_mods = getter() if getter is not None else getattr(eff, "modifiers", [])
            for mod in eff_mods:
                stat = str(mod.stat)
                if stat in _RATE_LIMIT_STATS:
                    rate_limit_mods.append(mod)
                elif stat in _PROC_CHANCE_STATS:
                    proc_chance_mods.append(mod)
    return rate_limit_mods, proc_chance_mods


class TriggerManager:
    """Manages reactive proc listeners, actor/tag/attack-type filtering, and rate-limit lockouts."""

    def __init__(self):
        # Maps event_name -> list of compiled trigger dicts
        self._listeners = {}
        # Maps owner_id -> events it has listeners on, so unsubscribe only touches those lists
        self._owner_events = {}

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
            # Trigger tags + owning effect tags: what 228/229 modifiers are matched against.
            entry["all_tags"] = entry["tags"] | entry["effect_tags"]
            self._listeners.setdefault(event, []).append(entry)
            self._owner_events.setdefault(owner_id, {})[event] = None

    def unsubscribe(self, owner_id):
        """Removes all triggers tied to a specific effect or passive instance."""
        events = self._owner_events.pop(owner_id, None)
        if not events:
            return
        for event in events:
            entries = self._listeners.get(event)
            if entries:
                self._listeners[event] = [sub for sub in entries if sub["owner_id"] != owner_id]

    def get_remaining_icd(self, source_fqn: str, current_time: float, caster=None) -> float:
        """Returns the maximum remaining trigger rate-limit lockout for the given ability FQN."""
        max_rem = 0.0
        for entries in self._listeners.values():
            for sub in entries:
                if caster is not None and sub.get("caster") is not caster:
                    continue
                abl = sub.get("ability")
                if getattr(abl, "fqn", None) == source_fqn:
                    next_time = float(sub.get("next_allowed_time", 0.0) or 0.0)
                    if next_time > current_time:
                        max_rem = max(max_rem, next_time - current_time)
        return max_rem

    def dispatch(self, event_name: str, sim, context: dict):
        """Filters incoming combat events and delegates execution to the ability."""
        entries = self._listeners.get(event_name)
        if not entries:
            return

        event_tags = frozenset(context.get("tags") or [])
        # Per-caster (rate-limit mods, proc-chance mods), valid until a branch runs and may change effects.
        trigger_mods = {}

        # Snapshot the list to allow cascading actions/triggers during iteration
        for sub in list(entries):
            caster = sub["caster"]

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
                    ctx_weapon_mode = context.get("weapon_mode") or 0
                    if ctx_weapon_mode != req_weapon_mode:
                        continue

            # The pure filters above run first; the modifier lookups below only for surviving listeners.
            abl_fqn = getattr(sub["ability"], "fqn", None)
            sub_tags = sub["all_tags"]
            mods = trigger_mods.get(id(caster))
            if mods is None:
                mods = trigger_mods[id(caster)] = _collect_trigger_mods(caster)
            rate_limit_mods, proc_chance_mods = mods

            # 5. Internal cooldown / rate limit on trigger (STAT_eff_trigger_rate_limit_modifier_fixed / 229)
            base_min_interval = sub["min_interval"]
            rate_limit_mod = 0.0
            for mod in rate_limit_mods:
                if mod.applies_to(ability_fqn=abl_fqn, ability_tags=sub_tags):
                    rate_limit_mod += float(mod.value)

            effective_interval = max(0.0, base_min_interval + rate_limit_mod)
            # Rate limits shrink with the caster's Alacrity (confirmed in game), unrounded, after the flat 229 mod.
            if effective_interval > 0.0:
                scale_time = getattr(caster, "scale_time_modifier", None)
                if scale_time is not None:
                    effective_interval = scale_time(effective_interval)
            if effective_interval > 0.0 and sim.current_time < sub["next_allowed_time"]:
                continue

            # 6. Proc chance check (STAT_eff_trigger_proc_chance_percent_modifier_fixed / 228)
            proc_chance = sub["proc_chance"]
            if proc_chance is not None:
                bonus_proc = 0.0
                for mod in proc_chance_mods:
                    if mod.applies_to(ability_fqn=abl_fqn, ability_tags=sub_tags):
                        # Stat 228 is a fraction (0.3 = +30 points); proc_chance is on a 0-100 scale.
                        bonus_proc += float(mod.value) * 100.0

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
                "is_proc": True,
                "trigger_name": event_name,
            }
            if effective_interval > 0.0:
                sub["next_allowed_time"] = sim.current_time + effective_interval
            ran = sub["ability"].execute_branch(
                sim,
                sub["branch"],
                sub["caster"],
                sub["target"],
                context=branch_ctx,
            )
            trigger_mods.clear()  # the branch may have applied, removed or restacked effects
            if ran and getattr(sim, "tracer", None) is not None:
                sim.tracer.record_proc_dispatch(
                    timestamp=sim.current_time,
                    trigger_name=event_name,
                    source_name=getattr(sub["ability"], "name", "Ability"),
                    effect_name=str(sub.get("effect_key") or getattr(sub["ability"], "name", "")),
                    passed=True,
                    reason="Trigger conditions satisfied",
                )
            if not ran and effective_interval > 0.0:
                sub["next_allowed_time"] = sim.current_time
