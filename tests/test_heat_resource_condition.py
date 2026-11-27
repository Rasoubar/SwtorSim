"""Unit tests for ``has_specified_resource_amount`` against heat vs. available-resource pools.

Game data states resource thresholds as resource AVAILABLE. ``HeatPool`` stores heat BUILT UP,
so the condition must compare the remaining capacity (``max_value - heat``) for heat pools only.
"""

import unittest
from types import SimpleNamespace

from src.swtorsim.requirements import evaluate_single_extracted_condition
from src.swtorsim.resources import EnergyPool, HeatPool, StandardPool


def _cond(comparison, amount):
    return {
        "type": "has_specified_resource_amount",
        "actor": "caster",
        "comparison": comparison,
        "floats": {"resource_amount": amount},
        "ints": {"resource_type": 2},
    }


def _check(pool, comparison, amount):
    return evaluate_single_extracted_condition(_cond(comparison, amount), SimpleNamespace(resource=pool), None)


def _heat(value):
    pool = HeatPool()
    pool.current_value = value
    return pool


class HeatResourceConditionTests(unittest.TestCase):
    def test_vent_heat_lte_60_needs_at_least_40_heat(self):
        """Vent Heat (lte 60): castable once heat >= 40, refused below that."""
        self.assertFalse(_check(_heat(0.0), "lte", 60.0))
        self.assertFalse(_check(_heat(39.0), "lte", 60.0))
        self.assertTrue(_check(_heat(40.0), "lte", 60.0))
        self.assertTrue(_check(_heat(99.0), "lte", 60.0))

    def test_vent_heat_plus_lte_50_needs_at_least_50_heat(self):
        self.assertFalse(_check(_heat(49.0), "lte", 50.0))
        self.assertTrue(_check(_heat(50.0), "lte", 50.0))
        self.assertTrue(_check(_heat(86.0), "lte", 50.0))

    def test_channel_gte_6_allowed_unless_heat_above_94(self):
        """Unload (gte 6): needs 6 heat room, i.e. heat <= 94."""
        self.assertTrue(_check(_heat(0.0), "gte", 6.0))
        self.assertTrue(_check(_heat(94.0), "gte", 6.0))
        self.assertFalse(_check(_heat(95.0), "gte", 6.0))

    def test_lt_threshold_for_channel_cancel_is_heat_room(self):
        """Channel cancel (lt 6) triggers only when less than 6 heat room is left."""
        self.assertFalse(_check(_heat(10.0), "lt", 6.0))
        self.assertTrue(_check(_heat(95.0), "lt", 6.0))

    def test_non_heat_pools_compare_raw_value(self):
        force = StandardPool("Force")
        force.current_value = 30.0
        self.assertTrue(_check(force, "gte", 20.0))
        self.assertFalse(_check(force, "lte", 20.0))
        energy = EnergyPool()
        energy.current_value = 10.0
        self.assertFalse(_check(energy, "gte", 20.0))
        self.assertTrue(_check(energy, "lte", 20.0))

    def test_rotation_rule_checks_stay_in_heat_units(self):
        """caster_energy_above/below are rotation rules in raw heat units, not game-data thresholds."""
        from src.swtorsim.requirements import check_caster_energy_above, check_caster_energy_below
        caster = SimpleNamespace(resource=_heat(80.0))
        self.assertTrue(check_caster_energy_above(70, caster, None))
        self.assertFalse(check_caster_energy_below(70, caster, None))


if __name__ == "__main__":
    unittest.main()
