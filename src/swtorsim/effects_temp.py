from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.swtorsim.modifiers import Modifier


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
    scales_with_stacks: bool = False

    # Payloads
    modifiers: List[Modifier] = field(default_factory=list)
    branches: List[Dict[str, Any]] = field(default_factory=list)

    # State
    is_expired: bool = False

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
            Modifier(stat=m.stat, value=m.value * self.stacks, targets=m.targets)
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
        """Constructs an active or passive effect from a blueprint effect node."""
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
        max_stacks = stack_charge.get("nr_occurances", 1)

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

        return cls(
            fqn=parent_fqn,
            name=effect_node.get("name") or parent_name,
            number=effect_node.get("number", 1),
            tags=frozenset(effect_node.get("tags", [])),
            expires_at=computed_expires_at,
            tick_interval=effect_node.get("tick_interval"),
            stacks=1,
            max_stacks=max_stacks,
            scales_with_stacks=effect_node.get("scales_with_stacks", False),
            modifiers=parsed_modifiers,
            branches=branches,
        )