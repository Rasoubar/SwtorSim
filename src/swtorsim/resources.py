from typing import Any, Optional

class ResourcePool:
    """Base class for resource pools"""

    def __init__(self, pool_type: str, max_value: float = 100.0, base_regen: float = 0.0):
        self.pool_type = pool_type
        self.max_value = max_value
        self.base_regen = base_regen
        self.current_value = max_value

    def can_afford(self, amount: float) -> bool:
        """Returns True if the pool has sufficient resource to pay `amount`."""
        raise NotImplementedError

    def spend(self, amount: float) -> bool:
        """Deducts `amount` if affordable. Returns True on success, False otherwise."""
        raise NotImplementedError

    def generate(self, amount: float):
        """Adds `amount` of resource to the pool, capped at `max_value`."""
        raise NotImplementedError

    def tick_passive_regen(self, delta_time: float, alacrity_modifier: float = 1.0, player: Any = None):
        """Ticks passive regeneration over time"""
        pass


class StandardPool(ResourcePool):
    """Force: Flat regen rate regardless of current value"""

    def __init__(self, pool_type: str = "Force", max_value: float = 100.0, base_regen: float = 8.0):
        super().__init__(pool_type, max_value, base_regen)

    def can_afford(self, amount: float) -> bool:
        return self.current_value >= amount

    def spend(self, amount: float) -> bool:
        if not self.can_afford(amount):
            return False
        self.current_value -= amount
        return True

    def generate(self, amount: float):
        self.current_value = min(self.max_value, self.current_value + amount)

    def tick_passive_regen(self, delta_time: float, alacrity_modifier: float = 1.0, player: Any = None):
        base = self.base_regen
        if player is not None and hasattr(player, "calculate_resource_regen"):
            rate = player.calculate_resource_regen(base, self.pool_type)
        else:
            rate = base
        actual_regen = rate * alacrity_modifier
        self.generate(actual_regen * delta_time)


class HeatPool(ResourcePool):
    """Heat: Starts at 0, builds up to 100. Vents faster when low, slower when high.

    Note: To maintain interface consistency with other pools, `spend()` builds heat
    and `generate()` vents/reduces heat.
    """

    def __init__(self, pool_type: str = "Heat", max_value: float = 100.0, base_regen: float = 5.0):
        super().__init__(pool_type, max_value, base_regen)
        self.current_value = 0.0

    def can_afford(self, amount: float) -> bool:
        return (self.current_value + amount) <= self.max_value

    def spend(self, amount: float) -> bool:
        if not self.can_afford(amount):
            return False
        self.current_value += amount
        return True

    def generate(self, amount: float):
        """Vents heat (lowers value towards 0)"""
        self.current_value = max(0.0, self.current_value - amount)

    def get_current_regen_rate(self) -> float:
        """Exact brackets: <40 is 5.0, 40-79 is 3.0, 80+ is 2.0"""
        if self.current_value < 40.0:
            return 5.0
        elif self.current_value < 80.0:
            return 3.0
        return 2.0

    def tick_passive_regen(self, delta_time: float, alacrity_modifier: float = 1.0, player: Any = None):
        base = self.get_current_regen_rate()
        if player is not None and hasattr(player, "calculate_resource_regen"):
            rate = player.calculate_resource_regen(base, self.pool_type)
        else:
            rate = base
        actual_regen = rate * alacrity_modifier
        self.generate(actual_regen * delta_time)


class EnergyPool(StandardPool):
    """Energy: Starts at 100. Reverse Heat brackets."""

    def __init__(self, pool_type: str = "Energy", max_value: float = 100.0, base_regen: float = 5.0):
        super().__init__(pool_type, max_value, base_regen)

    def can_afford(self, amount: float) -> bool:
        return self.current_value >= amount

    def generate(self, amount: float):
        self.current_value = min(self.max_value, self.current_value + amount)

    def get_current_regen_rate(self) -> float:
        """Exact brackets: >=60 is 5.0, 20-59 is 3.0, <20 is 2.0"""
        if self.current_value >= 60.0:
            return 5.0
        elif self.current_value >= 20.0:
            return 3.0
        return 2.0

    def tick_passive_regen(self, delta_time: float, alacrity_modifier: float = 1.0, player: Any = None):
        base = self.get_current_regen_rate()
        if player is not None and hasattr(player, "calculate_resource_regen"):
            rate = player.calculate_resource_regen(base, self.pool_type)
        else:
            rate = base
        actual_regen = rate * alacrity_modifier
        self.generate(actual_regen * delta_time)


class BuilderPool(ResourcePool):
    """Rage/Focus: Starts empty (0), built by abilities. Supports optional passive decay."""

    def __init__(self, pool_type: str = "Rage", max_value: float = 12.0, decay_rate: float = 0.0):
        super().__init__(pool_type, max_value, base_regen=0.0)
        self.current_value = 0.0
        self.decay_rate = decay_rate

    def can_afford(self, amount: float) -> bool:
        return self.current_value >= amount

    def spend(self, amount: float) -> bool:
        if not self.can_afford(amount):
            return False
        self.current_value -= amount
        return True

    def generate(self, amount: float):
        self.current_value = min(self.max_value, self.current_value + amount)

    def tick_passive_regen(self, delta_time: float, alacrity_modifier: float = 1.0, player: Any = None):
        """Loses resource over time if decay_rate > 0. Not properly implemented yet."""
        if self.decay_rate > 0.0:
            self.current_value = max(0.0, self.current_value - (self.decay_rate * delta_time))

RESOURCE_POOL_MAP = {
    "force": StandardPool,
    "energy": EnergyPool,
    "heat": HeatPool,
    "rage": BuilderPool,
    "focus": BuilderPool,
}


# Class (discipline tab_name, lowercase) -> resource pool type. Classes not listed use the "Force" default.
CLASS_RESOURCE_MAP = {
    "marauder": "rage",
}


def resource_type_for_class(class_name: Optional[str]) -> str:
    """Returns the resource pool type for a class name, defaulting to Force."""
    return CLASS_RESOURCE_MAP.get((class_name or "").strip().lower(), "Force")


def create_resource_pool(pool_type: str = "Force", max_value: Optional[float] = None, base_regen: float = 8.0) -> ResourcePool:
    """Helper to instantiate the appropriate ResourcePool subclass."""
    cls = RESOURCE_POOL_MAP.get(pool_type.lower(), StandardPool)
    if issubclass(cls, BuilderPool):
        # Builder pools (Rage/Focus) have no passive regen and their own max value.
        if max_value is None:
            return cls(pool_type=pool_type)
        return cls(pool_type=pool_type, max_value=max_value)
    return cls(pool_type=pool_type, max_value=100.0 if max_value is None else max_value, base_regen=base_regen)