"""Instant abilities dispatch on_ability_post_activate before their entry effects run.

What a post-activate spends or grants is settled before the cast's hits are calculated and their damage triggers fire.
Damage triggers still fire per branch (tests/test_hit_group.py), timed casts and channels keep their order.

- Energize (PTS Darkness): Shock's post-activate grants Energize_3 (+50% Force crit damage on Shock, 1s) while
  Recklessness is up; Energize itself is removed by Shock's on_damage_dealt. Energize_3 must exist when Shock's hit
  is calculated.
- Corrosive Return (PTS Lethality): Corrosive Assault spends a Tactical Advantage stack at post-activate; Corrosive
  Return refunds one when the Corrosive Assault hit lands and no stack is left (10s rate limit). In game, a Corrosive
  Assault cast at 1 stack ends at 1.
"""

import json
import os
import unittest
from pathlib import Path
from unittest import mock

from src.swtorsim import abilities, events
from src.swtorsim.abilities import Ability, AbilityBlueprint
from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.run_config import load_run_config
from src.swtorsim.setup import prepare_simulation

ROOT = Path(__file__).resolve().parents[1]
PTS = ROOT / "data" / "extractor" / "pts" / "parsed" / "abl"
DARKNESS = ROOT / "data" / "run_config" / "Darkness.json"
LETHALITY = ROOT / "data" / "run_config" / "Lethality.json"
ENERGIZE_PATH = PTS / "sith_inquisitor" / "skill" / "darkness" / "energize.json"
TA_PATH = PTS / "agent" / "tactical_advantage.json"

ENERGIZE_BUFF = "abl.sith_inquisitor.skill.darkness.energize:2"
ENERGIZE_3 = "abl.sith_inquisitor.skill.darkness.energize:3"
TA_STACKS = "abl.agent.tactical_advantage:2"


def _ability(path):
    return Ability(AbilityBlueprint.from_dict(json.loads(path.read_text(encoding="utf-8"))))


def _prepare(path):
    config = load_run_config(str(path))
    inputs = load_from_run_config(config)
    return prepare_simulation(
        inputs.rotation_config, inputs.stats_config, inputs.loadout_blueprints, config.dummy_hp,
        inputs.debuff_module, verbose=False, seed=4242,
    )


def _active(entity, key):
    eff = entity.effects.get(key)
    return eff is not None and not eff.is_expired


class _CwdMixin:
    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)


@unittest.skipUnless(DARKNESS.exists() and ENERGIZE_PATH.exists(), "PTS Darkness data missing")
class EnergizeShockTests(_CwdMixin, unittest.TestCase):
    def setUp(self):
        self.sim, self.player, self.target = _prepare(DARKNESS)
        self.player.resource.current_value = 100.0
        self.shock = self.player.ability_db["abl.sith_inquisitor.shock"]
        # The Energize proc (effect 2), as Energize_1 grants it.
        _ability(ENERGIZE_PATH).execute_effect(2, self.player, self.player, self.sim)
        self.assertTrue(_active(self.player, ENERGIZE_BUFF))

    def _cast_shock(self):
        """Casts Shock and returns, per calculated hit, whether Energize_3 was up when the hit was calculated."""
        seen = []
        original = events.calculate_hit

        def record(source, target, action, *args, **kwargs):
            seen.append(_active(self.player, ENERGIZE_3))
            return original(source, target, action, *args, **kwargs)

        with mock.patch.object(events, "calculate_hit", record), \
                mock.patch.object(abilities, "accuracy_roll", return_value=True):
            self.assertTrue(self.shock.cast(self.player, self.target, self.sim))
        return seen

    def test_energize_3_is_up_when_shock_is_calculated_under_recklessness(self):
        self.player.ability_db["abl.sith_inquisitor.recklessness"].execute_effect(1, self.player, self.player, self.sim)

        seen = self._cast_shock()

        self.assertTrue(seen)
        self.assertTrue(seen[0])
        self.assertFalse(_active(self.player, ENERGIZE_BUFF))  # Shock's hit still removes Energize

    def test_no_energize_3_without_recklessness(self):
        seen = self._cast_shock()

        self.assertTrue(seen)
        self.assertFalse(any(seen))
        self.assertFalse(_active(self.player, ENERGIZE_3))


@unittest.skipUnless(LETHALITY.exists() and TA_PATH.exists(), "PTS Lethality data missing")
class CorrosiveReturnCastTests(_CwdMixin, unittest.TestCase):
    def setUp(self):
        self.sim, self.player, self.target = _prepare(LETHALITY)
        self.player.pre_combat = None  # the rotation's pre-pull Stealth step would keep effects off the dummy
        self.player.resource.current_value = 100.0
        self.ca = self.player.ability_db["abl.agent.skill.lethality.corrosive_assault"]
        self.ta = _ability(TA_PATH)

    def _stacks(self):
        eff = self.player.effects.get(TA_STACKS)
        return 0 if eff is None or eff.is_expired else eff.stacks

    def _give_stacks(self, n):
        for _ in range(n):
            self.ta.execute_effect(2, self.player, self.player, self.sim)
        self.assertEqual(self._stacks(), n)

    def _cast_corrosive_assault(self):
        with mock.patch.object(abilities, "accuracy_roll", return_value=True):
            self.assertTrue(self.ca.cast(self.player, self.target, self.sim))

    def test_last_stack_is_refunded(self):
        self._give_stacks(1)

        self._cast_corrosive_assault()

        self.assertEqual(self._stacks(), 1)

    def test_no_refund_while_a_stack_is_left(self):
        self._give_stacks(2)

        self._cast_corrosive_assault()

        self.assertEqual(self._stacks(), 1)

    def test_no_refund_without_corrosive_return(self):
        self.sim.triggers.unsubscribe(f"{id(self.player)}:abl.agent.skill.lethality.mods.tier2.corrosive_return:1")
        self._give_stacks(1)

        self._cast_corrosive_assault()

        self.assertEqual(self._stacks(), 0)


if __name__ == "__main__":
    unittest.main()
