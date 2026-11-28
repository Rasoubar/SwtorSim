"""Regression tests for bug-hunt Medium #14-#16 (WASM client parity, rule form, clock rewind)."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.swtorsim import rotation_builder as rb
from src.swtorsim import pyodide_bridge
from src.swtorsim.engine import Simulation
from src.swtorsim.entities import Dummy, Player
from src.swtorsim.events import PreCombatRunner

ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _slice(text, start_marker, length):
    start = text.index(start_marker)
    return text[start : start + length]


class ClockNeverRewindsTests(unittest.TestCase):
    """#16: the next decision time is rounded to 4 decimals but never lands before the current time."""

    NOISY = 14.496300000000002  # rounds to 14.4963, which is below itself

    def test_next_action_time_without_lead(self):
        p = Player("T")
        p.next_gcd = self.NOISY
        self.assertGreaterEqual(p.get_next_action_time(self.NOISY), self.NOISY)

    def test_next_action_time_with_lead(self):
        p = Player("T")
        p.next_gcd = self.NOISY + 0.2
        p.rotation = SimpleNamespace(get_next_lead_time=lambda *a, **k: 0.4)
        self.assertGreaterEqual(p.get_next_action_time(self.NOISY), self.NOISY)

    def test_next_action_time_still_rounds_on_the_grid(self):
        p = Player("T")
        p.next_gcd = 3.123456
        self.assertEqual(p.get_next_action_time(1.0), 3.1235)

    def test_pre_combat_request_is_not_scheduled_in_the_past(self):
        p = Player("T")
        sim = Simulation(verbose=False, seed=42)
        sim.current_time = self.NOISY
        runner = PreCombatRunner(p, Dummy("D", 1000), [{"wait": 0.0}])
        runner.request(sim, self.NOISY)
        self.assertGreaterEqual(sim.queue[0][0], sim.current_time)


class BridgeFormatRotationTests(unittest.TestCase):
    """#14a: the browser build formats rotation files with the same normalization as the native server."""

    def _call(self, payload):
        return json.loads(pyodide_bridge.dispatch("FORMAT_ROTATION", json.dumps(payload)))

    def test_matches_native_file_data(self):
        payload = {
            "steps": [{"type": "fixed", "ability_id": "thrash"}],
            "pre_combat": [{"ability": "phantom_stride", "wait_for_cooldown": False}],
            "pull_conditions": {"caster_has_buff": "Stealth"},
            "pull_max_wait": 10,
            "weave": [{"ability_id": "recklessness", "pre_cast_offset": 0.2, "rules": {}}],
        }
        out = self._call(payload)
        expected = rb.build_rotation_file_data(
            payload["steps"], payload["pre_combat"], payload["pull_conditions"], payload["pull_max_wait"],
            weave=payload["weave"],
        )
        self.assertEqual(json.loads(out["content"]), expected)
        self.assertEqual(out["content"], json.dumps(expected, indent=4, ensure_ascii=False))
        self.assertNotIn("wait_for_cooldown", out["content"])
        self.assertIn("lead_time", out["content"])
        self.assertNotIn("pre_cast_offset", out["content"])

    def test_bare_step_list_stays_a_list(self):
        out = self._call({"steps": [{"type": "fixed", "ability_id": "thrash"}]})
        self.assertEqual(json.loads(out["content"]), [{"type": "fixed", "ability_id": "thrash"}])

    def test_rejects_non_list_steps(self):
        self.assertIn("error", self._call({"steps": "nope"}))


class WasmClientHardeningTests(unittest.TestCase):
    """#14b/#14c: iteration cap, rotation save through the bridge, progress flag reset in a finally."""

    def setUp(self):
        self.js = _read("tools/web/pyodide_client.js")

    def test_rotation_save_uses_bridge_formatter(self):
        block = _slice(self.js, 'pathname === "/api/rotation/save"', 2600)
        self.assertIn('callPrimaryWorker("FORMAT_ROTATION"', block)
        self.assertNotIn("fileData.sequence = payload.steps", block)

    def test_batch_iterations_are_capped(self):
        block = _slice(self.js, "async function executeBatchMultiCore", 600)
        self.assertIn("Math.min(10000", block)

    def test_simulate_route_resets_running_in_finally(self):
        block = _slice(self.js, 'pathname === "/api/simulate")', 2200)
        self.assertIn("finally {", block)
        tail = block[block.index("finally {") :]
        self.assertIn("state.latestProgress.running = false", tail[:200])


class RuleFormTests(unittest.TestCase):
    """#15: zero is a valid number, datalists exist, fields clear, and the builder survives failed requests."""

    def setUp(self):
        self.form = _read("tools/rotation_rule_form.js")
        self.html = _read("tools/rotation_builder_ui.html")

    def test_zero_is_not_replaced_by_a_default(self):
        self.assertNotIn("|| 0.5", self.form)
        self.assertNotIn("|| 1.5", self.form)
        self.assertIn("Number.isFinite", self.form)

    def test_datalist_is_rendered_for_list_attribute(self):
        self.assertIn('<datalist id="${listId}">', self.form)

    def test_builder_clears_fields_when_key_has_no_form(self):
        self.assertNotIn('if (html !== null) document.getElementById("ruleDynamicFields").innerHTML = html;', self.html)

    def test_dry_run_and_save_handle_failed_requests(self):
        for marker in ("async function runDryRunSimulation", "async function saveRotationToDisk"):
            body = _slice(self.html, marker, 2200)
            end = body.find("\n}\n")
            body = body[: end if end > 0 else len(body)]
            self.assertIn("try {", body, marker)
            self.assertIn("res.ok", body, marker)


if __name__ == "__main__":
    unittest.main()
