class PriorityRotation:
    def __init__(self, priority_list: list):
        self.priority_list = priority_list

    def evaluate(self, player, target, sim) -> bool:
        for ability in self.priority_list:
            if ability.can_cast(player, sim):
                return ability.cast(player, target, sim)
        return False

