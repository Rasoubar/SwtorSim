"""Unit tests verifying that timed casts spend their resource cost on completion instead of at cast start."""

import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.events import CastFinishEvent
from src.swtorsim.run_config import load_run_config
from src.swtorsim.setup import prepare_simulation

RUN_CONFIG_PATH = ROOT / "data" / "run_config" / "Hatred.json"


class CastResourceTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def setUp(self):
        config = load_run_config(str(RUN_CONFIG_PATH))
        inputs = load_from_run_config(config)
        self.sim, self.player, self.target = prepare_simulation(
            inputs.rotation_config,
            inputs.stats_config,
            inputs.loadout_blueprints,
            config.dummy_hp,
            inputs.debuff_module,
            verbose=False,
            seed=4242,
        )
        # Whirlwind: activation type "cast" with a 2.0s base cast time and a resource cost.
        # Remove Haunted Dreams passive buff which reduces Whirlwind cast time to instant.
        self.player.effects.pop("Haunted Dreams", None)
        self.ability = self.player.ability_db["abl.sith_inquisitor.whirlwind"]
        self.player.resource.current_value = 50.0
        self.expected_cost = self.player.calculate_resource_cost(self.ability.name, self.ability.energy_cost)
        self.assertGreater(self.expected_cost, 0.0)

    def _start_cast_and_get_finish_event(self):
        self.assertTrue(self.ability.cast(self.player, self.target, self.sim))
        finish = [(t, ev) for (t, _seq, ev) in self.sim.queue if isinstance(ev, CastFinishEvent)]
        self.assertEqual(len(finish), 1)
        return finish[0]

    def test_cast_does_not_spend_at_start(self):
        """Starting a timed cast leaves the resource pool untouched and sets the active cast."""
        self._start_cast_and_get_finish_event()
        self.assertIs(self.player.active_cast, self.ability)
        self.assertAlmostEqual(self.player.resource.current_value, 50.0)

    def test_cast_spends_on_completion(self):
        """Completing a timed cast deducts the resource cost exactly once."""
        finish_time, finish_event = self._start_cast_and_get_finish_event()
        self.sim.current_time = finish_time
        finish_event.resolve(self.sim)
        self.assertIsNone(self.player.active_cast)
        self.assertAlmostEqual(self.player.resource.current_value, 50.0 - self.expected_cost)

    def test_interrupted_cast_spends_nothing(self):
        """A cast cancelled before completion never deducts its resource cost."""
        finish_time, finish_event = self._start_cast_and_get_finish_event()
        self.player.active_cast = None
        self.player.is_casting = False
        self.sim.current_time = finish_time
        finish_event.resolve(self.sim)
        self.assertAlmostEqual(self.player.resource.current_value, 50.0)

    def test_cast_fails_when_unaffordable_at_completion(self):
        """If the pool cannot cover the cost at completion, the cast fails without spending or executing."""
        finish_time, finish_event = self._start_cast_and_get_finish_event()
        self.player.resource.current_value = 0.0
        executed = []
        original = self.ability.execute_effect
        self.ability.execute_effect = lambda *a, **k: executed.append(a)
        try:
            self.sim.current_time = finish_time
            finish_event.resolve(self.sim)
        finally:
            self.ability.execute_effect = original
        self.assertEqual(executed, [])
        self.assertAlmostEqual(self.player.resource.current_value, 0.0)
        self.assertIsNone(self.player.active_cast)


if __name__ == "__main__":
    unittest.main()
