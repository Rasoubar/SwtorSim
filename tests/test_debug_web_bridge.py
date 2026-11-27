"""The browser build's path: setup intake, bridge dispatch, and slices + aggregation equal the native serial results."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.swtorsim import pyodide_bridge
from src.swtorsim.debug import debug_api, debug_slices
from src.swtorsim.debug.debug_bridge import dispatch as debug_dispatch

HATRED = Path(__file__).resolve().parents[1] / "data" / "run_config" / "Hatred.json"
needs_hatred = unittest.skipUnless(HATRED.is_file(), "Hatred run config not present")


def _json_trip(value):
    """What the page does between two workers: through JSON text and back."""
    return json.loads(json.dumps(value))


def _hatred_setup():
    """A simulator-style request payload for Hatred (what the Combat Simulator page sends)."""
    from src.swtorsim.web_gui import load_run_config_bundle

    raw = load_run_config_bundle("data/run_config/Hatred.json", "live")["run_config"]
    return {**raw, "environment": "live", "mode": "TEST"}


@needs_hatred
class SetupIntakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.setup = _hatred_setup()

    def test_the_debugger_shows_the_same_fight_the_simulator_runs(self):
        from src.swtorsim.web_gui import execute_simulation_from_payload

        simulator = execute_simulation_from_payload(dict(self.setup))
        traced = debug_api.handle("trace", {"setup": self.setup})
        self.assertEqual(traced["summary"]["total_damage"], int(simulator["total_damage"]))
        self.assertEqual(traced["config"]["source"], "setup")
        self.assertEqual(traced["config"]["name"], "Assassin Hatred")

    def test_a_setup_equals_the_saved_config_it_came_from(self):
        by_setup = debug_api.handle("trace", {"setup": self.setup})
        by_config = debug_api.handle("trace", {"config": "Hatred"})
        self.assertEqual(by_setup["summary"]["total_damage"], by_config["summary"]["total_damage"])
        self.assertEqual(by_setup["proc"]["evals"], by_config["proc"]["evals"])

    def test_state_and_change_take_a_setup(self):
        traced = debug_api.handle("trace", {"setup": self.setup})
        hit = next(e for e in traced["events"] if e["type"] == "damage_hit" and e["t"] > 30)
        state = debug_api.handle("state", {"setup": self.setup, "at": hit["raw"]})
        self.assertTrue(state["abilities"])
        change = debug_api.handle("change", {"setup": self.setup, "at": hit["raw"]})
        self.assertGreaterEqual(abs(change["diff"]["target_hp"]["delta"]), hit["damage"])

    def test_a_request_without_a_fight_is_refused(self):
        with self.assertRaises(ValueError):
            debug_api.handle("trace", {})


@needs_hatred
class NativeServerSetupTests(unittest.TestCase):
    """The local debugger server (used with the native simulator) accepts the simulator's setup over HTTP."""

    def test_posting_a_setup_to_the_server_traces_it(self):
        import threading
        import urllib.request
        from http.server import ThreadingHTTPServer

        from src.swtorsim.debug.web_debugger import DebuggerRequestHandler

        server = ThreadingHTTPServer(("127.0.0.1", 0), DebuggerRequestHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            body = json.dumps({"setup": _hatred_setup()}).encode()
            req = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}/api/trace", body,
                                         {"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as res:
                traced = json.loads(res.read())
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(traced["config"]["source"], "setup")
        self.assertEqual(traced["summary"]["total_damage"], debug_api.handle("trace", {"config": "Hatred"})["summary"]["total_damage"])


class LaunchFromTheSimulatorServerTests(unittest.TestCase):
    """The native simulator starts the debugger itself (a separate process) when Debug is pressed."""

    def tearDown(self):
        from src.swtorsim import web_gui

        web_gui.stop_debugger()

    def test_the_debugger_process_is_started_reused_and_stopped(self):
        import urllib.request

        from src.swtorsim import web_gui

        url = web_gui.ensure_debugger_running(default_port=8790)  # not the default port: a debugger of your own may be running
        with urllib.request.urlopen(url + "api/configs", timeout=5) as res:
            self.assertIn("configs", json.loads(res.read()))
        self.assertEqual(web_gui.ensure_debugger_running(default_port=8790), url)  # reused, not started twice
        port = int(url.rstrip("/").rsplit(":", 1)[1])
        web_gui.stop_debugger()
        self.assertFalse(web_gui._debugger_answers("127.0.0.1", port))

    def test_a_debugger_running_older_code_is_not_reused(self):
        """A debugger left running from before a code change keeps the old code; the simulator must start a fresh one."""
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        from src.swtorsim import web_gui

        class StaleDebugger(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                body = json.dumps({"configs": ["Hatred"], "version": "an-older-version"}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        stale = ThreadingHTTPServer(("127.0.0.1", 0), StaleDebugger)
        threading.Thread(target=stale.serve_forever, daemon=True).start()
        stale_port = stale.server_address[1]
        try:
            current = web_gui._debugger_code_version()
            self.assertTrue(web_gui._debugger_answers("127.0.0.1", stale_port))  # it answers...
            self.assertFalse(web_gui._debugger_answers("127.0.0.1", stale_port, current))  # ...but not as the current code
            url = web_gui.ensure_debugger_running(default_port=stale_port)
            self.assertNotEqual(url, f"http://127.0.0.1:{stale_port}/")
            self.assertTrue(web_gui._debugger_answers("127.0.0.1", int(url.rstrip("/").rsplit(":", 1)[1]), current))
        finally:
            stale.shutdown()
            stale.server_close()

    def test_a_started_debugger_reports_the_version_it_started_with(self):
        import urllib.request

        from src.swtorsim import web_gui

        url = web_gui.ensure_debugger_running(default_port=8790)
        with urllib.request.urlopen(url + "api/configs", timeout=5) as res:
            self.assertEqual(json.loads(res.read())["version"], web_gui._debugger_code_version())

    def test_the_route_returns_the_address_or_the_reason_it_failed(self):
        import threading
        import urllib.error
        import urllib.request
        from http.server import ThreadingHTTPServer

        from src.swtorsim import web_gui

        server = ThreadingHTTPServer(("127.0.0.1", 0), web_gui.SimulatorRequestHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}/api/launch_debugger"
        post = lambda: urllib.request.urlopen(urllib.request.Request(base, b"{}", {"Content-Type": "application/json"}))
        try:
            with patch.object(web_gui, "ensure_debugger_running", return_value="http://127.0.0.1:9/"):
                with post() as res:
                    self.assertEqual(json.loads(res.read()), {"ok": True, "url": "http://127.0.0.1:9/"})
            with patch.object(web_gui, "ensure_debugger_running", side_effect=RuntimeError("no port")):
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    post()
                self.assertEqual(raised.exception.code, 500)
                self.assertIn("no port", json.loads(raised.exception.read())["error"])
        finally:
            server.shutdown()
            server.server_close()


class ConfigListTests(unittest.TestCase):
    def test_custom_run_configs_are_listed_and_resolve(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "custom").mkdir()
            (Path(tmp) / "Shipped.json").write_text("{}")
            (Path(tmp) / "custom" / "Mine.json").write_text("{}")
            with patch.object(debug_api, "RUN_CONFIG_DIR", Path(tmp)):
                self.assertEqual(debug_api.list_configs()["configs"], ["Shipped", "custom/Mine"])
                self.assertTrue(debug_api.resolve_config("custom/Mine").endswith("Mine.json"))
                with self.assertRaises(ValueError):
                    debug_api.resolve_config("custom/../Shipped")


class IconsWithoutFilesTests(unittest.TestCase):
    def test_without_icon_folders_every_plain_name_is_listed(self):
        """The browser build keeps the icon files next to the page, not in Python's file system."""
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as tmp:
            missing = (Path(tmp) / "nope",)
            bp = SimpleNamespace(name="Strike", icon="strike.png", effects={})
            odd = SimpleNamespace(name="Bad", icon="../x.png", effects={})
            with patch.object(debug_api, "ICON_DIRS", missing):
                icons = debug_api.icon_map({"a": bp, "b": odd})
        self.assertEqual(icons, {"Strike": "strike.png"})


@needs_hatred
class BridgeTests(unittest.TestCase):
    def test_the_bridge_routes_debug_actions_and_reports_unknown_ones(self):
        configs = json.loads(pyodide_bridge.dispatch("DEBUG_CONFIGS", "{}"))
        self.assertIn("Hatred", configs["configs"])
        bad = json.loads(pyodide_bridge.dispatch("DEBUG_NOPE", "{}"))
        self.assertIn("Unknown debugger action", bad["error"])

    def test_a_trace_through_the_bridge_is_the_api_trace(self):
        via_bridge = json.loads(pyodide_bridge.dispatch("DEBUG_TRACE", json.dumps({"config": "Hatred"})))
        direct = _json_trip(debug_api.handle("trace", {"config": "Hatred"}))
        self.assertEqual(via_bridge["summary"], direct["summary"])
        self.assertEqual(via_bridge["proc"]["evals"], direct["proc"]["evals"])


@needs_hatred
class SliceEqualsSerialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = debug_api.handle("trace", {"config": "Hatred"})
        proc = cls.trace["proc"]
        cls.rule = next(r for r in proc["rules"] if r["mean_chance"] and r["mean_chance"] < 100)
        cls.row = next(e for e in proc["evals"] if e[2] == cls.rule["id"] and e[5] is not None)
        cls.hit = next(e for e in cls.trace["events"] if e["type"] == "damage_hit" and e["t"] > 30)

    def _fight(self):
        return {"config": "Hatred"}

    def test_measure_slices_and_aggregation_equal_the_serial_result(self):
        serial = debug_api.handle("measure", {"config": "Hatred", "key": self.rule["key"], "anchor": self.row[1], "trials": 40})
        # Two workers' slices, results through JSON, aggregated in order.
        first = _json_trip(debug_slices.trials_slice(key=self.rule["key"], anchor=self.row[1], first=0, count=20, **self._fight()))
        second = _json_trip(debug_slices.trials_slice(key=self.rule["key"], anchor=self.row[1], first=20, count=20, **self._fight()))
        aggregated = debug_slices.measure_aggregate(
            key=self.rule["key"], anchor=self.row[1], trials=first + second, max_trials=40)
        self.assertTrue(aggregated["done"])
        pooled = aggregated["result"]
        for field in ("trials", "rolls", "roll_passes", "fires", "observed", "expected", "verdict", "stopped_because"):
            self.assertEqual(pooled[field], serial[field], field)

    def test_the_aggregation_asks_for_more_trials_when_the_rule_is_not_decided(self):
        some = _json_trip(debug_slices.trials_slice(key=self.rule["key"], anchor=self.row[1], first=0, count=5, **self._fight()))
        wanted = debug_slices.measure_aggregate(key=self.rule["key"], anchor=self.row[1], trials=some, max_trials=40)
        self.assertEqual(wanted, {"done": False, "trials": 5})

    def test_exact_check_slices_equal_the_serial_result(self):
        serial = debug_api.handle("sweep", {"config": "Hatred", "key": self.rule["key"], "anchor": self.row[1], "step": 10})
        plan = _json_trip(debug_slices.sweep_plan(key=self.rule["key"], anchor=self.row[1], step=10, **self._fight()))
        self.assertIsNotNone(plan["chance"])
        half = len(plan["values"]) // 2
        results = _json_trip(
            debug_slices.forced_slice(key=self.rule["key"], anchor=self.row[1], values=plan["values"][:half], **self._fight())
            + debug_slices.forced_slice(key=self.rule["key"], anchor=self.row[1], values=plan["values"][half:], **self._fight())
        )
        pooled = debug_slices.sweep_aggregate(
            key=self.rule["key"], anchor=self.row[1], probe=plan["probe"], values=plan["values"], results=results, step=10)
        for field in ("chance", "tested", "passed", "expected", "verdict", "problems"):
            self.assertEqual(pooled[field], serial[field], field)

    def test_a_roll_without_a_chance_has_nothing_to_sweep_in_the_plan(self):
        rule = next(r for r in self.trace["proc"]["rules"] if r["mean_chance"] is None)
        row = next(e for e in self.trace["proc"]["evals"] if e[2] == rule["id"])
        plan = debug_slices.sweep_plan(key=rule["key"], anchor=row[1], **self._fight())
        self.assertEqual((plan["chance"], plan["values"]), (None, []))

    def test_damage_slices_and_aggregation_equal_the_serial_result(self):
        serial = debug_api.handle("damage", {"config": "Hatred", "ability": self.hit["ability"], "anchor": self.hit["raw"], "trials": 12})
        a = _json_trip(debug_slices.damage_slice(ability=self.hit["ability"], anchor=self.hit["raw"], first=0, count=6,
                                                 want_reference=True, **self._fight()))
        b = _json_trip(debug_slices.damage_slice(ability=self.hit["ability"], anchor=self.hit["raw"], first=6, count=6, **self._fight()))
        pooled = debug_slices.damage_aggregate(
            ability=self.hit["ability"], anchor=self.hit["raw"], trials=a["hits"] + b["hits"], reference=a["reference"])
        for field in ("trials", "hits", "crits", "normal", "crit_damage", "reference", "verdict"):
            self.assertEqual(pooled[field], serial[field], field)


if __name__ == "__main__":
    unittest.main()
