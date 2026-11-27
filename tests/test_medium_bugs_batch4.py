"""Regression tests for bug-hunt Medium #22 (debuff stack rule name matching), #23 (unmodeled condition types) and
#24 (modify_stack_charge target).

#20, #21 and #25 were set aside."""

import contextlib
import io
import unittest
from pathlib import Path
from types import SimpleNamespace

import src.swtorsim.config_load as cl
import src.swtorsim.run_config as rc
import src.swtorsim.setup as su
from src.swtorsim.abilities import Ability, AbilityBlueprint, handle_modify_stack_charge

from src.swtorsim.entities import Dummy, Player
from src.swtorsim.requirements import (
    check_caster_buff_stacks,
    check_target_debuff_stacks,
    evaluate_single_extracted_condition,
)

ROOT = Path(__file__).resolve().parents[1]
ABL = ROOT / "data" / "extractor" / "live" / "parsed" / "abl"


def _effect(name, stacks):
    return SimpleNamespace(
        name=name, fqn="abl.test." + name.lower().replace(" ", "_"), stacks=stacks, is_expired=False, tags=[]
    )


class TargetDebuffStackNameTests(unittest.TestCase):
    """#22: the target debuff stack rule finds effects the way the caster buff stack rule does."""

    def setUp(self):
        self.player = Player("P")
        self.dummy = Dummy("D", 1000)
        self.dummy.effects["abl.test.affliction:1"] = _effect("Affliction", 2)
        self.player.effects["abl.test.static_charge:1"] = _effect("Static Charge", 3)

    def test_lowercase_dict_name_matches(self):
        self.assertTrue(check_target_debuff_stacks({"name": "affliction", "stacks": 2}, self.player, self.dummy))

    def test_underscore_name_matches(self):
        self.assertTrue(check_target_debuff_stacks(["static_charge", 1], self.dummy, self.player))

    def test_list_form_respects_the_stack_count(self):
        self.assertTrue(check_target_debuff_stacks(["affliction", 2], self.player, self.dummy))
        self.assertFalse(check_target_debuff_stacks(["affliction", 3], self.player, self.dummy))

    def test_exact_name_still_matches(self):
        self.assertTrue(check_target_debuff_stacks({"name": "Affliction", "stacks": 1}, self.player, self.dummy))

    def test_missing_debuff_does_not_match(self):
        self.assertFalse(check_target_debuff_stacks(["Nope", 1], self.player, self.dummy))

    def test_bare_string_means_at_least_one_stack(self):
        self.assertTrue(check_target_debuff_stacks("Affliction", self.player, self.dummy))
        self.assertFalse(check_target_debuff_stacks("Nope", self.player, self.dummy))
        self.assertTrue(check_caster_buff_stacks("Static Charge", self.player, self.dummy))
        self.assertFalse(check_caster_buff_stacks("Nope", self.player, self.dummy))


SPEC = "abl.test.convection"


class _FakeEffect:
    """Just enough of an ActiveEffect for handle_modify_stack_charge."""

    def __init__(self, stacks, max_stacks, defines_capacity):
        self.stacks = stacks
        self.max_stacks = max_stacks
        self.is_expired = False
        self.fqn = SPEC
        self.ability_ref = SimpleNamespace(fqn=SPEC)
        self.effect_blueprint = {"stack_charge": {"max": max_stacks}} if defines_capacity else {}

    def modify_stacks(self, delta):
        self.stacks = max(0, min(self.stacks + delta, self.max_stacks))


def _fake_entity(effects):
    entity = SimpleNamespace(name="C", effects=effects)
    entity.cleanup_expired_effects = lambda keys: [effects.pop(k, None) for k in keys]
    return entity


class ModifyStackChargeTargetTests(unittest.TestCase):
    """#24: the action names only an ability; it acts on that ability's effect that defines stack capacity."""

    ACTION = {"action_type": "modify_stack_charge", "floats": {"amount_min": -1.0}, "ints": {"ability_spec": SPEC}}

    def _run(self, order, owner_key):
        effects = {
            "plain": _FakeEffect(1, 1, False),
            "stackable": _FakeEffect(2, 2, True),
            "other_plain": _FakeEffect(1, 1, False),
        }
        caster = _fake_entity({k: effects[k] for k in order})
        handle_modify_stack_charge(None, caster, caster, self.ACTION, context={"owner_effect_key": owner_key, "owner_entity": caster})
        return effects

    def test_stackable_effect_is_hit_whatever_the_insertion_order(self):
        for order in (("plain", "stackable", "other_plain"), ("stackable", "plain", "other_plain"), ("other_plain", "plain", "stackable")):
            effects = self._run(order, owner_key="stackable")
            self.assertEqual(effects["stackable"].stacks, 1, order)
            self.assertEqual(effects["plain"].stacks, 1, order)
            self.assertEqual(effects["other_plain"].stacks, 1, order)

    def test_stackable_effect_is_hit_when_the_action_fires_from_a_plain_effect(self):
        effects = self._run(("plain", "stackable", "other_plain"), owner_key="other_plain")
        self.assertEqual(effects["stackable"].stacks, 1)
        self.assertEqual(effects["plain"].stacks, 1)

    def test_without_an_active_stackable_effect_nothing_happens(self):
        effects = {"a": _FakeEffect(3, 3, False), "b": _FakeEffect(1, 1, False)}
        caster = _fake_entity(effects)
        handle_modify_stack_charge(None, caster, caster, self.ACTION, context={"owner_entity": caster})
        self.assertEqual((effects["a"].stacks, effects["b"].stacks), (3, 1))
        self.assertEqual(set(caster.effects), {"a", "b"})


class ConvectionLightningStrikeTests(unittest.TestCase):
    """#24: Lightning Strike uses up one Convection charge on the 2-stack buff, not on its parent effect."""

    def test_lightning_strike_consumes_a_charge_of_the_buff(self):
        with contextlib.redirect_stdout(io.StringIO()):
            cfg = rc.load_run_config(str(ROOT / "data/run_config/Hatred.json"))
            _rot, stats, bps, debuffs = cl.load_from_run_config(cfg)
            sim, p, d = su.prepare_simulation([], stats, bps, 1000000, debuffs, seed=1)
            inq = ABL / "sith_inquisitor"
            conv = Ability(AbilityBlueprint.from_file(inq / "skill/lightning/convection.json"))
            fs = Ability(AbilityBlueprint.from_file(inq / "force_speed.json"))
            ls = Ability(AbilityBlueprint.from_file(inq / "lightning_strike.json"))
            for abl in (conv, fs, ls):
                p.ability_db[abl.fqn] = abl
            p.resource.current = p.resource.max_value
            conv.effects[1].execute(sim, p, p, ability=conv)
            fs.cast(p, d, sim)
            sim.run_until(0.1)
            buff_key = conv.fqn + ":2"
            self.assertEqual(p.effects[buff_key].stacks, 2)
            p.next_gcd = 0.0
            ls.cast(p, d, sim)
            sim.run_until(0.2)
        self.assertIn(conv.fqn + ":1", p.effects)
        self.assertEqual(p.effects[buff_key].stacks, 1)


def _cond(cond_type, negated=False, **extra):
    return {"id": "1", "type": cond_type, "negated": negated, "actor": "target", **extra}


class UnmodeledConditionTypeTests(unittest.TestCase):
    """#23: six extracted condition types no longer fall into the "always true" fallback."""

    def setUp(self):
        self.player = Player("P")
        self.dummy = Dummy("D", 1000)

    def _eval(self, item):
        return evaluate_single_extracted_condition(item, self.player, self.dummy)

    def test_not_has_effect(self):
        item = _cond("not_has_effect", tags=["tag.abl.pvp.guard"])
        self.assertTrue(self._eval(item))
        self.dummy.effects["abl.test.guard:1"] = SimpleNamespace(
            name="Guard", fqn="abl.test.guard", stacks=1, is_expired=False, tags=["tag.abl.pvp.guard"]
        )
        self.assertFalse(self._eval(item))

    def test_is_dead(self):
        self.assertFalse(self._eval(_cond("is_dead")))
        self.assertTrue(self._eval(_cond("is_dead", negated=True)))
        self.dummy.hp = 0
        self.assertTrue(self._eval(_cond("is_dead")))
        self.assertFalse(self._eval(_cond("is_dead", negated=True)))

    def test_has_pending_revive_is_never_true(self):
        self.assertFalse(self._eval(_cond("has_pending_revive")))
        self.assertTrue(self._eval(_cond("has_pending_revive", negated=True)))

    def test_is_area_is_never_true(self):
        self.assertFalse(self._eval(_cond("is_area")))
        self.assertTrue(self._eval(_cond("is_area", negated=True)))

    def test_unmodeled_types_stay_true(self):
        self.assertTrue(self._eval(_cond("is_object")))
        self.assertTrue(self._eval(_cond("if_not_weapon_type")))

    def test_extracted_revive_conditions_on_a_living_target(self):
        import json

        data = json.loads((ABL / "agent/resuscitation_probe.json").read_text(encoding="utf-8"))
        by_type = {c["type"]: c for c in data["conditions"]["list"] if c["type"] in ("is_dead", "has_pending_revive")}
        self.assertFalse(self._eval(by_type["is_dead"]))  # a living target cannot be revived
        self.assertTrue(self._eval(by_type["has_pending_revive"]))  # negated: no revive is pending


if __name__ == "__main__":
    unittest.main()
