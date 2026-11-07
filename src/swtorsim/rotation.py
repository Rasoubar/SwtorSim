"""Sequential and priority-based ability rotation evaluator."""

from src.swtorsim.requirements import validate_all

class Rotation:
    """Evaluates an ordered sequence of opener and looping priority/fixed/optional ability steps."""

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
                lead_time = float(step_data.get("lead_time") or step_data.get("pre_cast_offset") or 0.0)
                self.sequence.append(
                    OptionalAbilityStep(
                        step_data["ability_id"],
                        step_data.get("rules", {}),
                        lead_time=lead_time,
                    )
                )
            elif step_data["type"] == "loop_anchor": #discriminates rotation from opener if applicable
                self.loop_start_index = len(self.sequence)
                continue

    def get_next_lead_time(self, player=None, current_time: float = 0.0) -> float:
        """Returns the lead_time (in seconds) of the current or next immediate optional off-GCD step."""
        if self.current_step >= len(self.sequence):
            return 0.0
        step = self.sequence[self.current_step]
        if isinstance(step, OptionalAbilityStep):
            return getattr(step, "lead_time", 0.0)
        return 0.0

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
    """Mandatory rotation step that blocks until its target ability is successfully cast."""

    def __init__(self, ability_id):
        self.ability_id = ability_id

    def evaluate(self, player, target, sim) -> bool:
        """Mandatory step. Only resolves (returns True) if the ability casts successfully."""
        ability = player.ability_db.get(self.ability_id)
        return ability.cast(player, target, sim)

class PriorityBlockStep:
    """Priority-ordered pool of conditional ability options; casts the first available option."""

    def __init__(self, name, pool):
        self.name = name
        self.pool = pool

    def evaluate(self, player, target, sim) -> bool:
        """Mandatory block step. Resolves if any valid priority option casts successfully."""
        for option in self.pool:
            wanna_cast = validate_all(option.get("rules", {}), player, target, sim)
            if wanna_cast:
                ability = player.ability_db.get(option["ability_id"])
                if ability and ability.cast(player, target, sim):
                    return True
        return False


class OptionalAbilityStep:
    """Non-blocking step (typically off-GCD buffs/adrenals) that attempts to cast and advances."""

    def __init__(self, ability_id, rules=None, lead_time: float = 0.0):
        self.ability_id = ability_id
        self.rules = rules if rules is not None else {}
        self.lead_time = float(lead_time or 0.0)

    def evaluate(self, player, target, sim) -> bool:
        """Non-blocking step. Tries to cast if rules allow.
        If evaluated early (before player.next_gcd due to lead_time):
            - If it successfully casts, resolves and advances (returns True).
            - If it cannot cast yet (rules fail or on cooldown), returns False so it retries at next_gcd.
        If evaluated at or after player.next_gcd:
            - Always resolves and advances (returns True) even if it did not cast.
        """
        is_early = (getattr(player, "next_gcd", 0.0) - sim.current_time) > 1e-4
        wanna_cast = validate_all(self.rules, player, target, sim=sim)
        if wanna_cast:
            ability = player.ability_db.get(self.ability_id)
            if ability and ability.can_cast(player, target, sim):
                ability.cast(player, target, sim)
                return True
        if is_early:
            return False
        return True
