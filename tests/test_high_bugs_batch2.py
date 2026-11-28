"""Regression tests for bug-hunt High #4-#6 (rule alias keys, PTS run config class/spec, actor_4 conditions)."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.swtorsim import rotation_builder as rb
from src.swtorsim import pyodide_bridge
from src.swtorsim.abilities import AbilityBlueprint
from src.swtorsim.entities import Dummy, Player
from src.swtorsim.requirements import CONDITION_REGISTRY, evaluate_single_extracted_condition

ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class RuleKeySingleNameTests(unittest.TestCase):
    """#4: every engine rule key is in the editor catalog, so the editor never has to guess a key."""

    def test_engine_registry_matches_editor_catalog(self):
        self.assertEqual(set(CONDITION_REGISTRY), {c["key"] for c in rb.CONDITION_METADATA})

    def test_known_rule_keys_match_catalog(self):
        self.assertEqual(rb.KNOWN_RULE_KEYS, {c["key"] for c in rb.CONDITION_METADATA})

    def test_no_two_keys_share_a_check_function(self):
        funcs = list(CONDITION_REGISTRY.values())
        self.assertEqual(len(funcs), len({id(f) for f in funcs}))


class UnknownRuleKeyEditorTests(unittest.TestCase):
    """#4: editing a rule whose key is not in the catalog must not silently pick a replacement type."""

    def test_uis_never_fall_back_to_a_guessed_key(self):
        for page in ("tools/rotation_builder_ui.html", "tools/rotation_map_ui.html"):
            html = _read(page)
            self.assertNotIn(': "caster_buff_stacks"', html, page)
            self.assertIn("-- Unknown rule", html, page)

    def test_builder_requires_a_type_before_saving(self):
        html = _read("tools/rotation_builder_ui.html")
        start = html.index("function commitRuleFromModal")
        self.assertIn('if (!key) return showToast("Pick a rule type first.", true);', html[start : start + 500])

    def test_map_disables_save_for_unselected_type(self):
        html = _read("tools/rotation_map_ui.html")
        start = html.index("function renderRuleFields")
        body = html[start : start + 900]
        self.assertIn("if (!key) {", body)
        self.assertIn('getElementById("rpSave").disabled = true', body)


class BuilderRunConfigClassSpecTests(unittest.TestCase):
    """#5: run configs carry only spec_path; the builder needs class, spec and environment resolved."""

    def test_pts_config_resolves_class_spec_and_environment(self):
        bundle = rb.load_builder_run_config("data/run_config/Dirty Fighting.json")
        self.assertEqual(bundle["environment"], "pts")
        self.assertEqual(bundle["class_name"], "Gunslinger")
        self.assertEqual(bundle["spec_name"], "Dirty Fighting")

    def test_live_config_resolves_live_environment(self):
        bundle = rb.load_builder_run_config("data/run_config/Carnage.json")
        self.assertEqual(bundle["environment"], "live")
        self.assertEqual(bundle["class_name"], "Marauder")

    def test_missing_config_raises(self):
        with self.assertRaises(FileNotFoundError):
            rb.load_builder_run_config("data/run_config/does_not_exist.json")

    def test_pyodide_bridge_returns_same_bundle(self):
        out = json.loads(pyodide_bridge.dispatch("LOAD_BUILDER_RUN_CONFIG", json.dumps({"path": "data/run_config/Dirty Fighting.json"})))
        self.assertEqual(out["environment"], "pts")
        self.assertEqual(out["spec_name"], "Dirty Fighting")

    def test_builder_ui_switches_environment_before_matching(self):
        html = _read("tools/rotation_builder_ui.html")
        start = html.index("async function onSelectRunConfig")
        body = html[start : start + 1500]
        self.assertLess(body.index("setEnvironment(data.environment)"), body.index("workspaceCatalog.disciplines"))


class Actor4ConditionTests(unittest.TestCase):
    """#6: GOM actor_4 is the enemy, even when the branch redirects `target` to the caster."""

    @classmethod
    def setUpClass(cls):
        bp = AbilityBlueprint.from_file(ROOT / "data/extractor/live/parsed/abl/itm/tactical/sow/war_kni/mar_sen/ani_watch/dmg_aoe_01.json")
        cls.cond = bp.effects[2].conditions["list"][0]

    def _entities(self, enemy_hp):
        caster = Player("Mara")
        caster.hp = caster.max_hp = 1000
        dummy = Dummy("D", 1000)
        dummy.hp = enemy_hp
        return caster, dummy

    def test_condition_is_actor_4_health_below_30(self):
        self.assertEqual((self.cond["actor"], self.cond["type"], self.cond["comparison"]), ("actor_4", "if_health", "lt"))

    def test_low_hp_enemy_passes_and_healthy_enemy_fails(self):
        caster, dummy = self._entities(100)
        self.assertTrue(evaluate_single_extracted_condition(self.cond, caster, dummy))
        dummy.hp = 900
        self.assertFalse(evaluate_single_extracted_condition(self.cond, caster, dummy))

    def test_target_redirected_to_caster_falls_back_to_current_target(self):
        caster, dummy = self._entities(100)
        caster.current_target = dummy
        self.assertTrue(evaluate_single_extracted_condition(self.cond, caster, caster))

    def test_context_enemy_target_wins(self):
        caster, dummy = self._entities(100)
        self.assertTrue(evaluate_single_extracted_condition(self.cond, caster, caster, context={"enemy_target": dummy}))

    def test_has_effect_checks_enemy_not_caster(self):
        caster, dummy = self._entities(1000)
        cond = {"type": "has_effect", "actor": "actor_4", "tags": ["tag.test.dot"], "count": 1}
        self.assertFalse(evaluate_single_extracted_condition(cond, caster, dummy))
        dummy.effects["dot"] = SimpleNamespace(tags=["tag.test.dot"], name="dot", stacks=1, is_expired=False)
        self.assertTrue(evaluate_single_extracted_condition(cond, caster, dummy))
        caster.current_target = dummy
        self.assertTrue(evaluate_single_extracted_condition(cond, caster, caster))


if __name__ == "__main__":
    unittest.main()
