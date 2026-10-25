from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.swtorsim.modifiers import Modifier


class ActiveDot:
    """Tracks tick timing and state for active Damage-over-Time (DoT) effects."""
    __slots__ = ['name', 'interval', 'ticks_remaining', 'action_data']

    def __init__(self, name, interval, ticks_remaining, action_data: dict):
        self.name = name
        self.interval = interval
        self.ticks_remaining = ticks_remaining
        self.action_data = action_data


class ActiveChannel:
    """Tracks progress, tick intervals, and resource costs for channeled abilities. Can use more testing."""
    def __init__(self, name, action_data, total_ticks, tick_interval, tick_cost):
        self.name = name
        self.action_data = action_data
        self.remaining_ticks = total_ticks
        self.tick_interval = tick_interval
        self.tick_cost = tick_cost


@dataclass
class ActiveEffect:
    """A live effect instance running on an actor."""

    # Identity
    fqn: str
    name: str
    number: int = 1
    tags: frozenset = frozenset()

    # Timers
    expires_at: Optional[float] = None
    tick_interval: Optional[float] = None

    # Stacks / Charges
    stacks: int = 1
    max_stacks: int = 1
    initial_stacks: int = 1
    scales_with_stacks: bool = False

    @property
    def charges(self) -> int:
        return self.stacks

    @charges.setter
    def charges(self, value: int):
        self.stacks = value

    @property
    def max_charges(self) -> int:
        return self.max_stacks

    # Payloads
    modifiers: List[Modifier] = field(default_factory=list)
    branches: List[Dict[str, Any]] = field(default_factory=list)

    # State
    is_passive: bool = False
    is_expired: bool = False
    total_ticks: int = 0
    ticks_remaining: int = 0
    owner_id: Optional[str] = None
    effect_blueprint: Any = field(default=None, repr=False, compare=False)
    ability_ref: Any = field(default=None, repr=False, compare=False)
    caster_ref: Any = field(default=None, repr=False, compare=False)

    def time_remaining(self, current_time: float) -> float:
        if self.expires_at is None:
            return float("inf")
        return max(0.0, self.expires_at - current_time)

    def modify_stacks(self, amount: int) -> None:
        self.stacks = max(0, min(self.stacks + amount, self.max_stacks))
        if self.stacks == 0 and self.max_stacks > 0:
            self.is_expired = True

    def get_effective_modifiers(self) -> List[Modifier]:
        """Returns modifiers, scaled by stack count if scales_with_stacks is enabled."""
        if not self.scales_with_stacks or self.stacks == 1:
            return self.modifiers
        return [
            Modifier(stat=m.stat, value=m.value * self.stacks, targets=m.targets, conditional_tag=m.conditional_tag)
            for m in self.modifiers
        ]

    @classmethod
    def from_stat_changes(cls, data: Dict[str, Any]) -> "ActiveEffect":
        """Constructs a permanent passive from a blueprint containing stat_changes."""
        stat_changes = data.get("stat_changes") or []
        modifiers = [
            Modifier.from_stat_change(sc)
            for sc in stat_changes
            if isinstance(sc, dict)
        ]

        return cls(
            fqn=data["fqn"],
            name=data.get("name", data["fqn"]),
            number=1,
            tags=frozenset(data.get("tags", [])),
            expires_at=None,
            tick_interval=None,
            modifiers=modifiers,
            branches=[],
        )

    @classmethod
    def from_effect_node(
        cls,
        parent_fqn: str,
        parent_name: str,
        effect_node: Dict[str, Any],
        current_time: Optional[float] = None,
        expires_at: Optional[float] = None,
    ) -> "ActiveEffect":
        """Constructs an active or passive effect from a blueprint effect node dict."""
        is_passive = any(
            init.get("initializer_type") == "eff_initializer__set_passive"
            and init.get("bools", {}).get("is_passive", False)
            for init in effect_node.get("initializers", [])
        )

        if is_passive:
            computed_expires_at = None
        elif expires_at is not None:
            computed_expires_at = expires_at
        elif "duration" in effect_node and current_time is not None:
            computed_expires_at = current_time + effect_node["duration"]
        else:
            computed_expires_at = None

        stack_charge = effect_node.get("stack_charge") or {}
        max_stacks = int(stack_charge.get("max", stack_charge.get("nr_occurances", 1)) or 1)
        initial_stacks = int(stack_charge.get("initial", 1) or 1)
        if initial_stacks > max_stacks:
            max_stacks = initial_stacks
        scales_with_stacks = bool(
            stack_charge.get("scales_with_stack_charge", False)
            or effect_node.get("scales_with_stacks", False)
        )

        # Collect modifiers directly from action nodes
        branches = effect_node.get("branches") or []
        parsed_modifiers: List[Modifier] = []

        for branch in branches:
            if not isinstance(branch, dict):
                continue
            for action in branch.get("actions", []):
                if not isinstance(action, dict):
                    continue
                action_type = action.get("action_type")
                if action_type == "modify_stat":
                    parsed_modifiers.append(Modifier.from_modify_stat(action))
                elif action_type == "modify_meta_stat":
                    parsed_modifiers.append(
                        Modifier.from_modify_meta_stat(action)
                    )
                elif action_type in (
                    "apply_conditional_meta_stat_mod",
                    "apply_conditional_stat_mod",
                ):
                    parsed_modifiers.append(
                        Modifier.from_conditional_stat_mod(action)
                    )

        return cls(
            fqn=parent_fqn,
            name=effect_node.get("name") or parent_name,
            number=effect_node.get("number", 1),
            tags=frozenset(effect_node.get("tags", [])),
            expires_at=computed_expires_at,
            tick_interval=effect_node.get("tick_interval"),
            stacks=initial_stacks,
            max_stacks=max_stacks,
            initial_stacks=initial_stacks,
            scales_with_stacks=scales_with_stacks,
            modifiers=parsed_modifiers,
            branches=branches,
        )

    @classmethod
    def from_effect(
        cls,
        ability: Any,
        effect: Any,
        current_time: Optional[float] = None,
        expires_at: Optional[float] = None,
        caster: Any = None,
        target: Any = None,
        sim: Any = None,
    ) -> "ActiveEffect":
        """Constructs an ActiveEffect from a runtime Ability and abilities.Effect instance."""
        blueprint = getattr(ability, "blueprint", None)
        parent_fqn = getattr(blueprint, "fqn", "") or getattr(ability, "name", "")
        parent_name = getattr(ability, "name", parent_fqn)

        is_passive = bool(getattr(effect, "is_passive", False))
        duration = float(getattr(effect, "duration", 0.0) or 0.0)

        if is_passive:
            computed_expires_at = None
        elif expires_at is not None:
            computed_expires_at = expires_at
        elif duration > 0.0 and current_time is not None:
            computed_expires_at = current_time + duration
        else:
            computed_expires_at = None

        stack_charge = getattr(effect, "stack_charge", None) or {}
        max_stacks = int(stack_charge.get("max", stack_charge.get("nr_occurances", 1)) or 1)
        initial_stacks = int(stack_charge.get("initial", 1) or 1)
        if initial_stacks > max_stacks:
            max_stacks = initial_stacks
        scales_with_stacks = bool(
            stack_charge.get("scales_with_stack_charge", False)
            or getattr(effect, "scales_with_stacks", False)
        )

        raw_branches = getattr(effect, "branches", None) or []
        parsed_modifiers: List[Modifier] = []
        serialized_branches: List[Dict[str, Any]] = []

        for branch in raw_branches:
            branch_conditions = getattr(branch, "conditions", None) if not isinstance(branch, dict) else branch.get("conditions")
            if branch_conditions and caster is not None:
                from src.swtorsim.requirements import validate_all
                if not validate_all(branch_conditions, caster, target or caster, sim=sim):
                    continue

            if isinstance(branch, dict):
                actions = branch.get("actions", [])
                serialized_branches.append(branch)
            else:
                actions = getattr(branch, "actions", []) or []
                serialized_branches.append(
                    {
                        "index": getattr(branch, "index", 0),
                        "triggers": getattr(branch, "triggers", []),
                        "conditions": getattr(branch, "conditions", None),
                        "actions": actions,
                        "target_overrides": getattr(branch, "target_overrides", []),
                        "run_if_none_ran": getattr(branch, "run_if_none_ran", []),
                        "is_attack": getattr(branch, "is_attack", False),
                    }
                )
            for action in actions:
                if not isinstance(action, dict):
                    continue
                action_type = action.get("action_type")
                if action_type == "modify_stat":
                    parsed_modifiers.append(Modifier.from_modify_stat(action))
                elif action_type == "modify_meta_stat":
                    parsed_modifiers.append(
                        Modifier.from_modify_meta_stat(action)
                    )
                elif action_type in (
                    "apply_conditional_meta_stat_mod",
                    "apply_conditional_stat_mod",
                ):
                    parsed_modifiers.append(
                        Modifier.from_conditional_stat_mod(action)
                    )

        tick_interval = getattr(effect, "tick_interval", None)
        if tick_interval is not None and float(tick_interval) <= 0.0:
            tick_interval = None

        return cls(
            fqn=parent_fqn,
            name=getattr(effect, "name", None) or parent_name,
            number=getattr(effect, "number", 1),
            tags=frozenset(getattr(effect, "tags", None) or []),
            expires_at=computed_expires_at,
            tick_interval=tick_interval,
            stacks=initial_stacks,
            max_stacks=max_stacks,
            initial_stacks=initial_stacks,
            scales_with_stacks=scales_with_stacks,
            modifiers=parsed_modifiers,
            branches=serialized_branches,
            is_passive=is_passive,
            effect_blueprint=effect,
            ability_ref=ability,
        )


class ProcData:
    """Defines trigger conditions, probability, and internal cooldowns (ICD) for passive procs."""
    __slots__ = ['name','actions','chance','icd','next_possible_proc','trigger','required_tags','affected_by_cdr',
                 'conditions']

    def __init__(self, name: str, trigger: str, actions: list,
                 required_tags: list , chance: float = 1.0, icd: float = 0.0, affected_by_cdr = False, conditions: dict = None):
        self.name = name
        self.trigger = trigger
        self.required_tags = parse_tags(required_tags)
        self.chance = chance
        self.icd = icd
        self.actions = actions
        self.next_possible_proc = 0.0
        self.affected_by_cdr = affected_by_cdr
        self.conditions = conditions if conditions is not None else {}

    @classmethod
    def from_dict(cls, data: dict, fallback_name: str) -> "ProcData":
        """Constructs a Permanent Proc from a dict config"""
        name = data.get("proc_name") or data.get("name") or fallback_name
        return cls(
            name=name,
            trigger=data.get("trigger", "hit"),
            actions=data.get("actions", []),
            required_tags=data.get("required_tags"),
            chance=data.get("chance", 1.0),
            icd=data.get("icd", 0.0),
            affected_by_cdr=data.get("affected_by_cdr", False),
            conditions=data.get("conditions")
        )


def parse_tags(raw_tags) -> frozenset | None:
    """Normalizes tags to a frozenset, or None if empty."""
    if not raw_tags:
        return None
    if isinstance(raw_tags, frozenset):
        return raw_tags
    if isinstance(raw_tags, str):
        return frozenset([raw_tags])
    return frozenset(raw_tags)
