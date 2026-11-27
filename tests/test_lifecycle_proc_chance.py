"""Unit tests: lifecycle triggers (on_tick etc.) honor proc_chance_percent and stat 228 bonuses.

Lifecycle triggers never reach the TriggerManager, so Effect.execute_triggered_branches rolls them.
Example: Crushing Darkness' DoT has a 25% per-tick chance to call Forked Darkness, and Death Channel
adds +25 points to it through stat 228.
"""

import random
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.swtorsim import abilities
from src.swtorsim.abilities import AbilityBlueprint
from src.swtorsim.engine import Simulation
from src.swtorsim.entities import Dummy, Player
from src.swtorsim.modifiers import Modifier

DOT_TAG = "tag.test.dot"
GAIN = {"action_type": "energy_recovery", "min": 2.0, "max": 2.0}
NEVER = {"list": [{"id": "c1", "type": "is_companion"}], "logic": {"condition": "c1"}}


def _dot(chance=None, conditions=None, trigger="on_tick"):
    """A ticking effect whose single branch gives the caster 2 Force on ``trigger``."""
    t = {"trigger": trigger, "tick_number": 0, "delay": 0.0}
    if chance is not None:
        t["floats"] = {"proc_chance_percent": chance}
    blueprint = AbilityBlueprint.from_dict({
        "fqn": "abl.test.dot",
        "name": "Dot",
        "type": "active",
        "effects": [{
            "number": 1,
            "entry": True,
            "name": "Dot",
            "duration": 6.0,
            "tick_interval": 1.0,
            "tags": [DOT_TAG],
            "branches": [{
                "index": 2,
                "triggers": [t],
                "actions": [GAIN],
                "conditions": conditions,
                "target_overrides": [{"type": "caster"}],
            }],
        }],
    })
    return blueprint.effects[1]


def _bonus(value, targets):
    """A caster effect carrying a stat 228 (trigger proc chance) modifier."""
    return SimpleNamespace(
        is_expired=False,
        modifiers=[Modifier(stat="228", value=value, targets=frozenset(targets))],
    )


class LifecycleProcChanceTests(unittest.TestCase):
    def setUp(self):
        self.sim = Simulation(verbose=False, seed=1)
        self.player = Player("sorcerer")
        self.target = Dummy("Target Dummy", hp=1_000_000)
        self.player.current_target = self.target
        self.player.resource.current_value = 50.0

    def _tick(self, effect, roll=None, trigger="on_tick"):
        kwargs = {"tick_number": 1} if trigger == "on_tick" else {}
        if roll is None:
            effect.execute_triggered_branches(trigger, self.sim, self.player, self.target, **kwargs)
            return
        with patch.object(abilities.random, "random", return_value=roll):
            effect.execute_triggered_branches(trigger, self.sim, self.player, self.target, **kwargs)

    def test_tick_branch_fires_when_the_roll_is_under_the_chance(self):
        self._tick(_dot(chance=25.0), roll=0.10)

        self.assertEqual(self.player.resource.current_value, 52.0)

    def test_tick_branch_does_not_fire_when_the_roll_is_over_the_chance(self):
        self._tick(_dot(chance=25.0), roll=0.40)

        self.assertEqual(self.player.resource.current_value, 50.0)

    def test_stat_228_on_the_effect_tag_raises_the_tick_chance(self):
        # Death Channel: +0.25 -> 25% becomes 50%, so a 0.40 roll now passes.
        self.player.effects["bonus"] = _bonus(0.25, [DOT_TAG])

        self._tick(_dot(chance=25.0), roll=0.40)

        self.assertEqual(self.player.resource.current_value, 52.0)

    def test_stat_228_for_another_tag_does_not_apply(self):
        self.player.effects["bonus"] = _bonus(0.25, ["tag.test.other"])

        self._tick(_dot(chance=25.0), roll=0.40)

        self.assertEqual(self.player.resource.current_value, 50.0)

    def test_tick_branch_without_a_chance_always_fires_and_draws_nothing(self):
        random.seed(7)
        state = random.getstate()

        self._tick(_dot(chance=None))

        self.assertEqual(random.getstate(), state)
        self.assertEqual(self.player.resource.current_value, 52.0)

    def test_failed_conditions_do_not_draw_from_the_rng(self):
        random.seed(7)
        state = random.getstate()

        self._tick(_dot(chance=25.0, conditions=NEVER))

        self.assertEqual(random.getstate(), state)
        self.assertEqual(self.player.resource.current_value, 50.0)

    def test_on_apply_chance_is_rolled_too(self):
        self._tick(_dot(chance=25.0, trigger="on_apply"), roll=0.40, trigger="on_apply")

        self.assertEqual(self.player.resource.current_value, 50.0)


if __name__ == "__main__":
    unittest.main()
