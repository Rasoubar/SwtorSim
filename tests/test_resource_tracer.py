import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.swtorsim.abilities import handle_resource_gain_action, handle_resource_spend_action
from src.swtorsim.debug.tracer import CombatTracer
from src.swtorsim.engine import Simulation
from src.swtorsim.entities import Player
from src.swtorsim.events import ResourceGainEvent
from src.swtorsim.resources import EnergyPool


class ResourceTracerTests(unittest.TestCase):
    def setUp(self):
        self.sim = Simulation()
        self.tracer = CombatTracer()
        self.sim.tracer = self.tracer
        self.player = Player(name="TestSniper")
        self.player.level = 80
        self.player.resource = EnergyPool(max_value=110.0, base_regen=0.0)
        self.player.resource.current_value = 80.0

    def test_resource_gain_event_logging(self):
        """Verifies that ResourceGainEvent logs to tracer with delta, current, and reason."""
        gain_event = ResourceGainEvent(self.player, 15.0, source="Proc: Target Lock")
        gain_event.resolve(self.sim)

        self.assertEqual(self.player.resource.current, 95.0)
        res_events = [e for e in self.tracer.events if e.get("type") == "resource"]
        self.assertEqual(len(res_events), 1)
        ev = res_events[0]
        self.assertEqual(ev["entity"], "TestSniper")
        self.assertEqual(ev["resource"], "Energy")
        self.assertEqual(ev["current"], 95.0)
        self.assertEqual(ev["delta"], 15.0)
        self.assertEqual(ev["reason"], "Proc: Target Lock")

        # Verify resource samples updated for sparkline
        self.assertTrue(any(s["v"] == 95.0 for s in self.tracer.resource_samples))

    def test_handle_resource_gain_action_proc_naming(self):
        """Verifies that handle_resource_gain_action cleanly formats proc names in reason."""
        action = {"action_type": "energy_recovery", "min": 2.0}
        context = {"is_proc": True, "owner_effect_key": "Ballistic Redistribution_1"}
        handle_resource_gain_action(
            self.sim,
            self.player,
            action,
            source_name="Ballistic Redistribution",
            context=context,
        )

        self.assertEqual(self.player.resource.current, 82.0)
        res_events = [e for e in self.tracer.events if e.get("type") == "resource"]
        self.assertEqual(len(res_events), 1)
        ev = res_events[0]
        self.assertEqual(ev["reason"], "Proc: Ballistic Redistribution")
        self.assertEqual(ev["delta"], 2.0)

    def test_handle_resource_spend_action_logging(self):
        """Verifies that handle_resource_spend_action logs negative delta with reason."""
        action = {"action_type": "spend_energy", "floats": {"amount": 6.0}}
        handle_resource_spend_action(
            self.player,
            action,
            sim=self.sim,
            source_name="Penetrating Blasts",
        )

        self.assertEqual(self.player.resource.current, 74.0)
        res_events = [e for e in self.tracer.events if e.get("type") == "resource"]
        self.assertEqual(len(res_events), 1)
        ev = res_events[0]
        self.assertEqual(ev["delta"], -6.0)
        self.assertEqual(ev["reason"], "Spend: Penetrating Blasts")


if __name__ == "__main__":
    unittest.main()
