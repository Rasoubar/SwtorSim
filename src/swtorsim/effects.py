"""Runtime state representations for active buffs, debuffs, DoTs, and channeled abilities."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.swtorsim.modifiers import Modifier


def _resolve_branch_modifiers(
    raw_branches: List[Any],
    caster: Any = None,
    target: Any = None,
    sim: Any = None,
    stacks: int = 1,
) -> tuple[List[Modifier], List[Dict[str, Any]]]:
    """Evaluates branch conditions and ``run_if_none_ran`` rules in index order to collect active ``Modifier`` instances and serialized branches.

    Args:
        raw_branches: Sequence of raw branch dicts (from JSON) or ``abilities.Branch`` objects.
        caster: Source entity applying or owning the effect.
        target: Target entity receiving the effect (defaults to ``caster`` when ``None``).
        sim: Optional ``Simulation`` instance for time/cooldown condition checks.
        stacks: Initial stack/charge count passed into the condition evaluation context.

    Returns:
        A ``(parsed_modifiers, serialized_branches)`` tuple containing only the modifiers
        and branch dicts from branches whose conditions and ``run_if_none_ran`` gates passed.
    """
    parsed_modifiers: List[Modifier] = []
    serialized_branches: List[Dict[str, Any]] = []
    executed_branches: set[int] = set()
    branch_ctx = {
        "stack_multiplier": stacks,
        "current_stacks": stacks,
        "stacks": stacks,
        "charges": stacks,
    }
    actual_target = target if target is not None else caster

    for idx, branch in enumerate(raw_branches or ()):
        if isinstance(branch, dict):
            b_index = branch.get("index", idx + 1)
            branch_conditions = branch.get("conditions")
            run_if_none = branch.get("run_if_none_ran") or []
            actions = branch.get("actions") or []
            target_overrides = branch.get("target_overrides") or []
            serialized_branch = branch
        else:
            b_index = getattr(branch, "index", idx + 1)
            branch_conditions = getattr(branch, "conditions", None)
            run_if_none = getattr(branch, "run_if_none_ran", None) or []
            actions = getattr(branch, "actions", None) or []
            target_overrides = getattr(branch, "target_overrides", None) or []
            serialized_branch = {
                "index": b_index,
                "triggers": getattr(branch, "triggers", []),
                "conditions": branch_conditions,
                "actions": actions,
                "target_overrides": target_overrides,
                "run_if_none_ran": run_if_none,
                "is_attack": getattr(branch, "is_attack", False),
            }

        if run_if_none and any(b in executed_branches for b in run_if_none):
            continue

        if branch_conditions:
            from src.swtorsim.requirements import validate_all
            if not validate_all(
                branch_conditions,
                caster,
                actual_target,
                sim=sim,
                context=branch_ctx,
            ):
                continue

        executed_branches.add(b_index)
        serialized_branches.append(serialized_branch)

        for action in actions:
            if not isinstance(action, dict):
                continue
            action_type = action.get("action_type")
            if action_type == "modify_stat":
                parsed_modifiers.append(Modifier.from_modify_stat(action))
            elif action_type == "modify_meta_stat":
                parsed_modifiers.append(Modifier.from_modify_meta_stat(action))
            elif action_type in (
                "apply_conditional_meta_stat_mod",
                "apply_conditional_stat_mod",
            ):
                parsed_modifiers.append(
                    Modifier.from_conditional_stat_mod(action)
                )

    return parsed_modifiers, serialized_branches


class ActiveDot:
    """Tracks tick timing and state for active Damage-over-Time (DoT) effects."""
    __slots__ = ['name', 'interval', 'ticks_remaining', 'action_data']

    def __init__(self, name, interval, ticks_remaining, action_data: dict):
        self.name = name
        self.interval = interval
        self.ticks_remaining = ticks_remaining
        self.action_data = action_data


class ActiveChannel:
    """Tracks progress, tick intervals, and resource costs for channeled abilities."""

    def __init__(
        self,
        name: str,
        action_data: Optional[dict] = None,
        total_ticks: int = 0,
        tick_interval: float = 1.0,
        tick_cost: float = 0.0,
        ability: Any = None,
        duration: float = 0.0,
        caster: Any = None,
        target: Any = None,
    ):
        self.name = name
        self.action_data = action_data or {}
        self.total_ticks = total_ticks
        self.remaining_ticks = total_ticks
        self.current_tick = 0
        self.tick_interval = tick_interval
        self.tick_cost = tick_cost
        self.ability = ability
        self.duration = duration
        self.caster = caster
        self.target = target
        self.is_finished = False
        self.attached_effects: list = []


@dataclass
class ActiveEffect:
    """A live effect instance running on an actor."""

    # Identity
    fqn: str
    name: str
    number: int = 1
    tags: frozenset = frozenset()

    @property
    def canonical_id(self) -> str:
        if self.fqn and self.number is not None:
            return f"{self.fqn}:{self.number}"
        return self.fqn or self.name or f"effect_{id(self)}"

    # Timers
    expires_at: Optional[float] = None
    duration: float = 0.0
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
    immunities: set[str] = field(default_factory=set)

    # State
    is_passive: bool = False
    is_expired: bool = False
    total_ticks: int = 0
    ticks_remaining: int = 0
    tick_generation: int = 0  # bumped by reset_timer so a pending DotTick on the old tick phase is discarded
    owner_id: Optional[str] = None
    effect_blueprint: Any = field(default=None, repr=False, compare=False)
    ability_ref: Any = field(default=None, repr=False, compare=False)
    caster_ref: Any = field(default=None, repr=False, compare=False)
    # on_pre_remove runs once per instance, whichever path removes the effect (expiry, remove_effect, dispel, 0 stacks)
    pre_remove_fired: bool = field(default=False, repr=False, compare=False)

    def time_remaining(self, current_time: float) -> float:
        """Returns remaining duration in seconds, or ``inf`` if permanent."""
        if self.expires_at is None:
            return float("inf")
        return max(0.0, self.expires_at - current_time)

    def modify_stacks(self, amount: int) -> None:
        """Adjusts stack count by ``amount`` (clamped to ``[0, max_stacks]``) and marks expired at 0."""
        self.stacks = max(0, min(self.stacks + amount, self.max_stacks))
        if self.stacks == 0 and self.max_stacks > 0:
            self.is_expired = True

    def set_stacks(self, value: int) -> None:
        """Sets stack count directly to ``value`` (clamped to ``[0, max_stacks]``) and marks expired at 0."""
        max_st = self.max_stacks if self.max_stacks > 0 else 1
        self.stacks = max(0, min(value, max_st))
        if self.stacks == 0 and self.max_stacks > 0:
            self.is_expired = True

    def get_effective_modifiers(self) -> List[Modifier]:
        """Returns modifiers, scaled by stack count if scales_with_stacks is enabled."""
        if not self.scales_with_stacks or self.stacks == 1:
            return self.modifiers
        return [
            Modifier(
                stat=m.stat,
                value=m.value * self.stacks,
                targets=m.targets,
                conditional_tag=m.conditional_tag,
                is_percent=m.is_percent,
                actor=getattr(m, "actor", None),
                require_owner=getattr(m, "require_owner", False),
            )
            for m in self.modifiers
        ]

    def modifier_stats(self) -> frozenset:
        """Returns the stat ids (as strings) this effect's modifiers carry; stacks never change them.

        Lets callers skip effects that cannot contribute to a stat without building the
        stack-scaled modifier list. Cached per modifiers list, rebuilt if the list is swapped or resized.
        """
        mods = self.modifiers
        cache = self.__dict__.get("_modifier_stats")
        if cache is None or cache[0] is not mods or cache[1] != len(mods):
            cache = (mods, len(mods), frozenset(str(m.stat) for m in mods))
            self.__dict__["_modifier_stats"] = cache
        return cache[2]

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
        caster: Any = None,
        target: Any = None,
        sim: Any = None,
    ) -> "ActiveEffect":
        """Constructs an active or passive ``ActiveEffect`` from a parsed blueprint effect node dict, evaluating branch conditions and ``run_if_none_ran`` rules against ``caster`` and ``target``."""
        is_passive = any(
            init.get("initializer_type") == "eff_initializer__set_passive"
            and init.get("bools", {}).get("is_passive", False)
            for init in effect_node.get("initializers", [])
        )

        duration = float(effect_node.get("duration", 0.0) or 0.0)

        if is_passive:
            computed_expires_at = None
        elif expires_at is not None:
            computed_expires_at = expires_at
        elif duration > 0.0 and current_time is not None:
            computed_expires_at = current_time + duration
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

        raw_branches = effect_node.get("branches") or []
        parsed_modifiers, serialized_branches = _resolve_branch_modifiers(
            raw_branches,
            caster=caster,
            target=target if target is not None else caster,
            sim=sim,
            stacks=initial_stacks,
        )

        return cls(
            fqn=parent_fqn,
            name=effect_node.get("name") or parent_name,
            number=effect_node.get("number", 1),
            tags=frozenset(effect_node.get("tags", [])),
            expires_at=computed_expires_at,
            duration=duration,
            tick_interval=effect_node.get("tick_interval"),
            stacks=initial_stacks,
            max_stacks=max_stacks,
            initial_stacks=initial_stacks,
            scales_with_stacks=scales_with_stacks,
            modifiers=parsed_modifiers,
            branches=serialized_branches,
            is_passive=is_passive,
            effect_blueprint=effect_node,
            caster_ref=caster,
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
        """Constructs an ``ActiveEffect`` from a runtime ``Ability`` and ``abilities.Effect`` instance, evaluating branch conditions and ``run_if_none_ran`` rules against ``caster`` and ``target``."""
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

        # Apply STAT_eff_charges_max (61) and STAT_eff_charges_initial (60)
        eff_tags = frozenset(getattr(effect, "tags", None) or [])
        eff_name = getattr(effect, "name", "") or parent_name

        if caster is not None:
            caster_effects = getattr(caster, "effects", {}) or {}
            for c_eff in caster_effects.values():
                if getattr(c_eff, "is_expired", False):
                    continue
                getter = getattr(c_eff, "get_effective_modifiers", None)
                c_mods = getter() if getter is not None else getattr(c_eff, "modifiers", [])
                for mod in c_mods or ():
                    st = str(mod.stat)
                    if st in ("61", "STAT_eff_charges_max"):
                        if mod.applies_to(ability_tags=eff_tags) or (eff_name and mod.applies_to(ability_fqn=eff_name)):
                            if mod.is_percent:
                                max_stacks = int(round(max_stacks * (1.0 + mod.value)))
                            else:
                                max_stacks += int(mod.value)
                    elif st in ("60", "STAT_eff_charges_initial"):
                        if mod.applies_to(ability_tags=eff_tags) or (eff_name and mod.applies_to(ability_fqn=eff_name)):
                            if mod.is_percent:
                                initial_stacks = int(round(initial_stacks * (1.0 + mod.value)))
                            else:
                                initial_stacks += int(mod.value)

        max_stacks = max(1, max_stacks)
        initial_stacks = max(0, min(initial_stacks, max_stacks))
        scales_with_stacks = bool(
            stack_charge.get("scales_with_stack_charge", False)
            or getattr(effect, "scales_with_stacks", False)
        )

        raw_branches = getattr(effect, "branches", None) or []
        parsed_modifiers, serialized_branches = _resolve_branch_modifiers(
            raw_branches,
            caster=caster,
            target=target if target is not None else caster,
            sim=sim,
            stacks=initial_stacks,
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
            duration=duration,
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
            caster_ref=caster,
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


class EffectCollection(dict):
    """Dictionary of active effects supporting dual canonical ID and name/tag lookups.

    Keys are canonical effect identifiers (e.g. 'abl.agent.snipe:2'). Lookups by
    display name (e.g. 'Followthrough') or source FQN automatically resolve across
    active, non-expired effect instances to maintain complete transparency with
    rotation rules, telemetry, and unit tests.
    """

    def __contains__(self, key: Any) -> bool:
        if super().__contains__(key):
            val = super().__getitem__(key)
            if not getattr(val, "is_expired", False):
                return True
        if isinstance(key, str):
            for eff in super().values():
                if getattr(eff, "is_expired", False):
                    continue
                if getattr(eff, "name", None) == key or getattr(eff, "fqn", None) == key:
                    return True
        return False

    def __getitem__(self, key: Any) -> Any:
        if super().__contains__(key):
            val = super().__getitem__(key)
            if not getattr(val, "is_expired", False):
                return val
        if isinstance(key, str):
            for eff in super().values():
                if getattr(eff, "is_expired", False):
                    continue
                if getattr(eff, "name", None) == key or getattr(eff, "fqn", None) == key:
                    return eff
        return super().__getitem__(key)

    def get(self, key: Any, default: Any = None) -> Any:
        if super().__contains__(key):
            val = super().get(key, default)
            if val is not default and not getattr(val, "is_expired", False):
                return val
        if isinstance(key, str):
            for eff in super().values():
                if getattr(eff, "is_expired", False):
                    continue
                if getattr(eff, "name", None) == key or getattr(eff, "fqn", None) == key:
                    return eff
        return default

    def pop(self, key: Any, *args) -> Any:
        if super().__contains__(key):
            return super().pop(key, *args)
        if isinstance(key, str):
            keys_to_pop = [
                k for k, eff in super().items()
                if getattr(eff, "name", None) == key or getattr(eff, "fqn", None) == key
            ]
            if keys_to_pop:
                res = None
                for k in keys_to_pop:
                    res = super().pop(k)
                return res
        if args:
            return args[0]
        raise KeyError(key)

    def get_all(self, name_or_fqn: str) -> List[ActiveEffect]:
        """Returns all active, non-expired effects matching the given name or FQN."""
        matches = []
        for eff in super().values():
            if getattr(eff, "is_expired", False):
                continue
            if getattr(eff, "name", None) == name_or_fqn or getattr(eff, "fqn", None) == name_or_fqn:
                matches.append(eff)
        return matches

