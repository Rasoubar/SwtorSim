"""gcd_stall run-config option: a fraction of GCDs is lengthened by 0.1s to mimic lag."""

import json
import os
import random
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.run_config import load_run_config
from src.swtorsim.setup import prepare_simulation
from src.swtorsim.tester import Tester

RUN_CONFIG_PATH = ROOT / "data" / "run_config" / "Hatred.json"


class GcdStallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)
        cls.config = load_run_config(str(RUN_CONFIG_PATH))
        cls.inputs = load_from_run_config(cls.config)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def _sim(self, gcd_stall):
        return prepare_simulation(
            self.inputs.rotation_config,
            self.inputs.stats_config,
            self.inputs.loadout_blueprints,
            self.config.dummy_hp,
            self.inputs.debuff_module,
            verbose=False,
            seed=1,
            gcd_stall=gcd_stall,
        )

    def _gcd_after_lock(self, sim, player, ability):
        sim.current_time = 0.0
        player.next_gcd = 0.0
        ability.apply_cooldown_locks(player, sim)
        return player.next_gcd

    def _gcd_ability(self, player):
        return next(a for a in player.ability_db.values() if a.triggers_gcd and not a.has_charges and a.cooldown == 0.0)

    def test_default_is_zero_and_consumes_no_rng(self):
        # A run config without the key defaults to 0 (the shipped configs may set their own value).
        raw = json.loads(RUN_CONFIG_PATH.read_text(encoding="utf-8"))
        raw.pop("gcd_stall", None)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cfg.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            self.assertEqual(load_run_config(str(path)).gcd_stall, 0.0)
        sim, player, _ = self._sim(0.0)
        self.assertEqual(player.gcd_stall, 0.0)
        abl = self._gcd_ability(player)
        random.seed(99)
        expected_next_draw = random.random()
        random.seed(99)
        self._gcd_after_lock(sim, player, abl)
        self.assertEqual(random.random(), expected_next_draw)

    def test_full_stall_adds_a_tenth_of_a_second(self):
        sim0, player0, _ = self._sim(0.0)
        sim1, player1, _ = self._sim(1.0)
        base = self._gcd_after_lock(sim0, player0, self._gcd_ability(player0))
        stalled = self._gcd_after_lock(sim1, player1, self._gcd_ability(player1))
        self.assertAlmostEqual(stalled - base, 0.1, places=4)

    def test_fraction_of_gcds_stalled_matches_chance(self):
        sim, player, _ = self._sim(0.3)
        abl = self._gcd_ability(player)
        base_sim, base_player, _ = self._sim(0.0)
        base = self._gcd_after_lock(base_sim, base_player, self._gcd_ability(base_player))
        random.seed(7)
        n = 4000
        stalled = sum(1 for _ in range(n) if self._gcd_after_lock(sim, player, abl) > base + 0.05)
        self.assertAlmostEqual(stalled / n, 0.3, delta=0.03)

    def test_config_parses_and_validates(self):
        raw = json.loads(RUN_CONFIG_PATH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            for value, ok in ((0.3, True), (0, True), (1, True), (-0.1, False), (1.5, False), ("x", False)):
                raw["gcd_stall"] = value
                path = Path(tmp) / "cfg.json"
                path.write_text(json.dumps(raw), encoding="utf-8")
                if ok:
                    self.assertEqual(load_run_config(str(path)).gcd_stall, float(value))
                else:
                    with self.assertRaises(ValueError, msg=repr(value)):
                        load_run_config(str(path))

    def test_tester_forwards_value_to_workers(self):
        tester = Tester({}, {}, {}, 10, 1000, None, gcd_stall=0.25)
        self.assertEqual(tester.engine_settings["gcd_stall"], 0.25)


if __name__ == "__main__":
    unittest.main()
