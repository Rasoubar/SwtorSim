class PriorityRotation:
    def __init__(self, priority_list: list):
        self.priority_list = priority_list

    def evaluate(self, player, target, sim) -> bool:
        for ability in self.priority_list:
            if ability.can_cast(player, target, sim):
                return ability.cast(player, target, sim)
        return False

    
class FixedRotation:
    def __init__(self, sequence: list, loop: bool = True):
        self.sequence = sequence
        self.loop = loop
        self.current_step = 0

    def evaluate(self, player, target, sim) -> bool:
        if self.current_step >= len(self.sequence):
            return False
        ability = self.sequence[self.current_step]
        if ability.can_cast(player, target, sim):
            success = ability.cast(player, target, sim)
            if success:
                self.current_step += 1
                if self.loop and self.current_step >= len(self.sequence):
                    self.current_step = 0
                return True

        return False