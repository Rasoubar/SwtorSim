"""The generated traced TriggerManager must behave exactly like the real one and log every proc evaluation."""

import contextlib
import io
import random
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import gen_debug_engine  # noqa: E402
from src.swtorsim.debug.generated.triggers_traced import TriggerManager as TracedTriggerManager  # noqa: E402
from src.swtorsim.debug.traced_run import traced_engine  # noqa: E402
from src.swtorsim.triggers import TriggerManager  # noqa: E402


class _Branch:
    def __init__(self, proc_chance=None, interval=0.0):
        trigger = {"trigger": "on_damage_dealt", "tags": []}
        if proc_chance is not None:
            trigger["floats"] = {"proc_chance_percent": proc_chance}
        if interval:
            trigger["intervals"] = {"interval_61": interval}
        self.triggers = [trigger]


class _Ability:
    def __init__(self):
        self.fqn = "abl.test.proc"
        self.name = "Test Proc"
        self.runs = 0

    def execute_branch(self, sim, branch, caster, target, context=None):
        self.runs += 1
        return True


def _drive(manager_cls, seed):
    """Dispatches 400 hits 0.5s apart against a 30% proc with a 3s ICD; returns run times and RNG end state."""
    caster = SimpleNamespace(effects={})
    target = SimpleNamespace(effects={})
    ability = _Ability()
    times = []
    original_run = ability.execute_branch

    def tracking(sim, branch, c, t, context=None):
        times.append(sim.current_time)
        return original_run(sim, branch, c, t, context=context)

    ability.execute_branch = tracking
    manager = manager_cls()
    manager.subscribe("owner", ability, _Branch(proc_chance=30.0, interval=3.0), caster, target)
    random.seed(seed)
    for i in range(400):
        sim = SimpleNamespace(current_time=i * 0.5, tracer=None)
        manager.dispatch("on_damage_dealt", sim, {"caster": caster, "target": target, "tags": []})
    return times, random.getstate(), manager


class GeneratedUpToDateTests(unittest.TestCase):
    def test_generated_files_match_the_real_engine(self):
        """Drift guard: fails when triggers.py changed and tools/gen_debug_engine.py was not re-run."""
        self.assertTrue(gen_debug_engine.is_up_to_date())


class TracedTriggerParityTests(unittest.TestCase):
    def test_same_procs_and_same_random_draws_as_the_real_manager(self):
        for seed in (1, 2, 3):
            real_times, real_state, _ = _drive(TriggerManager, seed)
            traced_times, traced_state, _ = _drive(TracedTriggerManager, seed)
            self.assertEqual(real_times, traced_times)
            self.assertEqual(real_state, traced_state)

    def test_every_evaluation_is_logged_with_its_outcome(self):
        times, _, manager = _drive(TracedTriggerManager, 1)
        outcomes = [rec["outcome"] for rec in manager.proc_log]
        self.assertEqual(outcomes.count("fired"), len(times))
        self.assertGreater(outcomes.count("blocked_icd"), 0)
        self.assertGreater(outcomes.count("roll_failed"), 0)
        failed = next(rec for rec in manager.proc_log if rec["outcome"] == "roll_failed")
        self.assertEqual(failed["chance"], 30.0)
        self.assertGreater(failed["draw"], 30.0)
        blocked = next(rec for rec in manager.proc_log if rec["outcome"] == "blocked_icd")
        self.assertGreater(blocked["remaining"], 0.0)


class TracedFullSimParityTests(unittest.TestCase):
    CONFIG = Path(__file__).resolve().parents[1] / "data" / "run_config" / "Hatred.json"

    def _total_damage(self, traced):
        from src.swtorsim.config_load import load_from_run_config
        from src.swtorsim.run_config import load_run_config
        from src.swtorsim.setup import prepare_simulation

        cfg = load_run_config(str(self.CONFIG))
        with contextlib.redirect_stdout(io.StringIO()):
            inputs = load_from_run_config(cfg)
            ctx = traced_engine() if traced else contextlib.nullcontext()
            with ctx:
                sim, _player, _target = prepare_simulation(
                    inputs.rotation_config, inputs.stats_config, inputs.loadout_blueprints,
                    cfg.dummy_hp, inputs.debuff_module, seed=cfg.seed,
                )
                sim.verbose = False
                sim.run_until(float(getattr(cfg, "duration", 300.0) or 300.0))
        return float(sim.tracker.total_damage), sim

    @unittest.skipUnless(CONFIG.is_file(), "Hatred run config not present")
    def test_traced_run_deals_identical_damage(self):
        real_damage, real_sim = self._total_damage(traced=False)
        traced_damage, traced_sim = self._total_damage(traced=True)
        self.assertNotIsInstance(real_sim.triggers, TracedTriggerManager)
        self.assertIsInstance(traced_sim.triggers, TracedTriggerManager)
        self.assertEqual(real_damage, traced_damage)
        self.assertGreater(len(traced_sim.triggers.proc_log), 0)

    def test_swap_is_undone_after_the_block(self):
        import src.swtorsim.engine as engine

        with traced_engine():
            self.assertIs(engine.TriggerManager, TracedTriggerManager)
        self.assertIs(engine.TriggerManager, TriggerManager)


class ForcedDrawTests(unittest.TestCase):
    """A sweep can force one rule's draw; with nothing forced the manager behaves as before."""

    KEY = ("abl.test.proc", None, None, 0)

    def _hits(self, forced, seed=5):
        caster = SimpleNamespace(effects={})
        target = SimpleNamespace(effects={})
        ability = _Ability()
        manager = TracedTriggerManager()
        manager.subscribe("owner", ability, _Branch(proc_chance=30.0), caster, target)
        manager.forced_draws = None if forced is None else {self.KEY: forced}
        random.seed(seed)
        sim = SimpleNamespace(current_time=0.0, tracer=None)
        manager.dispatch("on_damage_dealt", sim, {"caster": caster, "target": target, "tags": []})
        return ability.runs, random.getstate(), manager.proc_log

    def test_forced_draw_decides_the_roll_at_the_chance_boundary(self):
        self.assertEqual(self._hits(30.0)[0], 1)       # a draw equal to the chance passes
        self.assertEqual(self._hits(30.000001)[0], 0)  # just above fails
        self.assertEqual(self._hits(1.0)[0], 1)
        self.assertEqual(self._hits(100.0)[0], 0)

    def test_forcing_does_not_change_how_many_random_numbers_are_used(self):
        self.assertEqual(self._hits(10.0)[1], self._hits(None)[1])

    def test_the_log_shows_the_forced_draw(self):
        (rec,) = self._hits(77.0)[2]
        self.assertEqual((rec["outcome"], rec["draw"]), ("roll_failed", 77.0))


if __name__ == "__main__":
    unittest.main()
