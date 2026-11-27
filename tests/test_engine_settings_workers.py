"""Engine toggles must reach spawned Monte Carlo workers (CLI Tester path)."""

import multiprocessing
import unittest

from src.swtorsim import settings
from src.swtorsim.tester import Tester


def _worker_probe(snapshot):
    settings.apply_engine_settings(snapshot)
    return (
        settings.is_projectile_flight_time_enabled(),
        settings.get_default_combat_distance(),
        settings.is_in_flashpoint_operation(),
        settings.get_data_environment(),
    )


class EngineSettingsWorkerTests(unittest.TestCase):
    def setUp(self):
        self._saved = settings.snapshot_engine_settings()
        self.addCleanup(settings.apply_engine_settings, self._saved)

    def test_tester_snapshots_parent_toggles(self):
        settings.set_projectile_flight_time(True)
        settings.set_default_combat_distance(12.5)
        settings.set_in_flashpoint_operation(False)
        tester = Tester({}, {}, {}, 10, 1000, None, enable_stem_matching=True)
        snap = tester.engine_settings
        self.assertTrue(snap["enable_projectile_flight_time"])
        self.assertEqual(snap["combat_distance"], 12.5)
        self.assertFalse(snap["in_flashpoint_operation"])
        self.assertTrue(snap["enable_stem_matching"])

    def test_spawned_worker_receives_toggles(self):
        settings.set_projectile_flight_time(True)
        settings.set_default_combat_distance(12.5)
        settings.set_in_flashpoint_operation(False)
        snap = settings.snapshot_engine_settings()
        ctx = multiprocessing.get_context("spawn")
        with ctx.Pool(1) as pool:
            result = pool.apply(_worker_probe, (snap,))
        self.assertEqual(result, (True, 12.5, False, snap["environment"]))


if __name__ == "__main__":
    unittest.main()
