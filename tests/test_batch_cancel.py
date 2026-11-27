"""Tests for cancelling an in-flight Monte Carlo batch (native web_gui backend)."""

import threading
import time
import types
import unittest
from unittest import mock

from src.swtorsim import web_gui


def _slow_worker(args):
    """Module-level so the multiprocessing pool can pickle it."""
    time.sleep(0.05)
    return {"run_id": int(args[0]) + 1}


def _config(iterations):
    return types.SimpleNamespace(
        iterations=iterations, dummy_hp=1, seed=1, duration=1,
        enable_stem_matching=True, enable_projectile_flight_time=True,
        combat_distance=5.0, in_flashpoint_operation=False,
        stats_path="s", rotation_path="r", training_dummy_armor_debuff=False,
    )


def _inputs():
    return {
        "rotation_config": [], "stats_config": {"stats": {}},
        "loadout_blueprints": {}, "debuff_module": None, "selected_fqns": (),
    }


class BatchCancelTests(unittest.TestCase):
    def setUp(self):
        web_gui._SIM_CANCEL.clear()
        patches = [
            mock.patch.object(web_gui, "prepare_simulation", return_value=(None, None, None)),
            mock.patch.object(web_gui, "_extract_computed_player_stats", return_value={}),
            mock.patch.object(web_gui, "_aggregate_batch_results", side_effect=lambda h, *a, **k: {"n": len(h)}),
            mock.patch.object(web_gui, "_batch_worker_task", _slow_worker),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(web_gui.cleanup_simulation_pool)
        self.addCleanup(web_gui._SIM_CANCEL.clear)

    def test_uncancelled_sequential_batch_completes(self):
        fake_sys = types.SimpleNamespace(platform="emscripten")
        with mock.patch.object(web_gui, "sys", fake_sys):
            result = web_gui._run_batch_monte_carlo_detailed(_config(3), _inputs())
        self.assertEqual(result, {"n": 3})

    def test_cancel_stops_sequential_batch(self):
        fake_sys = types.SimpleNamespace(platform="emscripten")
        calls = []

        def worker(args):
            calls.append(args[0])
            if len(calls) == 2:
                web_gui.request_simulation_cancel()
            return {"run_id": args[0] + 1}

        with mock.patch.object(web_gui, "sys", fake_sys), mock.patch.object(web_gui, "_batch_worker_task", worker):
            with self.assertRaises(web_gui.SimulationCancelled):
                web_gui._run_batch_monte_carlo_detailed(_config(50), _inputs())
        self.assertEqual(len(calls), 2, "No further runs may start after cancel")
        self.assertFalse(web_gui.get_simulation_progress()["running"])

    def test_cancel_terminates_parallel_pool(self):
        threading.Timer(1.0, web_gui.request_simulation_cancel).start()
        t0 = time.perf_counter()
        with self.assertRaises(web_gui.SimulationCancelled):
            web_gui._run_batch_monte_carlo_detailed(_config(100000), _inputs())
        self.assertLess(time.perf_counter() - t0, 30.0)
        self.assertIsNone(web_gui._GLOBAL_SIMULATION_POOL, "Cancel must tear down the worker pool")
        self.assertFalse(web_gui.get_simulation_progress()["running"])

    def test_next_batch_clears_stale_cancel(self):
        web_gui.request_simulation_cancel()
        fake_sys = types.SimpleNamespace(platform="emscripten")
        with mock.patch.object(web_gui, "sys", fake_sys):
            result = web_gui._run_batch_monte_carlo_detailed(_config(2), _inputs())
        self.assertEqual(result, {"n": 2})


if __name__ == "__main__":
    unittest.main()
