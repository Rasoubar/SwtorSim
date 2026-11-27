"""State snapshot (read-only), damage checks and the rotation / raw-time additions of the debugger API."""

import random
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.swtorsim.debug import debug_api, inspect_state
from src.swtorsim.debug.damage_check import (
    DamageMeasurement,
    ParallelDamageTrials,
    measure_damage,
    run_damage_trial,
)
from src.swtorsim.debug.proc_measure import make_sim_builder

CONFIG = Path(__file__).resolve().parents[1] / "data" / "run_config" / "Hatred.json"
needs_hatred = unittest.skipUnless(CONFIG.is_file(), "Hatred run config not present")


@needs_hatred
class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_sim, _seed, _duration = make_sim_builder(str(CONFIG))
        cls.build_sim = staticmethod(build_sim)
        cls.sim = build_sim()
        cls.sim.run_until(60.0)
        cls.snap = inspect_state.snapshot(cls.sim, 60.0)

    def test_shape(self):
        snap = self.snap
        for key in ("at", "gcd_remaining", "resource", "abilities", "effects", "icds", "stats", "target"):
            self.assertIn(key, snap)
        self.assertGreaterEqual(snap["gcd_remaining"], 0.0)
        self.assertGreater(snap["resource"]["max"], 0)

    def test_each_ability_is_listed_once(self):
        names = [a["name"] for a in self.snap["abilities"]]
        self.assertEqual(len(names), len(set(names)))

    def test_charge_based_abilities_are_ready_by_charges(self):
        charged = [a for a in self.snap["abilities"] if a["max_charges"]]
        self.assertTrue(charged)
        for ability in charged:
            self.assertEqual(ability["ready"], ability["charges"] >= 1, ability)
            if ability["charges"] < ability["max_charges"]:
                self.assertIsNotNone(ability["recharge_in"])

    def test_effects_report_remaining_time_or_permanent(self):
        effects = self.snap["effects"]
        self.assertTrue(effects)
        for eff in effects:
            if eff["permanent"]:
                self.assertIsNone(eff["remaining"])
            else:
                self.assertGreaterEqual(eff["remaining"], 0.0)
        self.assertTrue(any(e["entity"] == "Target" for e in effects))

    def test_running_icds_have_time_left(self):
        for icd in self.snap["icds"]:
            self.assertGreater(icd["remaining"], 0.0)

    def test_taking_a_snapshot_changes_nothing(self):
        """Read-only: same clock, queue and random state before and after, and the fight then plays out identically."""
        def finish(take_snapshot):
            sim = self.build_sim()
            sim.run_until(60.0)
            before = (sim.current_time, len(sim.queue), random.getstate())
            if take_snapshot:
                inspect_state.snapshot(sim, 60.0)
            self.assertEqual((sim.current_time, len(sim.queue), random.getstate()), before)
            sim.run_until(120.0)
            return sim.tracker.total_damage

        self.assertEqual(finish(True), finish(False))


class DamageAggregationTests(unittest.TestCase):
    """measure_damage with scripted hits: the crit tally, ranges and verdicts."""

    def _run(self, hits_per_trial, reference, trials=10):
        def run_batch(first, count):
            return [list(hits_per_trial) for _ in range(count)]

        return measure_damage(None, "Thrash", 5.0, trials=trials, run_batch=run_batch, reference=reference)

    def test_tally_ranges_and_ratio(self):
        hits = [{"damage": 100, "crit": False, "bonus_crit": 0.1}, {"damage": 160, "crit": True, "bonus_crit": 0.1}]
        result = self._run(hits, {"crit_chance": 0.4, "crit_modifier": 0.6})
        self.assertEqual((result.trials, result.hits, result.crits), (10, 20, 10))
        data = result.to_dict()
        self.assertEqual(data["normal"], {"n": 10, "min": 100, "mean": 100.0, "max": 100})
        self.assertAlmostEqual(data["crit_ratio"], 1.6)
        self.assertAlmostEqual(data["expected_crit"], 0.5)  # stat 40% + the hit's own 10%
        self.assertEqual(data["verdict"], "consistent")      # observed 50%

    def test_a_crit_rate_far_from_the_stats_is_reported_as_differing(self):
        hits = [{"damage": 100, "crit": False, "bonus_crit": None}] * 9 + [{"damage": 160, "crit": True, "bonus_crit": None}]
        result = self._run(hits, {"crit_chance": 0.9, "crit_modifier": 0.6}, trials=40)
        self.assertEqual(result.verdict, "differs from the stats")

    def test_no_hits_and_no_reference(self):
        self.assertEqual(self._run([], {"crit_chance": 0.3, "crit_modifier": 0.5}).verdict, "no hits in the window")
        one = [{"damage": 100, "crit": False, "bonus_crit": None}]
        self.assertEqual(self._run(one, {}).verdict, "no reference")

    def test_batches_give_the_serial_result(self):
        script = {}

        def hits_for(seed):
            rng = random.Random(seed)
            return [{"damage": 100 + rng.randint(0, 9), "crit": rng.random() < 0.3, "bonus_crit": None}]

        def run_batch(first, count):
            return [hits_for(2_000_003 + i) for i in range(first, first + count)]

        serial = measure_damage(None, "A", 1.0, trials=50, run_batch=run_batch, batch_size=1, reference={})
        batched = measure_damage(None, "A", 1.0, trials=50, run_batch=run_batch, batch_size=16, reference={})
        self.assertEqual((serial.hits, serial.crits, serial.normal, serial.crit_damage),
                         (batched.hits, batched.crits, batched.normal, batched.crit_damage))


@needs_hatred
class RealFightDamageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = debug_api.handle("trace", {"config": "Hatred"})
        cls.hit = next(e for e in cls.trace["events"] if e["type"] == "damage_hit" and e["t"] > 30)

    def test_trace_carries_rotation_decisions_and_exact_raw_times(self):
        self.assertTrue(self.trace["rotation"])
        decision = self.trace["rotation"][5]
        self.assertIn("candidates", decision)
        self.assertIn("chosen", decision)
        offset = self.trace["proc"]["time_offset"]
        self.assertAlmostEqual(self.hit["raw"] - offset, self.hit["t"], places=3)
        casts = [e for e in self.trace["events"] if e["type"] == "cast_start"]
        self.assertTrue(all("raw" in c for c in casts))

    def test_every_cast_after_the_pull_has_a_matching_decision(self):
        casts = [e for e in self.trace["events"] if e["type"] == "cast_start" and e["t"] > 5]
        matched = sum(
            1 for c in casts
            if any(d["chosen"] == c["ability"] and abs(d["t"] - c["t"]) < 0.02 for d in self.trace["rotation"])
        )
        self.assertGreater(matched / len(casts), 0.8)

    def test_state_api_matches_the_snapshot_at_that_moment(self):
        state = debug_api.handle("state", {"config": "Hatred", "at": self.hit["raw"]})
        self.assertAlmostEqual(state["at"], self.hit["raw"], places=5)
        self.assertTrue(state["abilities"])

    def test_damage_trials_replay_the_same_hit(self):
        result = debug_api.handle("damage", {
            "config": "Hatred", "ability": self.hit["ability"], "anchor": self.hit["raw"], "trials": 12, "workers": 1,
        })
        self.assertEqual(result["trials"], 12)
        self.assertGreaterEqual(result["hits"], 12)
        self.assertLessEqual(result["crits"], result["hits"])
        normal = result["normal"]
        if normal:
            self.assertLessEqual(normal["min"], normal["mean"])
            self.assertLessEqual(normal["mean"], normal["max"])
        self.assertIn("crit_chance", result["reference"])

    def test_the_traced_hit_is_reproduced_by_its_replay_seed(self):
        """Trial seeds differ from the trace's, but every replay must still contain this ability's hit at the anchor."""
        build_sim, _seed, _duration = make_sim_builder(str(CONFIG), with_tracer=True)
        hits = run_damage_trial(build_sim, self.hit["ability"], self.hit["raw"], 0.0, 2_000_003)
        self.assertTrue(hits)

    def test_worker_processes_give_the_serial_damage_result(self):
        build_sim, _seed, _duration = make_sim_builder(str(CONFIG), with_tracer=True)
        serial = measure_damage(build_sim, self.hit["ability"], self.hit["raw"], trials=8)
        with ParallelDamageTrials(str(CONFIG), "live", None, self.hit["ability"], self.hit["raw"], 0.0, workers=2) as pool:
            parallel = measure_damage(None, self.hit["ability"], self.hit["raw"], trials=8, run_batch=pool.run_batch,
                                      batch_size=pool.batch_size, reference=serial.reference)
        self.assertEqual((serial.hits, serial.crits, serial.normal, serial.crit_damage),
                         (parallel.hits, parallel.crits, parallel.normal, parallel.crit_damage))


if __name__ == "__main__":
    unittest.main()
