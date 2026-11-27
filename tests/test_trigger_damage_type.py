"""Unit tests: damage triggers receive the resolved damage type, not the raw action default."""

import unittest
from types import SimpleNamespace
from unittest import mock

from src.swtorsim.events import DamageHit


def _resolve(action_data, resolved_type):
    """Resolves a DamageHit with a stubbed hit calculation; returns {event: context}."""
    seen = {}

    def fake_hit(source, target, action):
        if resolved_type is not None:
            action["resolved_damage_type"] = resolved_type
        return 100.0, False

    sim = SimpleNamespace(
        current_time=1.0,
        combat_start_time=None,
        verbose=False,
        tracer=None,
        tracker=SimpleNamespace(log_damage=lambda *a, **k: None),
        triggers=SimpleNamespace(dispatch=lambda event, _sim, ctx: seen.setdefault(event, ctx)),
    )
    source = SimpleNamespace(name="Tester")
    target = SimpleNamespace(name="Target Dummy", hp=1000.0)
    with mock.patch("src.swtorsim.events.calculate_hit", fake_hit):
        DamageHit(source, target, action_data, "Strike").resolve(sim)
    return seen


class TriggerDamageTypeTests(unittest.TestCase):
    def test_weapon_hit_without_raw_type_reports_the_resolved_type(self):
        seen = _resolve({"action_type": "damage", "attack_type": 1}, resolved_type=2)

        for event in ("on_pre_damage_dealt", "on_pre_damage_taken", "on_damage_dealt", "on_damage_taken"):
            self.assertEqual(seen[event]["damage_type"], 2, event)

    def test_raw_type_is_used_when_the_hit_resolves_none(self):
        seen = _resolve({"action_type": "damage", "attack_type": 3, "damage_type": 4}, resolved_type=None)

        self.assertEqual(seen["on_damage_dealt"]["damage_type"], 4)


if __name__ == "__main__":
    unittest.main()
