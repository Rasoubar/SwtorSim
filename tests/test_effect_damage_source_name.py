"""Damage breakdown is labelled by effect display name; casts stay under the ability name."""

import unittest
from types import SimpleNamespace
from unittest import mock

from src.swtorsim import abilities
from src.swtorsim.abilities import Branch, Effect, damage_source_name
from src.swtorsim.metrics import Metrics


class _FakeHit:
    """Stand-in for DamageHit that records the label it was given."""

    seen = []

    def __init__(self, caster, target, action_data, ability_name, **kwargs):
        self.ability_name = ability_name
        self.is_crit = False
        _FakeHit.seen.append(ability_name)

    def resolve(self, sim):
        pass


def _run_effect(effect, ability_name="Fusion Missile", periodic=False):
    _FakeHit.seen = []
    branch = Branch(index=2, actions=[{"action_type": "damage", "coeff": 1.0}])
    effect.branches = [branch]
    ability = SimpleNamespace(name=ability_name, fqn="abl.test", tags=[], type="active")
    caster = SimpleNamespace(stats={})
    ctx = {"is_periodic": periodic}
    with mock.patch.object(abilities, "DamageHit", _FakeHit), \
            mock.patch.object(abilities, "accuracy_roll", return_value=True):
        effect.execute_triggered_branches(
            "on_tick", None, caster, object(), context=ctx, ability=ability, include_untriggered=True
        )
    return list(_FakeHit.seen)


class EffectDamageSourceNameTests(unittest.TestCase):
    def test_named_periodic_effect_logs_under_effect_name(self):
        eff = Effect(number=1, entry=True, name="Radiation Burns")
        self.assertEqual(_run_effect(eff, periodic=True), ["Radiation Burns"])

    def test_named_non_periodic_effect_logs_under_effect_name(self):
        eff = Effect(number=1, entry=True, name="Priming Shot Hit")
        self.assertEqual(_run_effect(eff, periodic=False), ["Priming Shot Hit"])

    def test_empty_or_missing_name_falls_back_to_ability_name(self):
        for name in ("", None, "   "):
            with self.subTest(name=name):
                self.assertEqual(_run_effect(Effect(number=1, entry=True, name=name)), ["Fusion Missile"])

    def test_auto_generated_helper_name_falls_back_to_ability_name(self):
        eff = Effect(number=3, entry=True, name="Fusion Missile_3")
        self.assertEqual(_run_effect(eff), ["Fusion Missile"])

    def test_no_effect_in_context_uses_ability_name(self):
        self.assertEqual(damage_source_name({}, "Fusion Missile"), "Fusion Missile")
        self.assertEqual(damage_source_name(None, "Fusion Missile"), "Fusion Missile")

    def test_casts_stay_under_ability_name_while_damage_uses_effect_name(self):
        m = Metrics()
        m.log_cast("Fusion Missile")
        m.log_damage("Radiation Burns", 100.0, False, None, 1.0)
        self.assertEqual(m.cast_counts, {"Fusion Missile": 1})
        self.assertEqual(list(m.breakdown), ["Radiation Burns"])

    def test_active_effect_fallback_in_damage_source_name(self):
        active = SimpleNamespace(effect_blueprint=Effect(number=2, entry=False, name="Burning (Priming Shot)"))
        self.assertEqual(damage_source_name({"active_effect": active}, "Burning Shot"), "Burning (Priming Shot)")

    def test_trigger_dispatch_passes_owning_effect_over_parent_effect(self):
        from src.swtorsim.triggers import TriggerManager

        tm = TriggerManager()
        captured = []
        parent_eff = Effect(number=1, entry=True, name="Parent Effect")
        owning_eff = Effect(number=2, entry=False, name="Burning (Priming Shot)")
        branch = Branch(index=0, triggers=[{"trigger": "on_damage_taken"}])
        ability = SimpleNamespace(
            name="Burning Shot",
            fqn="abl.test.burning_shot",
            tags=(),
            execute_branch=lambda sim, b, caster, target, context=None: captured.append(context.get("effect")) or True,
        )
        caster = SimpleNamespace(effects={}, modifiers=[], stats={})
        target = SimpleNamespace(effects={"burning_key": SimpleNamespace(effect_blueprint=owning_eff, stacks=1, is_expired=False)})
        tm.subscribe("owner_1", ability, branch, caster, target, effect_key="burning_key")
        tm.dispatch("on_damage_taken", SimpleNamespace(current_time=1.0), {"caster": caster, "target": target, "effect": parent_eff})
        self.assertEqual(captured, [owning_eff])

        # Without an active owner_effect, stale parent effect is stripped rather than inherited.
        captured.clear()
        target.effects.clear()
        tm.dispatch("on_damage_taken", SimpleNamespace(current_time=2.0), {"caster": caster, "target": target, "effect": parent_eff})
        self.assertEqual(captured, [None])


if __name__ == "__main__":
    unittest.main()
