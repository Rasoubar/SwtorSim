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
            is_attack=data.get("is_attack", False),
        )

    def execute(self, sim, caster, target, context=None, ability=None) -> tuple[bool, bool]:
        """
        Evaluates branch conditions and executes actions.
        Returns: (ran, success)
          - ran: True if conditions passed and actions were attempted.
          - success: False only if an action failed (e.g. accuracy miss).
        """
        actual_target = target

        # 1. Target overrides
        for override in self.target_overrides:
            if override.get("type") == "trigger_target" and context and "target" in context:
                actual_target = context["target"]

        # 2. Branch conditions (failing conditions skips the branch, not an attack miss)
        if self.conditions:
            if not validate_all(self.conditions, caster, actual_target, sim=sim, context=context):
                return False, True

        # 3. Actions execution
        source_name = ability.name if ability else "Unknown"
        for action in self.actions:
            success = execute_single_action(
                sim, caster, actual_target, action, source_name, ability=ability
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
    tags: List[str] = field(default_factory=list)
    branches: List[Branch] = field(default_factory=list)
    stack_charge: Optional[Dict[str, Any]] = None
    conditions: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Effect":
        is_passive = any(
            init.get("initializer_type") == "eff_initializer__set_passive"
            and init.get("bools", {}).get("is_passive", False)
            for init in data.get("initializers", [])
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
            tags=data.get("tags") or [],
            branches=[Branch.from_dict(b) for b in data.get("branches", [])],
            stack_charge=data.get("stack_charge"),
            conditions=data.get("conditions"),
        )

    @property
    def is_persistent(self) -> bool:
        """True if the effect is a timed buff/debuff or permanent passive."""
        return self.duration > 0.0 or self.is_passive

    @property
    def is_instant(self) -> bool:
        """True if the effect evaluates immediately and does not live on an actor."""
        return not self.is_persistent

    def execute(self, sim, caster, target, context=None, ability=None):
        """Resolves an effect: routes persistent effects to actor, or resolves instant branches."""
        # 1. Persistent Fork
        if self.is_persistent:
            target.apply_effect(sim, ability, self, caster)
            return

        # 2. Instant Fork
        executed_branches = set()
        for branch in self.branches:
            triggers = getattr(branch, "triggers", [])
            is_immediate = not triggers or any(t.get("trigger") == "on_apply" for t in triggers)
            if not is_immediate:
                continue

            if branch.run_if_none_ran and any(b in executed_branches for b in branch.run_if_none_ran):
                continue

            ran, success = branch.execute(sim, caster, target, context=context, ability=ability)
            if ran:
                executed_branches.add(branch.index)
            if not success and getattr(branch, "is_attack", False):
                break


@dataclass(slots=True)
class AbilityBlueprint:
    fqn: str
    name: str
    type: str  # "active" or "passive"
    energy_cost: float
    base_gcd: float
    cooldown: float
    tags: List[str] = field(default_factory=list)
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

        raw_cost = data.get("energy_cost")
        raw_gcd = data.get("base_gcd")
        raw_cd = data.get("cooldown")

        return cls(
            fqn=data.get("fqn") or "",
            name=data.get("name") or "Unknown Ability",
            type=data.get("type") or "active",
            energy_cost=float(raw_cost) if raw_cost is not None else 0.0,
            base_gcd=float(raw_gcd) if raw_gcd is not None else 1.5,
            cooldown=float(raw_cd) if raw_cd is not None else 0.0,
            tags=data.get("tags") or [],
            effects=effects_map,
            entry_effect_ids=entry_ids,
            file_path=file_path,
        )

    @classmethod
    def from_file(cls, filepath: Path) -> "AbilityBlueprint":
        with filepath.open("r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f), file_path=filepath)

# --- Action Handlers ---


def execute_single_action(sim, caster, target, action, source_name, ability=None):
    """Calls the appropriate function for the action type."""
    if not validate_all(action.get("conditions", {}), caster, target, sim=sim):
        return False
    if "chance" in action and random.random() > action["chance"]:
        return False

    action_type = action.get("action_type")
    delay = action.get("delay", 0.0)

    if action_type == "damage":
        return handle_damage_action(sim, caster, target, action, source_name, delay)
    elif action_type == "resource_gain":
        handle_resource_gain_action(sim, caster, action, delay)
    elif action_type == "cooldown_mod":
        handle_cooldown_modification(sim, caster, action)
    elif action_type == "grant_charge":
        handle_restore_charge(sim, caster, action)
    elif action_type == "buff_remove":
        handle_buff_remove_action(sim, caster, action)
    elif action_type == "call_effect":
        if ability and "effect" in action:
            ability.execute_effect(action["effect"], caster, target, sim)
    elif action_type == "modify_stack_charge":
        pass
    else:
        raise ValueError(
            f"CRITICAL ENGINE ERROR: Unrecognized action_type '{action_type}' "
            f"triggered by '{source_name}'. Please check your JSON blueprints."
        )
    return True


def handle_damage_action(sim, caster, target, action, source_name, delay):
    """Rolls accuracy then schedules or executes the hit."""
    if not accuracy_roll(caster, action.get("hand", "main")):
        return False
    hit_event = DamageHit(caster, target, action, source_name)
    if delay > 0.0:
        sim.schedule_relative(delay, hit_event)
    else:
        hit_event.resolve(sim)
    return True


def handle_resource_gain_action(sim, caster, action, delay):
    """Schedules or executes the resource gain event."""
    regen = action.get("value", 0.0)
    gain_event = ResourceGainEvent(caster, regen)
    if delay > 0.0:
        sim.schedule_relative(delay, gain_event)
    else:
        gain_event.resolve(sim)


def handle_cooldown_modification(sim, caster, action):
    """Applies cooldown reductions or resets to targeted abilities."""
    cooldown_dict = getattr(caster, "cooldowns", {})
    ability_db = caster.ability_db
    if not (cooldown_dict and ability_db and "target_tags" in action):
        return
    reset_tags = frozenset(action["target_tags"])
    is_reset = action.get("reset", False)
    for cd_key in list(cooldown_dict.keys()):
        if cooldown_dict[cd_key] <= sim.current_time:
            del cooldown_dict[cd_key]
            continue
        ability_data = ability_db.get(cd_key.lower().replace(" ", "_"))
        ability_tags = getattr(ability_data, "tags", frozenset()) if ability_data else frozenset()
        if reset_tags & ability_tags:
            if is_reset:
                del cooldown_dict[cd_key]
            else:
                reduction = action.get("value", 0.0)
                new_cd = max(sim.current_time, cooldown_dict[cd_key] + reduction)
                cooldown_dict[cd_key] = new_cd
                if cooldown_dict[cd_key] <= sim.current_time:
                    del cooldown_dict[cd_key]


def handle_restore_charge(sim, caster, action):
    """Restores a charge to the target ability."""
    target_ability_name = action.get("target_ability")
    amount = action.get("amount", 1)
    if target_ability_name in caster.ability_db:
        ability = caster.ability_db[target_ability_name]
        ability.restore_charge(caster, sim, amount=amount, from_timer=False)


def handle_buff_remove_action(sim, caster, action):
    """Removes a buff from the caster."""
    effect_name = action.get("effect_name")
    if effect_name and caster.has_effect(effect_name):
        caster.cleanup_expired_effects([effect_name])
        print(f"[{sim.current_time:.3f}] {caster.name} consumed/removed buff: {effect_name}")


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
        self.triggers_gcd = blueprint.type == "active"
        self.tags = frozenset(blueprint.tags or [])
        self.conditions = {}

        # Effect graph
        self.effects = blueprint.effects
        self.entry_effect_ids = blueprint.entry_effect_ids

        # Charges
        self.max_charges = getattr(blueprint, "max_charges", 0)
        self.charges = self.max_charges
        self.recharge_time = getattr(blueprint, "recharge_time", self.cooldown)
        self.active_charge_event = None

    @property
    def has_charges(self):
        return self.max_charges > 0

    def execute_effect(self, effect_id, caster, target, sim, context=None):
        """Delegates effect execution directly to the target Effect instance."""
        effect = self.effects.get(effect_id)
        if effect:
            effect.execute(sim, caster, target, context=context, ability=self)

    def schedule_recharge(self, caster, sim):
        """Snapshots CDR, creates a new event reference, and schedules it."""
        actual_recharge = caster.calculate_cooldown(self.recharge_time)
        event = ChargeRestoreEvent(caster, self)
        self.active_charge_event = event
        sim.schedule_relative(actual_recharge, event)

    def consume_charge(self, caster, sim):
        """Deducts a charge and initiates the recharge chain if dropping from max capacity."""
        if not self.has_charges or self.charges < 1:
            return

        was_at_max = (self.charges == self.max_charges)
        self.charges -= 1

        if was_at_max:
            self.schedule_recharge(caster, sim)

    def restore_charge(self, caster, sim, amount: int = 1, from_timer: bool = False):
        """Grants charge(s), handles max capacity cleanup, and chains timers if needed."""
        if not self.has_charges:
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

        return validate_all(self.conditions, caster, target)

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

        for entry_id in self.entry_effect_ids:
            self.execute_effect(entry_id, caster, target, sim)

        return True