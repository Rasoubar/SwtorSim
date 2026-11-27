"""Hits resolved by one branch share a snapshot: post-hit triggers wait until the whole branch has landed.

Mirrors the game: Dual Saber Throw / Priming Shot main and off-hand hits both get a buff that the first hit consumes.
Hits split across separate branches (Vicious Slash + Dispatcher's Challenge) keep resolving one after the other.
"""

import unittest
from types import SimpleNamespace
from unittest import mock

from src.swtorsim import abilities
from src.swtorsim.abilities import Branch


MAIN = {"action_type": "damage", "hand": "main", "attack_type": 1}
OFF = {"action_type": "damage", "hand": "off", "attack_type": 1}


class _Sim:
    """Minimal simulation: a consumable +100% buff, a trigger log and a manual event queue."""

    def __init__(self):
        self.current_time = 1.0
        self.combat_start_time = None
        self.verbose = False
        self.tracer = None
        self.tracker = SimpleNamespace(log_damage=lambda *a, **k: None)
        self.buff = True
        self.damages = []
        self.log = []
        self.scheduled = []
        self.triggers = SimpleNamespace(dispatch=self._dispatch)

    def _dispatch(self, event, _sim, ctx):
        self.log.append(event)
        if event == "on_damage_dealt":
            self.buff = False  # the buff is consumed by the first landed hit

    def schedule_relative(self, delay, event):
        self.scheduled.append(event)

    def fake_hit(self, source, target, action):
        dmg = 200.0 if self.buff else 100.0
        self.damages.append(dmg)
        self.log.append("hit:" + action.get("hand", "main"))
        return dmg, False


def _run(branches, rolls, sim=None):
    """Executes the branches in order against one sim; ``rolls`` feeds accuracy_roll."""
    sim = sim or _Sim()
    ability = SimpleNamespace(name="Dual Saber Throw", fqn="abl.test.dst", tags=[], type="active")
    caster = SimpleNamespace(stats={"Off_hand_max": 100.0})
    target = SimpleNamespace(name="Target Dummy", hp=1_000_000.0)
    results = []
    with mock.patch("src.swtorsim.events.calculate_hit", sim.fake_hit), \
            mock.patch.object(abilities, "accuracy_roll", side_effect=list(rolls)):
        for branch in branches:
            results.append(branch.execute(sim, caster, target, context=None, ability=ability))
    return sim, results


def _post(sim):
    """Post-hit dispatches only (the pre-hit ones stay immediate)."""
    return [e for e in sim.log if e in ("on_damage_dealt", "on_damage_taken")]


class HitGroupTests(unittest.TestCase):
    def test_same_branch_off_hand_gets_the_buff_the_main_hit_consumes(self):
        sim, _ = _run([Branch(index=3, actions=[MAIN, OFF])], [True, True])

        self.assertEqual(sim.damages, [200.0, 200.0])
        self.assertFalse(sim.buff)

    def test_post_hit_triggers_wait_for_every_hit_in_the_branch(self):
        sim, _ = _run([Branch(index=3, actions=[MAIN, OFF])], [True, True])

        hits = [i for i, e in enumerate(sim.log) if e.startswith("hit:")]
        first_post = min(i for i, e in enumerate(sim.log) if e == "on_damage_dealt")
        self.assertEqual(len(hits), 2)
        self.assertLess(max(hits), first_post)
        self.assertEqual(_post(sim), ["on_damage_dealt", "on_damage_taken"] * 2)

    def test_separate_branches_keep_resolving_one_after_the_other(self):
        sim, _ = _run(
            [Branch(index=2, actions=[MAIN]), Branch(index=3, actions=[OFF])],
            [True, True],
        )

        self.assertEqual(sim.damages, [200.0, 100.0])

    def test_single_damage_branch_dispatches_immediately(self):
        sim, _ = _run([Branch(index=2, actions=[MAIN])], [True])

        self.assertEqual(sim.log[-2:], ["on_damage_dealt", "on_damage_taken"])
        self.assertEqual(sim.log[0], "hit:main")

    def test_main_miss_off_hand_still_gets_the_buff_and_consumes_it(self):
        sim, _ = _run([Branch(index=3, actions=[MAIN, OFF])], [False, True])

        self.assertEqual(sim.damages, [200.0])
        self.assertFalse(sim.buff)

    def test_off_hand_miss_still_consumes_the_buff(self):
        sim, _ = _run([Branch(index=3, actions=[MAIN, OFF])], [True, False])

        self.assertEqual(sim.damages, [200.0])
        self.assertFalse(sim.buff)
        self.assertEqual(_post(sim), ["on_damage_dealt", "on_damage_taken"])

    def test_both_miss_dispatches_nothing_and_keeps_the_buff(self):
        sim, results = _run([Branch(index=3, actions=[MAIN, OFF])], [False, False])

        self.assertEqual(sim.damages, [])
        self.assertEqual(_post(sim), [])
        self.assertTrue(sim.buff)
        self.assertEqual(results, [(True, False)])

    def test_each_landed_hit_dispatches_once(self):
        sim, _ = _run([Branch(index=3, actions=[MAIN, OFF])], [True, True])

        self.assertEqual(sim.log.count("on_damage_dealt"), 2)
        self.assertEqual(sim.log.count("on_damage_taken"), 2)

    def test_delayed_hits_share_the_snapshot_and_flush_after_the_last_one(self):
        delayed_main = dict(MAIN, delay=0.5)
        delayed_off = dict(OFF, delay=0.5)
        sim, _ = _run([Branch(index=3, actions=[delayed_main, delayed_off])], [True, True])

        self.assertEqual(sim.damages, [])
        self.assertEqual(_post(sim), [])
        self.assertEqual(len(sim.scheduled), 2)
        with mock.patch("src.swtorsim.events.calculate_hit", sim.fake_hit):
            sim.scheduled[0].resolve(sim)
            self.assertEqual(_post(sim), [])  # the off-hand hit is still outstanding
            sim.scheduled[1].resolve(sim)

        self.assertEqual(sim.damages, [200.0, 200.0])
        self.assertEqual(_post(sim), ["on_damage_dealt", "on_damage_taken"] * 2)

    def test_branch_returns_the_same_result_as_before(self):
        _, results = _run([Branch(index=3, actions=[MAIN, OFF])], [True, True])

        self.assertEqual(results, [(True, True)])

    def test_group_is_cleared_after_the_branch_and_after_an_error(self):
        sim = _Sim()
        with self.assertRaises(RuntimeError):
            _run([Branch(index=3, actions=[MAIN, OFF])], [True, RuntimeError("boom")], sim=sim)

        self.assertIsNone(sim.hit_group)
        self.assertEqual(_post(sim), ["on_damage_dealt", "on_damage_taken"])  # the landed hit still fires

        sim.log.clear()
        sim.buff = True
        _run([Branch(index=2, actions=[MAIN])], [True], sim=sim)
        self.assertEqual(sim.log[-2:], ["on_damage_dealt", "on_damage_taken"])
        self.assertIsNone(sim.hit_group)

    def test_branches_run_from_a_flush_open_their_own_group(self):
        sim = _Sim()
        inner = Branch(index=4, actions=[MAIN, OFF])
        seen = []
        original = sim._dispatch

        def dispatch(event, s, ctx):
            original(event, s, ctx)
            if event == "on_damage_taken" and not seen:
                seen.append(True)
                sim.buff = True
                with mock.patch.object(abilities, "accuracy_roll", side_effect=[True, True]):
                    inner.execute(
                        sim,
                        SimpleNamespace(stats={"Off_hand_max": 100.0}),
                        SimpleNamespace(name="Target Dummy", hp=1_000_000.0),
                        context=None,
                        ability=SimpleNamespace(name="Inner", fqn="abl.test.inner", tags=[], type="active"),
                    )

        sim.triggers = SimpleNamespace(dispatch=dispatch)
        _run([Branch(index=3, actions=[MAIN, OFF])], [True, True], sim=sim)

        self.assertEqual(sim.damages, [200.0, 200.0, 200.0, 200.0])
        self.assertIsNone(sim.hit_group)

    def test_runs_without_a_simulation_object(self):
        class _Hit:
            def __init__(self, *a, **k):
                self.is_crit = False

            def resolve(self, sim):
                pass

        branch = Branch(index=3, actions=[MAIN, OFF])
        with mock.patch.object(abilities, "DamageHit", _Hit), \
                mock.patch.object(abilities, "accuracy_roll", return_value=True):
            ran = branch.execute(
                None,
                SimpleNamespace(stats={"Off_hand_max": 100.0}),
                object(),
                context=None,
                ability=SimpleNamespace(name="X", fqn="abl.x", tags=[], type="active"),
            )

        self.assertEqual(ran, (True, True))


if __name__ == "__main__":
    unittest.main()
