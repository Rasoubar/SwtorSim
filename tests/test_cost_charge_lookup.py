"""Unit tests for resource-cost and max-charge modifier lookups and the per-effect stat-set skip."""

import unittest
from types import SimpleNamespace

from src.swtorsim.effects import ActiveEffect
from src.swtorsim.entities import Player
from src.swtorsim.modifiers import Modifier

SHOT = SimpleNamespace(fqn="abl.test.shot", name="shot", tags=frozenset({"tag.test.shot"}))


def _effect(key, modifiers, **kwargs):
    return ActiveEffect(fqn=key, name=key, modifiers=modifiers, **kwargs)


class CostAndChargeLookupTests(unittest.TestCase):
    def setUp(self):
        self.player = Player("Tester")
        self.player.ability_db["shot"] = SHOT
        # An effect that carries only unrelated stats must never change either result.
        self.player.effects["unrelated:1"] = _effect(
            "unrelated", [Modifier(stat="64", value=-3.0, targets=frozenset({"abl.test.shot"}))]
        )

    def test_cost_without_cost_modifiers_is_base(self):
        self.assertEqual(self.player.calculate_resource_cost("shot", 10.0), 10.0)

    def test_cost_applies_flat_percent_and_stack_scaling(self):
        self.player.effects["flat:1"] = _effect(
            "flat",
            [Modifier(stat="68", value=-2.0, targets=frozenset({"abl.test.shot"}))],
            stacks=2, max_stacks=3, scales_with_stacks=True,
        )
        self.player.effects["pct:1"] = _effect(
            "pct", [Modifier(stat="69", value=-0.5, targets=frozenset({"tag.test.shot"}), is_percent=True)]
        )
        # (10 * (1 - 0.5)) + (-2 * 2 stacks) = 1
        self.assertAlmostEqual(self.player.calculate_resource_cost("shot", 10.0), 1.0)

    def test_cost_ignores_expired_and_untargeted_effects(self):
        self.player.effects["expired:1"] = _effect(
            "expired", [Modifier(stat="68", value=-5.0, targets=frozenset({"abl.test.shot"}))], is_expired=True
        )
        self.player.effects["other:1"] = _effect(
            "other", [Modifier(stat="68", value=-5.0, targets=frozenset({"abl.test.other"}))]
        )
        self.assertEqual(self.player.calculate_resource_cost("shot", 10.0), 10.0)

    def test_cost_still_scans_effects_without_a_stat_set(self):
        """Effect objects that do not expose modifier_stats are scanned in full, as before."""
        mods = [Modifier(stat="70", value=-4.0, targets=frozenset({"abl.test.shot"}))]
        self.player.effects["plain:1"] = SimpleNamespace(is_expired=False, get_effective_modifiers=lambda: mods)
        self.assertEqual(self.player.calculate_resource_cost("shot", 10.0), 6.0)

    def test_max_charges_unchanged_without_charge_modifiers(self):
        self.assertIsNone(self.player.calculate_ability_max_charges(None, ability=SHOT))
        self.assertEqual(self.player.calculate_ability_max_charges(2, ability=SHOT), 2)

    def test_max_charges_adds_matching_modifier(self):
        self.player.effects["charges:1"] = _effect(
            "charges", [Modifier(stat="422", value=1.0, targets=frozenset({"tag.test.shot"}))]
        )
        self.assertEqual(self.player.calculate_ability_max_charges(None, ability=SHOT), 2)
        self.assertEqual(self.player.calculate_ability_max_charges(2, ability=SHOT), 3)


class ModifierStatsTests(unittest.TestCase):
    def test_stat_set_follows_the_modifier_list(self):
        effect = _effect("e", [Modifier(stat="68", value=1.0), Modifier(stat=422, value=1.0)])
        self.assertEqual(effect.modifier_stats(), frozenset({"68", "422"}))
        self.assertIs(effect.modifier_stats(), effect.modifier_stats())

        effect.modifiers.append(Modifier(stat="229", value=1.0))
        self.assertEqual(effect.modifier_stats(), frozenset({"68", "422", "229"}))

        effect.modifiers = [Modifier(stat="64", value=1.0)]
        self.assertEqual(effect.modifier_stats(), frozenset({"64"}))

    def test_stat_set_does_not_affect_equality(self):
        first = _effect("e", [Modifier(stat="68", value=1.0)])
        second = _effect("e", [Modifier(stat="68", value=1.0)])
        first.modifier_stats()
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
