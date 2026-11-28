"""Comparison operators on rotation rules, and legacy keys keeping their old operator."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.swtorsim.rotation_builder import CONDITION_METADATA
from src.swtorsim.requirements import (
    compare_values,
    validate_all,
)

LEGACY_KEYS = {
    "target_hp_below_pct",
    "target_hp_above_pct",
    "caster_energy_above",
    "caster_energy_below",
    "proc_cooldown_above",
    "ability_cooldown_under",
    "ability_cooldown_above",
}

OPERATORS = ("lt", "lte", "eq", "gt", "gte")


class _Resource:
    def __init__(self, value):
        self.current_value = value


class _Actor:
    def __init__(self, hp_ratio=1.0, resource=100.0, effects=()):
        self.hp_ratio = hp_ratio
        self.resource = _Resource(resource)
        self._effects = set(effects)
        self.effects = {}
        self.procs = {}
        self.proc_registry = {}
        self.cooldowns = {}
        self.ability_db = {}

    def has_effect(self, name):
        return name in self._effects


class _Proc:
    def __init__(self, ready_at):
        self.next_possible_proc = ready_at


class _Sim:
    def __init__(self, now):
        self.current_time = now


class _Effect:
    def __init__(self, name, expires_at, passive=False, expired=False, tags=()):
        self.name = name
        self.fqn = ""
        self.expires_at = expires_at
        self.is_passive = passive
        self.is_expired = expired
        self.tags = tags

    def time_remaining(self, now):
        if self.expires_at is None:
            return float("inf")
        return max(0.0, self.expires_at - now)


class RuleComparisonTests(unittest.TestCase):
    def test_picker_hides_legacy_keys(self):
        visible = {item["key"] for item in CONDITION_METADATA if item.get("picker", True)}
        self.assertTrue(LEGACY_KEYS.isdisjoint(visible))
        self.assertTrue({"target_hp_pct", "caster_energy", "proc_cooldown", "ability_cooldown"} <= visible)

    def test_each_operator_matches_compare_values(self):
        caster = _Actor(resource=40)
        target = _Actor(hp_ratio=0.30)
        sim = _Sim(0.0)
        caster.cooldowns["Strike"] = 4.0
        caster.procs["Bloodletting"] = _Proc(5.0)
        samples = (
            ("target_hp_pct", {"pct": 0.30}, target.hp_ratio, 0.30),
            ("caster_energy", {"value": 40}, caster.resource.current_value, 40),
            ("ability_cooldown", {"name": "Strike", "value": 4.0}, 4.0, 4.0),
            ("proc_cooldown", {"name": "Bloodletting", "value": 5.0}, 5.0, 5.0),
        )
        for key, payload, actual, expected in samples:
            for op in OPERATORS:
                body = dict(payload)
                body["comparison"] = op
                with self.subTest(key=key, op=op):
                    self.assertEqual(
                        validate_all({key: body}, caster, target, sim=sim),
                        compare_values(actual, op, expected),
                    )

    def test_legacy_keys_match_the_historical_operator(self):
        pairs = (
            (0.2, 0.3, 0.4),
        )
        for hp in pairs[0]:
            caster = _Actor()
            target = _Actor(hp_ratio=hp)
            with self.subTest(kind="hp", hp=hp):
                self.assertEqual(
                    validate_all({"target_hp_below_pct": 0.3}, caster, target),
                    validate_all({"target_hp_pct": {"pct": 0.3, "comparison": "lte"}}, caster, target),
                )
                self.assertEqual(
                    validate_all({"target_hp_above_pct": 0.3}, caster, target),
                    validate_all({"target_hp_pct": {"pct": 0.3, "comparison": "gt"}}, caster, target),
                )
        for resource in (39, 40, 41):
            caster = _Actor(resource=resource)
            target = _Actor()
            with self.subTest(kind="energy", resource=resource):
                self.assertEqual(
                    validate_all({"caster_energy_above": 40}, caster, target),
                    validate_all({"caster_energy": {"value": 40, "comparison": "gte"}}, caster, target),
                )
                self.assertEqual(
                    validate_all({"caster_energy_below": 40}, caster, target),
                    validate_all({"caster_energy": {"value": 40, "comparison": "lt"}}, caster, target),
                )
        sim = _Sim(1.0)
        caster = _Actor()
        caster.cooldowns["Strike"] = 5.0
        target = _Actor()
        for seconds in (3.0, 4.0, 5.0):
            with self.subTest(kind="ability", seconds=seconds):
                legacy_under = {"ability_cooldown_under": {"name": "Strike", "value": seconds}}
                legacy_above = {"ability_cooldown_above": {"name": "Strike", "value": seconds}}
                self.assertEqual(
                    validate_all(legacy_under, caster, target, sim=sim),
                    validate_all({"ability_cooldown": {"name": "Strike", "value": seconds, "comparison": "lt"}}, caster, target, sim=sim),
                )
                self.assertEqual(
                    validate_all(legacy_above, caster, target, sim=sim),
                    validate_all({"ability_cooldown": {"name": "Strike", "value": seconds, "comparison": "gt"}}, caster, target, sim=sim),
                )
        caster.procs["Bloodletting"] = _Proc(6.0)
        for seconds in (4.0, 5.0, 6.0):
            with self.subTest(kind="proc", seconds=seconds):
                legacy = {"proc_cooldown_above": {"name": "Bloodletting", "value": seconds, "comparison": "lt"}}
                self.assertEqual(
                    validate_all(legacy, caster, target, sim=sim),
                    validate_all({"proc_cooldown": {"name": "Bloodletting", "value": seconds, "comparison": "gt"}}, caster, target, sim=sim),
                )

    def test_hp_bypass_buff_makes_the_rule_true(self):
        caster = _Actor(effects={"Reaper's Rush"})
        target = _Actor(hp_ratio=0.9)
        rule = {"pct": 0.3, "comparison": "lte", "bypass_if_buff_active": "Reaper's Rush"}
        self.assertTrue(validate_all({"target_hp_pct": rule}, caster, target))
        self.assertTrue(validate_all({"target_hp_below_pct": rule}, caster, target))
        self.assertFalse(validate_all({"target_hp_pct": {"pct": 0.3, "comparison": "lte"}}, caster, target))

    def test_proc_rule_is_false_while_the_buff_is_active(self):
        caster = _Actor(effects={"Bloodletting"})
        caster.procs["Bloodletting"] = _Proc(0.0)
        target = _Actor()
        sim = _Sim(0.0)
        for op in OPERATORS:
            with self.subTest(op=op):
                rule = {"name": "Bloodletting", "value": 0.0, "comparison": op}
                self.assertFalse(validate_all({"proc_cooldown": rule}, caster, target, sim=sim))
        self.assertFalse(
            validate_all({"proc_cooldown_above": {"name": "Bloodletting", "value": 0.0}}, caster, target, sim=sim)
        )


class EffectRemainingTests(unittest.TestCase):
    def _actor(self, effects):
        actor = _Actor()
        actor.effects = effects
        return actor

    def test_each_operator_matches_compare_values(self):
        caster = self._actor({"recklessness": _Effect("Recklessness", expires_at=7.0)})
        target = self._actor({"terror": _Effect("Creeping Terror", expires_at=5.0)})
        sim = _Sim(2.0)
        samples = (
            ("caster_buff_remaining", "Recklessness", 5.0),
            ("target_debuff_remaining", "Creeping Terror", 3.0),
        )
        for key, name, actual in samples:
            for op in OPERATORS:
                for expected in (actual - 1, actual, actual + 1):
                    with self.subTest(key=key, op=op, expected=expected):
                        rule = {"name": name, "value": expected, "comparison": op}
                        self.assertEqual(
                            validate_all({key: rule}, caster, target, sim=sim),
                            compare_values(actual, op, expected),
                        )

    def test_missing_effect_counts_as_zero(self):
        caster = _Actor()
        target = _Actor()
        sim = _Sim(0.0)
        self.assertTrue(validate_all(
            {"caster_buff_remaining": {"name": "Recklessness", "value": 3, "comparison": "lt"}},
            caster, target, sim=sim,
        ))
        self.assertFalse(validate_all(
            {"target_debuff_remaining": {"name": "Creeping Terror", "value": 0, "comparison": "gt"}},
            caster, target, sim=sim,
        ))

    def test_uses_the_longer_copy_and_ignores_expired_passive_and_lockout(self):
        caster = self._actor({
            "short": _Effect("Recklessness", expires_at=4.0),
            "long": _Effect("Recklessness", expires_at=9.0),
            "gone": _Effect("Recklessness", expires_at=100.0, expired=True),
            "passive": _Effect("Recklessness", expires_at=None, passive=True),
            "lock": _Effect("Recklessness", expires_at=100.0, tags=("lockout",)),
        })
        sim = _Sim(1.0)
        self.assertTrue(validate_all(
            {"caster_buff_remaining": {"name": "recklessness", "value": 8, "comparison": "eq"}},
            caster, _Actor(), sim=sim,
        ))
        self.assertFalse(validate_all(
            {"caster_buff_remaining": {"name": "Recklessness", "value": 3, "comparison": "lte"}},
            caster, _Actor(), sim=sim,
        ))

    def test_permanent_buff_has_infinite_time_left(self):
        caster = self._actor({"a": _Effect("Recklessness", expires_at=None)})
        sim = _Sim(10.0)
        self.assertTrue(validate_all(
            {"caster_buff_remaining": {"name": "Recklessness", "value": 5, "comparison": "gt"}},
            caster, _Actor(), sim=sim,
        ))
        self.assertFalse(validate_all(
            {"caster_buff_remaining": {"name": "Recklessness", "value": 5, "comparison": "lt"}},
            caster, _Actor(), sim=sim,
        ))


if __name__ == "__main__":
    unittest.main()
