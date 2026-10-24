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

    def execute(self, sim, caster, target, context=None, ability=None):
        """Resolves an effect: routes persistent effects to actor, or resolves instant branches."""
        effect_target = _resolve_target_overrides(self.target_overrides, target, caster, context)

        if self.conditions:
            if not validate_all(self.conditions, caster, effect_target, sim=sim, context=context):
                return

        if self.is_persistent:
            effect_key = (
                self.name
                or f"{getattr(ability, 'name', None) or getattr(ability, 'fqn', '')}:{self.number}"
            )
            existing = effect_target.effects.get(effect_key)
            was_refreshed = existing is not None and not getattr(existing, "is_expired", False)
            effect_target.apply_effect(sim, ability, self, caster)
            self.execute_triggered_branches(
                "on_refresh" if was_refreshed else "on_apply",
                sim,
                caster,
                effect_target,
                context=context,
                ability=ability,
                include_untriggered=False,
            )
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
        "grant_immunity",
        "taunt",
        "taunt_damage_reduce",
        "ability_interrupt",
        "ability_activate",
        "ability_deactivate",
        "ability_cancel",
        "become_stealthed",
        "set_posture",
        "take_cover",
        "leave_cover",
        "take_portable_cover",
        "enter_combat",
        "exit_combat",
        "revive",
        "summon_pet",
        "execute_hydra_hook",
        "custom",
        "invoke_projectile",
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
        "cooldown",
        "global_cooldown",
        "reset_timer",
        "modify_active_duration",
        "set_effect_stack_charge",
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
        handle_resource_gain_action(sim, caster, action, delay)
    elif action_type in ("spend_energy", "spend_force"):
        handle_resource_spend_action(caster, action)
    elif action_type in ("cooldown_mod", "modify_cooldown", "modify_recharge_time"):
        handle_cooldown_modification(sim, caster, action)
    elif action_type in ("grant_charge", "modify_ability_stack_charge"):
        handle_restore_charge(sim, caster, action)
    elif action_type == "modify_stack_charge":
        handle_modify_stack_charge(sim, caster, target, action, context=context)
    elif action_type in ("buff_remove", "remove_effect", "dispel"):
        handle_buff_remove_action(sim, caster, target, action, ability=ability, context=context)
    elif action_type == "execute_ability":
        handle_execute_ability(sim, caster, target, action)
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
            if (
                key == spec
                or abl_fqn == spec
                or getattr(abl, "name", None) == spec
                or (base_stem and abl_fqn.endswith(f".{base_stem}_plus"))
            ):
                matched.append(abl)
                seen_ids.add(id(abl))
                continue
            if getattr(abl, "name", "").lower().replace(" ", "_") == str(spec).lower().replace(" ", "_"):
                matched.append(abl)
                seen_ids.add(id(abl))
                continue
        if tag_set and (tag_set & set(getattr(abl, "tags", ()))):
            matched.append(abl)
            seen_ids.add(id(abl))
    return matched


def handle_damage_action(sim, caster, target, action, source_name, delay, ability=None, context=None):
    """Rolls accuracy then schedules or executes the hit."""
    hand = action.get("hand", "main")
    if hand == "off" and getattr(caster, "stats", {}).get("Off_hand_max", 0) <= 0:
        return True
    is_periodic = bool((context or {}).get("is_periodic", False)) or any(
        "periodic_damage" in str(t) for t in (context or {}).get("effect_tags", ())
    )
    if not is_periodic and not accuracy_roll(caster, hand):
        return False
    combined_tags = (
        set(action.get("tags") or ())
        | set(getattr(ability, "tags", ()) or ())
        | set((context or {}).get("effect_tags") or ())
    )
    from_proc = getattr(ability, "type", "active") == "passive"
    hit_event = DamageHit(
        caster,
        target,
        action,
        source_name,
        tags=combined_tags,
        from_proc=from_proc,
        ability_fqn=getattr(ability, "fqn", None),
    )
    if delay > 0.0:
        sim.schedule_relative(delay, hit_event)
    else:
        hit_event.resolve(sim)
    return True


def handle_resource_gain_action(sim, caster, action, delay):
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
    """Modifies stacks on an active effect (e.g. Deathmark consuming a stack on DoT tick)."""
    floats = action.get("floats") or {}
    delta = int(round(float(floats.get("amount_min", floats.get("amount_max", 0.0)))))
    if delta == 0:
        return

    owner_entity = (context or {}).get("owner_entity") or target
    owner_key = (context or {}).get("owner_effect_key")
    eff = getattr(owner_entity, "effects", {}).get(owner_key) if owner_key else None
    if eff is None or getattr(eff, "is_expired", False):
        return

    eff.modify_stacks(delta)
    if delta < 0 and sim is not None and hasattr(sim, "triggers") and not (context or {}).get("from_stack_event"):
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

    def schedule_recharge(self, caster, sim):
        """Snapshots CDR, creates a new event reference, and schedules it."""
        actual_recharge = caster.calculate_cooldown(self.recharge_time)
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

    def can_cast(self, caster: "Player", target: "Dummy", sim) -> bool:
        """Checks if the ability is ready to cast based on GCD, cooldown, cost, and conditions."""
        if self.triggers_gcd and sim.current_time < caster.next_gcd:
            return False

        if getattr(caster, "active_channel", None) is not None:
            return False

        if self.has_charges and self.charges < 1:
            return False

        if sim.current_time < caster.cooldowns.get(self.name, 0.0):
            return False

        modified_cost = caster.calculate_resource_cost(self.name, self.energy_cost, apply=False)

        if not caster.resource.can_afford(modified_cost):
            return False

        conds = self.conditions or getattr(self.blueprint, "conditions", None) or {}
        return validate_all(conds, caster, target, sim=sim)

    def apply_cooldown_locks(self, caster, sim):
        """Deducts charges or sets cooldown, and sets GCD lockouts."""
        caster.next_gcd = round(sim.current_time, 4)
        if self.triggers_gcd:
            caster.next_gcd = round(sim.current_time + caster.calculate_gcd(self.base_gcd), 4)

        if self.has_charges:
            self.consume_charge(caster, sim)
        elif self.cooldown > 0.0:
            caster.cooldowns[self.name] = round(sim.current_time + caster.calculate_cooldown(self.cooldown), 4)

    def cast(self, caster, target, sim):
        """Executes the ability: spends resources, locks cooldowns, and triggers entry effects."""
        if not self.can_cast(caster, target, sim):
            return False

        if getattr(caster, "active_channel", None) is not None:
            print(f"[{sim.current_time:.3f}] {caster.name} interrupted channel to cast {self.name}!")
            caster.active_channel = None
            caster.is_channeling = False

        final_spend = caster.calculate_resource_cost(self.name, self.energy_cost, apply=True)
        caster.resource.spend(final_spend)
        print(f"[{sim.current_time:.2f}s] {caster.name} casts {self.name}")

        self.apply_cooldown_locks(caster, sim)

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
        ability_target = target if is_aggressive else caster

        for entry_id in self.entry_effect_ids:
            self.execute_effect(entry_id, caster, ability_target, sim)

        if sim is not None and hasattr(sim, "triggers"):
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
