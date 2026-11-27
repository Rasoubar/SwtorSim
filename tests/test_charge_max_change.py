"""Unit tests: current charges follow a change of an ability's max charges."""

import unittest
from types import SimpleNamespace

from src.swtorsim.abilities import Ability, AbilityBlueprint


def _ability(max_charges, charges):
    ability = Ability(AbilityBlueprint.from_dict({
        "fqn": "abl.test.dash", "name": "Dash", "type": "active", "max_charges": max_charges,
    }))
    ability.charges = charges
    return ability


def _caster(new_max):
    return SimpleNamespace(calculate_ability_max_charges=lambda base, ability=None: new_max)


class ChargeMaxChangeTests(unittest.TestCase):
    def test_losing_a_bonus_charge_caps_current_charges_at_the_new_max(self):
        for before, after in ((2, 1), (1, 1)):
            ability = _ability(2, before)
            ability.apply_charge_modifiers(_caster(1))
            self.assertEqual((ability.charges, ability.max_charges), (after, 1), before)

    def test_spent_charges_are_not_handed_back_when_max_drops(self):
        ability = _ability(2, 0)
        ability.apply_charge_modifiers(_caster(1))
        self.assertEqual((ability.charges, ability.max_charges), (0, 1))

    def test_gaining_a_bonus_charge_shifts_current_charges_up(self):
        for before, after in ((1, 2), (0, 1)):
            ability = _ability(1, before)
            ability.apply_charge_modifiers(_caster(2))
            self.assertEqual((ability.charges, ability.max_charges), (after, 2), before)

    def test_unchanged_max_leaves_charges_alone(self):
        ability = _ability(2, 0)
        ability.apply_charge_modifiers(_caster(2))
        self.assertEqual((ability.charges, ability.max_charges), (0, 2))


if __name__ == "__main__":
    unittest.main()
