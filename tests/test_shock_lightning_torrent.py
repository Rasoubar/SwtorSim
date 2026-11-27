"""Shock under Lightning Torrent's buff casts Crushing Darkness (PTS Lightning data).

PTS `shock.json` effect 1 branch 3 (target has the caster's Crushing Darkness DoT, caster has Convulsing Currents):
damage, call_effect 2 (snare), call_effect 6. Effect 6 ("Shock_6") requires the Lightning Torrent buff
(`force_lightning.json` effect 7, tag `force_lightning_lightning_buff`) and executes Crushing Darkness on its
`on_pre_remove` 1s later. The buff makes Shock crit and removes itself on Shock's critical `on_damage_dealt`.

The branch's hit triggers are held until the branch has run (HitGroup), so call_effect 6 still sees the buff that the
hit consumes. Dispatching them right after the hit removed the buff first and Shock never cast Crushing Darkness.
"""

import contextlib
import io
import os
import unittest
from pathlib import Path
from unittest import mock

from src.swtorsim import abilities

ROOT = Path(__file__).resolve().parents[1]
PTS_PARSED = ROOT / "data" / "extractor" / "pts" / "parsed"
SHOCK = "abl.sith_inquisitor.shock"
CRUSHING_DARKNESS = "abl.sith_inquisitor.crushing_darkness"
LIGHTNING_TORRENT = "abl.sith_inquisitor.skill.lightning.force_lightning"
CONVULSING_CURRENTS = "tal.sith_inquisitor.skill.lightning.convulsing_currents"
PATHS = (
    PTS_PARSED / "abl" / "sith_inquisitor" / "shock.json",
    PTS_PARSED / "abl" / "sith_inquisitor" / "crushing_darkness.json",
    PTS_PARSED / "abl" / "sith_inquisitor" / "skill" / "lightning" / "force_lightning.json",
    PTS_PARSED / "tal" / "sith_inquisitor" / "skill" / "lightning" / "convulsing_currents.json",
)
TORRENT_BUFF = f"{LIGHTNING_TORRENT}:7"
CD_DOT = f"{CRUSHING_DARKNESS}:2"
SHOCK_6 = f"{SHOCK}:6"


@unittest.skipUnless(all(p.exists() for p in PATHS), "PTS data missing")
class ShockLightningTorrentTests(unittest.TestCase):
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
            loadout = load_complete_loadout(
                [SHOCK, CRUSHING_DARKNESS, LIGHTNING_TORRENT, CONVULSING_CURRENTS], parsed_dir=PTS_PARSED
            )
            stats_config = {"class_name": "sorcerer", "level": 80, "stats": {}}
            self.sim, self.player, self.target = prepare_simulation(
                [], stats_config, loadout, 10_000_000, {}, verbose=False
            )
        self.cd_executions = []
        execute_effect = abilities.Ability.execute_effect

        def spy(ability, effect_id, caster, target, sim, context=None):
            if ability.fqn == CRUSHING_DARKNESS and effect_id == 1:
                self.cd_executions.append(sim.current_time)
            return execute_effect(ability, effect_id, caster, target, sim, context=context)

        patcher = mock.patch.object(abilities.Ability, "execute_effect", spy)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(abilities, "accuracy_roll", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _ability(self, fqn):
        return self.player.ability_db[fqn]

    def _advance(self, time):
        self.sim.run_until(time, target=self.target)
        self.sim.current_time = time

    def _shock(self, with_torrent_buff):
        """Crushing Darkness DoT on the dummy, optionally the Torrent buff on the caster, then Shock's entry effect."""
        self._ability(CRUSHING_DARKNESS).execute_effect(2, self.player, self.target, self.sim)
        if with_torrent_buff:
            self._ability(LIGHTNING_TORRENT).execute_effect(7, self.player, self.player, self.sim)
            self.assertIn(TORRENT_BUFF, self.player.effects)
        self.cd_executions.clear()
        self._ability(SHOCK).execute_effect(1, self.player, self.target, self.sim)

    def test_shock_under_torrent_buff_casts_crushing_darkness(self):
        self._shock(with_torrent_buff=True)

        self.assertIn(SHOCK_6, self.target.effects)
        self.assertNotIn(TORRENT_BUFF, self.player.effects)  # Shock's crit still consumes the buff
        self.assertEqual(self.cd_executions, [])
        self._advance(self.sim.current_time + 1.5)
        self.assertEqual(len(self.cd_executions), 1)

    def test_shock_without_torrent_buff_casts_nothing(self):
        self._shock(with_torrent_buff=False)

        self.assertNotIn(SHOCK_6, self.target.effects)
        self._advance(self.sim.current_time + 1.5)
        self.assertEqual(self.cd_executions, [])


if __name__ == "__main__":
    unittest.main()
