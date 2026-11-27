"""Unit tests: an effect's on_stack_charge_decreased branches run when it loses a stack."""

import random
import unittest

from src.swtorsim.abilities import Ability, AbilityBlueprint, execute_single_action
from src.swtorsim.engine import Simulation
from src.swtorsim.entities import Dummy, Player

FQN = "abl.test.mark"
KEY = f"{FQN}:1"
CONSUME = {"action_type": "modify_stack_charge", "floats": {"amount_min": -1.0, "amount_max": -1.0}}
REFUND = {"action_type": "modify_stack_charge", "floats": {"amount_min": 1.0, "amount_max": 1.0}}
GAIN = {"action_type": "energy_recovery", "min": 2.0, "max": 2.0}
NEVER = {"list": [{"id": "c1", "type": "is_companion"}], "logic": {"condition": "c1"}}


def _branch(index, actions, chance=None, conditions=None, overrides=None):
    trigger = {"trigger": "on_stack_charge_decreased"}
    if chance is not None:
        trigger["floats"] = {"proc_chance_percent": chance}
    return {
        "index": index,
        "triggers": [trigger],
        "actions": actions,
        "conditions": conditions,
        "target_overrides": overrides or [],
    }


def _setup(branches, stacks=3):
    """A 30s mark with ``stacks`` charges on the dummy, cast by the player (Force at 50)."""
    blueprint = AbilityBlueprint.from_dict({
        "fqn": FQN,
        "name": "Mark",
        "type": "active",
        "effects": [{
            "number": 1,
            "entry": True,
            "name": "Mark",
            "duration": 30.0,
            "stack_charge": {"initial": stacks, "max": stacks},
            "branches": branches,
        }],
    })
    sim = Simulation(verbose=False, seed=1)
    player = Player("assassin")
    target = Dummy("Target Dummy", hp=1_000_000)
    player.current_target = target
    player.resource.current_value = 50.0
    Ability(blueprint).execute_effect(1, player, target, sim)
    return sim, player, target


def _consume(sim, player, target):
    context = {"owner_entity": target, "owner_effect_key": KEY}
    execute_single_action(sim, player, target, CONSUME, "Mark", context=context)


class StackDecreaseBranchTests(unittest.TestCase):
    def test_losing_a_stack_runs_the_effects_decrease_branch(self):
        sim, player, target = _setup([_branch(2, [GAIN], overrides=[{"type": "caster"}])])

        _consume(sim, player, target)

        self.assertEqual(target.effects[KEY].stacks, 2)
        self.assertEqual(player.resource.current_value, 52.0)

    def test_branch_runs_for_the_last_stack_before_the_effect_is_removed(self):
        sim, player, target = _setup([_branch(2, [GAIN], overrides=[{"type": "caster"}])], stacks=1)

        _consume(sim, player, target)

        self.assertEqual(player.resource.current_value, 52.0)
        self.assertNotIn(KEY, target.effects)

    def test_trigger_proc_chance_is_rolled(self):
        sim, player, target = _setup([
            _branch(2, [GAIN], chance=0.0, overrides=[{"type": "caster"}]),
            _branch(3, [GAIN], chance=100.0, overrides=[{"type": "caster"}]),
        ])
        random.seed(7)

        _consume(sim, player, target)

        # Only the 100% branch fires.
        self.assertEqual(player.resource.current_value, 52.0)

    def test_failed_conditions_do_not_draw_from_the_rng(self):
        sim, player, target = _setup([_branch(2, [GAIN], chance=50.0, conditions=NEVER)])
        random.seed(7)
        state = random.getstate()

        _consume(sim, player, target)

        self.assertEqual(random.getstate(), state)
        self.assertEqual(player.resource.current_value, 50.0)

    def test_refund_branch_gives_the_stack_back(self):
        sim, player, target = _setup([_branch(2, [REFUND])])

        _consume(sim, player, target)

        self.assertEqual(target.effects[KEY].stacks, 3)

    def test_refund_branch_keeps_the_last_stack_alive(self):
        sim, player, target = _setup([_branch(2, [REFUND])], stacks=1)

        _consume(sim, player, target)

        self.assertIn(KEY, target.effects)
        self.assertEqual(target.effects[KEY].stacks, 1)
        self.assertFalse(target.effects[KEY].is_expired)

    def test_branch_that_removes_a_stack_does_not_reenter(self):
        sim, player, target = _setup([_branch(2, [CONSUME])])

        _consume(sim, player, target)

        # One stack by the consume, one by the branch; the branch's own loss does not fire it again.
        self.assertEqual(target.effects[KEY].stacks, 1)


if __name__ == "__main__":
    unittest.main()
