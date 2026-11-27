"""Extracted effect conditions with `from_actor: caster` only count effects the caster applied."""

import unittest
from types import SimpleNamespace

from src.swtorsim.requirements import evaluate_single_extracted_condition


def _effect(name, applier, stacks=1):
    return SimpleNamespace(name=name, fqn="", tags=["tag.test.dot"], stacks=stacks, is_expired=False,
                           caster_ref=applier)


class FromActorConditionTests(unittest.TestCase):
    def setUp(self):
        self.player = SimpleNamespace(name="Player", effects={}, dots={})
        self.other = SimpleNamespace(name="Other player", effects={}, dots={})
        self.dummy = SimpleNamespace(name="Dummy", effects={}, dots={})

    def _cond(self, cond_type, from_actor, **extra):
        item = {"type": cond_type, "actor": "target", "tags": ["tag.test.dot"], "from_actor": from_actor}
        item.update(extra)
        return evaluate_single_extracted_condition(item, self.player, self.dummy)

    def test_caster_restriction_ignores_another_appliers_effect(self):
        self.dummy.effects["dot"] = _effect("Dot", self.other)
        self.assertFalse(self._cond("has_effect", "caster"))
        self.assertTrue(self._cond("not_has_effect", "caster"))
        self.assertFalse(self._cond("has_effect_at_stack_charge_count", "caster", count=1, comparison="gte"))

    def test_caster_restriction_counts_own_effect(self):
        self.dummy.effects["dot"] = _effect("Dot", self.player, stacks=2)
        self.assertTrue(self._cond("has_effect", "caster"))
        self.assertFalse(self._cond("not_has_effect", "caster"))
        self.assertTrue(self._cond("has_effect_at_stack_charge_count", "caster", count=2, comparison="eq"))

    def test_other_from_actor_values_are_unrestricted(self):
        self.dummy.effects["dot"] = _effect("Dot", self.other)
        self.assertTrue(self._cond("has_effect", "actor_1"))
        self.assertTrue(self._cond("has_effect", "target"))

    def test_effect_without_recorded_applier_still_counts(self):
        self.dummy.effects["dot"] = _effect("Dot", None)
        self.assertTrue(self._cond("has_effect", "caster"))


if __name__ == "__main__":
    unittest.main()
