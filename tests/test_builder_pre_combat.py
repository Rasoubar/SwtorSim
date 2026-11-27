"""Tests for pre-combat / tactical-swap support in the rotation builder backend."""

import os
from pathlib import Path
import unittest

from data.rotation_builder import (
    build_rotation_file_data,
    class_tactical_fqns,
    normalize_pre_combat_steps,
    normalize_rotation_steps,
    run_dry_run_preview,
)
from src.swtorsim.run_config import load_run_config

ROOT = Path(__file__).resolve().parents[1]
RUN_CONFIG_PATH = ROOT / "data" / "run_config" / "Hatred.json"
# Must differ from the run config's own tactical (Hatred.json starts on the generic damage tactical).
NEW_TACTICAL = "abl.itm.tactical.sow.inq_con.sin_shad.hat_sen.dmg_sust_01"
ROTATION = [{"type": "fixed", "ability_id": "thrash"}]


class BuilderPreCombatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def test_bare_array_when_no_pre_combat(self):
        self.assertEqual(build_rotation_file_data(ROTATION, []), ROTATION)
        self.assertEqual(build_rotation_file_data(ROTATION, None), ROTATION)

    def test_wrapper_round_trip(self):
        pre = [
            {"ability": "stealth"},
            {"swap_tactical": NEW_TACTICAL},
        ]
        data = build_rotation_file_data(ROTATION, pre)
        self.assertEqual(data, {"pre_combat": pre, "sequence": ROTATION})
        steps, _warnings = normalize_rotation_steps(data)
        self.assertEqual(steps, ROTATION)
        self.assertEqual(normalize_pre_combat_steps(data), pre)

    def test_legacy_keep_timed_effects_key_is_dropped(self):
        for legacy in (True, False):
            data = {"pre_combat": [{"swap_tactical": NEW_TACTICAL, "keep_timed_effects": legacy}], "sequence": ROTATION}
            self.assertEqual(normalize_pre_combat_steps(data), [{"swap_tactical": NEW_TACTICAL}])

    def test_bare_array_has_no_pre_combat(self):
        self.assertEqual(normalize_pre_combat_steps(ROTATION), [])

    @unittest.skipUnless(RUN_CONFIG_PATH.exists(), "Hatred run config not available")
    def test_preview_logs_swap_and_rejects_foreign_tactical(self):
        cfg = load_run_config(str(RUN_CONFIG_PATH))
        self.assertIn(NEW_TACTICAL, class_tactical_fqns("assassin"))
        payload = {
            "spec_path": cfg.spec_path,
            "choices": cfg.choices,
            "tactical_fqn": cfg.tactical_fqn,
            "legendary_fqns": cfg.legendary_fqns,
            "relic_fqns": cfg.relic_fqns,
            "rotation": ROTATION,
            "pre_combat": [{"swap_tactical": NEW_TACTICAL}],
            "duration": 5.0,
        }
        result = run_dry_run_preview(payload)
        self.assertEqual(len(result["tactical_swaps"]), 1)
        self.assertEqual(result["tactical_swaps"][0]["to"], NEW_TACTICAL)
        self.assertEqual(result["tactical_swaps"][0]["from"], cfg.tactical_fqn)
        self.assertGreater(len(result["casts"]), 0)

        bad = dict(payload, pre_combat=[{"swap_tactical": "abl.itm.tactical.sow.sol_tro.not_my_class"}])
        with self.assertRaises(ValueError):
            run_dry_run_preview(bad)


class BuilderPullGateTests(unittest.TestCase):
    PULL = {"caster_energy_above": 50}

    def test_wait_until_step_round_trip(self):
        pre = [{"wait_until": {"caster_has_buff": "Recklessness"}, "max_wait": 10.0}]
        from data.rotation_builder import normalize_pre_combat_steps as norm
        self.assertEqual(norm({"pre_combat": pre, "sequence": ROTATION}), pre)

    def test_pull_gate_only_wrapper(self):
        from data.rotation_builder import normalize_pull_gate
        data = build_rotation_file_data(ROTATION, [], self.PULL, 20)
        self.assertEqual(data, {"pull_conditions": self.PULL, "pull_max_wait": 20.0, "sequence": ROTATION})
        self.assertEqual(normalize_pull_gate(data), {"pull_conditions": self.PULL, "pull_max_wait": 20.0})
        self.assertEqual(normalize_pull_gate(ROTATION), {})

    def test_empty_pull_gate_keeps_bare_array(self):
        self.assertEqual(build_rotation_file_data(ROTATION, [], {}, 60), ROTATION)

    @unittest.skipUnless(RUN_CONFIG_PATH.exists(), "Hatred run config not available")
    def test_preview_reports_pull_gate_and_failure(self):
        cfg = load_run_config(str(RUN_CONFIG_PATH))
        payload = {
            "spec_path": cfg.spec_path,
            "choices": cfg.choices,
            "tactical_fqn": cfg.tactical_fqn,
            "legendary_fqns": cfg.legendary_fqns,
            "relic_fqns": cfg.relic_fqns,
            "rotation": ROTATION,
            "pre_combat": ["force_speed"],
            "pull_conditions": {"ability_cooldown_under": {"name": "Force Speed", "value": 0.05}},
            "duration": 5.0,
        }
        result = run_dry_run_preview(payload)
        self.assertGreater(result["pull_gate_wait"], 10.0)
        self.assertGreater(result["pre_combat_duration"], 10.0)

        from src.swtorsim.events import PullConditionsNotMetError
        bad = dict(payload, pull_conditions={"caster_has_buff": "No Such Buff"}, pull_max_wait=1.0)
        with self.assertRaises(PullConditionsNotMetError):
            run_dry_run_preview(bad)


if __name__ == "__main__":
    unittest.main()
