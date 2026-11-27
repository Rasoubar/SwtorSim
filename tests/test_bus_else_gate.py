"""Else gates (``run_if_none_ran``) on the event bus: TriggerManager.dispatch skips a gated branch when one of its
gate branches of the same owner ran on the same event, like Effect.execute_triggered_branches does.

Shape taken from live Combustible Gas Cylinder_1: branch 3 (talent-conditioned) and branch 4 (gate [3]) both
listen to ``on_damage_dealt`` with their own 1 s rate limit.
"""

import unittest
from types import SimpleNamespace

from src.swtorsim.abilities import Branch
from src.swtorsim.triggers import TriggerManager


class _Ability:
    """Records which branch indices ran; ``passes`` decides each branch's result (conditions)."""

    def __init__(self, passes):
        self.fqn = "abl.test.else_gate"
        self.name = self.fqn
        self.passes = passes
        self.ran = []

    def execute_branch(self, sim, branch, caster, target, context=None):
        if self.passes.get(branch.index, True):
            self.ran.append(branch.index)
            return True
        return False


def _branch(index, gate=(), interval=0.0):
    trigger = {"trigger": "on_damage_dealt"}
    if interval:
        trigger["intervals"] = {"interval_61": interval}
    return Branch(index=index, triggers=[trigger], run_if_none_ran=list(gate))


class BusElseGateTests(unittest.TestCase):
    def setUp(self):
        self.caster = SimpleNamespace(effects={})
        self.target = SimpleNamespace(effects={})
        self.triggers = TriggerManager()

    def _subscribe(self, owner, ability, *branches):
        for branch in branches:
            self.triggers.subscribe(owner, ability, branch, self.caster, self.target)

    def _dispatch(self, now=0.0):
        sim = SimpleNamespace(current_time=now, tracer=None)
        self.triggers.dispatch("on_damage_dealt", sim, {"caster": self.caster, "target": self.target, "tags": []})

    def test_gated_branch_skipped_when_gate_branch_ran(self):
        ability = _Ability({3: True})
        self._subscribe("cgc", ability, _branch(3), _branch(4, gate=[3]))
        self._dispatch()
        self.assertEqual(ability.ran, [3])

    def test_gated_branch_runs_when_gate_branch_did_not(self):
        ability = _Ability({3: False})
        self._subscribe("cgc", ability, _branch(3), _branch(4, gate=[3]))
        self._dispatch()
        self.assertEqual(ability.ran, [4])

    def test_gate_is_per_event(self):
        ability = _Ability({3: True})
        self._subscribe("cgc", ability, _branch(3), _branch(4, gate=[3]))
        self._dispatch(0.0)
        ability.passes[3] = False
        self._dispatch(1.0)
        self.assertEqual(ability.ran, [3, 4])

    def test_gate_is_per_owner(self):
        first = _Ability({3: True})
        second = _Ability({3: False})
        self._subscribe("cgc_a", first, _branch(3), _branch(4, gate=[3]))
        self._subscribe("cgc_b", second, _branch(3), _branch(4, gate=[3]))
        self._dispatch()
        self.assertEqual(first.ran, [3])
        self.assertEqual(second.ran, [4])

    def test_skipped_gated_branch_keeps_its_rate_limit_free(self):
        ability = _Ability({3: True})
        self._subscribe("cgc", ability, _branch(3, interval=1.0), _branch(4, gate=[3], interval=1.0))
        self._dispatch(0.0)
        ability.passes[3] = False
        self._dispatch(0.5)
        self.assertEqual(ability.ran, [3, 4])


if __name__ == "__main__":
    unittest.main()
