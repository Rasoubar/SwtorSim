"""Unit tests for the single live PlayerReady chain and the Monte Carlo report histogram call."""

import contextlib
import io
import unittest
from unittest import mock

from src.swtorsim.engine import Simulation
from src.swtorsim.events import PlayerReady, schedule_next_decision
from src.swtorsim.tester import Tester


class _IdleRotation:
    """Rotation that never finds anything to cast, so PlayerReady keeps polling."""

    current_step = 0
    sequence = []

    def __init__(self):
        self.evaluations = 0

    def evaluate(self, player, target, sim):
        self.evaluations += 1
        return False


class _IdlePlayer:
    def __init__(self):
        self.rotation = _IdleRotation()
        self.next_gcd = 0.0
        self.active_cast = None
        self.active_channel = None


def _queued_player_ready(sim):
    return [event for _, _, event in sim.queue if isinstance(event, PlayerReady)]


class DecisionChainTests(unittest.TestCase):
    def test_second_hand_off_supersedes_the_first_chain(self):
        """Two hand-offs leave one polling chain, not two."""
        sim = Simulation(verbose=False, seed=1)
        player = _IdlePlayer()
        schedule_next_decision(player, None, sim)
        schedule_next_decision(player, None, sim)

        sim.run_until(0.95)

        self.assertEqual(player.rotation.evaluations, 10)
        self.assertEqual(len(_queued_player_ready(sim)), 1)

    def test_superseded_player_ready_does_not_evaluate_or_reschedule(self):
        """A PlayerReady from an older generation is a no-op."""
        sim = Simulation(verbose=False, seed=1)
        player = _IdlePlayer()
        stale = PlayerReady(player, None)
        schedule_next_decision(player, None, sim)
        queued_before = len(sim.queue)

        stale.resolve(sim)

        self.assertEqual(player.rotation.evaluations, 0)
        self.assertEqual(len(sim.queue), queued_before)

    def test_directly_built_player_ready_joins_the_live_chain(self):
        """PlayerReady built without a generation (setup, tests) still drives the rotation."""
        sim = Simulation(verbose=False, seed=1)
        player = _IdlePlayer()
        sim.schedule_absolute(0.0, PlayerReady(player, None))

        sim.run_until(0.25)

        self.assertEqual(player.rotation.evaluations, 3)
        self.assertEqual(len(_queued_player_ready(sim)), 1)


class MonteCarloReportHistogramTests(unittest.TestCase):
    def test_histogram_is_drawn_without_an_execute_phase(self):
        """The DPS histogram does not depend on the fight reaching the execute phase."""
        summary = {
            "avg_dps": 100.0,
            "median_dps": 100.0,
            "min_dps": 90.0,
            "max_dps": 110.0,
            "std_dev": 5.0,
            "total_time": 300.0,
            "macro_breakdown": {},
            "total_exec_duration": 0.0,
            "all_dps": [90.0, 100.0, 110.0],
        }
        with mock.patch.object(Tester, "_plot_dps_histogram") as plot, \
                mock.patch.object(Tester, "print_macro_phase_table"), \
                contextlib.redirect_stdout(io.StringIO()):
            Tester.produce_monte_carlo_report(summary, 3)

        plot.assert_called_once_with([90.0, 100.0, 110.0], 100.0, 5.0, 3)


if __name__ == "__main__":
    unittest.main()
