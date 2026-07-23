from src.swtorsim.requirements import validate_all

class Rotation:
    def __init__(self, name, steps_config, loop: bool = True):
        self.name = name
        self.sequence = []
        self.current_step = 0
        self.loop_start_index = 0
        self.loop = loop

        self.build_steps(steps_config)

    def build_steps(self, steps_config):
        """On setup builds the rotation according to config"""
        for step_data in steps_config:
            if step_data["type"] == "fixed":
                self.sequence.append(FixedAbilityStep(step_data["ability_id"]))
            elif step_data["type"] == "priority_block":
                self.sequence.append(PriorityBlockStep(step_data["name"], step_data["pool"]))
            elif step_data["type"] == "optional":
                self.sequence.append(OptionalAbilityStep(step_data["ability_id"], step_data.get("rules", {})))
            elif step_data["type"] == "loop_anchor": #discriminates rotation from opener if applicable
                self.loop_start_index = len(self.sequence)
                continue

    def evaluate(self, player, target, sim) -> bool:
        """Evaluates the current step in the sequence.
        Returns:
            bool: True if the step resolved and advanced the rotation pointer,
                  False if the step is blocked (e.g., mandatory ability on cooldown).
        """
        if self.current_step >= len(self.sequence):
            return False
        step = self.sequence[self.current_step]
        if step.evaluate(player, target, sim): #evaluates different step kinds acording to their class rules
            self.current_step += 1
            if self.loop and self.current_step >= len(self.sequence):
                self.current_step = self.loop_start_index
            return True
        return False


class FixedAbilityStep:
    def __init__(self, ability_id):
        self.ability_id = ability_id

    def evaluate(self, player, target, sim) -> bool:
        """Mandatory step. Only resolves (returns True) if the ability casts successfully."""
        ability = sim.ability_db.get(self.ability_id)
        return ability.cast(player, target, sim)

class PriorityBlockStep:
    def __init__(self, name, pool):
        self.name = name
        self.pool = pool

    def evaluate(self, player, target, sim) -> bool:
        """Mandatory block step. Resolves if any valid priority option casts successfully."""
        for option in self.pool:
            wanna_cast = validate_all(option.get("rules", {}), player, target, sim)
            if wanna_cast:
                ability = sim.ability_db.get(option["ability_id"])
                if ability and ability.cast(player, target, sim):
                    return True
        return False


class OptionalAbilityStep:
    def __init__(self, ability_id, rules=None):
        self.ability_id = ability_id
        self.rules = rules if rules is not None else {}

    def evaluate(self, player, target, sim) -> bool:
        """Non-blocking step. Tries to cast if rules allow, but ALWAYS resolves so the rotation advances"""
        wanna_cast = validate_all(self.rules, player, target, sim=sim)
        if wanna_cast:
            ability = sim.ability_db.get(self.ability_id)
            ability.cast(player, target, sim)
        return True