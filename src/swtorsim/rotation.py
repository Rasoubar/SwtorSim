"""Sequential and priority-based ability rotation evaluator."""

from src.swtorsim.requirements import validate_all

DEFAULT_OFF_GCD_LEAD_TIME: float = 0.4


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
                lead = step_data.get("lead_time") if "lead_time" in step_data else step_data.get("pre_cast_offset")
                self.sequence.append(FixedAbilityStep(step_data["ability_id"], lead_time=lead))
            elif step_data["type"] == "priority_block":
                lead = step_data.get("lead_time") if "lead_time" in step_data else step_data.get("pre_cast_offset")
                self.sequence.append(PriorityBlockStep(step_data["name"], step_data["pool"], lead_time=lead))
            elif step_data["type"] == "optional":
                lead = step_data.get("lead_time") if "lead_time" in step_data else step_data.get("pre_cast_offset")
                self.sequence.append(
                    OptionalAbilityStep(
                        step_data["ability_id"],
                        step_data.get("rules", {}),
                        lead_time=lead,
                    )
                )
            elif step_data["type"] == "loop_anchor": #discriminates rotation from opener if applicable
                self.loop_start_index = len(self.sequence)
                continue

    def get_next_lead_time(self, player=None, current_time: float = 0.0) -> float:
        """Returns the lead_time (in seconds) if the upcoming ability is off-GCD and can be cast early."""
        if self.current_step >= len(self.sequence):
            return 0.0
        step = self.sequence[self.current_step]

        # 1. Direct step with ability_id (FixedAbilityStep or OptionalAbilityStep)
        ability_id = getattr(step, "ability_id", None)
        if ability_id and player is not None:
            ability = player.ability_db.get(ability_id)
            if ability and not getattr(ability, "triggers_gcd", True):
                lead = getattr(step, "lead_time", None)
                if lead is not None:
                    return max(0.0, float(lead))
                return DEFAULT_OFF_GCD_LEAD_TIME

        # 2. PriorityBlockStep: check the top viable candidate in the pool
        if isinstance(step, PriorityBlockStep) and player is not None:
            target = getattr(player, "current_target", None)
            for option in getattr(step, "pool", ()):
                rules = option.get("rules", {})
                if rules and not validate_all(rules, player, target):
                    continue
                abl_id = option.get("ability_id")
                ability = player.ability_db.get(abl_id) if abl_id else None
                if ability and not getattr(ability, "triggers_gcd", True):
                    lead = option.get("lead_time")
                    if lead is None:
                        lead = getattr(step, "lead_time", None)
                    return max(0.0, float(lead)) if lead is not None else DEFAULT_OFF_GCD_LEAD_TIME
                # First viable candidate in priority block is an on-GCD ability; do not lead early
                break

        # 3. Explicit lead_time defined on step regardless of ability detection
        lead = getattr(step, "lead_time", None)
        if lead is not None and lead > 0.0:
            return float(lead)

        return 0.0

    def evaluate(self, player, target, sim) -> bool:
        """Evaluates the current step in the sequence.
        Returns:
            bool: True if the step resolved and advanced the rotation pointer,
                  False if the step is blocked (e.g., mandatory ability on cooldown,
                  or early evaluation that cannot cast yet).
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

    def __init__(self, ability_id, lead_time: float | None = None):
        self.ability_id = ability_id
        self.lead_time = float(lead_time) if lead_time is not None else None

    def evaluate(self, player, target, sim) -> bool:
        """Mandatory step. Resolves (returns True) if the ability casts successfully.
        If evaluated early (before player.next_gcd due to lead_time):
            - If it casts successfully, resolves and advances (returns True).
            - If it cannot cast yet (e.g. cooldown/resource), returns False so it retries at next_gcd.
        """
        is_early = (getattr(player, "next_gcd", 0.0) - sim.current_time) > 1e-4
        ability = player.ability_db.get(self.ability_id)
        if is_early and (not ability or getattr(ability, "triggers_gcd", True)):
            return False
        if ability and ability.can_cast(player, target, sim):
            return ability.cast(player, target, sim)
        if is_early:
            return False
        return False


class PriorityBlockStep:
    """Priority-ordered pool of conditional ability options; casts the first available option."""

    def __init__(self, name, pool, lead_time: float | None = None):
        self.name = name
        self.pool = pool
        self.lead_time = float(lead_time) if lead_time is not None else None

    def evaluate(self, player, target, sim) -> bool:
        """Mandatory block step. Resolves if any valid priority option casts successfully."""
        is_early = (getattr(player, "next_gcd", 0.0) - sim.current_time) > 1e-4
        for option in self.pool:
            wanna_cast = validate_all(option.get("rules", {}), player, target, sim)
            if wanna_cast:
                ability = player.ability_db.get(option["ability_id"])
                # If we are early (before next_gcd), only off-GCD abilities can be cast
                if is_early and (not ability or getattr(ability, "triggers_gcd", True)):
                    continue
                if ability and ability.cast(player, target, sim):
                    return True
        return False


class OptionalAbilityStep:
    """Non-blocking step (typically off-GCD buffs/adrenals) that attempts to cast and advances."""

    def __init__(self, ability_id, rules=None, lead_time: float | None = None):
        self.ability_id = ability_id
        self.rules = rules if rules is not None else {}
        self.lead_time = float(lead_time) if lead_time is not None else None

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
            if is_early and (not ability or getattr(ability, "triggers_gcd", True)):
                return False
            if ability and ability.can_cast(player, target, sim):
                ability.cast(player, target, sim)
                return True
        if is_early:
            return False
        return True
