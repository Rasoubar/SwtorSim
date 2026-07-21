class ResourcePool:
    def __init__(self, pool_type: str = "Force", max_value: float = 100.0, base_regen: float = 8.0):
        self.pool_type = pool_type
        self.max_value = max_value
        self.current_value = max_value
        self.base_regen = base_regen

    def can_afford(self, amount: float) -> bool:
        # heat was dumb to put already, I only really play assassin, pt tank and merc heal so I thought "oh, I can't
        # account only for force" but forgot about warriors.
        if self.pool_type == "Heat":
            return self.current_value + amount <= self.max_value
        else:
            return self.current_value >= amount

    def spend(self, amount: float) -> bool:
        if self.pool_type == "Heat":
            if self.current_value + amount > self.max_value:
                return False
            self.current_value += amount
            return True
        else:
            if self.current_value < amount:
                return False
            self.current_value -= amount
            return True

    def generate(self, amount: float):
        if self.pool_type == "Heat":
            self.current_value = max(0.0, self.current_value - amount)
        else:
            self.current_value = min(self.max_value, self.current_value + amount)

    def tick_passive_regen(self, delta_time: float, alacrity_modifier: float = 1.0): #only works properly for force rn
        actual_regen_rate = self.base_regen * alacrity_modifier
        self.generate(actual_regen_rate * delta_time)
