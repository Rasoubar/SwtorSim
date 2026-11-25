"""Comparison operators on rotation rules, and legacy keys keeping their old operator."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.rotation_builder import CONDITION_METADATA
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


if __name__ == "__main__":
    unittest.main()
