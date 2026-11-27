"""Regression tests for bug-hunt High #7-#9 (ability charge condition, attack targeting, retaliation buffs)."""

import contextlib
import io
import unittest
from pathlib import Path

import src.swtorsim.config_load as cl
import src.swtorsim.run_config as rc
import src.swtorsim.setup as su
from src.swtorsim import settings
from src.swtorsim.abilities import Ability, AbilityBlueprint
from src.swtorsim.entities import Dummy, Player
from src.swtorsim.requirements import evaluate_single_extracted_condition

ROOT = Path(__file__).resolve().parents[1]
ABL = ROOT / "data" / "extractor" / "live" / "parsed" / "abl"


def _ability(rel):
    return Ability(AbilityBlueprint.from_file(ABL / rel))


def _carnage_sim():
    with contextlib.redirect_stdout(io.StringIO()):
        cfg = rc.load_run_config(str(ROOT / "data/run_config/Carnage.json"))
        _rot, stats, bps, debuffs = cl.load_from_run_config(cfg)
        return su.prepare_simulation([], stats, bps, 1000000, debuffs, seed=1)


def _charge_cond(spec, actor="caster", amount=1.0):
    return {"type": "has_ability_stack_charge", "actor": actor, "ability_spec": spec, "comparison": "gte", "floats": {"amount": amount}}


class AbilityStackChargeConditionTests(unittest.TestCase):
    """#7: charges may be None, the actor must be honored, and stem matching must apply."""

    def setUp(self):
        self.addCleanup(settings.set_stem_matching, settings.is_stem_matching_enabled())

    def test_non_charge_ability_does_not_crash_and_counts_as_zero(self):
        snipe = _ability("agent/snipe.json")
        self.assertIsNone(snipe.charges)
        caster = Player("Op", abilities={snipe.fqn: snipe})
        self.assertFalse(evaluate_single_extracted_condition(_charge_cond(snipe.fqn), caster, Dummy("D", 1000)))
        self.assertTrue(evaluate_single_extracted_condition({**_charge_cond(snipe.fqn), "comparison": "lte"}, caster, Dummy("D", 1000)))

    def test_named_actor_ability_is_used(self):
        exf = _ability("agent/exfiltrate.json")
        exf.charges = 2
        owner = Player("Owner", abilities={exf.fqn: exf})
        other = Player("Other")
        cond = _charge_cond(exf.fqn, actor="target", amount=2.0)
        self.assertTrue(evaluate_single_extracted_condition(cond, other, owner))

    def test_falls_back_to_caster_when_actor_lacks_the_ability(self):
        exf = _ability("agent/exfiltrate.json")
        exf.charges = 2
        caster = Player("Caster", abilities={exf.fqn: exf})
        cond = _charge_cond(exf.fqn, actor="target", amount=2.0)
        self.assertTrue(evaluate_single_extracted_condition(cond, caster, Dummy("D", 1000)))

    def test_stem_matching_finds_plus_ability(self):
        plus = _ability("sith_inquisitor/skill/hatred/assassinate_plus.json")
        plus.charges = 3
        caster = Player("Sin", abilities={plus.fqn: plus})
        cond = _charge_cond("abl.sith_inquisitor.skill.hatred.assassinate", amount=3.0)
        settings.set_stem_matching(False)
        self.assertFalse(evaluate_single_extracted_condition(cond, caster, Dummy("D", 1000)))
        settings.set_stem_matching(True)
        self.assertTrue(evaluate_single_extracted_condition(cond, caster, Dummy("D", 1000)))


class AttackTargetingTests(unittest.TestCase):
    """#8: any ability with a damaging branch targets the enemy, whatever other tags it carries."""

    def test_is_aggressive_for_class_tagged_attacks(self):
        for rel in (
            "sith_warrior/skill/rage/obliterate.json",
            "jedi_knight/skill/watchman/merciless_slash.json",
            "smuggler/skill/ruffian/point_blank_shot.json",
        ):
            self.assertTrue(_ability(rel).is_aggressive, rel)

    def test_self_buff_is_not_aggressive(self):
        self.assertFalse(_ability("sith_warrior/enrage.json").is_aggressive)

    def test_obliterate_damages_dummy_not_caster(self):
        sim, player, dummy = _carnage_sim()
        player.resource.current = player.resource.max_value
        obliterate = _ability("sith_warrior/skill/rage/obliterate.json")
        player_hp, dummy_hp = player.hp, dummy.hp
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(obliterate.cast(player, dummy, sim))
            sim.run_until(1.0)
        self.assertEqual(player.hp, player_hp)
        self.assertLess(dummy.hp, dummy_hp)
        self.assertTrue(player.in_combat)


class RetaliationBuffTargetTests(unittest.TestCase):
    """#9: Cloak of Pain / Rebuke are tagged aggressive but are self buffs that retaliate on damage taken."""

    def test_cloak_of_pain_lands_on_the_player(self):
        sim, player, dummy = _carnage_sim()
        cop = player.ability_db["abl.sith_warrior.cloak_of_pain"]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(cop.cast(player, dummy, sim))
            sim.run_until(0.1)
        self.assertTrue([k for k in player.effects if "cloak_of_pain:1" in k])
        self.assertFalse([k for k in dummy.effects if "cloak_of_pain:1" in k])

    def test_damaging_the_dummy_does_not_trigger_cloak_retaliation(self):
        sim, player, dummy = _carnage_sim()
        cop = player.ability_db["abl.sith_warrior.cloak_of_pain"]
        with contextlib.redirect_stdout(io.StringIO()):
            cop.cast(player, dummy, sim)
            sim.run_until(0.1)
            hp = player.hp
            sim.triggers.dispatch(
                "on_damage_taken",
                sim,
                {"caster": player, "target": dummy, "ability_spec": "x", "damage_type": 2, "tags": set()},
            )
        self.assertEqual(player.hp, hp)


if __name__ == "__main__":
    unittest.main()
