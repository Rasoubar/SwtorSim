"""Explicit ability targeting: the extractor emits ablTargetRule as target_rule and Ability.targets_enemy / is_aggressive honor it."""

import contextlib
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

SWTORSIM_ROOT = Path(__file__).resolve().parents[1]
if str(SWTORSIM_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(SWTORSIM_ROOT / "src"))

import src.swtorsim.config_load as cl
import src.swtorsim.run_config as rc
import src.swtorsim.setup as su
from extractor import abilities as extractor_abilities
from src.swtorsim.abilities import Ability, AbilityBlueprint

ABL = SWTORSIM_ROOT / "data" / "extractor" / "live" / "parsed" / "abl"


def _record(**fields):
    return SimpleNamespace(resolved_fields=[{"name": k, "value": v} for k, v in fields.items()])


def _ability(rel, rule="__keep__"):
    bp = AbilityBlueprint.from_file(ABL / rel)
    if rule != "__keep__":
        bp.target_rule = rule
    return Ability(bp)


class ExtractorTargetRuleTests(unittest.TestCase):
    def test_rules_are_snake_cased_without_prefix(self):
        cases = {
            "tgtRuleAttackable": "attackable",
            "tgtRuleFriendly": "friendly",
            "tgtRuleGroundSelf": "ground_self",
            "tgtRuleFriendlyDead": "friendly_dead",
            "tgtRuleCoverObject": "cover_object",
            "tgtRuleAny": "any",
        }
        for raw, expected in cases.items():
            self.assertEqual(extractor_abilities._target_rule(_record(ablTargetRule=raw)), expected)

    def test_missing_field_means_self_cast(self):
        self.assertEqual(extractor_abilities._target_rule(_record(ablCooldownTime=60.0)), "self")


class BlueprintTargetRuleTests(unittest.TestCase):
    def test_from_dict_reads_target_rule_and_range(self):
        bp = AbilityBlueprint.from_dict({"fqn": "abl.x", "type": "active", "target_rule": "attackable", "max_range": 3.0})
        self.assertEqual((bp.target_rule, bp.max_range), ("attackable", 3.0))

    def test_older_data_has_no_target_rule(self):
        bp = AbilityBlueprint.from_dict({"fqn": "abl.x", "type": "active"})
        self.assertIsNone(bp.target_rule)


class TargetsEnemyTests(unittest.TestCase):
    """targets_enemy decides who the cast is aimed at; is_aggressive decides combat entry and stealth break."""

    def test_attackable_targets_enemy_even_without_tags_or_damage(self):
        enrage = _ability("sith_warrior/enrage.json", "attackable")
        self.assertTrue(enrage.targets_enemy)
        self.assertTrue(enrage.is_aggressive)

    def test_self_rule_beats_aggressive_tag_and_damage_for_targeting(self):
        cloak = _ability("sith_warrior/cloak_of_pain.json")
        self.assertIn("tag.abl.utility.aggressive_action", cloak.tags)
        cloak.blueprint.target_rule = "self"
        self.assertFalse(cloak.targets_enemy)
        self.assertFalse(_ability("sith_warrior/skill/rage/obliterate.json", "self").targets_enemy)

    def test_friendly_rule_does_not_target_enemy(self):
        self.assertFalse(_ability("sith_warrior/skill/rage/obliterate.json", "friendly").targets_enemy)

    def test_ground_and_any_fall_back_to_tags_and_damage(self):
        self.assertTrue(_ability("sith_warrior/skill/rage/obliterate.json", "ground").targets_enemy)
        self.assertFalse(_ability("sith_warrior/enrage.json", "any").targets_enemy)

    def test_no_rule_falls_back_to_tags_and_damage(self):
        self.assertTrue(_ability("sith_warrior/skill/rage/obliterate.json", None).targets_enemy)
        self.assertFalse(_ability("sith_warrior/enrage.json", None).targets_enemy)
        self.assertTrue(_ability("sith_warrior/skill/rage/obliterate.json", None).is_aggressive)

    def test_self_centered_damaging_aoe_is_still_a_hostile_action(self):
        sweep = _ability("sith_warrior/sweeping_slash.json", "self")
        self.assertFalse(sweep.targets_enemy)
        self.assertTrue(sweep.is_aggressive)

    def test_non_damaging_self_buff_is_not_aggressive(self):
        self.assertFalse(_ability("sith_warrior/enrage.json", "self").is_aggressive)


class SelfCenteredAoeCastTests(unittest.TestCase):
    """A rule=self AoE must still damage the enemy and put the caster in combat."""

    def test_sweeping_slash_with_self_rule_damages_dummy_and_enters_combat(self):
        with contextlib.redirect_stdout(io.StringIO()):
            cfg = rc.load_run_config(str(SWTORSIM_ROOT / "data/run_config/Carnage.json"))
            _rot, stats, bps, debuffs = cl.load_from_run_config(cfg)
            sim, player, dummy = su.prepare_simulation([], stats, bps, 1000000, debuffs, seed=1)
        sweep = _ability("sith_warrior/sweeping_slash.json", "self")
        player.ability_db[sweep.fqn] = sweep
        player.resource.current = player.resource.max_value
        hp = dummy.hp
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(sweep.cast(player, dummy, sim))
            sim.run_until(1.0)
        self.assertLess(dummy.hp, hp)
        self.assertTrue(player.in_combat)


if __name__ == "__main__":
    unittest.main()
