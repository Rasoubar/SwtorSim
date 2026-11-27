"""Unit tests for handle_cooldown_action target resolution (timer_spec vs the triggering ability)."""

import unittest
from types import SimpleNamespace

from src.swtorsim.abilities import handle_cooldown_action


def _abl(name, cooldown):
    return SimpleNamespace(name=name, fqn=f"abl.{name}", cooldown=cooldown)


def _caster(*abilities):
    db = {a.fqn: a for a in abilities}
    return SimpleNamespace(
        ability_db=db,
        cooldowns={},
        calculate_cooldown=lambda cd, ability=None: cd,
    )


def _sim(now=10.0):
    return SimpleNamespace(current_time=now)


def _action(ints, duration=9.0):
    return {
        "action_type": "cooldown",
        "ints": ints,
        "bools": {"ignore_alacrity": False},
        "duration": duration,
    }


class CooldownActionTargetTests(unittest.TestCase):
    def setUp(self):
        self.jet_charge = _abl("jet_charge", 15.0)
        self.rising_phoenix = _abl("rising_phoenix", 15.0)
        self.caster = _caster(self.jet_charge, self.rising_phoenix)

    def test_timer_spec_redirects_cooldown_to_named_ability(self):
        action = _action({"timer_spec": "abl.jet_charge"})
        handle_cooldown_action(_sim(), self.caster, action, ability=self.rising_phoenix)
        self.assertEqual(self.caster.cooldowns, {"jet_charge": 19.0})

    def test_timer_spec_equal_to_own_ability_is_unchanged(self):
        action = _action({"timer_spec": "abl.jet_charge"})
        handle_cooldown_action(_sim(), self.caster, action, ability=self.jet_charge)
        self.assertEqual(self.caster.cooldowns, {"jet_charge": 19.0})

    def test_ability_spec_still_honored(self):
        action = _action({"ability_spec": "abl.jet_charge"})
        handle_cooldown_action(_sim(), self.caster, action, ability=self.rising_phoenix)
        self.assertEqual(self.caster.cooldowns, {"jet_charge": 19.0})

    def test_no_spec_uses_triggering_ability(self):
        handle_cooldown_action(_sim(), self.caster, _action({}), ability=self.rising_phoenix)
        self.assertEqual(self.caster.cooldowns, {"rising_phoenix": 19.0})

    def test_unknown_timer_spec_falls_back_to_triggering_ability(self):
        action = _action({"timer_spec": "abl.not_in_build"})
        handle_cooldown_action(_sim(), self.caster, action, ability=self.rising_phoenix)
        self.assertEqual(self.caster.cooldowns, {"rising_phoenix": 19.0})


if __name__ == "__main__":
    unittest.main()
