import random
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path
from src.swtorsim.combat_math import accuracy_roll
from src.swtorsim.entities import Dummy, Player
from src.swtorsim.events import ChargeRestoreEvent, DamageHit, ResourceGainEvent
from src.swtorsim.requirements import validate_all



# --- Effect Data Structures & Execution ---


def _resolve_target_overrides(overrides, current_target, caster, context=None):
    """Resolves extracted target_overrides against caster, enemy_target, and trigger context."""
    if not overrides:
        return current_target
    enemy_target = (
        (context or {}).get("enemy_target")
        or getattr(caster, "current_target", None)
        or current_target
    )
    resolved = current_target
    for override in overrides:
        o_type = override.get("type") if isinstance(override, dict) else None
        if o_type == "caster":
            resolved = caster
        elif o_type in ("aoe_sphere", "aoe_cone", "enemies_list", "primary_target"):
            resolved = enemy_target
        elif o_type in ("party_members"):
            # In single-actor simulation, party members resolves to caster
            resolved = caster
        elif o_type == "trigger_target" and context and "target" in context:
            resolved = context["target"]
        elif o_type == "trigger_caster" and context and "caster" in context:
            resolved = context["caster"]
    return resolved


@dataclass(slots=True)
class Branch:
    index: int
    triggers: List[Dict[str, Any]] = field(default_factory=list)
    conditions: Optional[Dict[str, Any]] = None
    actions: List[Dict[str, Any]] = field(default_factory=list)
    target_overrides: List[Dict[str, Any]] = field(default_factory=list)
    run_if_none_ran: List[int] = field(default_factory=list)
    is_attack: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Branch":
        return cls(
            index=data.get("index", 0),
            triggers=data.get("triggers", []),
            conditions=data.get("conditions"),
            actions=data.get("actions", []),
            target_overrides=data.get("target_overrides", []),
            run_if_none_ran=data.get("run_if_none_ran", []),
            is_attack=(
                bool(data["is_attack"])
                if "is_attack" in data
                else any(
                    isinstance(a, dict) and a.get("action_type") == "damage"
                    for a in data.get("actions", [])
                )
            ),
        )

    def execute(self, sim, caster, target, context=None, ability=None) -> tuple[bool, bool]:
        """
        Evaluates branch conditions and executes actions.
        Returns: (ran, success)
          - ran: True if conditions passed and actions were attempted.
          - success: False only if an action failed (e.g. accuracy miss).
        """
        # 1. Target overrides
        actual_target = _resolve_target_overrides(self.target_overrides, target, caster, context)

        # 2. Branch conditions (failing conditions skips the branch, not an attack miss)
        if self.conditions:
            if not validate_all(self.conditions, caster, actual_target, sim=sim, context=context):
                return False, True

        # 3. Actions execution
        source_name = ability.name if ability else "Unknown"
        for action in self.actions:
            success = execute_single_action(
                sim, caster, actual_target, action, source_name, ability=ability, context=context
            )
            if not success:
                return True, False

        return True, True


@dataclass(slots=True)
class Effect:
    number: int
    entry: bool
    duration: float = 0.0
    tick_interval: float = 0.0
    eff_ignore_alacrity: bool = False
    is_passive: bool = False
    name: Optional[str] = None
    icon: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    branches: List[Any] = field(default_factory=list)
    stack_charge: Optional[Dict[str, Any]] = None
    conditions: Optional[Dict[str, Any]] = None
    target_overrides: List[Any] = field(default_factory=list)
    initializers: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Effect":
        initializers = list(data.get("initializers") or [])
        is_passive = any(
            init.get("initializer_type") == "eff_initializer__set_passive"
            and init.get("bools", {}).get("is_passive", False)
            for init in initializers
            if isinstance(init, dict)
        )

        raw_duration = data.get("duration")
        raw_tick = data.get("tick_interval")

        return cls(
            number=data["number"],
            entry=bool(data.get("entry", False)),
            duration=float(raw_duration) if raw_duration is not None else 0.0,
            tick_interval=float(raw_tick) if raw_tick is not None else 0.0,
            eff_ignore_alacrity=bool(data.get("effIgnoreAlacrity", False)),
            is_passive=is_passive,
            name=data.get("name"),
            icon=data.get("icon"),
            tags=data.get("tags") or [],
            branches=[Branch.from_dict(b) for b in data.get("branches", [])],
            stack_charge=data.get("stack_charge"),
            conditions=data.get("conditions"),
            target_overrides=list(data.get("target_overrides") or []),
            initializers=initializers,
        )

    @property
    def is_persistent(self) -> bool:
        """True if the effect is a timed buff/debuff or permanent passive."""
        return self.duration > 0.0 or self.is_passive

    @property
    def is_instant(self) -> bool:
        """True if the effect evaluates immediately and does not live on an actor."""
        return not self.is_persistent

    def execute_triggered_branches(
        self,
        trigger_name: str,
        sim,
        caster,
        target,
        context=None,
        ability=None,
        include_untriggered: bool = False,
        tick_number: Optional[int] = None,
    ):
        """Executes branches matching trigger_name (and optionally untriggered branches)."""
        branch_context = dict(context) if context else {}
        existing_tags = set(branch_context.get("effect_tags") or ())
        branch_context["effect_tags"] = existing_tags | set(self.tags or ())
        branch_context["effect"] = self
        executed_branches = set()
        for branch in self.branches:
            triggers = getattr(branch, "triggers", [])
            if not triggers:
                if not include_untriggered:
                    continue
            else:
                matched = False
                for t in triggers:
                    if t.get("trigger") != trigger_name:
                        continue
                    if trigger_name == "on_tick" and tick_number is not None:
                        t_num = t.get("tick_number") or 0
                        if t_num not in (0, tick_number):
                            continue
                    if trigger_name in ("on_stack_charge_increased", "on_stack_charge_decreased"):
                        ints = t.get("ints") or {}
                        req_count = ints.get("count") if "count" in ints else t.get("count")
                        if req_count is not None and int(req_count) > 0:
                            current_stacks = branch_context.get("current_stacks")
                            if current_stacks is not None and int(current_stacks) < int(req_count):
                                continue
                    if trigger_name == "on_channeling_ended":
                        bools = t.get("bools") or {}
                        if "is_successful" in bools and "is_successful" in branch_context:
                            if bools["is_successful"] != branch_context["is_successful"]:
                                continue
                    matched = True
                    break
                if not matched:
                    continue

            if branch.run_if_none_ran and any(b in executed_branches for b in branch.run_if_none_ran):
                continue

            ran, success = branch.execute(sim, caster, target, context=branch_context, ability=ability)
            if ran:
                executed_branches.add(branch.index)
            if not success and getattr(branch, "is_attack", False):
                break

    def schedule_timer_branches(self, sim, caster, target, context=None, ability=None):
        """Schedules any branches triggered on on_timer_expired at sim.current_time + delay."""
        if sim is None:
            return
        branch_context = dict(context) if context else {}
        existing_tags = set(branch_context.get("effect_tags") or ())
        branch_context["effect_tags"] = existing_tags | set(self.tags or ())
        branch_context["effect"] = self

        for branch in self.branches:
            triggers = getattr(branch, "triggers", [])
            for t in triggers:
                if t.get("trigger") == "on_timer_expired":
                    delay = float(t.get("delay", 0.0) or 0.0)
                    if delay > 0.0:
                        from src.swtorsim.events import DelayedBranchEvent

                        sim.schedule_relative(
                            delay,
                            DelayedBranchEvent(
                                branch,
                                caster,
                                target,
                                ability=ability,
                                context=branch_context,
                            ),
                        )
                    break

    def execute(self, sim, caster, target, context=None, ability=None):
        """Resolves an effect: routes persistent effects to actor, or resolves instant branches."""
        effect_target = _resolve_target_overrides(self.target_overrides, target, caster, context)
        if not self.target_overrides:
            has_caster_trigger = any(
                t.get("trigger") in ("on_damage_dealt", "on_ability_activated")
                for b in self.branches
                for t in getattr(b, "triggers", [])
            )
            if has_caster_trigger:
                effect_target = caster

        if self.conditions:
            if not validate_all(self.conditions, caster, effect_target, sim=sim, context=context):
                return

        if hasattr(effect_target, "is_immune_to_effect") and effect_target.is_immune_to_effect(self):
            return

        if self.is_persistent:
            effect_key = (
                self.name
                or f"{getattr(ability, 'name', None) or getattr(ability, 'fqn', '')}:{self.number}"
            )
            existing = effect_target.effects.get(effect_key)
            was_refreshed = existing is not None and not getattr(existing, "is_expired", False)
            old_stacks = getattr(existing, "stacks", 0) if was_refreshed else 0
            effect_key, effect_instance, duration = effect_target.apply_effect(sim, ability, self, caster)
            if caster is not None and getattr(caster, "active_channel", None) is not None:
                active_chan = caster.active_channel
                if getattr(active_chan, "ability", None) is ability or getattr(ability, "fqn", None) == getattr(getattr(active_chan, "ability", None), "fqn", None):
                    if hasattr(active_chan, "attached_effects"):
                        active_chan.attached_effects.append((effect_target, effect_key, effect_instance))
            cur_stacks = getattr(effect_instance, "stacks", 1)
            stack_increased = was_refreshed and (cur_stacks > old_stacks)

            branch_ctx = dict(context) if context else {}
            branch_ctx["stack_multiplier"] = cur_stacks
            branch_ctx["current_stacks"] = cur_stacks
            branch_ctx["active_effect"] = effect_instance
            branch_ctx["owner_effect_key"] = effect_key
            branch_ctx["owner_entity"] = effect_target
            branch_ctx["effect"] = self

            self.execute_triggered_branches(
                "on_refresh" if was_refreshed else "on_apply",
                sim,
                caster,
                effect_target,
                context=branch_ctx,
                ability=ability,
                include_untriggered=False,
            )
            if stack_increased:
                self.execute_triggered_branches(
                    "on_stack_charge_increased",
                    sim,
                    caster,
                    effect_target,
                    context=branch_ctx,
                    ability=ability,
                    include_untriggered=False,
                )
                if sim is not None and hasattr(sim, "triggers"):
                    sim.triggers.dispatch(
                        "on_stack_charge_increased",
                        sim,
                        {
                            **branch_ctx,
                            "caster": caster,
                            "target": effect_target,
                        },
                    )
            self.schedule_timer_branches(sim, caster, effect_target, context=branch_ctx, ability=ability)
            return

        self.execute_triggered_branches(
            "on_apply",
            sim,
            caster,
            effect_target,
            context=context,
            ability=ability,
            include_untriggered=True,
        )
        self.schedule_timer_branches(sim, caster, effect_target, context=context, ability=ability)


@dataclass(slots=True)
class AbilityBlueprint:
    fqn: str
    name: str
    type: str  # "active" or "passive"
    energy_cost: float
    base_gcd: float
    cooldown: float
    triggers_gcd: bool = False
    tags: List[str] = field(default_factory=list)
    icon: Optional[str] = None
    max_charges: Optional[int] = None
    abl_ignore_alacrity: bool = False
    activation: Optional[Dict[str, Any]] = None
    conditions: Optional[Dict[str, Any]] = None
    stat_changes: List[Dict[str, Any]] = field(default_factory=list)
    effects: Dict[int, Effect] = field(default_factory=dict)
    entry_effect_ids: List[int] = field(default_factory=list)
    file_path: Optional[Path] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any], file_path: Optional[Path] = None) -> "AbilityBlueprint":
        effects_map: Dict[int, Effect] = {}
        entry_ids: List[int] = []

        for eff_data in data.get("effects") or []:
            effect = Effect.from_dict(eff_data)
            effects_map[effect.number] = effect
            if effect.entry:
                entry_ids.append(effect.number)

        # 1. Default missing type to "passive"
        ability_type = data.get("type") or "passive"

        raw_cost = data.get("energy_cost")
        raw_gcd = data.get("base_gcd")
        raw_cd = data.get("cooldown")
        raw_charges = data.get("max_charges")

        # 2. Derive base_gcd and triggers_gcd correctly based on ability_type
        if raw_gcd is not None:
            base_gcd = float(raw_gcd)
        else:
            base_gcd = 1.5 if ability_type == "active" else 0.0

        if "triggers_gcd" in data:
            triggers_gcd = bool(data["triggers_gcd"])
        else:
            triggers_gcd = (ability_type == "active")

        return cls(
            fqn=data.get("fqn") or "",
            name=data.get("name") or "Unknown Ability",
            type=ability_type,
            energy_cost=float(raw_cost) if raw_cost is not None else 0.0,
            base_gcd=base_gcd,
            cooldown=float(raw_cd) if raw_cd is not None else 0.0,
            triggers_gcd=triggers_gcd,
            tags=data.get("tags") or [],
            icon=data.get("icon"),
            max_charges=int(raw_charges) if raw_charges is not None else None,
            abl_ignore_alacrity=bool(data.get("ablIgnoreAlacrity", False)),
            activation=data.get("activation"),
            conditions=data.get("conditions"),
            stat_changes=list(data.get("stat_changes") or []),
            effects=effects_map,
            entry_effect_ids=entry_ids,
            file_path=file_path,
        )

    @classmethod
    def from_file(cls, filepath: Path) -> "AbilityBlueprint":
        with filepath.open("r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f), file_path=filepath)
# --- Action Handlers ---

NOOP_ACTION_TYPES = frozenset(
    {
        "ballistic_impulse",
        "ballistic_to_caster",
        "teleport_to_target",
        "dive_to_point",
        "swap_caster_position_with_target",
        "stun",
        "mark_as_neutralized",
        "taunt",
        "taunt_damage_reduce",
        "ability_interrupt",
        "ability_activate",
        "ability_deactivate",
        "set_posture",
        "revive",
        "summon_pet",
        "execute_hydra_hook",
        "custom",
        "modify_stat",
        "modify_meta_stat",
        "apply_conditional_stat_mod",
        "apply_conditional_meta_stat_mod",
        "heal",
        "regen_health",
        "spend_health",
        "absorb_damage",
        "reflect_damage",
        "redirect_damage",
        "grant_temporary_ability_package",
        "god_damage",
        "insta_kill",
    }
)


def execute_single_action(sim, caster, target, action, source_name, ability=None, context=None):
    """Calls the appropriate function for the action type."""
    if not validate_all(action.get("conditions", {}), caster, target, sim=sim, context=context):
        return False
    if "chance" in action and random.random() > action["chance"]:
        return False

    action_type = action.get("action_type")
    delay = action.get("delay", 0.0)

    if action_type == "damage":
        return handle_damage_action(sim, caster, target, action, source_name, delay, ability=ability, context=context)
    elif action_type in (
        "resource_gain",
        "energy_recovery",
        "regen_force",
        "regen_energy",
        "restore_action_points",
    ):
        handle_resource_gain_action(sim, caster, action, delay, ability=ability)
    elif action_type in ("spend_energy", "spend_force"):
        handle_resource_spend_action(caster, action)
    elif action_type in ("cooldown_mod", "modify_cooldown", "modify_recharge_time"):
        handle_cooldown_modification(sim, caster, action)
    elif action_type in ("grant_charge", "modify_ability_stack_charge"):
        handle_restore_charge(sim, caster, action)
    elif action_type == "modify_stack_charge":
        handle_modify_stack_charge(sim, caster, target, action, context=context)
    elif action_type == "set_effect_stack_charge":
        handle_set_effect_stack_charge(sim, caster, target, action, ability=ability, context=context)
    elif action_type in ("buff_remove", "remove_effect", "dispel"):
        handle_buff_remove_action(sim, caster, target, action, ability=ability, context=context)
    elif action_type == "execute_ability":
        handle_execute_ability(sim, caster, target, action)
    elif action_type == "invoke_projectile":
        handle_invoke_projectile(sim, caster, target, action, ability=ability, context=context)
    elif action_type == "reset_timer":
        handle_reset_timer(sim, caster, target, action, ability=ability, context=context)
    elif action_type == "modify_active_duration":
        handle_modify_active_duration(sim, caster, target, action, ability=ability, context=context)
    elif action_type == "take_cover":
        handle_take_cover(caster, target, action, is_portable=False)
    elif action_type == "take_portable_cover":
        handle_take_cover(caster, target, action, is_portable=True)
    elif action_type == "leave_cover":
        handle_leave_cover(caster, target, action)
    elif action_type == "become_stealthed":
        handle_become_stealthed(caster, target, action)
    elif action_type == "enter_combat":
        handle_enter_combat(caster, target, action, sim=sim)
    elif action_type == "exit_combat":
        handle_exit_combat(caster, target, action, sim=sim)
    elif action_type == "ability_cancel":
        handle_ability_cancel(caster, target, action)
    elif action_type == "cooldown":
        handle_cooldown_action(sim, caster, action, ability=ability, context=context)
    elif action_type == "global_cooldown":
        handle_global_cooldown(sim, caster, action)
    elif action_type == "custom":
        handle_custom_action(sim, caster, target, action, context=context)
    elif action_type == "grant_immunity":
        handle_grant_immunity(sim, caster, target, action, context=context)
    elif action_type == "call_effect":
        if ability and "effect" in action:
            call_target = caster if action.get("to_actor") == "caster" else target
            ability.execute_effect(action["effect"], caster, call_target, sim, context=context)
    elif action_type in NOOP_ACTION_TYPES:
        pass
    else:
        raise ValueError(
            f"CRITICAL ENGINE ERROR: Unrecognized action_type '{action_type}' "
            f"triggered by '{source_name}'. Please check your JSON blueprints."
        )
    return True


def _find_target_abilities(caster, action):
    """Resolves target Ability instances from caster.ability_db using legacy or extracted action keys."""
    ability_db = getattr(caster, "ability_db", {})
    if not ability_db:
        return []

    ints = action.get("ints") or {}
    strings = action.get("strings") or {}
    spec = action.get("target_ability") or action.get("ability_spec") or ints.get("ability_spec")

    tag_set = set(action.get("target_tags") or []) | set(action.get("tags") or [])
    for k in ("tag", "tags"):
        val = strings.get(k)
        if val:
            tag_set.update(t.strip() for t in val.split(",") if t.strip())

    matched = []
    seen_ids = set()
    base_stem = str(spec).split(".")[-1] if spec else ""
    for key, abl in ability_db.items():
        if id(abl) in seen_ids:
            continue
        if spec and spec != 0:
            abl_fqn = getattr(abl, "fqn", "") or ""
            from src.swtorsim.settings import is_stem_matching_enabled
            if (
                key == spec
                or abl_fqn == spec
                or getattr(abl, "name", None) == spec
                or (is_stem_matching_enabled() and base_stem and abl_fqn.endswith(f".{base_stem}_plus"))
            ):
                matched.append(abl)
                seen_ids.add(id(abl))
                continue
        if tag_set and (tag_set & set(getattr(abl, "tags", ()))):
            matched.append(abl)
            seen_ids.add(id(abl))
    return matched


def handle_damage_action(sim, caster, target, action, source_name, delay, ability=None, context=None):
    """Rolls accuracy then schedules or executes the hit (accounting for flurry multi-blow actions)."""
    hand = action.get("hand", "main")
    if hand == "off" and getattr(caster, "stats", {}).get("Off_hand_max", 0) <= 0:
        return True
    is_periodic = bool((context or {}).get("is_periodic", False)) or any(
        t.endswith(".periodic_damage") or t == "tag.abl.debuff.damage_over_time"
        for t in (context or {}).get("effect_tags", ())
    )

    flurry_count = int(action.get("flurry_max") or action.get("flurry_min") or 1)
    if flurry_count < 1:
        flurry_count = 1

    combined_tags = (
        set(action.get("tags") or ())
        | set(getattr(ability, "tags", ()) or ())
        | set((context or {}).get("effect_tags") or ())
    )
    from_proc = getattr(ability, "type", "active") == "passive"
    action_data = dict(action)
    action_data["is_periodic"] = is_periodic

    # Resolve canonical attack_type (1 Melee, 2 Ranged, 3 Force, 4 Tech) and spell_type (1 Weapon, 2 Tech, 3 Force)
    ability_fqn = getattr(ability, "fqn", "") or ""
    tags_str = " ".join(str(t).lower() for t in combined_tags)
    is_tech = (
        "tech_attack" in tags_str
        or "tech_ability" in tags_str
        or any(cls in ability_fqn.lower() for cls in (".agent.", ".smuggler.", ".bounty_hunter.", ".trooper."))
        or (getattr(caster, "stats", {}).get("Tech Power", 0.0) > 0 and getattr(caster, "stats", {}).get("Force Power", 0.0) <= 0)
    )

    if "hand" in action:
        action_data.setdefault("spell_type", 1)
        slots = set(str(s) for s in (action.get("slots") or ()))
        if slots & {"2", "4"}:
            action_data["attack_type"] = 2
        elif slots & {"3", "5"}:
            action_data["attack_type"] = 1
        elif "attack_type" not in action_data or action_data["attack_type"] == 1:
            is_ranged = (
                "ranged_attack" in tags_str
                or "ranged_ability" in tags_str
                or any(cls in ability_fqn.lower() for cls in (".agent.", ".smuggler.", ".bounty_hunter.", ".trooper."))
            )
            action_data["attack_type"] = 2 if is_ranged else 1
    else:
        if is_tech:
            action_data["attack_type"] = 4
            action_data.setdefault("spell_type", 2)
        else:
            action_data["attack_type"] = 3
            action_data.setdefault("spell_type", 3)

    stack_mult = (context or {}).get("stack_multiplier", 1)

    base_coeff = float(action.get("coeff", 0.0) or 0.0) * stack_mult
    base_shp_min = float(action.get("shp_min", 0.0) or 0.0) * stack_mult
    base_shp_max = float(action.get("shp_max", 0.0) or 0.0) * stack_mult
    raw_amp = float(action.get("amp", 0.0) or 0.0)

    if flurry_count > 1:
        action_data["coeff"] = base_coeff / flurry_count
        action_data["shp_min"] = base_shp_min / flurry_count
        action_data["shp_max"] = base_shp_max / flurry_count
        action_data["amp"] = ((1.0 + raw_amp) / flurry_count) - 1.0
    else:
        action_data["coeff"] = base_coeff
        action_data["shp_min"] = base_shp_min
        action_data["shp_max"] = base_shp_max

    hit_any = False
    for i in range(flurry_count):
        if not accuracy_roll(
            caster,
            hand=hand,
            attack_type=action_data.get("attack_type", 1),
            ability_fqn=getattr(ability, "fqn", None),
            action_tags=combined_tags,
            target=target,
        ):
            continue
        hit_any = True
        hit_event = DamageHit(
            caster,
            target,
            action_data,
            source_name,
            tags=combined_tags,
            from_proc=from_proc,
            ability_fqn=getattr(ability, "fqn", None),
        )
        if delay > 0.0:
            sim.schedule_relative(delay, hit_event)
        else:
            hit_event.resolve(sim)

    return hit_any


def handle_resource_gain_action(sim, caster, action, delay: float = 0.0, ability: Any = None):
    """Schedules or executes the resource gain event (legacy & extracted schemas)."""
    floats = action.get("floats") or {}
    flat = (
        action.get("value")
        or action.get("max")
        or action.get("min")
        or floats.get("amount")
        or floats.get("amount_max")
        or floats.get("amount_min")
        or 0.0
    )
    pct = (
        action.get("percent")
        or floats.get("amount_percent")
        or floats.get("amount_percent_of_max")
        or 0.0
    )
    max_res = getattr(getattr(caster, "resource", None), "max_value", 0.0) or 0.0
    regen = float(flat) + float(pct) * float(max_res)
    if regen <= 0.0:
        return
    # Evaluate action resource restore modifiers
    pct_bonus = 0.0
    flat_bonus = 0.0
    if hasattr(caster, "effects"):
        pool_type = getattr(getattr(caster, "resource", None), "pool_type", "").lower()
        is_ap = pool_type in ("rage", "focus")
        is_force = pool_type in ("force",)
        is_tech = pool_type in ("energy", "heat", "ammo")

        abl_fqn = getattr(ability, "fqn", None)
        abl_tags = getattr(ability, "tags", frozenset()) or frozenset()
        if not isinstance(abl_tags, frozenset):
            abl_tags = frozenset(abl_tags)

        for eff in caster.effects.values():
            if getattr(eff, "is_expired", False):
                continue
            getter = getattr(eff, "get_effective_modifiers", None)
            eff_mods = getter() if getter is not None else getattr(eff, "modifiers", [])
            for mod in eff_mods:
                stat = str(mod.stat)
                val = float(mod.value)

                if is_ap:
                    if stat in ("91", "STAT_eff_action_restore_action_points_modifier_percentage"):
                        if not mod.targets or mod.applies_to(ability_fqn=abl_fqn, ability_tags=abl_tags):
                            pct_bonus += val
                    elif stat in ("90", "STAT_eff_action_restore_action_points_modifier_fixed"):
                        if not mod.targets or mod.applies_to(ability_fqn=abl_fqn, ability_tags=abl_tags):
                            flat_bonus += val

                elif is_force:
                    if stat in ("93", "STAT_eff_action_restore_force_modifier_percentage"):
                        if not mod.targets or mod.applies_to(ability_fqn=abl_fqn, ability_tags=abl_tags):
                            pct_bonus += val
                    elif stat in ("92", "STAT_eff_action_restore_force_modifier_fixed"):
                        if not mod.targets or mod.applies_to(ability_fqn=abl_fqn, ability_tags=abl_tags):
                            flat_bonus += val

                elif is_tech:
                    if stat in ("95", "STAT_eff_action_restore_energy_modifier_percentage"):
                        if not mod.targets or mod.applies_to(ability_fqn=abl_fqn, ability_tags=abl_tags):
                            pct_bonus += val
                    elif stat in ("94", "STAT_eff_action_restore_energy_modifier_fixed"):
                        if not mod.targets or mod.applies_to(ability_fqn=abl_fqn, ability_tags=abl_tags):
                            flat_bonus += val

    regen = max(0.0, (regen * (1.0 + pct_bonus)) + flat_bonus)
    if regen <= 0.0:
        return

    gain_event = ResourceGainEvent(caster, regen)
    if delay > 0.0:
        sim.schedule_relative(delay, gain_event)
    else:
        gain_event.resolve(sim)


def handle_resource_spend_action(caster, action):
    """Spends resources for extracted spend_energy / spend_force actions."""
    resource = getattr(caster, "resource", None)
    if resource is None:
        return
    floats = action.get("floats") or {}
    flat = floats.get("amount", 0.0)
    pct_max = floats.get("amount_percent_of_max", 0.0)
    pct_cur = floats.get("amount_percent_of_current", 0.0)
    spend = (
        float(flat)
        + float(pct_max) * float(getattr(resource, "max_value", 0.0))
        + float(pct_cur) * float(getattr(resource, "current_value", 0.0))
    )
    if spend > 0.0:
        resource.spend(spend)


def handle_cooldown_modification(sim, caster, action):
    """Applies cooldown or recharge reductions/resets to targeted abilities."""
    cooldown_dict = getattr(caster, "cooldowns", {})
    floats = action.get("floats") or {}
    bools = action.get("bools") or {}
    action_type = action.get("action_type")
    is_pct = bool(bools.get("is_percentage", False))
    amount = float(action.get("value", floats.get("amount", 0.0)))
    is_reset = bool(action.get("reset", False)) or (is_pct and amount <= -1.0)

    for abl in _find_target_abilities(caster, action):
        if action_type == "modify_recharge_time":
            if is_pct:
                abl.recharge_time = max(0.0, abl.recharge_time * (1.0 + amount))
            else:
                abl.recharge_time = max(0.0, abl.recharge_time + amount)
            continue

        for cd_key in (abl.name, abl.fqn):
            if cd_key not in cooldown_dict:
                continue
            if cooldown_dict[cd_key] <= sim.current_time:
                del cooldown_dict[cd_key]
                continue
            if is_reset:
                del cooldown_dict[cd_key]
            else:
                delta = (amount * abl.cooldown) if is_pct else amount
                new_cd = max(sim.current_time, cooldown_dict[cd_key] + delta)
                if new_cd <= sim.current_time:
                    del cooldown_dict[cd_key]
                else:
                    cooldown_dict[cd_key] = new_cd


def handle_restore_charge(sim, caster, action):
    """Modifies charges on the target ability (legacy grant_charge & extracted modify_ability_stack_charge)."""
    floats = action.get("floats") or {}
    raw_amount = action.get(
        "amount",
        floats.get("amount_min", floats.get("amount_max", 1)),
    )
    amount = int(round(float(raw_amount)))
    if amount == 0:
        return

    for ability in _find_target_abilities(caster, action):
        if amount > 0:
            ability.restore_charge(caster, sim, amount=amount, from_timer=False)
        else:
            for _ in range(abs(amount)):
                ability.consume_charge(caster, sim)


def handle_modify_stack_charge(sim, caster, target, action, context=None):
    """Modifies stacks on an active effect (e.g. Deathmark consuming a stack, Deadly Saber charges)."""
    floats = action.get("floats") or {}
    delta = int(round(float(floats.get("amount_min", floats.get("amount_max", 0.0)))))
    if delta == 0:
        return

    owner_entity = (context or {}).get("owner_entity") or target
    owner_key = (context or {}).get("owner_effect_key")
    eff = getattr(owner_entity, "effects", {}).get(owner_key) if owner_key else None

    # Search by tag if owner_key not resolved or if action specifies tags
    search_tags = set(action.get("tags") or [])
    tag_str = (action.get("strings") or {}).get("tag")
    if tag_str:
        search_tags.add(tag_str)

    if (eff is None or getattr(eff, "is_expired", False)) and search_tags:
        for k, e in getattr(owner_entity, "effects", {}).items():
            if not getattr(e, "is_expired", False) and (set(getattr(e, "tags", ())) & search_tags):
                eff = e
                owner_key = k
                break
        if eff is None and caster is not None and caster is not owner_entity:
            for k, e in getattr(caster, "effects", {}).items():
                if not getattr(e, "is_expired", False) and (set(getattr(e, "tags", ())) & search_tags):
                    eff = e
                    owner_key = k
                    owner_entity = caster
                    break

    if eff is None or getattr(eff, "is_expired", False):
        return

    old_stacks = eff.stacks
    eff.modify_stacks(delta)
    cur_stacks = eff.stacks

    if delta > 0 and cur_stacks > old_stacks:
        blueprint = getattr(eff, "effect_blueprint", None)
        if blueprint and hasattr(blueprint, "execute_triggered_branches"):
            ctx = {
                **(context or {}),
                "stack_multiplier": cur_stacks,
                "owner_effect_key": owner_key,
                "owner_entity": owner_entity,
            }
            blueprint.execute_triggered_branches(
                "on_stack_charge_increased",
                sim,
                getattr(eff, "caster_ref", caster),
                owner_entity,
                context=ctx,
                ability=getattr(eff, "ability_ref", None),
                include_untriggered=False,
            )
        if sim is not None and hasattr(sim, "triggers"):
            sim.triggers.dispatch(
                "on_stack_charge_increased",
                sim,
                {
                    **(context or {}),
                    "caster": caster,
                    "target": owner_entity,
                    "stack_multiplier": cur_stacks,
                },
            )
    elif delta < 0 and sim is not None and hasattr(sim, "triggers") and not (context or {}).get("from_stack_event"):
        sim.triggers.dispatch(
            "on_stack_charge_decreased",
            sim,
            {
                **(context or {}),
                "caster": caster,
                "target": owner_entity,
                "from_stack_event": True,
            },
        )
    if getattr(eff, "stacks", 1) <= 0:
        owner_entity.cleanup_expired_effects([owner_key])


def handle_set_effect_stack_charge(sim, caster, target, action, ability=None, context=None):
    """Sets stacks on an active effect to a fixed value (e.g. Ward of the Continuum capping Dark Ward at 10 charges)."""
    floats = action.get("floats") or {}
    amount_raw = floats.get(
        "amount",
        floats.get(
            "amount_min",
            floats.get(
                "amount_max",
                action.get("amount", action.get("value", action.get("count", 0.0))),
            ),
        ),
    )
    target_stacks = int(round(float(amount_raw)))

    owner_entity = (context or {}).get("owner_entity") or target
    owner_key = (context or {}).get("owner_effect_key")
    eff = getattr(owner_entity, "effects", {}).get(owner_key) if owner_key else None

    # Search by tag or ability_spec if owner_key not resolved or if action specifies tags/spec
    search_tags = set(action.get("tags") or [])
    tag_str = (action.get("strings") or {}).get("tag")
    if tag_str:
        search_tags.add(tag_str)
    spec = (action.get("ints") or {}).get("ability_spec") or action.get("ability_spec")
    if spec == 0:
        spec = None

    if (eff is None or getattr(eff, "is_expired", False)) and (search_tags or spec):
        for k, e in getattr(owner_entity, "effects", {}).items():
            if getattr(e, "is_expired", False):
                continue
            eff_tags = set(getattr(e, "tags", ()))
            eff_spec = getattr(e, "fqn", "") or getattr(getattr(e, "ability_ref", None), "fqn", "")
            if (search_tags and eff_tags & search_tags) or (spec and spec == eff_spec):
                eff = e
                owner_key = k
                break
        if eff is None and caster is not None and caster is not owner_entity:
            for k, e in getattr(caster, "effects", {}).items():
                if getattr(e, "is_expired", False):
                    continue
                eff_tags = set(getattr(e, "tags", ()))
                eff_spec = getattr(e, "fqn", "") or getattr(getattr(e, "ability_ref", None), "fqn", "")
                if (search_tags and eff_tags & search_tags) or (spec and spec == eff_spec):
                    eff = e
                    owner_key = k
                    owner_entity = caster
                    break

    if eff is None or getattr(eff, "is_expired", False):
        return

    eff.set_stacks(target_stacks)

    if getattr(eff, "scales_with_stacks", False) and getattr(eff, "modifiers", None):
        if hasattr(owner_entity, "recalculate_stats"):
            owner_entity.recalculate_stats()

    if getattr(eff, "stacks", 1) <= 0:
        owner_entity.cleanup_expired_effects([owner_key])


def handle_buff_remove_action(sim, caster, target, action, ability=None, context=None):
    """Removes active effects from caster/target (buff_remove, remove_effect, dispel)."""
    action_type = action.get("action_type")
    effect_name = action.get("effect_name")
    if effect_name and caster.has_effect(effect_name):
        caster.cleanup_expired_effects([effect_name])
        print(f"[{sim.current_time:.3f}] {caster.name} consumed/removed buff: {effect_name}")
        return

    if action_type == "remove_effect":
        owner_key = (context or {}).get("owner_effect_key")
        owner_entity = (context or {}).get("owner_entity")
        if owner_key and owner_entity is not None and owner_key in getattr(owner_entity, "effects", {}):
            owner_entity.cleanup_expired_effects([owner_key])
            return
        if ability is not None:
            for actor in (caster, target):
                effects_dict = getattr(actor, "effects", {})
                to_remove = [
                    k for k, eff in effects_dict.items()
                    if not getattr(eff, "is_passive", False)
                    and not any("lockout" in t for t in getattr(eff, "tags", ()))
                    and (getattr(eff, "fqn", None) == ability.fqn or k == ability.name)
                ]
                if to_remove:
                    actor.cleanup_expired_effects(to_remove)
        return

    if action_type == "dispel":
        ints = action.get("ints") or {}
        strings = action.get("strings") or {}
        spec = ints.get("ability_spec")
        dispel_tags = set(action.get("tags") or [])
        if strings.get("tag"):
            dispel_tags.add(strings["tag"])

        for actor in (caster, target):
            effects_dict = getattr(actor, "effects", {})
            to_remove = []
            for k, eff in effects_dict.items():
                if spec and spec != 0 and getattr(eff, "ability_fqn", None) == spec:
                    to_remove.append(k)
                elif dispel_tags and (dispel_tags & set(getattr(eff, "tags", ()))):
                    to_remove.append(k)
            if to_remove:
                if sim is not None and hasattr(sim, "triggers"):
                    for k in to_remove:
                        eff_inst = effects_dict.get(k)
                        if eff_inst:
                            sim.triggers.dispatch(
                                "on_effect_dispelled",
                                sim,
                                {
                                    "caster": caster,
                                    "target": actor,
                                    "enemy_target": actor,
                                    "tags": frozenset(getattr(eff_inst, "tags", ())),
                                    "ability_spec": getattr(eff_inst, "ability_fqn", None),
                                },
                            )
                actor.cleanup_expired_effects(to_remove)


def handle_execute_ability(sim, caster, target, action):
    """Executes entry effects of a sub-ability referenced by execute_ability."""
    ints = action.get("ints") or {}
    spec = ints.get("ability_spec") or action.get("ability_spec")
    if not spec or spec == 0:
        return
    sub_ability = (
        getattr(caster, "ability_db", {}).get(spec)
        or getattr(caster, "passive_db", {}).get(spec)
    )
    if sub_ability is None:
        return
    for entry_id in getattr(sub_ability, "entry_effect_ids", ()):
        if hasattr(sub_ability, "execute_effect"):
            sub_ability.execute_effect(entry_id, caster, target, sim)
        elif entry_id in getattr(sub_ability, "effects", {}):
            sub_ability.effects[entry_id].execute(sim, caster, target, ability=sub_ability)


# --- Ability Container ---


class Ability:
    """Represents a combat ability with resource management, charges, and effect delegation."""

    def __init__(self, blueprint):
        self.blueprint = blueprint
        self.name = blueprint.name
        self.fqn = blueprint.fqn
        self.type = blueprint.type
        self.cooldown = blueprint.cooldown
        self.base_gcd = blueprint.base_gcd
        self.energy_cost = blueprint.energy_cost
        self.triggers_gcd = blueprint.triggers_gcd #this is stupid and you should be ashamed
        self.abl_ignore_alacrity = getattr(blueprint, "abl_ignore_alacrity", False)
        self.activation = getattr(blueprint, "activation", None)
        self.tags = frozenset(blueprint.tags or [])
        self.conditions = {}

        # Effect graph
        self.effects = blueprint.effects
        self.entry_effect_ids = blueprint.entry_effect_ids

        # Charges
        self.max_charges: Optional[int] = blueprint.max_charges
        self.charges: Optional[int] = blueprint.max_charges
        self.recharge_time = getattr(blueprint, "recharge_time", self.cooldown)
        self.active_charge_event = None

    @property
    def has_charges(self) -> bool:
        return self.max_charges is not None and self.max_charges > 0

    def execute_effect(self, effect_id, caster, target, sim, context=None):
        """Delegates effect execution directly to the target Effect instance."""
        effect = self.effects.get(effect_id)
        if effect:
            effect.execute(sim, caster, target, context=context, ability=self)

    def execute_branch(self, sim, branch, caster, target, context=None) -> bool:
        """Executes a triggered branch on this ability and returns whether it ran."""
        ran, _success = branch.execute(sim, caster, target, context=context, ability=self)
        return ran

    def apply_charge_modifiers(self, caster):
        """Updates max_charges and current charges if player passives/talents grant extra charges."""
        if hasattr(caster, "calculate_ability_max_charges"):
            base_max = getattr(self.blueprint, "max_charges", None)
            new_max = caster.calculate_ability_max_charges(base_max, ability=self)
            if new_max is not None and new_max != self.max_charges:
                diff = new_max - (self.max_charges or 1)
                self.max_charges = new_max
                self.charges = new_max if self.charges is None else max(1, self.charges + diff)

    def schedule_recharge(self, caster, sim):
        """Snapshots CDR, creates a new event reference, and schedules it."""
        if hasattr(caster, "calculate_recharge_time"):
            actual_recharge = caster.calculate_recharge_time(self.recharge_time, ability=self)
        else:
            actual_recharge = caster.calculate_cooldown(self.recharge_time, ability=self)
        event = ChargeRestoreEvent(caster, self)
        self.active_charge_event = event
        sim.schedule_relative(actual_recharge, event)

    def consume_charge(self, caster, sim):
        """Deducts a charge and initiates the recharge chain if dropping from max capacity."""
        if not self.has_charges or self.charges is None or self.charges < 1:
            return

        was_at_max = (self.charges == self.max_charges)
        self.charges -= 1

        if was_at_max:
            self.schedule_recharge(caster, sim)

    def restore_charge(self, caster, sim, amount: int = 1, from_timer: bool = False):
        """Grants charge(s), handles max capacity cleanup, and chains timers if needed."""
        if not self.has_charges or self.charges is None or self.max_charges is None:
            return

        self.charges = min(self.max_charges, self.charges + amount)
        print(f"[{sim.current_time:.2f}s] {self.name} charge restored ({self.charges}/{self.max_charges})")

        if self.charges == self.max_charges:
            self.active_charge_event = None
        elif from_timer:
            self.schedule_recharge(caster, sim)

    def can_cast(self, caster: "Player", target: "Dummy", sim, allow_clip: bool = False) -> bool:
        """Checks if the ability is ready to cast based on GCD, cooldown, cost, and conditions."""
        if hasattr(self, "apply_charge_modifiers") and caster is not None:
            self.apply_charge_modifiers(caster)
        if self.triggers_gcd and sim.current_time < caster.next_gcd:
            return False

        # Protect active channels by default: neither GCD nor off-GCD abilities can interrupt
        # unless explicit clipping is permitted
        if getattr(caster, "active_channel", None) is not None and not allow_clip:
            return False

        if getattr(caster, "active_cast", None) is not None and not allow_clip:
            return False

        if self.has_charges and self.charges < 1:
            return False

        if sim.current_time < caster.cooldowns.get(self.name, 0.0):
            return False

        modified_cost = caster.calculate_resource_cost(self.name, self.energy_cost, apply=False)

        if not caster.resource.can_afford(modified_cost):
            return False

        is_aggressive = (
            "tag.abl.utility.aggressive_action" in self.tags
            or "tag.abl.utility.is_basic_attack" in self.tags
            or (
                not self.tags
                and any(
                    getattr(b, "is_attack", False)
                    for eff in self.effects.values()
                    for b in getattr(eff, "branches", ())
                )
            )
        )
        ability_target = target if is_aggressive else caster
        conds = self.conditions or getattr(self.blueprint, "conditions", None) or {}
        return validate_all(conds, caster, ability_target, sim=sim)

    def apply_cooldown_locks(self, caster, sim):
        """Deducts charges or sets cooldown, and sets GCD lockouts."""
        caster.next_gcd = round(sim.current_time, 4)
        if self.triggers_gcd:
            caster.next_gcd = round(sim.current_time + caster.calculate_gcd(self.base_gcd, ability=self), 4)

        if self.has_charges:
            self.consume_charge(caster, sim)
        elif self.cooldown > 0.0:
            caster.cooldowns[self.name] = round(sim.current_time + caster.calculate_cooldown(self.cooldown, ability=self), 4)

    def cast(self, caster, target, sim, allow_clip: bool = False):
        """Executes the ability: spends resources, locks cooldowns, and triggers entry effects."""
        if not self.can_cast(caster, target, sim, allow_clip=allow_clip):
            return False

        if getattr(caster, "active_channel", None) is not None:
            old_channel = caster.active_channel
            print(f"[{sim.current_time:.3f}] {caster.name} interrupted channel to cast {self.name}!")
            old_channel.is_finished = True
            caster.active_channel = None
            caster.is_channeling = False
            cleanup_channel_effects(old_channel, sim)
            if sim is not None and hasattr(sim, "triggers"):
                sim.triggers.dispatch(
                    "on_channeling_ended",
                    sim,
                    {
                        "caster": caster,
                        "target": getattr(old_channel, "target", None),
                        "enemy_target": getattr(old_channel, "target", None),
                        "ability_spec": getattr(getattr(old_channel, "ability", None), "fqn", None),
                        "tags": getattr(getattr(old_channel, "ability", None), "tags", ()),
                        "is_successful": False,
                    },
                )

        if getattr(caster, "active_cast", None) is not None:
            print(f"[{sim.current_time:.3f}] {caster.name} interrupted cast to cast {self.name}!")
            caster.active_cast = None
            caster.is_casting = False

        final_spend = caster.calculate_resource_cost(self.name, self.energy_cost, apply=True)
        caster.resource.spend(final_spend)
        print(f"[{sim.current_time:.2f}s] {caster.name} casts {self.name}")

        self.apply_cooldown_locks(caster, sim)

        if sim is not None and hasattr(sim, "triggers"):
            sim.triggers.dispatch(
                "on_ability_activate",
                sim,
                {
                    "caster": caster,
                    "target": target,
                    "enemy_target": target,
                    "ability_spec": self.fqn,
                    "tags": self.tags,
                    "from_actor": 2,
                },
            )

        caster.current_target = target
        is_aggressive = (
            "tag.abl.utility.aggressive_action" in self.tags
            or "tag.abl.utility.is_basic_attack" in self.tags
            or (
                not self.tags
                and any(
                    getattr(b, "is_attack", False)
                    for eff in self.effects.values()
                    for b in getattr(eff, "branches", ())
                )
            )
        )
        if is_aggressive and hasattr(caster, "break_stealth"):
            caster.break_stealth(sim)
        if is_aggressive and not getattr(caster, "in_combat", False):
            caster.in_combat = True
            if sim is not None and hasattr(sim, "triggers"):
                sim.triggers.dispatch(
                    "on_enter_combat",
                    sim,
                    {"caster": caster, "target": target, "actor": caster},
                )
        ability_target = target if is_aggressive else caster

        # Check if ability has channel or cast activation
        activation = self.activation or getattr(self.blueprint, "activation", None) or {}
        act_type = activation.get("type") if isinstance(activation, dict) else None
        act_dur = float(activation.get("duration", 0.0)) if isinstance(activation, dict) else 0.0

        dispatch_post_activate = True
        if act_type == "channel" and act_dur > 0.0:
            self._start_channel(caster, ability_target, sim, act_dur)
        elif act_type == "cast" and act_dur > 0.0:
            scaled_cast_time = (
                caster.calculate_cast_time(act_dur, ability=self)
                if hasattr(caster, "calculate_cast_time")
                else act_dur
            )
            if scaled_cast_time > 0.0 and sim is not None:
                caster.active_cast = self
                caster.is_casting = True
                from src.swtorsim.events import CastFinishEvent
                sim.schedule_absolute(
                    sim.current_time + scaled_cast_time,
                    CastFinishEvent(
                        caster=caster,
                        target=ability_target,
                        ability=self,
                        entry_effect_ids=list(self.entry_effect_ids),
                    ),
                )
                dispatch_post_activate = False
            else:
                for entry_id in self.entry_effect_ids:
                    self.execute_effect(entry_id, caster, ability_target, sim)
        else:
            for entry_id in self.entry_effect_ids:
                self.execute_effect(entry_id, caster, ability_target, sim)

        if dispatch_post_activate and sim is not None and hasattr(sim, "triggers"):
            sim.triggers.dispatch(
                "on_ability_post_activate",
                sim,
                {
                    "caster": caster,
                    "target": target,
                    "enemy_target": target,
                    "ability_spec": self.fqn,
                    "tags": self.tags,
                    "from_actor": 2,
                },
            )

        return True

    def _start_channel(self, caster, ability_target, sim, channel_duration: float):
        """Initializes ActiveChannel, executes on_apply initial tick, and schedules periodic channel ticks."""
        from src.swtorsim.effects import ActiveChannel
        from src.swtorsim.events import ChannelTickEvent

        ignore_alacrity = self.abl_ignore_alacrity or getattr(self.blueprint, "abl_ignore_alacrity", False)
        scaled_duration = (
            caster.calculate_channel_duration(channel_duration, ability=self)
            if hasattr(caster, "calculate_channel_duration")
            else (caster.scale_time_modifier(channel_duration) if not ignore_alacrity else channel_duration)
        )

        # Determine tick interval and tick count
        base_interval = None
        for eff in self.effects.values():
            t_int = getattr(eff, "tick_interval", None)
            if t_int and t_int > 0.0:
                base_interval = float(t_int)
                break

        if base_interval is None:
            delays = []
            for eff in self.effects.values():
                for b in getattr(eff, "branches", ()):
                    for t in getattr(b, "triggers", ()):
                        if t.get("trigger") == "on_tick" and t.get("delay") is not None:
                            d = float(t["delay"])
                            if d > 0.0:
                                delays.append(d)
            if delays:
                delays.sort()
                base_interval = delays[0]

        if base_interval is None or base_interval <= 0.0:
            base_interval = min(1.0, channel_duration / 3.0) if channel_duration >= 1.0 else channel_duration

        if hasattr(caster, "calculate_effect_tick"):
            base_interval = caster.calculate_effect_tick(base_interval, ability=self)

        scaled_interval = caster.scale_time_modifier(base_interval) if not ignore_alacrity else base_interval
        total_ticks = max(1, int(round(scaled_duration / scaled_interval)))

        channel = ActiveChannel(
            name=self.name,
            total_ticks=total_ticks,
            tick_interval=scaled_interval,
            tick_cost=0.0,
            ability=self,
            duration=scaled_duration,
            caster=caster,
            target=ability_target,
        )
        caster.active_channel = channel
        caster.is_channeling = True

        # Execute on_apply / entry effects immediately for initial impact
        for entry_id in self.entry_effect_ids:
            self.execute_effect(entry_id, caster, ability_target, sim)

        # If on_apply triggered ability_cancel, do not schedule ticks and return actor to ready
        if getattr(channel, "is_finished", False):
            cleanup_channel_effects(channel, sim)
            if sim is not None:
                from src.swtorsim.events import PlayerReady
                target_time = max(sim.current_time, getattr(caster, "next_gcd", sim.current_time))
                sim.schedule_absolute(target_time, PlayerReady(caster, ability_target))
            return

        # Schedule the first periodic tick event
        if sim is not None:
            sim.schedule_relative(scaled_interval, ChannelTickEvent(channel))

def handle_invoke_projectile(sim, caster, target, action, ability=None, context=None):
    """Resolves or schedules on_travel_complete for projectile actions based on distance & travel speed."""
    parent_effect = (context or {}).get("effect")
    if parent_effect is None:
        return

    from src.swtorsim.settings import is_projectile_flight_time_enabled, get_default_combat_distance

    floats = action.get("floats")
    travel_speed = float(floats.get("travel_speed", 0.0)) if isinstance(floats, dict) else 0.0

    time_to_hit = 0.0
    if is_projectile_flight_time_enabled() and travel_speed > 0.0:
        distance = getattr(target, "combat_distance", None)
        if distance is None:
            distance = get_default_combat_distance()
        if distance > 0.0:
            time_to_hit = distance / (travel_speed * 10.0)

    if time_to_hit > 0.0 and sim is not None:
        from src.swtorsim.events import ProjectileImpactEvent
        sim.schedule_relative(
            time_to_hit,
            ProjectileImpactEvent(
                parent_effect,
                caster,
                target,
                ability=ability,
                context=context,
            ),
        )
    else:
        parent_effect.execute_triggered_branches(
            "on_travel_complete",
            sim,
            caster,
            target,
            context=context,
            ability=ability,
        )

def handle_reset_timer(sim, caster, target, action, ability=None, context=None):
    """Resets the duration and ticks of the active effect on owner_entity back to full."""
    if not isinstance(context, dict):
        return

    owner_entity = context.get("owner_entity")
    effect_key = context.get("owner_effect_key")
    if owner_entity is None or effect_key is None:
        return

    active_effect = getattr(owner_entity, "effects", {}).get(effect_key)
    if active_effect is None or getattr(active_effect, "is_expired", False):
        return

    current_time = sim.current_time if sim is not None else 0.0
    duration = getattr(active_effect, "duration", 0.0)
    if duration <= 0.0:
        eff_bp = getattr(active_effect, "effect_blueprint", None)
        duration = float(getattr(eff_bp, "duration", 0.0) if eff_bp else 0.0)

    if duration > 0.0:
        new_expires_at = current_time + duration
        active_effect.expires_at = new_expires_at
        if sim is not None:
            from src.swtorsim.events import EffectExpire
            sim.schedule_absolute(new_expires_at, EffectExpire(owner_entity, effect_key, active_effect))

    total_ticks = getattr(active_effect, "total_ticks", 0)
    if total_ticks > 0:
        active_effect.ticks_remaining = total_ticks

def handle_modify_active_duration(sim, caster, target, action, ability=None, context=None):
    """Modifies the active duration of target effect(s) by adding action['duration'] seconds."""
    duration_delta = float(action.get("duration", 0.0) or 0.0)
    if duration_delta == 0.0:
        intervals = action.get("intervals")
        if isinstance(intervals, dict) and "18" in intervals:
            duration_delta = float(intervals["18"] or 0.0)
    if duration_delta == 0.0:
        return

    # Determine target actor (1 = caster, 2 = target)
    ints = action.get("ints")
    actor_id = ints.get("actor", 1) if isinstance(ints, dict) else 1
    actor = caster if actor_id == 1 else target
    if actor is None or not hasattr(actor, "effects"):
        return

    action_tags = frozenset(action.get("tags") or [])
    current_time = sim.current_time if sim is not None else 0.0

    matching_effects = []
    if action_tags:
        for eff_key, eff_inst in actor.effects.items():
            if getattr(eff_inst, "is_expired", False):
                continue
            eff_tags = getattr(eff_inst, "tags", frozenset())
            if eff_tags & action_tags:
                matching_effects.append((eff_key, eff_inst))
    else:
        if isinstance(context, dict):
            owner_key = context.get("owner_effect_key")
            if owner_key and owner_key in actor.effects:
                eff_inst = actor.effects[owner_key]
                if not getattr(eff_inst, "is_expired", False):
                    matching_effects.append((owner_key, eff_inst))

    for eff_key, active_eff in matching_effects:
        if active_eff.expires_at is not None:
            new_expires_at = max(current_time, active_eff.expires_at + duration_delta)
            active_eff.expires_at = new_expires_at
            if sim is not None:
                from src.swtorsim.events import EffectExpire
                sim.schedule_absolute(new_expires_at, EffectExpire(actor, eff_key, active_eff))

def _resolve_state_actor(caster, target, action):
    if not isinstance(action, dict):
        return caster
    if action.get("to_actor") == "target" or action.get("ints", {}).get("actor") == 2:
        return target
    return caster


def handle_take_cover(caster, target, action, is_portable: bool = False):
    """Sets the actor in cover state."""
    actor = _resolve_state_actor(caster, target, action)
    if actor is not None:
        actor.is_in_cover = True
        if is_portable:
            actor.is_in_portable_cover = True


def handle_leave_cover(caster, target, action):
    """Clears the actor's cover state."""
    actor = _resolve_state_actor(caster, target, action)
    if actor is not None:
        actor.is_in_cover = False
        actor.is_in_portable_cover = False


def handle_become_stealthed(caster, target, action):
    """Enters stealth mode on the actor."""
    actor = _resolve_state_actor(caster, target, action)
    if actor is not None:
        actor.is_stealthed = True


def handle_enter_combat(caster, target, action, sim=None):
    """Puts the actor into combat state."""
    actor = _resolve_state_actor(caster, target, action)
    if actor is not None:
        actor.in_combat = True
        if sim is not None and hasattr(sim, "triggers"):
            sim.triggers.dispatch("on_enter_combat", sim, {"caster": caster, "target": target, "actor": actor})


def handle_exit_combat(caster, target, action, sim=None):
    """Drops the actor from combat state."""
    actor = _resolve_state_actor(caster, target, action)
    if actor is not None:
        actor.in_combat = False
        if sim is not None and hasattr(sim, "triggers"):
            sim.triggers.dispatch("on_exit_combat", sim, {"caster": caster, "target": target, "actor": actor})

def handle_grant_immunity(sim, caster, target, action, context=None):
    """Handles effAction_GrantImmunity by registering immunity tags on the target or active effect."""
    actor = _resolve_state_actor(caster, target, action) or target or caster
    if actor is None:
        return True
    tags = action.get("tags") or []
    if not tags:
        val = (action.get("strings") or {}).get("tag")
        if val:
            tags = [t.strip() for t in val.split(",") if t.strip()]
    if not tags:
        return True
    active_effect = (context or {}).get("active_effect")
    if active_effect is not None and hasattr(active_effect, "immunities"):
        active_effect.immunities.update(tags)
    elif hasattr(actor, "_base_immunities"):
        actor._base_immunities.update(tags)
    return True

def cleanup_channel_effects(channel, sim):
    """Cleans up channel-bound active effects applied during the channel, executing their on_pre_remove triggers."""
    if channel is None:
        return
    attached = getattr(channel, "attached_effects", [])
    if not attached:
        return
    for actor, effect_key, eff_inst in list(attached):
        # Do not clean up effects that have their own independent timer (e.g. duration > 0 with expires_at)
        if getattr(eff_inst, "duration", 0.0) > 0.0 and getattr(eff_inst, "expires_at", None) is not None:
            continue
        effects_dict = getattr(actor, "effects", {})
        if effect_key in effects_dict and effects_dict[effect_key] is eff_inst:
            bp = getattr(eff_inst, "effect_blueprint", None)
            ability = getattr(eff_inst, "ability_ref", None) or getattr(channel, "ability", None)
            caster = getattr(eff_inst, "caster_ref", None) or getattr(channel, "caster", None)
            if bp and hasattr(bp, "execute_triggered_branches"):
                expire_ctx = {
                    "stack_multiplier": getattr(eff_inst, "stacks", 1),
                    "current_stacks": getattr(eff_inst, "stacks", 1),
                    "active_effect": eff_inst,
                    "owner_effect_key": effect_key,
                    "owner_entity": actor,
                    "effect": bp,
                }
                bp.execute_triggered_branches(
                    "on_pre_remove",
                    sim,
                    caster,
                    actor,
                    context=expire_ctx,
                    ability=ability,
                )
            actor.cleanup_expired_effects([effect_key])


def handle_ability_cancel(caster, target, action):
    """Cancels active channel or cast on the actor."""
    actor = _resolve_state_actor(caster, target, action)
    if actor is None:
        return
    active_channel = getattr(actor, "active_channel", None)
    if active_channel is not None:
        active_channel.is_finished = True
        actor.active_channel = None
        actor.is_channeling = False
        cleanup_channel_effects(active_channel, getattr(actor, "_sim_ref", None))
        sim_ref = getattr(actor, "_sim_ref", None)
        if sim_ref is not None and hasattr(sim_ref, "triggers"):
            sim_ref.triggers.dispatch(
                "on_channeling_ended",
                sim_ref,
                {
                    "caster": actor,
                    "target": getattr(active_channel, "target", None),
                    "enemy_target": getattr(active_channel, "target", None),
                    "ability_spec": getattr(getattr(active_channel, "ability", None), "fqn", None),
                    "tags": getattr(getattr(active_channel, "ability", None), "tags", ()),
                    "is_successful": False,
                },
            )

    active_cast = getattr(actor, "active_cast", None)
    if active_cast is not None:
        actor.active_cast = None
        actor.is_casting = False


def handle_cooldown_action(sim, caster, action, ability=None, context=None):
    """Triggers a cooldown on the ability or specified ability spec."""
    if caster is None or sim is None:
        return

    target_abl = ability
    if target_abl is None and isinstance(context, dict):
        target_abl = context.get("ability")

    spec = action.get("ints", {}).get("ability_spec") or action.get("ability_spec")
    if spec and hasattr(caster, "ability_db") and spec in caster.ability_db:
        target_abl = caster.ability_db[spec]

    if target_abl is None:
        return

    cd_val = float(getattr(target_abl, "cooldown", 0.0) or 0.0)
    if cd_val <= 0.0:
        bp = getattr(target_abl, "blueprint", None)
        cd_val = float(getattr(bp, "cooldown", 0.0) or 0.0)

    custom_cd = action.get("floats", {}).get("duration") or action.get("duration")
    if custom_cd is not None and float(custom_cd) > 0.0:
        cd_val = float(custom_cd)

    if cd_val > 0.0:
        ignore_alacrity = bool(action.get("bools", {}).get("ignore_alacrity", False))
        if ignore_alacrity:
            final_cd = cd_val
        elif hasattr(caster, "calculate_cooldown"):
            final_cd = caster.calculate_cooldown(cd_val, ability=target_abl)
        else:
            final_cd = cd_val
        abl_name = getattr(target_abl, "name", None) or getattr(target_abl, "fqn", "")
        current_cd = caster.cooldowns.get(abl_name, 0.0)
        new_cd = round(sim.current_time + final_cd, 4)
        caster.cooldowns[abl_name] = max(current_cd, new_cd)


def handle_global_cooldown(sim, caster, action):
    """Triggers a global cooldown lock on the actor."""
    if caster is None or sim is None:
        return
    base_gcd = float(
        action.get("duration")
        or (action.get("intervals", {}).get("18") if isinstance(action.get("intervals"), dict) else None)
        or (action.get("floats", {}).get("duration") if isinstance(action.get("floats"), dict) else None)
        or 1.5
    )
    if hasattr(caster, "calculate_gcd"):
        gcd = caster.calculate_gcd(base_gcd)
    else:
        gcd = base_gcd
    caster.next_gcd = max(getattr(caster, "next_gcd", 0.0), round(sim.current_time + gcd, 4))


def handle_custom_action(sim, caster, target, action, context=None):
    """Handles engine-level custom action hooks (such as programmatic ability triggers)."""
    if caster is None:
        return
    ints = action.get("ints", {}) if isinstance(action, dict) else {}
    param1 = str(ints.get("param1", ""))

    # 6855115466292073041: BioWare programmatic ability trigger hook
    # (used by Force Cloak, Cloaking Screen, Disappearing Act, and Shoulder Cannon)
    if param1 == "6855115466292073041":
        spec = ints.get("param2")
        if not spec:
            return
        target_abl = getattr(caster, "ability_db", {}).get(spec)
        if target_abl is None:
            return

        entry_effect_ids = getattr(target_abl, "entry_effect_ids", ()) or ()
        for entry_id in entry_effect_ids:
            if hasattr(target_abl, "execute_effect"):
                target_abl.execute_effect(entry_id, caster, caster, sim, context=context)
