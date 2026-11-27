"""Lifecycle procs (on_tick, on_apply, ...) are logged by the traced engine and behave exactly like the real one."""

import random
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.swtorsim import abilities
from src.swtorsim.debug.traced_run import traced_engine
from src.swtorsim.engine import Simulation
from src.swtorsim.entities import Dummy, Player
from src.swtorsim.abilities import AbilityBlueprint
from src.swtorsim.modifiers import Modifier

DOT_TAG = "tag.test.dot"
GAIN = {"action_type": "energy_recovery", "min": 2.0, "max": 2.0}
NEVER = {"list": [{"id": "c1", "type": "is_companion"}], "logic": {"condition": "c1"}}


def _dot(chance=None, conditions=None, trigger="on_tick"):
    """A ticking effect whose single branch (index 2) gives the caster 2 Force on ``trigger``."""
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


class _Fixture(unittest.TestCase):
    def _build(self):
        sim = Simulation(verbose=False, seed=1)
        player = Player("sorcerer")
        target = Dummy("Target Dummy", hp=1_000_000)
        player.current_target = target
        player.resource.current_value = 50.0
        return sim, player, target

    def _tick(self, sim, player, target, effect, roll=None, trigger="on_tick"):
        kwargs = {"tick_number": 1} if trigger == "on_tick" else {}
        if roll is None:
            effect.execute_triggered_branches(trigger, sim, player, target, **kwargs)
            return
        with patch.object(abilities.random, "random", return_value=roll):
            effect.execute_triggered_branches(trigger, sim, player, target, **kwargs)


class TracedLifecycleLogTests(_Fixture):
    def _run(self, effect_factory, roll=None, bonus=None, trigger="on_tick"):
        with traced_engine():
            sim, player, target = self._build()
            if bonus is not None:
                player.effects["bonus"] = bonus
            effect = effect_factory()
            self._tick(sim, player, target, effect, roll=roll, trigger=trigger)
        return sim.triggers.proc_log, player

    def test_passed_roll_is_logged_as_fired_with_the_numbers(self):
        log, player = self._run(lambda: _dot(chance=25.0), roll=0.10)
        (rec,) = log
        self.assertEqual(rec["kind"], "lifecycle")
        self.assertEqual(rec["outcome"], "fired")
        self.assertEqual((rec["base_chance"], rec["chance"]), (25.0, 25.0))
        self.assertAlmostEqual(rec["draw"], 10.0)
        self.assertEqual((rec["event"], rec["branch_index"], rec["trigger_index"]), ("on_tick", 2, 0))
        self.assertEqual(player.resource.current_value, 52.0)

    def test_failed_roll_is_logged(self):
        log, player = self._run(lambda: _dot(chance=25.0), roll=0.40)
        (rec,) = log
        self.assertEqual(rec["outcome"], "roll_failed")
        self.assertAlmostEqual(rec["draw"], 40.0)
        self.assertEqual(player.resource.current_value, 50.0)

    def test_stat_228_shows_in_the_effective_chance_but_not_the_base(self):
        log, _ = self._run(lambda: _dot(chance=25.0), roll=0.40, bonus=_bonus(0.25, [DOT_TAG]))
        (rec,) = log
        self.assertEqual((rec["base_chance"], rec["chance"]), (25.0, 50.0))
        self.assertEqual(rec["outcome"], "fired")

    def test_no_chance_fires_without_a_draw(self):
        random.seed(7)
        state = random.getstate()
        log, _ = self._run(lambda: _dot(chance=None))
        (rec,) = log
        self.assertEqual(rec["outcome"], "fired")
        self.assertIsNone(rec["chance"])
        self.assertIsNone(rec["draw"])
        self.assertEqual(random.getstate(), state)

    def test_failed_conditions_are_logged_and_draw_nothing(self):
        random.seed(7)
        state = random.getstate()
        log, _ = self._run(lambda: _dot(chance=25.0, conditions=NEVER))
        (rec,) = log
        self.assertEqual(rec["outcome"], "blocked_condition")
        self.assertIsNone(rec["draw"])
        self.assertEqual(random.getstate(), state)

    def test_on_apply_is_logged(self):
        log, _ = self._run(lambda: _dot(chance=25.0, trigger="on_apply"), roll=0.40, trigger="on_apply")
        self.assertEqual([(r["event"], r["outcome"]) for r in log], [("on_apply", "roll_failed")])


class TracedLifecycleParityTests(_Fixture):
    def _drive(self, traced, seed):
        random.seed(seed)
        outcomes = []

        def body():
            sim, player, target = self._build()
            effect = _dot(chance=30.0)
            for _ in range(200):
                self._tick(sim, player, target, effect)
                outcomes.append(player.resource.current_value)
            return sim

        if traced:
            with traced_engine():
                sim = body()
        else:
            sim = body()
        return outcomes, random.getstate(), sim

    def test_same_results_and_same_random_draws_as_the_real_code(self):
        for seed in (1, 2, 3):
            real = self._drive(False, seed)
            traced = self._drive(True, seed)
            self.assertEqual(real[0], traced[0])
            self.assertEqual(real[1], traced[1])
        rolls = [r["outcome"] for r in traced[2].triggers.proc_log]
        self.assertEqual(len(rolls), 200)
        self.assertIn("roll_failed", rolls)
        self.assertIn("fired", rolls)

    def test_swap_is_undone_after_the_block(self):
        original_execute = abilities.Branch.execute
        original_triggered = abilities.Effect.execute_triggered_branches
        with traced_engine():
            self.assertIsNot(abilities.Branch.execute, original_execute)
            self.assertIsNot(abilities.Effect.execute_triggered_branches, original_triggered)
        self.assertIs(abilities.Branch.execute, original_execute)
        self.assertIs(abilities.Effect.execute_triggered_branches, original_triggered)


class LifecycleForcedDrawTests(_Fixture):
    KEY = (None, "Dot", 2, 0)  # the fixture calls the effect without an ability, so no fqn

    def _fire(self, forced):
        with traced_engine():
            sim, player, target = self._build()
            sim.triggers.forced_draws = None if forced is None else {self.KEY: forced}
            random.seed(3)
            self._tick(sim, player, target, _dot(chance=25.0))
            state = random.getstate()
        return player.resource.current_value, state, sim.triggers.proc_log

    def test_forced_draw_decides_the_lifecycle_roll_at_the_boundary(self):
        self.assertEqual(self._fire(25.0)[0], 52.0)
        self.assertEqual(self._fire(25.000001)[0], 50.0)

    def test_forcing_does_not_change_how_many_random_numbers_are_used(self):
        self.assertEqual(self._fire(10.0)[1], self._fire(None)[1])

    def test_the_log_shows_the_forced_draw(self):
        (rec,) = self._fire(90.0)[2]
        self.assertEqual((rec["outcome"], rec["draw"]), ("roll_failed", 90.0))


if __name__ == "__main__":
    unittest.main()
