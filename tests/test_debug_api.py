"""Debugger API and local server: trace payload shape, measuring from a trace row, and the HTTP routes."""

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from src.swtorsim.debug import debug_api
from src.swtorsim.debug.proc_measure import make_sim_builder
from src.swtorsim.debug.web_debugger import DebuggerRequestHandler

CONFIG = Path(__file__).resolve().parents[1] / "data" / "run_config" / "Hatred.json"
needs_hatred = unittest.skipUnless(CONFIG.is_file(), "Hatred run config not present")


class CompressTests(unittest.TestCase):
    def test_rows_are_columnar_and_raw_time_is_not_rounded(self):
        log = [
            {"t": 10.123456789, "event": "on_tick", "outcome": "roll_failed", "source": "A", "fqn": "a",
             "effect_key": "e", "branch_index": 1, "trigger_index": 0, "kind": "lifecycle",
             "base_chance": 25.0, "chance": 50.0, "draw": 61.5},
            {"t": 11.0, "event": "on_tick", "outcome": "blocked_icd", "source": "A", "fqn": "a",
             "effect_key": "e", "branch_index": 1, "trigger_index": 0, "kind": "lifecycle", "remaining": 1.5, "interval": 3.0},
        ]
        packed = debug_api.compress_proc_log(log, time_offset=10.0)
        self.assertEqual(len(packed["rules"]), 1)
        first, second = packed["evals"]
        self.assertAlmostEqual(first[0], 0.1235, places=4)  # relative time, rounded for display
        self.assertEqual(first[1], 10.123456789)            # raw time stays exact: it is the replay anchor
        self.assertEqual(packed["outcomes"][first[3]], "roll_failed")
        self.assertEqual(first[4:7], [25.0, 50.0, 61.5])
        self.assertEqual(second[7:9], [1.5, 3.0])
        self.assertEqual(packed["rules"][0]["outcomes"], {"roll_failed": 1, "blocked_icd": 1})


class ConfigTests(unittest.TestCase):
    def test_only_listed_configs_resolve(self):
        with self.assertRaises(ValueError):
            debug_api.resolve_config("../../etc/passwd")
        with self.assertRaises(ValueError):
            debug_api.resolve_config("Nope")


@needs_hatred
class TraceAndMeasureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = debug_api.handle("trace", {"config": "Hatred"})

    def test_trace_payload_has_what_the_ui_draws(self):
        self.assertEqual(self.trace["config"]["name"], "Hatred")
        self.assertGreater(self.trace["summary"]["dps"], 0)
        kinds = {e["type"] for e in self.trace["events"]}
        self.assertIn("damage_hit", kinds)
        self.assertIn("cast_start", kinds)
        self.assertTrue(self.trace["proc"]["rules"])
        self.assertTrue(self.trace["proc"]["evals"])
        json.dumps(self.trace)  # must be serializable as is

    def test_trace_carries_the_stat_sheet_and_the_gear_the_page_shows(self):
        derived, gear = self.trace["derived"], self.trace["gear"]
        for key in ("mastery", "power", "crit_rating", "crit_chance", "crit_multiplier", "alacrity_rating", "alacrity_pct",
                    "accuracy_rating", "gcd", "weapon_range"):
            self.assertIn(key, derived)
        self.assertGreater(derived["mastery"], 0)
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(gear["tactical"]["fqn"], config["tactical_fqn"])
        self.assertEqual(sorted(x["fqn"] for x in gear["legendaries"]), sorted(config["legendary_fqns"]))
        self.assertEqual(sorted(x["fqn"] for x in gear["relics"]), sorted(config["relic_fqns"]))

    def test_tracer_does_not_change_the_fight(self):
        """The traced run (with CombatTracer) and the untraced replays must be the same fight."""
        logs = []
        for with_tracer in (True, False):
            build_sim, _seed, duration = make_sim_builder(str(CONFIG), with_tracer=with_tracer)
            sim = build_sim()
            sim.run_timed(duration=duration, target=sim.incoming_attack_attacker)
            logs.append(([(r["t"], r["outcome"], r["source"]) for r in sim.triggers.proc_log], sim.tracker.total_damage))
        self.assertEqual(logs[0], logs[1])

    def test_exact_check_from_a_trace_row(self):
        proc = self.trace["proc"]
        rule = next(r for r in proc["rules"] if r["mean_chance"] and r["mean_chance"] < 100)
        row = next(e for e in proc["evals"] if e[2] == rule["id"] and e[5] is not None)
        result = debug_api.handle("sweep", {
            "config": "Hatred", "key": rule["key"], "anchor": row[1], "seed": self.trace["config"]["seed"], "step": 5,
        })
        self.assertEqual(result["verdict"], "exact", result["problems"])
        self.assertEqual(result["passed"], result["expected"])
        self.assertEqual(result["tested"], 20)

    def test_measuring_from_a_trace_row_finds_its_rolls(self):
        """Regression: the anchor in the payload must be exact, or the replay misses the evaluation it targets."""
        proc = self.trace["proc"]
        rule = next(r for r in proc["rules"] if r["mean_chance"] and r["mean_chance"] < 100)
        row = next(e for e in proc["evals"] if e[2] == rule["id"] and e[5] is not None)
        result = debug_api.handle("measure", {
            "config": "Hatred", "key": rule["key"], "anchor": row[1], "seed": self.trace["config"]["seed"],
            "trials": 20, "workers": 1,
        })
        self.assertEqual(result["trials"], 20)
        self.assertGreaterEqual(result["rolls"], 20)
        self.assertEqual(result["verdict"], "consistent")


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), DebuggerRequestHandler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _post(self, path, body):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, json.loads(res.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_serves_the_page_and_the_config_list(self):
        with urllib.request.urlopen(self.base + "/") as res:
            self.assertIn(b"SwtorSim Debugger", res.read())
        with urllib.request.urlopen(self.base + "/api/configs") as res:
            self.assertIsInstance(json.loads(res.read())["configs"], list)

    def test_unknown_action_is_404_and_bad_config_reports_an_error(self):
        status, body = self._post("/api/nope", {})
        self.assertEqual(status, 404)
        status, body = self._post("/api/trace", {"config": "Nope"})
        self.assertEqual(status, 500)
        self.assertIn("Unknown run config", body["error"])


if __name__ == "__main__":
    unittest.main()
