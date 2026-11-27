"""Unit tests for TriggerManager.dispatch filtering order, rate limits and proc-chance modifiers."""

import random
import unittest
from types import SimpleNamespace

from src.swtorsim.modifiers import Modifier
from src.swtorsim.triggers import TriggerManager


class _Branch:
    def __init__(self, event, tags=(), proc_chance=None, interval=0.0):
        trigger = {"trigger": event, "tags": list(tags)}
        if proc_chance is not None:
            trigger["floats"] = {"proc_chance_percent": proc_chance}
        if interval:
            trigger["intervals"] = {"interval_61": interval}
        self.triggers = [trigger]


class _Ability:
    def __init__(self, fqn, on_run=None):
        self.fqn = fqn
        self.name = fqn
        self.runs = 0
        self._on_run = on_run

    def execute_branch(self, sim, branch, caster, target, context=None):
        self.runs += 1
        if self._on_run is not None:
            self._on_run()
        return True


def _sim(now=0.0):
    return SimpleNamespace(current_time=now, tracer=None)


def _effect(stat, value, targets=()):
    return SimpleNamespace(
        is_expired=False,
        modifiers=[Modifier(stat=stat, value=value, targets=frozenset(targets))],
    )


class TriggerDispatchTests(unittest.TestCase):
    def setUp(self):
        self.caster = SimpleNamespace(effects={})
        self.target = SimpleNamespace(effects={})
        self.triggers = TriggerManager()

    def _subscribe(self, owner, ability, branch):
        self.triggers.subscribe(owner, ability, branch, self.caster, self.target)

    def _dispatch(self, sim, tags=()):
        self.triggers.dispatch(
            "on_damage_dealt", sim, {"caster": self.caster, "target": self.target, "tags": list(tags)}
        )

    def test_rate_limit_blocks_until_interval_elapsed(self):
        ability = _Ability("abl.test.icd")
        self._subscribe("icd", ability, _Branch("on_damage_dealt", interval=5.0))

        self._dispatch(_sim(0.0))
        self._dispatch(_sim(1.0))
        self.assertEqual(ability.runs, 1)
        self._dispatch(_sim(5.0))
        self.assertEqual(ability.runs, 2)

    def test_rate_limit_modifier_shortens_interval(self):
        ability = _Ability("abl.test.icd")
        self._subscribe("icd", ability, _Branch("on_damage_dealt", interval=5.0))
        self.caster.effects["haste"] = _effect("229", -3.0, targets=["abl.test.icd"])

        self._dispatch(_sim(0.0))
        self._dispatch(_sim(1.0))
        self.assertEqual(ability.runs, 1)
        self._dispatch(_sim(2.0))
        self.assertEqual(ability.runs, 2)

    def test_rate_limit_scales_with_caster_alacrity(self):
        """A 3s limit at 7.64% Alacrity is 2.787s: open again two 1.4s GCDs later, not three."""
        self.caster.scale_time_modifier = lambda base_time: base_time / 1.0764
        ability = _Ability("abl.test.icd")
        self._subscribe("icd", ability, _Branch("on_damage_dealt", interval=3.0))

        self._dispatch(_sim(0.0))
        self._dispatch(_sim(1.4))
        self.assertEqual(ability.runs, 1)
        self._dispatch(_sim(2.78))
        self.assertEqual(ability.runs, 1)
        self._dispatch(_sim(2.8))
        self.assertEqual(ability.runs, 2)

    def test_rate_limit_alacrity_is_read_when_the_proc_fires(self):
        """Alacrity gained mid-fight shortens the next lockout, not the one already running."""
        alacrity = [0.0]
        self.caster.scale_time_modifier = lambda base_time: base_time / (1.0 + alacrity[0])
        ability = _Ability("abl.test.icd")
        self._subscribe("icd", ability, _Branch("on_damage_dealt", interval=4.0))

        self._dispatch(_sim(0.0))
        alacrity[0] = 1.0
        self._dispatch(_sim(2.0))
        self.assertEqual(ability.runs, 1)
        self._dispatch(_sim(4.0))
        self.assertEqual(ability.runs, 2)
        self._dispatch(_sim(6.0))
        self.assertEqual(ability.runs, 3)

    def test_rate_limit_flat_modifier_applies_before_alacrity(self):
        """(5s - 3s) / 2 = 1s, not 5s / 2 - 3s (which would remove the limit)."""
        self.caster.scale_time_modifier = lambda base_time: base_time / 2.0
        ability = _Ability("abl.test.icd")
        self._subscribe("icd", ability, _Branch("on_damage_dealt", interval=5.0))
        self.caster.effects["haste"] = _effect("229", -3.0, targets=["abl.test.icd"])

        self._dispatch(_sim(0.0))
        self._dispatch(_sim(0.5))
        self.assertEqual(ability.runs, 1)
        self._dispatch(_sim(1.0))
        self.assertEqual(ability.runs, 2)

    def test_rate_limit_unscaled_for_caster_without_alacrity(self):
        """Entity.scale_time_modifier (dummy) returns the time unchanged."""
        self.caster.scale_time_modifier = lambda base_time: base_time
        ability = _Ability("abl.test.icd")
        self._subscribe("icd", ability, _Branch("on_damage_dealt", interval=3.0))

        self._dispatch(_sim(0.0))
        self._dispatch(_sim(2.9))
        self.assertEqual(ability.runs, 1)
        self._dispatch(_sim(3.0))
        self.assertEqual(ability.runs, 2)

    def test_proc_chance_modifier_matches_listener_tags_only(self):
        tagged = _Ability("abl.test.tagged")
        other = _Ability("abl.test.other")
        self._subscribe("tagged", tagged, _Branch("on_damage_dealt", tags=["tag.proc"], proc_chance=0.0))
        self._subscribe("other", other, _Branch("on_damage_dealt", tags=["tag.other"], proc_chance=0.0))
        self.caster.effects["bonus"] = _effect("228", 1.0, targets=["tag.proc"])

        self._dispatch(_sim(), tags=["tag.proc", "tag.other"])

        self.assertEqual(tagged.runs, 1)
        self.assertEqual(other.runs, 0)

    def test_effect_added_by_an_earlier_listener_is_seen_by_later_listeners(self):
        """Modifier lookups are refreshed after a branch runs within the same dispatch."""
        def grant_bonus():
            self.caster.effects["bonus"] = _effect("228", 1.0, targets=["abl.test.second"])

        first = _Ability("abl.test.first", on_run=grant_bonus)
        second = _Ability("abl.test.second")
        self._subscribe("first", first, _Branch("on_damage_dealt"))
        self._subscribe("second", second, _Branch("on_damage_dealt", proc_chance=0.0))

        self._dispatch(_sim())

        self.assertEqual(first.runs, 1)
        self.assertEqual(second.runs, 1)

    def test_filtered_out_listener_draws_no_random_number(self):
        ability = _Ability("abl.test.filtered")
        self._subscribe("filtered", ability, _Branch("on_damage_dealt", tags=["tag.wanted"], proc_chance=50.0))
        random.seed(7)
        state = random.getstate()

        self._dispatch(_sim(), tags=["tag.unrelated"])

        self.assertEqual(ability.runs, 0)
        self.assertEqual(random.getstate(), state)

    def test_unsubscribe_removes_only_that_owner_and_keeps_order(self):
        first = _Ability("abl.test.first")
        second = _Ability("abl.test.second")
        third = _Ability("abl.test.third")
        self._subscribe("first", first, _Branch("on_damage_dealt"))
        self._subscribe("second", second, _Branch("on_damage_dealt"))
        self._subscribe("second", second, _Branch("on_ability_activate"))
        self._subscribe("third", third, _Branch("on_damage_dealt"))

        self.triggers.unsubscribe("second")
        self.triggers.unsubscribe("never_subscribed")

        owners = [sub["owner_id"] for sub in self.triggers._listeners["on_damage_dealt"]]
        self.assertEqual(owners, ["first", "third"])
        self.assertEqual(self.triggers._listeners["on_ability_activate"], [])
        self._dispatch(_sim())
        self.assertEqual((first.runs, second.runs, third.runs), (1, 0, 1))

    def test_owner_can_resubscribe_after_unsubscribe(self):
        ability = _Ability("abl.test.resub")
        self._subscribe("owner", ability, _Branch("on_damage_dealt"))
        self.triggers.unsubscribe("owner")
        self._subscribe("owner", ability, _Branch("on_damage_dealt"))

        self._dispatch(_sim())
        self.assertEqual(ability.runs, 1)
        self.triggers.unsubscribe("owner")
        self._dispatch(_sim())
        self.assertEqual(ability.runs, 1)

    def test_proc_chance_modifier_is_a_fraction_of_one(self):
        """Stat 228 values are fractions added to the 0-100 base chance: 0.3 -> +30 points."""
        ability = _Ability("abl.test.proc")
        self._subscribe("proc", ability, _Branch("on_damage_dealt", proc_chance=70.0))
        self.caster.effects["bonus"] = _effect("228", 0.3, targets=["abl.test.proc"])
        random.seed(11)
        state = random.getstate()

        for _ in range(50):
            self._dispatch(_sim())

        # 70 + 30 = 100: always fires and never needs a random draw.
        self.assertEqual(ability.runs, 50)
        self.assertEqual(random.getstate(), state)

    def test_proc_chance_modifier_above_one_is_not_read_as_points(self):
        ability = _Ability("abl.test.proc")
        self._subscribe("proc", ability, _Branch("on_damage_dealt", proc_chance=0.0))
        self.caster.effects["bonus"] = _effect("228", 1.5, targets=["abl.test.proc"])

        for _ in range(50):
            self._dispatch(_sim())

        self.assertEqual(ability.runs, 50)


if __name__ == "__main__":
    unittest.main()
