"""Channel-end branches on live data: each runs once, on natural end and on interruption.

A channel ability's own ``on_channeling_ended`` branches sit on its effect 1, which is applied (and subscribed on the
event bus) for the duration of the channel. Natural end: the bus dispatch runs them; running them directly as well
used to run Madness Force Lightning's end-of-channel hit (effect 6) twice. Interruption: the dispatch now comes
before ``cleanup_channel_effects``, so effect 1 still hears it (Kolto Waves branch 5, ``is_successful: false``).
"""

import contextlib
import io
import os
import unittest
from pathlib import Path
from unittest import mock

from src.swtorsim.abilities import Ability, handle_ability_cancel

ROOT = Path(__file__).resolve().parents[1]
LIVE_PARSED = ROOT / "data" / "extractor" / "live" / "parsed"
FORCE_LIGHTNING = "abl.sith_inquisitor.skill.madness.force_lightning"
KOLTO_WAVES = "abl.agent.skill.medic.kolto_waves"
FL_PATH = LIVE_PARSED / "abl" / "sith_inquisitor" / "skill" / "madness" / "force_lightning.json"
KW_PATH = LIVE_PARSED / "abl" / "agent" / "skill" / "medic" / "kolto_waves.json"


@unittest.skipUnless(FL_PATH.exists() and KW_PATH.exists(), "live data missing")
class ChannelEndOnceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def setUp(self):
        self.effect_calls = []
        self.channel_end_runs = []
        execute_effect = Ability.execute_effect
        execute_branch = Ability.execute_branch

        def spy_effect(ability, effect_id, *args, **kwargs):
            self.effect_calls.append((ability.fqn, effect_id))
            return execute_effect(ability, effect_id, *args, **kwargs)

        def spy_branch(ability, sim, branch, caster, target, context=None):
            if (context or {}).get("trigger_name") == "on_channeling_ended":
                self.channel_end_runs.append((ability.fqn, branch.index, context.get("is_successful")))
            return execute_branch(ability, sim, branch, caster, target, context=context)

        for name, spy in (("execute_effect", spy_effect), ("execute_branch", spy_branch)):
            patcher = mock.patch.object(Ability, name, spy)
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def _make(fqn, class_name):
        from src.swtorsim.config_load import load_complete_loadout
        from src.swtorsim.setup import prepare_simulation

        with contextlib.redirect_stdout(io.StringIO()):
            loadout = load_complete_loadout([fqn], parsed_dir=LIVE_PARSED)
            stats_config = {"class_name": class_name, "level": 80, "stats": {}}
            sim, player, target = prepare_simulation([], stats_config, loadout, 10_000_000, {}, verbose=False)
        return sim, player, target, player.ability_db[fqn]

    @staticmethod
    def _advance(sim, target, time):
        sim.run_until(time, target=target)
        sim.current_time = time

    def _end_hits(self):
        return self.effect_calls.count((FORCE_LIGHTNING, 6))

    def test_force_lightning_end_hit_runs_once_per_completed_channel(self):
        sim, player, target, ability = self._make(FORCE_LIGHTNING, "sorcerer")
        self.assertTrue(ability.cast(player, target, sim))
        self._advance(sim, target, 4.0)
        self.assertIsNone(player.active_channel)
        self.assertEqual(self._end_hits(), 1)
        self.assertEqual(self.channel_end_runs, [(FORCE_LIGHTNING, 5, True)])

    def test_force_lightning_interrupted_channel_has_no_end_hit(self):
        sim, player, target, ability = self._make(FORCE_LIGHTNING, "sorcerer")
        self.assertTrue(ability.cast(player, target, sim))
        self._advance(sim, target, 1.0)
        handle_ability_cancel(player, target, {})
        self._advance(sim, target, 4.0)
        self.assertEqual(self._end_hits(), 0)

    def test_kolto_waves_hears_its_own_interruption(self):
        sim, player, target, ability = self._make(KOLTO_WAVES, "operative")
        self.assertTrue(ability.cast(player, target, sim))
        self._advance(sim, target, 1.0)
        self.assertIn(f"{KOLTO_WAVES}:1", dict.keys(player.effects))
        handle_ability_cancel(player, target, {})
        self.assertEqual(self.channel_end_runs, [(KOLTO_WAVES, 5, False)])
        self.assertNotIn(f"{KOLTO_WAVES}:1", dict.keys(player.effects))


if __name__ == "__main__":
    unittest.main()
