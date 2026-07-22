class ResourcePool:
    """Base class for resource pools."""

    def __init__(self, pool_type: str, max_value: float = 100.0, base_regen: float = 0.0):
        self.pool_type = pool_type
        self.max_value = max_value
        self.base_regen = base_regen
        self.current_value = max_value

    def can_afford(self, amount: float) -> bool:
        raise NotImplementedError

    def spend(self, amount: float) -> bool:
        raise NotImplementedError

    def generate(self, amount: float):
        raise NotImplementedError

    def tick_passive_regen(self, delta_time: float, alacrity_modifier: float = 1.0):
        """Ticks passive regeneration over time."""
        pass


class StandardPool(ResourcePool):
    """Force: Flat regen rate regardless of current value."""

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

    def tick_passive_regen(self, delta_time: float, alacrity_modifier: float = 1.0):
        actual_regen = self.base_regen * alacrity_modifier
        self.generate(actual_regen * delta_time)


class HeatPool(ResourcePool):
    """Heat: Starts at 0, builds up to 100. Vents faster when low, slower when high."""

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
        """Vents heat (lowers value towards 0)."""
        self.current_value = max(0.0, self.current_value - amount)

    def get_current_regen_rate(self) -> float:
        """Exact brackets: <40 is 5.0, 40-79 is 3.0, 80+ is 2.0"""
        if self.current_value < 40.0:
            return 5.0
        elif self.current_value < 80.0:
            return 3.0
        return 2.0

    def tick_passive_regen(self, delta_time: float, alacrity_modifier: float = 1.0):
        actual_regen = self.get_current_regen_rate() * alacrity_modifier
        self.generate(actual_regen * delta_time)


class EnergyPool(StandardPool):
    """Energy: Starts at 100. Reverse Heat brackets."""

    def __init__(self, pool_type: str = "Energy", max_value: float = 100.0, base_regen: float = 5.0):
        super().__init__(pool_type, max_value, base_regen)

    def can_afford(self, amount: float) -> bool:
        return self.current_value >= amount

    def get_current_regen_rate(self) -> float:
        """Exact brackets: >=60 is 5.0, 20-59 is 3.0, <20 is 2.0"""
        if self.current_value >= 60.0:
            return 5.0
        elif self.current_value >= 20.0:
            return 3.0
        return 2.0

    def tick_passive_regen(self, delta_time: float, alacrity_modifier: float = 1.0):
        actual_regen = self.get_current_regen_rate() * alacrity_modifier
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

    def tick_passive_regen(self, delta_time: float, alacrity_modifier: float = 1.0):
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


def create_resource_pool(pool_type: str = "Force", max_value: float = 100.0, base_regen: float = 8.0) -> ResourcePool:
    """Factory helper to instantiate the appropriate ResourcePool subclass."""
    cls = RESOURCE_POOL_MAP.get(pool_type.lower(), StandardPool)
    return cls(pool_type=pool_type, max_value=max_value, base_regen=base_regen)