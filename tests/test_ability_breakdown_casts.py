"""Ability breakdown carries cast counts and damage per cast (TEST, BATCH and execute phase)."""

import contextlib
import io
import os
import unittest

from data import rotation_builder
from src.swtorsim.metrics import Metrics
from src.swtorsim.web_gui import _format_ability_breakdown_rows


class _FakeTarget:
    def __init__(self, hp_ratio):
        self.hp_ratio = hp_ratio


class FormatRowsCastTests(unittest.TestCase):
    BREAKDOWN = {
        "Ravage": {"total_damage": 1000.0, "hit_count": 8, "crit_count": 2, "attack_types": set(), "damage_types": set()},
        "Bleed": {"total_damage": 300.0, "hit_count": 6, "crit_count": 0, "attack_types": set(), "damage_types": set()},
    }

    def test_single_run_casts_and_damage_per_cast(self):
        rows = {r["name"]: r for r in _format_ability_breakdown_rows(
            self.BREAKDOWN, 10.0, 1300.0, iterations=1, cast_counts={"Ravage": 4},
        )}
        self.assertEqual(rows["Ravage"]["casts"], 4)
        self.assertEqual(rows["Ravage"]["dmg_per_cast"], 250.0)
        self.assertEqual(rows["Ravage"]["hits"], 8)

    def test_uncast_damage_rows_have_no_casts(self):
        rows = {r["name"]: r for r in _format_ability_breakdown_rows(
            self.BREAKDOWN, 10.0, 1300.0, iterations=1, cast_counts={"Ravage": 4},
        )}
        self.assertIsNone(rows["Bleed"]["casts"])
        self.assertIsNone(rows["Bleed"]["dmg_per_cast"])

    def test_batch_casts_are_averaged_but_damage_per_cast_is_not_scaled(self):
        # 3 iterations: summed 9 casts -> 3.0 avg casts; 1000 total damage / 9 casts
        rows = {r["name"]: r for r in _format_ability_breakdown_rows(
            self.BREAKDOWN, 30.0, 1300.0, iterations=3, cast_counts={"Ravage": 9},
        )}
        self.assertEqual(rows["Ravage"]["casts"], 3.0)
        self.assertAlmostEqual(rows["Ravage"]["dmg_per_cast"], round(1000.0 / 9, 0))

    def test_no_cast_counts_argument_leaves_rows_without_casts(self):
        rows = _format_ability_breakdown_rows(self.BREAKDOWN, 10.0, 1300.0)
        self.assertTrue(all(r["casts"] is None and r["dmg_per_cast"] is None for r in rows))


class MetricsLogCastTests(unittest.TestCase):
    def test_execute_split_uses_target_hp_at_cast_time(self):
        m = Metrics()
        m.log_cast("Ravage", _FakeTarget(0.80))
        m.log_cast("Ravage", _FakeTarget(0.30))
        m.log_cast("Ravage", _FakeTarget(0.10))
        m.log_cast("Smash", None)
        self.assertEqual(m.cast_counts, {"Ravage": 3, "Smash": 1})
        self.assertEqual(m.execute_cast_counts, {"Ravage": 2})


class BreakdownCastIntegrationTests(unittest.TestCase):
    """Real simulator runs on the sniper test config (short fight)."""

    @classmethod
    def setUpClass(cls):
        from src.swtorsim import web_gui
        from src.swtorsim.config_load import load_from_run_config
        from src.swtorsim.run_config import load_run_config

        root = rotation_builder.SWTORSIM_ROOT
        prev = os.getcwd()
        os.chdir(root)
        try:
            cfg = load_run_config(str(root / "data/run_config/Marksmanship.json"))
            cfg.duration = 20
            inputs = load_from_run_config(cfg)
            sim_inputs = {
                "rotation_config": inputs.rotation_config,
                "stats_config": inputs.stats_config,
                "loadout_blueprints": inputs.loadout_blueprints,
                "debuff_module": inputs.debuff_module,
            }
            with contextlib.redirect_stdout(io.StringIO()):
                cls.test_result = web_gui._run_single_test_detailed(cfg, sim_inputs)

            settings_dict = {
                "enable_stem_matching": cfg.enable_stem_matching,
                "enable_projectile_flight_time": cfg.enable_projectile_flight_time,
                "combat_distance": cfg.combat_distance,
                "in_flashpoint_operation": cfg.in_flashpoint_operation,
            }
            prev_ctx = getattr(web_gui, "_WORKER_SIM_CONTEXT", None)
            web_gui._WORKER_SIM_CONTEXT = {**sim_inputs, "settings_dict": settings_dict}
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    cls.harvested = [
                        web_gui._batch_worker_task((i, cfg.seed, cfg.duration, cfg.dummy_hp))
                        for i in range(2)
                    ]
            finally:
                web_gui._WORKER_SIM_CONTEXT = prev_ctx
            cls.batch_result = web_gui._aggregate_batch_results(cls.harvested, cfg, 0.0, 2, {})
        finally:
            os.chdir(prev)

    def test_test_mode_casts_match_cast_events_in_combat_log(self):
        log_casts = {}
        for ev in self.test_result["combat_log"]:
            if ev["category"] == "cast":
                log_casts[ev["ability"]] = log_casts.get(ev["ability"], 0) + 1
        cast_rows = [r for r in self.test_result["breakdown"] if r["casts"] is not None]
        self.assertTrue(cast_rows)
        for r in cast_rows:
            self.assertEqual(r["casts"], log_casts[r["name"]], r["name"])
            self.assertAlmostEqual(r["dmg_per_cast"], round(r["total_damage"] / r["casts"], 0), delta=1.0)

    def test_test_mode_keeps_min_max_hit(self):
        self.assertTrue(all("min_hit" in r and "max_hit" in r for r in self.test_result["breakdown"]))

    def test_batch_casts_are_per_iteration_averages(self):
        summed = {}
        for h in self.harvested:
            for name, n in h["cast_counts"].items():
                summed[name] = summed.get(name, 0) + n
        cast_rows = [r for r in self.batch_result["breakdown"] if r["casts"] is not None]
        self.assertTrue(cast_rows)
        for r in cast_rows:
            self.assertAlmostEqual(r["casts"], summed[r["name"]] / 2, delta=0.06)

    def test_execute_casts_never_exceed_full_fight_casts(self):
        full = {r["name"]: r["casts"] for r in self.batch_result["breakdown"] if r["casts"] is not None}
        for r in self.batch_result["execute_breakdown"]:
            if r["casts"] is not None:
                self.assertLessEqual(r["casts"], full[r["name"]] + 0.06, r["name"])


if __name__ == "__main__":
    unittest.main()
