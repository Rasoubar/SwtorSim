"""Unit tests: stack count behavior on Entity.apply_effect refresh."""

import unittest

from src.swtorsim.abilities import Ability, AbilityBlueprint
from src.swtorsim.engine import Simulation
from src.swtorsim.entities import Dummy, Player


def _make_ability(
    fqn: str,
    initial: int,
    maximum: int,
    scales: bool,
    *,
    duration: float = 18.0,
    tags=None,
    is_by_tag: bool = False,
    relevant_tags=None,
) -> Ability:
    sc = {
        "initial": initial,
        "max": maximum,
        "nr_occurances": 1,
        "scales_with_stack_charge": scales,
        "is_by_tag": is_by_tag,
    }
    if relevant_tags is not None:
        sc["relevant_tags"] = relevant_tags
    bp = AbilityBlueprint.from_dict({
        "fqn": fqn,
        "name": fqn.split(".")[-1],
        "type": "active",
        "effects": [{
            "number": 1,
            "entry": True,
            "name": fqn.split(".")[-1],
            "duration": duration,
            "tags": list(tags or []),
            "stack_charge": sc,
            "branches": [],
        }],
    })
    return Ability(bp)


class StackRefreshResetTests(unittest.TestCase):
    """Verifies countdown charge-pool effects reset to initial_stacks on refresh while accumulating effects increment."""

    def test_countdown_pool_resets_to_initial_stacks_on_refresh(self):
        sim = Simulation(verbose=False, seed=1)
        player = Player("sorcerer")
        target = Dummy("Target Dummy", hp=1_000_000)
        ability = _make_ability("abl.test.countdown_pool", initial=6, maximum=6, scales=True)

        ability.execute_effect(1, player, target, sim)
        eff = target.effects.get("abl.test.countdown_pool:1")
        self.assertEqual(eff.stacks, 6)

        eff.modify_stacks(-4)
        self.assertEqual(eff.stacks, 2)

        ability.execute_effect(1, player, target, sim)
        refreshed = target.effects.get("abl.test.countdown_pool:1")
        self.assertEqual(refreshed.stacks, 6)

    def test_accumulating_stack_effect_increments_on_refresh(self):
        sim = Simulation(verbose=False, seed=1)
        player = Player("sorcerer")
        target = Dummy("Target Dummy", hp=1_000_000)
        ability = _make_ability("abl.test.accumulating", initial=1, maximum=3, scales=True)

        ability.execute_effect(1, player, target, sim)
        self.assertEqual(target.effects.get("abl.test.accumulating:1").stacks, 1)

        ability.execute_effect(1, player, target, sim)
        self.assertEqual(target.effects.get("abl.test.accumulating:1").stacks, 2)

        ability.execute_effect(1, player, target, sim)
        self.assertEqual(target.effects.get("abl.test.accumulating:1").stacks, 3)

    def test_is_by_tag_ignores_non_by_tag_effect(self):
        # e.g. Demolish (is_by_tag=True) must not drop or inherit expiry from affliction:6 (is_by_tag=False).
        sim = Simulation(verbose=False, seed=1)
        player = Player("sorcerer")
        target = Dummy("Target Dummy", hp=1_000_000)
        shared_tag = "tag.test.shared_dot"
        non_by_tag = _make_ability(
            "abl.test.non_by_tag", initial=6, maximum=6, scales=True, duration=18.0, tags=[shared_tag], is_by_tag=False
        )
        by_tag = _make_ability(
            "abl.test.by_tag", initial=1, maximum=1, scales=False, duration=6.0, tags=[shared_tag], is_by_tag=True, relevant_tags=shared_tag
        )

        non_by_tag.execute_effect(1, player, target, sim)
        by_tag.execute_effect(1, player, target, sim)

        self.assertIsNotNone(target.effects.get("abl.test.non_by_tag:1"))
        applied = target.effects.get("abl.test.by_tag:1")
        self.assertIsNotNone(applied)
        self.assertAlmostEqual(applied.expires_at, 6.0, places=3)

    def test_is_by_tag_replaces_other_by_tag_effect_with_own_expiry(self):
        sim = Simulation(verbose=False, seed=1)
        player = Player("sorcerer")
        target = Dummy("Target Dummy", hp=1_000_000)
        shared_tag = "tag.test.shared_dot"
        first = _make_ability(
            "abl.test.first", initial=1, maximum=1, scales=False, duration=18.0, tags=[shared_tag], is_by_tag=True, relevant_tags=shared_tag
        )
        second = _make_ability(
            "abl.test.second", initial=1, maximum=1, scales=False, duration=6.0, tags=[shared_tag], is_by_tag=True, relevant_tags=shared_tag
        )

        first.execute_effect(1, player, target, sim)
        second.execute_effect(1, player, target, sim)

        self.assertIsNone(target.effects.get("abl.test.first:1"))
        applied = target.effects.get("abl.test.second:1")
        self.assertIsNotNone(applied)
        self.assertAlmostEqual(applied.expires_at, 6.0, places=3)


if __name__ == "__main__":
    unittest.main()
