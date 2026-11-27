"""Hemorrhaging Blast + Blood Choke on live data: branch order with a mid-branch effect.

Live `hemorrhaging_blast.json` entry branch: main-hand hit, call_effect 2 (the debuff: echoes bleed damage taken
with a main + off-hand hit), off-hand hit. Both hits carry `hemorrhaging_blast_initial_dmg`, which detonates the
Blood Choke effects of the live tactical `vir_dir.dmg_burst_01` (effects 4 and 5; each removes itself).

The HitGroup parks the main-hand hit's post-hit triggers until the off-hand hit has landed (shared snapshot), so the
detonations fire after the debuff exists, and the debuff echoes each of them (Blood Choke is a bleed; Hemorrhaging
Blast's own hits are not). Live logs: casts that detonate both Blood Chokes show 6 Hemorrhaging Blast hits.
"""

import json
import unittest
from pathlib import Path
from unittest import mock

from src.swtorsim import abilities
from src.swtorsim.abilities import Ability, AbilityBlueprint
from src.swtorsim.engine import Simulation
from src.swtorsim.entities import Dummy, Player

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "data" / "extractor" / "live" / "parsed" / "abl"
HB_PATH = LIVE / "smuggler" / "skill" / "dirty_fighting" / "hemorrhaging_blast.json"
TACTICAL_PATH = LIVE / "itm" / "tactical" / "sow" / "age_smu" / "sni_gun" / "vir_dir" / "dmg_burst_01.json"
VITAL_SHOT_PATH = LIVE / "smuggler" / "vital_shot.json"

HB = "Hemorrhaging Blast"
CHOKE_VS = "Blood Choke (Vital Shot)"
CHOKE_SB = "Blood Choke (Shrap Bomb)"
DEBUFF_KEY = "abl.smuggler.skill.dirty_fighting.hemorrhaging_blast:2"
TACTICAL_FQN = "abl.itm.tactical.sow.age_smu.sni_gun.vir_dir.dmg_burst_01"


def _ability(path):
    return Ability(AbilityBlueprint.from_dict(json.loads(path.read_text(encoding="utf-8"))))


@unittest.skipUnless(HB_PATH.exists() and TACTICAL_PATH.exists() and VITAL_SHOT_PATH.exists(), "live data missing")
class HemorrhagingBlastBloodChokeTests(unittest.TestCase):
    def setUp(self):
        self.sim = Simulation(verbose=False, seed=1)
        self.player = Player("gunslinger")
        for stat in ("Main_hand_min", "Main_hand_max", "Off_hand_min", "Off_hand_max"):
            self.player.stats[stat] = 1000.0
        self.target = Dummy("Target Dummy", hp=10_000_000)
        self.player.current_target = self.target
        self.order = []
        log_damage = self.sim.tracker.log_damage

        def record(name, *args, **kwargs):
            self.order.append(name)
            return log_damage(name, *args, **kwargs)

        self.sim.tracker.log_damage = record
        self.tactical = _ability(TACTICAL_PATH)

    def _cast(self, main_hand_lands=True):
        """Blood Choke (Vital Shot) and (Shrap Bomb) on the dummy, then Hemorrhaging Blast's entry effect."""
        rolls = iter([main_hand_lands] + [True] * 20)
        with mock.patch.object(abilities, "accuracy_roll", side_effect=lambda *a, **k: next(rolls)):
            self.tactical.execute_effect(4, self.player, self.target, self.sim)
            self.tactical.execute_effect(5, self.player, self.target, self.sim)
            _ability(HB_PATH).execute_effect(1, self.player, self.target, self.sim)

    def _hits(self, name):
        return self.sim.tracker.breakdown.get(name, {}).get("hit_count", 0)

    def test_debuff_echoes_both_detonations(self):
        self._cast()

        self.assertEqual(self._hits(HB), 6)  # 2 own hits + 2 echoes x (main + off-hand)
        self.assertEqual(self._hits(CHOKE_VS), 1)
        self.assertEqual(self._hits(CHOKE_SB), 1)
        self.assertIn(DEBUFF_KEY, self.target.effects)
        self.assertFalse(any(k.startswith(TACTICAL_FQN) for k in self.target.effects))

    def test_main_hand_triggers_fire_after_the_off_hand_hit(self):
        """Shared snapshot: the detonations (main-hand triggers) resolve once both hits have landed, each echoed."""
        self._cast()

        self.assertEqual(self.order, [HB, HB, CHOKE_VS, HB, HB, CHOKE_SB, HB, HB])

    def test_main_hand_miss_off_hand_detonates_without_debuff(self):
        self._cast(main_hand_lands=False)

        self.assertEqual(self._hits(HB), 1)
        self.assertEqual(self._hits(CHOKE_VS), 1)
        self.assertEqual(self._hits(CHOKE_SB), 1)
        self.assertNotIn(DEBUFF_KEY, self.target.effects)

    def test_debuff_echoes_a_later_bleed(self):
        """A bleed after the cast (Vital Shot) is echoed too."""
        self._cast()
        self.order.clear()
        with mock.patch.object(abilities, "accuracy_roll", return_value=True):
            _ability(VITAL_SHOT_PATH).execute_effect(1, self.player, self.target, self.sim)

        self.assertEqual(self.order, ["Vital Shot", HB, HB])


if __name__ == "__main__":
    unittest.main()
