"""Proc measurement: replay trials count rolls against the recorded chance and flag a wrong chance."""

import random
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.swtorsim.debug.proc_measure import (
    ParallelTrials,
    make_sim_builder,
    measure_proc,
    proc_key,
    run_trial,
    sweep_proc,
    summarize_proc_log,
    wilson_interval,
)

needs_real = unittest.skipUnless(
    (Path(__file__).resolve().parents[1] / "data" / "run_config" / "Hatred.json").is_file(), "Hatred run config not present"
)

_ANCHOR = 5.0
_KEY = ("abl.test.proc", "eff", 0, 0)


class _FakeSim:
    """Rolls once at t=_ANCHOR with a true pass rate; records the chance it claims to have used."""

    def __init__(self, true_chance, claimed_chance):
        random.seed(42)
        self.triggers = SimpleNamespace(proc_log=[])
        self._true = true_chance
        self._claimed = claimed_chance
        self._done = False

    def run_until(self, t):
        if not self._done and t >= _ANCHOR:
            draw = random.random() * 100.0
            self.triggers.proc_log.append({
                "t": _ANCHOR, "event": "on_damage_dealt", "source": "Test Proc", "fqn": _KEY[0],
                "effect_key": _KEY[1], "branch_index": _KEY[2], "trigger_index": _KEY[3],
                "outcome": "fired" if draw <= self._true else "roll_failed",
                "chance": self._claimed, "draw": draw,
            })
            self._done = True


class WilsonTests(unittest.TestCase):
    def test_interval_contains_the_rate_and_narrows_with_trials(self):
        lo, hi = wilson_interval(30, 100)
        self.assertLess(lo, 0.30)
        self.assertGreater(hi, 0.30)
        lo2, hi2 = wilson_interval(300, 1000)
        self.assertLess(hi2 - lo2, hi - lo)

    def test_no_trials_is_the_full_range(self):
        self.assertEqual(wilson_interval(0, 0), (0.0, 1.0))


class MeasureProcTests(unittest.TestCase):
    def _measure(self, true_chance, claimed_chance, **kw):
        return measure_proc(
            lambda: _FakeSim(true_chance, claimed_chance), _KEY, _ANCHOR, max_trials=500, **kw
        )

    def test_a_correct_chance_is_consistent(self):
        result = self._measure(30.0, 30.0)
        self.assertEqual(result.verdict, "consistent")
        self.assertAlmostEqual(result.expected, 0.30)
        self.assertAlmostEqual(result.observed, 0.30, delta=0.08)

    def test_trials_use_distinct_seeds(self):
        result = self._measure(50.0, 50.0)
        self.assertGreater(result.roll_passes, 0)
        self.assertLess(result.roll_passes, result.rolls)

    def test_a_wrong_chance_is_flagged_and_stops_early(self):
        result = self._measure(60.0, 30.0)
        self.assertEqual(result.verdict, "MISMATCH")
        self.assertEqual(result.stopped_because, "decisive mismatch")
        self.assertLess(result.trials, 500)

    def test_guaranteed_proc_that_misses_is_a_mismatch(self):
        result = self._measure(0.0, 100.0)
        self.assertEqual(result.verdict, "MISMATCH")

    def test_rolls_outside_the_window_are_not_counted(self):
        result = measure_proc(lambda: _FakeSim(30.0, 30.0), _KEY, 1.0, window=1.0, max_trials=10, min_trials=10)
        self.assertEqual(result.rolls, 0)
        self.assertIn("no evaluations", result.verdict)


class SummaryTests(unittest.TestCase):
    def test_summary_counts_outcomes_per_rule(self):
        base = {"fqn": "a", "effect_key": None, "branch_index": 0, "trigger_index": 0, "source": "A"}
        log = [
            dict(base, t=1.0, outcome="blocked_icd"),
            dict(base, t=2.0, outcome="roll_failed", chance=30.0),
            dict(base, t=3.0, outcome="fired", chance=30.0),
        ]
        (row,) = summarize_proc_log(log)
        self.assertEqual(row["outcomes"], {"blocked_icd": 1, "roll_failed": 1, "fired": 1})
        self.assertEqual(row["first_roll"], 2.0)
        self.assertEqual(row["mean_chance"], 30.0)
        self.assertEqual(proc_key(log[0]), ("a", None, 0, 0))


class RealFightMeasureTests(unittest.TestCase):
    CONFIG = Path(__file__).resolve().parents[1] / "data" / "run_config" / "Hatred.json"

    @unittest.skipUnless(CONFIG.is_file(), "Hatred run config not present")
    def test_a_real_rolled_proc_matches_its_recorded_chance(self):
        build_sim, _seed, duration = make_sim_builder(str(self.CONFIG))
        sim = build_sim()
        sim.run_until(duration)
        rows = [r for r in summarize_proc_log(sim.triggers.proc_log) if r["mean_chance"] and r["mean_chance"] < 100.0]
        self.assertTrue(rows, "expected at least one proc with a chance below 100%")
        row = rows[0]
        result = measure_proc(build_sim, row["key"], row["first_roll"], max_trials=60, min_trials=60, source=row["source"])
        self.assertGreaterEqual(result.rolls, 60)
        self.assertEqual(result.verdict, "consistent", result.describe())


class BatchRunnerTests(unittest.TestCase):
    """A batch runner (as ParallelTrials is) must give exactly the serial result, whatever the batch size."""

    @staticmethod
    def _batch_runner(true_chance, claimed_chance, seed_base=1_000_003):
        def run_batch(first, count):
            return [run_trial(lambda: _FakeSim(true_chance, claimed_chance), _KEY, _ANCHOR, 0.0, seed_base + i)
                    for i in range(first, first + count)]
        return run_batch

    def _summary(self, result):
        return (result.trials, result.rolls, result.roll_passes, result.fires, result.stopped_because)

    def test_batches_match_the_serial_result_for_any_batch_size(self):
        serial = measure_proc(lambda: _FakeSim(30.0, 30.0), _KEY, _ANCHOR, max_trials=500)
        for batch_size in (1, 7, 32, 500):
            batched = measure_proc(None, _KEY, _ANCHOR, max_trials=500,
                                   run_batch=self._batch_runner(30.0, 30.0), batch_size=batch_size)
            self.assertEqual(self._summary(batched), self._summary(serial), batch_size)

    def test_early_stop_ignores_trials_past_the_stop_point(self):
        serial = measure_proc(lambda: _FakeSim(60.0, 30.0), _KEY, _ANCHOR, max_trials=500)
        batched = measure_proc(None, _KEY, _ANCHOR, max_trials=500,
                               run_batch=self._batch_runner(60.0, 30.0), batch_size=64)
        self.assertEqual(serial.stopped_because, "decisive mismatch")
        self.assertEqual(self._summary(batched), self._summary(serial))


class ParallelTrialsTests(unittest.TestCase):
    CONFIG = Path(__file__).resolve().parents[1] / "data" / "run_config" / "Hatred.json"

    @unittest.skipUnless(CONFIG.is_file(), "Hatred run config not present")
    def test_worker_processes_give_the_serial_result(self):
        build_sim, seed, duration = make_sim_builder(str(self.CONFIG))
        sim = build_sim()
        sim.run_until(duration)
        row = next(r for r in summarize_proc_log(sim.triggers.proc_log) if r["mean_chance"] and r["mean_chance"] < 100.0)
        args = (row["key"], row["first_roll"])
        serial = measure_proc(build_sim, *args, max_trials=24, min_trials=24)
        with ParallelTrials(str(self.CONFIG), "live", None, row["key"], row["first_roll"], 0.0, workers=2) as pool:
            parallel = measure_proc(None, *args, max_trials=24, min_trials=24,
                                    run_batch=pool.run_batch, batch_size=pool.batch_size)
        self.assertEqual(
            (serial.trials, serial.rolls, serial.roll_passes, serial.fires),
            (parallel.trials, parallel.rolls, parallel.roll_passes, parallel.fires),
        )

class _ForcedFakeSim:
    """Rolls once at t=_ANCHOR: passes when ``compare(draw, true_chance)``; honors forced draws like the engine."""

    def __init__(self, claimed, compare, true_chance=None):
        random.seed(42)
        self.triggers = SimpleNamespace(proc_log=[], forced_draws=None)
        self._claimed = claimed
        self._compare = compare
        self._true = claimed if true_chance is None else true_chance
        self._done = False

    def run_until(self, t):
        if self._done or t < _ANCHOR:
            return
        self._done = True
        draw = random.random() * 100.0
        forced = (self.triggers.forced_draws or {}).get(_KEY)
        if forced is not None:
            draw = forced
        if self._claimed is None or self._claimed >= 100.0:
            outcome, draw = "fired", None
        else:
            outcome = "fired" if self._compare(draw, self._true) else "roll_failed"
        self.triggers.proc_log.append({
            "t": _ANCHOR, "event": "on_damage_dealt", "source": "Test Proc", "fqn": _KEY[0], "effect_key": _KEY[1],
            "branch_index": _KEY[2], "trigger_index": _KEY[3], "outcome": outcome, "chance": self._claimed, "draw": draw,
        })


_LE = lambda draw, chance: draw <= chance  # the engine's rule: roll > chance fails


class SweepTests(unittest.TestCase):
    def _sweep(self, claimed, compare=_LE, true_chance=None, **kw):
        return sweep_proc(lambda: _ForcedFakeSim(claimed, compare, true_chance), _KEY, _ANCHOR, **kw)

    def test_a_correct_roll_is_exact(self):
        result = self._sweep(30.0)
        self.assertEqual(result.verdict, "exact", result.problems)
        self.assertEqual((result.observed_count, result.expected_count, len(result.values)), (30, 30, 100))
        self.assertTrue(result.boundary_at_chance_passes and result.boundary_above_chance_fails)

    def test_a_fractional_chance_counts_whole_draws_and_checks_the_edge(self):
        result = self._sweep(27.5)
        self.assertEqual(result.verdict, "exact", result.problems)
        self.assertEqual(result.observed_count, 27)
        fine = self._sweep(27.5, step=0.5)
        self.assertEqual((fine.observed_count, fine.expected_count, len(fine.values)), (55, 55, 200))

    def test_a_roll_that_uses_a_different_threshold_is_a_mismatch(self):
        result = self._sweep(30.0, true_chance=40.0)
        self.assertEqual(result.verdict, "MISMATCH")
        self.assertIn("40 passed, expected 30", result.problems[0])

    def test_an_off_by_one_comparison_is_caught_at_the_boundary(self):
        result = self._sweep(30.0, compare=lambda draw, chance: draw < chance)
        self.assertEqual(result.verdict, "MISMATCH")
        self.assertIn("a draw equal to the chance did not pass", result.problems)

    def test_no_chance_or_a_certain_chance_has_nothing_to_sweep(self):
        for claimed in (None, 100.0):
            result = self._sweep(claimed)
            self.assertEqual(result.verdict, "no roll")
            self.assertEqual(result.values, [])

    def test_a_batch_runner_gives_the_serial_result(self):
        serial = self._sweep(30.0)

        def run_forced(values):
            return [run_trial(lambda: _ForcedFakeSim(30.0, _LE), _KEY, _ANCHOR, 0.0, 1_000_003, v) for v in values]

        batched = sweep_proc(None, _KEY, _ANCHOR, run_forced=run_forced)
        self.assertEqual((batched.passes, batched.verdict), (serial.passes, serial.verdict))


@needs_real
class RealFightSweepTests(unittest.TestCase):
    def test_a_real_proc_roll_is_exact(self):
        build_sim, _seed, duration = make_sim_builder(str(RealFightMeasureTests.CONFIG))
        sim = build_sim()
        sim.run_until(duration)
        row = next(r for r in summarize_proc_log(sim.triggers.proc_log) if r["mean_chance"] and r["mean_chance"] < 100.0)
        result = sweep_proc(build_sim, row["key"], row["first_roll"], step=5.0, source=row["source"])
        self.assertEqual(result.verdict, "exact", result.describe())
        self.assertEqual(result.observed_count, result.expected_count)
        self.assertGreater(result.observed_count, 0)


if __name__ == "__main__":
    unittest.main()
