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
        # Loop-only "always weave" entries: each is tried like an optional step before every
        # sequence step from the loop anchor on. weave_pos = entries already resolved at this step.
        self.weave = []
        self.weave_pos = 0

        self.build_steps(steps_config)
        self.build_weave(steps_config)

    def build_steps(self, steps_config):
        """On setup builds the rotation according to config"""
        raw_list = (
            (steps_config.get("sequence") or steps_config.get("steps") or [])
            if isinstance(steps_config, dict)
            else (steps_config or [])
        )
        for step_data in raw_list:
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

    def build_weave(self, steps_config):
        """Builds the loop-only weave entries from the 'weave' list of a dict rotation config."""
        raw_weave = steps_config.get("weave") if isinstance(steps_config, dict) else None
        for entry in raw_weave or []:
            if not isinstance(entry, dict) or not entry.get("ability_id"):
                continue
            lead = entry.get("lead_time") if "lead_time" in entry else entry.get("pre_cast_offset")
            self.weave.append(OptionalAbilityStep(entry["ability_id"], entry.get("rules", {}), lead_time=lead))

    def pending_weave_step(self):
        """The weave entry to try before the current sequence step, or None (opener, or all tried)."""
        if self.weave and self.weave_pos < len(self.weave) and self.current_step >= self.loop_start_index:
            return self.weave[self.weave_pos]
        return None

    def get_next_lead_time(self, player=None, current_time: float = 0.0, sim=None) -> float:
        """Returns the lead_time (in seconds) if the upcoming ability is off-GCD and can be cast early.

        ``sim`` is passed to the priority-pool rule checks so clock-based rules (proc and ability
        cooldowns) preview the same answer the real evaluation will get.
        """
        if self.current_step >= len(self.sequence):
            return 0.0
        step = self.pending_weave_step() or self.sequence[self.current_step]

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
                if rules and not validate_all(rules, player, target, sim):
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
        weave_step = self.pending_weave_step()
        if weave_step is not None:
            # Same contract as an optional step placed here: resolves when cast or skipped at ready time.
            if weave_step.evaluate(player, target, sim):
                self.weave_pos += 1
                return True
            return False
        step = self.sequence[self.current_step]
        if step.evaluate(player, target, sim): #evaluates different step kinds acording to their class rules
            self.weave_pos = 0
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
        tracer = getattr(sim, "tracer", None)

        # Fast path when no diagnostic tracer is attached
        if tracer is None:
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

        # Diagnostic path when tracer is active
        candidates_trace = []
        for option in self.pool:
            wanna_cast = validate_all(option.get("rules", {}), player, target, sim)
            ability = player.ability_db.get(option["ability_id"])
            ability_name = ability.name if ability else option["ability_id"]
            if not wanna_cast:
                candidates_trace.append({
                    "ability": ability_name,
                    "rules_passed": False,
                    "can_cast": False,
                    "reason": "Priority rules not satisfied",
                    "accepted": False,
                })
                continue
            if is_early and (not ability or getattr(ability, "triggers_gcd", True)):
                candidates_trace.append({
                    "ability": ability_name,
                    "rules_passed": True,
                    "can_cast": False,
                    "reason": "Early check (triggers GCD)",
                    "accepted": False,
                })
                continue
            if ability:
                can_cast, reason = (
                    ability.check_cast_eligibility(player, target, sim)
                    if hasattr(ability, "check_cast_eligibility")
                    else (ability.can_cast(player, target, sim), "Ready")
                )
                if can_cast:
                    if ability.cast(player, target, sim):
                        candidates_trace.append({
                            "ability": ability_name,
                            "rules_passed": True,
                            "can_cast": True,
                            "reason": "Cast initiated",
                            "accepted": True,
                        })
                        tracer.record_rotation_evaluation(
                            timestamp=sim.current_time,
                            step_index=getattr(self, "step_index", 0),
                            step_type="priority_block",
                            step_name=self.name,
                            candidates=candidates_trace,
                            chosen_ability=ability_name,
                            is_stall=False,
                        )
                        return True
                    else:
                        reason = "Cast execution returned False"

                candidates_trace.append({
                    "ability": ability_name,
                    "rules_passed": True,
                    "can_cast": False,
                    "reason": reason,
                    "accepted": False,
                })

        tracer.record_rotation_evaluation(
            timestamp=sim.current_time,
            step_index=getattr(self, "step_index", 0),
            step_type="priority_block",
            step_name=self.name,
            candidates=candidates_trace,
            chosen_ability=None,
            is_stall=not is_early,
        )
        return False


class OptionalAbilityStep:
    """Non-blocking step (typically off-GCD buffs/adrenals) that attempts to cast and advances."""

    def __init__(self, ability_id, rules=None, lead_time: float | None = None):
        self.ability_id = ability_id
        self.rules = rules if rules is not None else {}
        self.lead_time = float(lead_time) if lead_time is not None else None

    def evaluate(self, player, target, sim) -> bool:
        """Non-blocking step. Tries to cast if rules allow.
        If evaluated early (before player.next_gcd due to lead_time) or during an active channel/cast:
            - If it successfully casts, resolves and advances (returns True).
            - If it cannot cast yet (rules fail, on cooldown, or busy channeling/casting),
              returns False so it retries once the character is ready.
        If evaluated when character is ready (at or after player.next_gcd and not channeling/casting):
            - Always resolves and advances (returns True) even if it did not cast.
        """
        is_early = (getattr(player, "next_gcd", 0.0) - sim.current_time) > 1e-4
        is_channeling_or_casting = (
            getattr(player, "active_channel", None) is not None
            or getattr(player, "active_cast", None) is not None
        )
        should_wait = is_early or is_channeling_or_casting

        tracer = getattr(sim, "tracer", None)
        ability = player.ability_db.get(self.ability_id)
        reason = None
        wanna_cast = validate_all(self.rules, player, target, sim=sim)
        if wanna_cast:
            if is_channeling_or_casting and (not ability or not getattr(ability, "allow_clip", False)):
                return False
            if is_early and (not ability or getattr(ability, "triggers_gcd", True)):
                return False
            if ability and ability.can_cast(player, target, sim):
                if tracer is not None:
                    self._trace(tracer, sim, ability, True, True, "Cast initiated", self.ability_id)
                ability.cast(player, target, sim)
                return True
            if tracer is not None and not should_wait:
                if ability and hasattr(ability, "check_cast_eligibility"):
                    reason = ability.check_cast_eligibility(player, target, sim)[1]
                else:
                    reason = "Cannot cast"
        elif tracer is not None and not should_wait:
            reason = "Optional rules not satisfied"
        if should_wait:
            return False
        if tracer is not None:
            self._trace(tracer, sim, ability, bool(wanna_cast), False, reason or "Skipped", None)
        return True

    def _trace(self, tracer, sim, ability, rules_passed, accepted, reason, chosen):
        """Records an optional-step decision (cast or skipped) for the debugger."""
        name = ability.name if ability else self.ability_id
        tracer.record_rotation_evaluation(
            timestamp=sim.current_time,
            step_index=getattr(self, "step_index", 0),
            step_type="optional",
            step_name=name,
            candidates=[{
                "ability": name,
                "rules_passed": rules_passed,
                "can_cast": accepted,
                "reason": reason,
                "accepted": accepted,
            }],
            chosen_ability=name if chosen else None,
            is_stall=False,
        )
