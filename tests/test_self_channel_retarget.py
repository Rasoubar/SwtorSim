"""After a self-target channel (Force Barrier) the rotation resumes on the enemy, not on the caster.

PTS `force_barrier.json` has `target_rule: "self"`, so its ActiveChannel's target is the caster. Channel end used to
schedule the next decision with that target, so every later rotation step (Shock here) hit the Sorcerer, and the web
GUI's cast wrapper crashed on `Player.hp_ratio`. Channel end now uses `caster.current_target`, as cast-time abilities do.
"""

import contextlib
import io
import os
import unittest
from pathlib import Path
from unittest import mock

from src.swtorsim import abilities
from src.swtorsim.events import PlayerReady

ROOT = Path(__file__).resolve().parents[1]
PTS_PARSED = ROOT / "data" / "extractor" / "pts" / "parsed"
FORCE_BARRIER = "abl.sith_inquisitor.force_barrier"
SHOCK = "abl.sith_inquisitor.shock"
PATHS = (
    PTS_PARSED / "abl" / "sith_inquisitor" / "force_barrier.json",
    PTS_PARSED / "abl" / "sith_inquisitor" / "shock.json",
)
ROTATION = [
    {"type": "fixed", "ability_id": "force_barrier"},
    {"type": "fixed", "ability_id": "shock"},
]


@unittest.skipUnless(all(p.exists() for p in PATHS), "PTS data missing")
class SelfChannelRetargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def setUp(self):
        from src.swtorsim.config_load import load_complete_loadout
        from src.swtorsim.setup import prepare_simulation

        with contextlib.redirect_stdout(io.StringIO()):
            loadout = load_complete_loadout([FORCE_BARRIER, SHOCK], parsed_dir=PTS_PARSED)
            stats_config = {"class_name": "sorcerer", "level": 80, "stats": {}}
            self.sim, self.player, self.target = prepare_simulation(
                ROTATION, stats_config, loadout, 10_000_000, {}, verbose=False, seed=1
            )
        self.shock_targets = []
        cast = abilities.Ability.cast

        def spy(ability, caster, target, sim, *args, **kwargs):
            if ability.fqn == SHOCK:
                self.shock_targets.append(target)
            return cast(ability, caster, target, sim, *args, **kwargs)

        for patcher in (
            mock.patch.object(abilities.Ability, "cast", spy),
            mock.patch.object(abilities, "accuracy_roll", return_value=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_rotation_after_force_barrier_targets_the_enemy(self):
        player_hp = self.player.hp
        self.sim.run_until(15.0, target=self.target)

        self.assertTrue(self.shock_targets, "Shock was never cast after Force Barrier")
        self.assertTrue(all(t is self.target for t in self.shock_targets))
        self.assertEqual(self.player.hp, player_hp)
        self.assertLess(self.target.hp, self.target.max_hp)

    def test_decisions_after_the_channel_carry_the_enemy(self):
        targets = []
        init = PlayerReady.__init__

        def spy_init(event, player, target, *args, **kwargs):
            targets.append(target)
            init(event, player, target, *args, **kwargs)

        with mock.patch.object(PlayerReady, "__init__", spy_init):
            self.sim.run_until(15.0, target=self.target)

        self.assertTrue(targets)
        self.assertFalse(any(t is self.player for t in targets))


if __name__ == "__main__":
    unittest.main()
