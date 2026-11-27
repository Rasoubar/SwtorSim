"""Unit tests for entity_has_effect count: stacks are summed across all matching effects and dots."""

import unittest
from types import SimpleNamespace

from src.swtorsim.effects import ActiveEffect
from src.swtorsim.requirements import entity_has_effect

DOT_TAG = "tag.abl.sith_inquisitor.sinister_succor_dot"


def _entity(*effects, dots=None):
    return SimpleNamespace(effects={e.canonical_id: e for e in effects}, dots=dots or {})


def _dot(number, name, **kwargs):
    return ActiveEffect(
        fqn=f"abl.test.{name.lower()}", name=name, tags=frozenset({DOT_TAG}),
        stacks=1, max_stacks=1, number=number, **kwargs,
    )


class EntityHasEffectCountTests(unittest.TestCase):
    def test_separate_effects_sharing_a_tag_add_up(self):
        """Creeping Terror + Discharge + Crushed each carry the tag once; Leeching Strike needs 3."""
        entity = _entity(_dot(1, "Creeping Terror"), _dot(2, "Discharge"), _dot(3, "Crushed"))
        self.assertTrue(entity_has_effect(entity, tags=[DOT_TAG], count=1))
        self.assertTrue(entity_has_effect(entity, tags=[DOT_TAG], count=2))
        self.assertTrue(entity_has_effect(entity, tags=[DOT_TAG], count=3))
        self.assertFalse(entity_has_effect(entity, tags=[DOT_TAG], count=4))

    def test_two_effects_do_not_satisfy_count_three(self):
        entity = _entity(_dot(1, "Creeping Terror"), _dot(2, "Discharge"))
        self.assertTrue(entity_has_effect(entity, tags=[DOT_TAG], count=2))
        self.assertFalse(entity_has_effect(entity, tags=[DOT_TAG], count=3))

    def test_single_effect_stacks_still_count(self):
        buff = ActiveEffect(
            fqn="abl.test.supercharge", name="Supercharge", tags=frozenset({"tag.test.sc"}),
            stacks=3, max_stacks=10,
        )
        entity = _entity(buff)
        self.assertTrue(entity_has_effect(entity, tags=["tag.test.sc"], count=3))
        self.assertFalse(entity_has_effect(entity, tags=["tag.test.sc"], count=4))

    def test_expired_effects_are_not_counted(self):
        expired = _dot(3, "Crushed", is_expired=True)
        entity = _entity(_dot(1, "Creeping Terror"), _dot(2, "Discharge"), expired)
        self.assertFalse(entity_has_effect(entity, tags=[DOT_TAG], count=3))

    def test_ability_spec_match_is_unchanged(self):
        entity = _entity(_dot(1, "Creeping Terror"), _dot(2, "Discharge"))
        self.assertTrue(entity_has_effect(entity, ability_spec="Discharge", count=1))
        self.assertFalse(entity_has_effect(entity, ability_spec="Discharge", count=2))

    def test_dots_honor_count(self):
        dots = {
            "Creeping Terror": SimpleNamespace(tags=[DOT_TAG], stacks=1, is_expired=False),
            "Discharge": SimpleNamespace(tags=[DOT_TAG], stacks=1, is_expired=False),
        }
        entity = _entity(dots=dots)
        self.assertTrue(entity_has_effect(entity, tags=[DOT_TAG], count=2))
        self.assertFalse(entity_has_effect(entity, tags=[DOT_TAG], count=3))

    def test_effects_and_dots_combine(self):
        dots = {"Discharge": SimpleNamespace(tags=[DOT_TAG], stacks=1, is_expired=False)}
        entity = _entity(_dot(1, "Creeping Terror"), _dot(2, "Crushed"), dots=dots)
        self.assertTrue(entity_has_effect(entity, tags=[DOT_TAG], count=3))

    def test_no_match_returns_false(self):
        self.assertFalse(entity_has_effect(_entity(_dot(1, "Creeping Terror")), tags=["tag.other"], count=1))
        self.assertFalse(entity_has_effect(None, tags=[DOT_TAG]))


if __name__ == "__main__":
    unittest.main()
