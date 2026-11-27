"""Unit tests for the extracted ``is_casting`` condition with a named ability."""

import unittest
from types import SimpleNamespace

from src.swtorsim.requirements import evaluate_single_extracted_condition

SNIPE = "abl.agent.snipe"


def _actor(active_cast=None, active_channel=None):
    return SimpleNamespace(active_cast=active_cast, active_channel=active_channel, is_channeling=False)


def _is_casting(actor, spec=None):
    item = {"type": "is_casting", "actor": "caster"}
    if spec:
        item["ability_spec"] = spec
    return evaluate_single_extracted_condition(item, actor, None)


class IsCastingConditionTests(unittest.TestCase):
    def test_timed_cast_matches_its_own_ability(self):
        """During a timed cast the player's active_cast is the ability itself."""
        actor = _actor(active_cast=SimpleNamespace(fqn=SNIPE))
        self.assertTrue(_is_casting(actor, SNIPE))
        self.assertFalse(_is_casting(actor, "abl.agent.ambush"))

    def test_channel_matches_the_ability_it_wraps(self):
        actor = _actor(active_channel=SimpleNamespace(ability=SimpleNamespace(fqn=SNIPE)))
        self.assertTrue(_is_casting(actor, SNIPE))
        self.assertFalse(_is_casting(actor, "abl.agent.ambush"))

    def test_idle_actor_is_not_casting(self):
        self.assertFalse(_is_casting(_actor(), SNIPE))
        self.assertFalse(_is_casting(_actor()))

    def test_unnamed_check_is_true_for_any_cast(self):
        self.assertTrue(_is_casting(_actor(active_cast=SimpleNamespace(fqn=SNIPE))))


if __name__ == "__main__":
    unittest.main()
