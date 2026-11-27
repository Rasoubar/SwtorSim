"""Unit tests for passive effects with a tick interval and no duration (e.g. Terminal Velocity)."""

import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from src.swtorsim.abilities import Ability, AbilityBlueprint
from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.events import DotTick
from src.swtorsim.resources import HeatPool
from src.swtorsim.run_config import load_run_config
from src.swtorsim.settings import get_extractor_data_dir
from src.swtorsim.setup import _equip_passive, prepare_simulation

RUN_CONFIG_PATH = ROOT / "data" / "run_config" / "Hatred.json"
TERMINAL_VELOCITY = "data/extractor/live/parsed/abl/bounty_hunter/skill/arsenal/terminal_velocity.json"
ACTIVE_WITH_PASSIVE_FLAGGED_TICK = {
    "fqn": "abl.test.channel_like",
    "name": "Channel Like",
    "type": "active",
    "cooldown": 0.0,
    "effects": [
        {
            "number": 1,
            "entry": True,
            "name": "Channel Like_1",
            "branches": [
                {"index": 2, "actions": [{"action_type": "energy_recovery", "min": 2.0, "max": 2.0, "percent": 0.0}],
                 "triggers": [{"trigger": "on_tick", "tick_number": 0, "delay": 0.0}]},
            ],
            "initializers": [
                {"initializer_type": "eff_initializer__set_passive", "bools": {"is_passive": True}},
                {"initializer_type": "eff_initializer__set_tick_rate"},
            ],
            "tick_interval": 1.0,
            "effIgnoreAlacrity": False,
        }
    ],
}


class PassiveEffectTickTests(unittest.TestCase):
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
        # Isolate the passive: drop the rotation / regen events and give the player a heat pool.
        self.sim.queue.clear()
        self.sim.current_time = 0.0
        self.player.resource = HeatPool()
        self.player.resource.current_value = 80.0
        self.base_tick = 1.5

    def _equip_terminal_velocity(self):
        """Applies Terminal Velocity the way character load does (Alacrity stat only)."""
        bp = AbilityBlueprint.from_file(ROOT / TERMINAL_VELOCITY)
        self.sim.loading = True
        try:
            _equip_passive(self.player, bp, self.sim)
        finally:
            self.sim.loading = False
        return bp

    def test_passive_tick_vents_heat_every_tick(self):
        """Terminal Velocity recovers 2 per tick on its 1.5s interval, scaled by Alacrity when applied."""
        self._equip_terminal_velocity()
        heat_after_apply = self.player.resource.current_value
        interval = self.player.scale_time_modifier(self.base_tick)
        self.sim.run_until(interval * 4 + 0.001)
        self.assertAlmostEqual(heat_after_apply - self.player.resource.current_value, 2.0 * 4)

    def test_passive_effect_never_expires(self):
        """A durationless passive keeps ticking and stays on the player."""
        self._equip_terminal_velocity()
        self.sim.run_until(120.0)
        self.assertTrue(any("terminal_velocity" in str(k) for k in self.player.effects.keys()))
        self.assertEqual(self.player.resource.current_value, 0.0)
        self.assertTrue(any(isinstance(ev, DotTick) for (_t, _s, ev) in self.sim.queue))

    def test_tick_length_is_fixed_when_applied(self):
        """The interval is decided at application: Alacrity gained afterwards does not change it."""
        self._equip_terminal_velocity()
        first = [t for (t, _s, ev) in self.sim.queue if isinstance(ev, DotTick)]
        self.assertEqual(len(first), 1)
        applied_interval = first[0] - self.sim.current_time
        self.assertAlmostEqual(applied_interval, self.player.scale_time_modifier(self.base_tick))
        self.player.stats["Alacrity"] = 0.5
        self.sim.run_until(first[0] + 0.0001)
        nxt = [t for (t, _s, ev) in self.sim.queue if isinstance(ev, DotTick)]
        self.assertEqual(len(nxt), 1)
        self.assertAlmostEqual(nxt[0] - first[0], applied_interval)

    def test_active_ability_effects_flagged_passive_do_not_self_tick(self):
        """Active abilities (channels) tick through their channel, not through the passive tick path."""
        bp = AbilityBlueprint.from_dict(ACTIVE_WITH_PASSIVE_FLAGGED_TICK)
        ability = Ability(bp)
        ability.execute_effect(1, self.player, self.player, self.sim)
        self.assertFalse(any(isinstance(ev, DotTick) for (_t, _s, ev) in self.sim.queue))


if __name__ == "__main__":
    unittest.main()
