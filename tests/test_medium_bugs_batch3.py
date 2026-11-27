"""Regression tests for bug-hunt Medium #17 and #19 (GCD near-tie tolerance, lead time on on-GCD options)."""

import contextlib
import io
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.swtorsim.abilities import Ability, AbilityBlueprint
from src.swtorsim.engine import Simulation
from src.swtorsim.entities import Dummy, Player
from src.swtorsim.events import PreCombatRunner
from src.swtorsim.rotation import FixedAbilityStep, OptionalAbilityStep, PriorityBlockStep, Rotation

ROOT = Path(__file__).resolve().parents[1]
SNIPE = ROOT / "data" / "extractor" / "live" / "parsed" / "abl" / "agent" / "snipe.json"


def _snipe_player():
    bp = AbilityBlueprint.from_file(SNIPE)
    with contextlib.redirect_stdout(io.StringIO()):
        p = Player("Op", abilities={bp.fqn: Ability(bp)})
    p.resource.current_value = 100.0
    return bp, p


class GcdTieToleranceTests(unittest.TestCase):
    """#17: a step is "ready" exactly when the ability's own GCD check passes; no 1e-4 window in between."""

    def test_optional_on_gcd_step_waits_instead_of_skipping(self):
        bp, p = _snipe_player()
        p.next_gcd = 1.40005
        sim = Simulation(verbose=False, seed=42)
        sim.current_time = 1.4
        step = OptionalAbilityStep(bp.fqn, rules={})
        self.assertFalse(step.evaluate(p, Dummy("D", 1000), sim))

    def test_optional_step_with_float_noise_waits(self):
        bp, p = _snipe_player()
        p.next_gcd = 95.754
        sim = Simulation(verbose=False, seed=42)
        sim.current_time = 95.7539999999999
        step = OptionalAbilityStep(bp.fqn, rules={})
        self.assertFalse(step.evaluate(p, Dummy("D", 1000), sim))

    def test_fixed_step_is_early_inside_the_old_window(self):
        bp, p = _snipe_player()
        p.next_gcd = 1.40005
        sim = Simulation(verbose=False, seed=42)
        sim.current_time = 1.4
        self.assertFalse(FixedAbilityStep(bp.fqn).evaluate(p, Dummy("D", 1000), sim))
        self.assertIsNone(p.active_cast)

    def test_pre_combat_waits_for_the_gcd_instead_of_skipping_the_step(self):
        bp, p = _snipe_player()
        p.next_gcd = 1.40005
        sim = Simulation(verbose=False, seed=42)
        sim.current_time = 1.4
        runner = PreCombatRunner(p, Dummy("D", 1000), [{"ability": bp.fqn}])
        runner.run(sim)
        self.assertEqual(runner.skipped, [])
        self.assertEqual(runner.index, 0)
        self.assertGreaterEqual(sim.queue[0][0], p.next_gcd)


def _gcd_player():
    p = Player("T")
    p.ability_db["filler"] = SimpleNamespace(name="filler", fqn="abl.test.filler", triggers_gcd=True)
    p.ability_db["off"] = SimpleNamespace(name="off", fqn="abl.test.off", triggers_gcd=False)
    p.current_target = Dummy("D", 1000)
    return p


class LeadTimeOnGcdTests(unittest.TestCase):
    """#19: a lead time only applies when the ability that will be cast is off the GCD."""

    def setUp(self):
        self.p = _gcd_player()
        self.sim = SimpleNamespace(current_time=1.0)

    def test_priority_block_with_on_gcd_top_option_has_no_lead(self):
        block = {
            "type": "priority_block", "name": "PB", "lead_time": 0.4,
            "pool": [{"ability_id": "off", "rules": {"target_hp_below_pct": 0.3}}, {"ability_id": "filler"}],
        }
        self.assertEqual(Rotation("r", [block]).get_next_lead_time(self.p, 1.0, self.sim), 0.0)

    def test_priority_block_with_off_gcd_top_option_keeps_lead(self):
        block = {
            "type": "priority_block", "name": "PB", "lead_time": 0.4,
            "pool": [{"ability_id": "off"}, {"ability_id": "filler"}],
        }
        self.assertEqual(Rotation("r", [block]).get_next_lead_time(self.p, 1.0, self.sim), 0.4)

    def test_fixed_on_gcd_step_has_no_lead(self):
        rot = Rotation("r", [{"type": "fixed", "ability_id": "filler", "lead_time": 0.4}])
        self.assertEqual(rot.get_next_lead_time(self.p, 1.0, self.sim), 0.0)

    def test_fixed_off_gcd_step_keeps_lead(self):
        rot = Rotation("r", [{"type": "fixed", "ability_id": "off", "lead_time": 0.4}])
        self.assertEqual(rot.get_next_lead_time(self.p, 1.0, self.sim), 0.4)

    def test_lower_priority_off_gcd_option_is_not_pulled_forward(self):
        """With the top option on the GCD, the player is not woken early, so no lower option is cast early."""
        block = PriorityBlockStep("PB", [{"ability_id": "filler"}, {"ability_id": "off"}], lead_time=0.4)
        rot = Rotation("r", [{"type": "priority_block", "name": "PB", "lead_time": 0.4,
                              "pool": block.pool}])
        self.assertEqual(rot.get_next_lead_time(self.p, 1.0, self.sim), 0.0)


if __name__ == "__main__":
    unittest.main()
