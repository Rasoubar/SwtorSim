"""Unit tests for entity_has_effect: expired effects do not count as present."""

import unittest
from types import SimpleNamespace

from src.swtorsim.effects import ActiveEffect
from src.swtorsim.requirements import entity_has_effect, get_entity_effect_stacks


def _entity(*effects):
    return SimpleNamespace(effects={e.canonical_id: e for e in effects}, dots={})


def _buff(**kwargs):
    return ActiveEffect(
        fqn="abl.test.primed_shots", name="Primed Shots", tags=frozenset({"tag.test.primed"}),
        stacks=2, max_stacks=2, **kwargs,
    )


class EntityHasEffectTests(unittest.TestCase):
    def test_active_effect_is_found_by_tag_name_and_fqn(self):
        entity = _entity(_buff())
        self.assertTrue(entity_has_effect(entity, tags=["tag.test.primed"]))
        self.assertTrue(entity_has_effect(entity, ability_spec="Primed Shots"))
        self.assertTrue(entity_has_effect(entity, ability_spec="abl.test.primed_shots"))
        self.assertTrue(entity_has_effect(entity, ability_spec="Primed Shots", count=2))
        self.assertFalse(entity_has_effect(entity, ability_spec="Primed Shots", count=3))

    def test_effect_that_lost_its_last_stack_is_not_present(self):
        """Between the last stack being consumed and cleanup, the effect is still in the collection."""
        buff = _buff()
        buff.modify_stacks(-2)
        entity = _entity(buff)
        self.assertTrue(buff.is_expired)

        self.assertFalse(entity_has_effect(entity, tags=["tag.test.primed"]))
        self.assertFalse(entity_has_effect(entity, ability_spec="Primed Shots"))
        self.assertEqual(get_entity_effect_stacks(entity, ability_spec="Primed Shots"), 0)

    def test_expired_instance_does_not_hide_an_active_one(self):
        expired = _buff(number=1, is_expired=True)
        active = _buff(number=2)
        self.assertTrue(entity_has_effect(_entity(expired, active), ability_spec="Primed Shots"))


if __name__ == "__main__":
    unittest.main()
