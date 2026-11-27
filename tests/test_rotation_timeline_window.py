"""Rotation builder Visual Map tab and pop-out Cast Timeline window wiring."""

import re
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from data import rotation_builder
from data.rotation_builder import RotationBuilderRequestHandler
from src.swtorsim import settings


class TimelineWindowRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), RotationBuilderRequestHandler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read().decode("utf-8")

    def test_timeline_route_serves_timeline_page(self):
        for path in ("/timeline", "/timeline.html"):
            status, ctype, body = self._get(path)
            self.assertEqual(status, 200)
            self.assertIn("text/html", ctype)
            self.assertIn("<title>SwtorSim - Cast Timeline</title>", body)

    def test_map_route_serves_map_page(self):
        for path in ("/map", "/map.html"):
            status, ctype, body = self._get(path)
            self.assertEqual(status, 200)
            self.assertIn("text/html", ctype)
            self.assertIn("<title>SwtorSim - Rotation Map</title>", body)

    def test_rule_form_script_route(self):
        status, ctype, body = self._get("/rule_form.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", ctype)
        self.assertIn("global.RuleForm = { listsFromLoadout, fieldsHtml, readValue };", body)

    def test_root_still_serves_builder(self):
        status, _, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("<title>SwtorSim - Rotation Builder</title>", body)


class TimelineWindowContractTests(unittest.TestCase):
    """The builder and the timeline window talk over a BroadcastChannel; both sides must agree."""

    @classmethod
    def setUpClass(cls):
        cls.builder = rotation_builder.UI_HTML_PATH.read_text(encoding="utf-8")
        cls.timeline = rotation_builder.TIMELINE_UI_PATH.read_text(encoding="utf-8")

    def test_channel_names_match(self):
        b = re.search(r'VIZ_CHANNEL_NAME = "([^"]+)"', self.builder)
        t = re.search(r'CHANNEL_BASE = "([^"]+)"', self.timeline)
        self.assertIsNotNone(b)
        self.assertIsNotNone(t)
        self.assertEqual(b.group(1), t.group(1))
        # The simulator feeds ?source=sim windows on the "-sim" channel.
        sim_html = (rotation_builder.SWTORSIM_ROOT / "tools" / "simulator_ui.html").read_text(encoding="utf-8")
        sim = re.search(r'CAST_TIMELINE_CHANNEL = "([^"]+)"', sim_html)
        self.assertIsNotNone(sim)
        self.assertEqual(sim.group(1), t.group(1) + "-sim")
        self.assertIn("timeline.html?source=sim&mode=${mode}", sim_html)
        self.assertIn("swtorsim_sim_timeline_open_mode", sim_html)
        self.assertIn("`${CHANNEL_BASE}-sim`", self.timeline)

    def test_message_types_handled_on_both_sides(self):
        # timeline -> builder
        for msg in ("hello", "select"):
            self.assertIn(f'type: "{msg}"', self.timeline)
            self.assertIn(f'msg.type === "{msg}"', self.builder)
        # builder -> timeline
        for msg in ("state", "stale", "select"):
            self.assertIn(f'msg.type === "{msg}"', self.timeline)
        self.assertIn('type: "state"', self.builder)
        self.assertIn('type: "stale"', self.builder)

    def test_builder_opens_timeline_and_map_windows(self):
        self.assertIn('url: "timeline.html"', self.builder)
        self.assertIn('url: "map.html"', self.builder)
        self.assertIn("function openCompanionWindow(", self.builder)
        self.assertIn('onclick="openVisualMapWindow()"', self.builder)
        self.assertNotIn("rTabMap", self.builder)  # the old Visual Map tab is gone

    def test_companion_dock_mode_toggle_contract(self):
        mp = rotation_builder.MAP_UI_PATH.read_text(encoding="utf-8")
        for html, pref in ((mp, "swtorsim_map_open_mode"), (self.timeline, "swtorsim_timeline_open_mode")):
            self.assertIn('id="btnDockMode"', html)
            self.assertIn("Move to Tab", html)
            self.assertIn("Pop Out Window", html)
            self.assertIn(pref, html)
        self.assertIn("swtorsim_map_open_mode", self.builder)
        self.assertIn("swtorsim_timeline_open_mode", self.builder)

    def test_map_channel_contract(self):
        mp = rotation_builder.MAP_UI_PATH.read_text(encoding="utf-8")
        b = re.search(r'const MAP_CHANNEL_NAME = "([^"]+)"', self.builder)
        m = re.search(r'const MAP_CHANNEL_NAME = "([^"]+)"', mp)
        self.assertIsNotNone(b)
        self.assertIsNotNone(m)
        self.assertEqual(b.group(1), m.group(1))
        # map -> builder
        for msg in ("hello", "goto"):
            self.assertIn(f'type: "{msg}"', mp)
            self.assertIn(f'msg.type === "{msg}"', self.builder)
        # builder -> map
        for msg in ("state", "select"):
            self.assertIn(f'msg.type === "{msg}"', mp)
        # an ability click carries the pool row; the builder flashes that row in the editor
        self.assertIn("entry: entry ? +entry.dataset.entry : null", mp)
        self.assertIn("pool-row-${e.editorIdx}-${entry}", self.builder)

    def test_map_edit_command_contract(self):
        """The map edits through "cmd" messages; the builder must handle every op the map sends."""
        mp = rotation_builder.MAP_UI_PATH.read_text(encoding="utf-8")
        self.assertIn('channel.postMessage({ type: "cmd", rev: STATE.rev, ...cmd })', mp)
        self.assertIn('msg.type === "cmd"', self.builder)
        ops = set(re.findall(r'\bop: "(\w+)"', mp))
        self.assertTrue(
            {"insert", "move", "anchor", "addRow", "moveRow", "rowToStep", "delRow", "type", "del",
             "setRule", "delRule", "weaveAdd", "weaveDel", "undo", "redo"} <= ops,
            ops,
        )
        self.assertIn('data-op="dup"', mp)  # sent as { op, step } from the step menu
        for op in ops | {"dup"}:
            if op in ("undo", "redo"):
                self.assertIn(f'if (msg.op === "{op}")', self.builder)
            else:
                self.assertIn(f'case "{op}":', self.builder, op)
        # a command built on an older rotation is dropped: the state carries rev, the builder compares it
        self.assertIn("rev: vizMapRev,", self.builder)
        self.assertIn("if (msg.rev !== vizMapRev) return vizBroadcastMap();", self.builder)
        # the state carries what the map needs to place drops and fill the palette / rule form
        for field in ("editorIdx: e.editorIdx,", "anchorIdx:", "total: rotationSteps.length,", "canUndo:", "catalog: {"):
            self.assertIn(field, self.builder)

    def test_map_trash_and_loop_row_breaks(self):
        mp = rotation_builder.MAP_UI_PATH.read_text(encoding="utf-8")
        # trash: a drop removes the dragged step / row / weave entry / anchor through existing commands
        self.assertIn('<div id="trash"', mp)
        for line in (
            'if (d.kind === "step") return { op: "del", step: d.idx };',
            'if (d.kind === "row") return { op: "delRow", step: d.step, row: d.row };',
            'if (d.kind === "weave") return { op: "weaveDel", idx: d.idx };',
        ):
            self.assertIn(line, mp)
        # row breaks are a view option of the loop lane only: nothing is sent to the builder
        self.assertIn("<select data-rowbreak>", mp)
        self.assertIn('laneHtml("opener", trackHtml("opener", opener, STATE.anchorIdx, ""))', mp)
        self.assertIn("const rows = loopRows(loop, rowBreakName());", mp)
        self.assertNotIn("rowbreak", self.builder.lower())

    def test_rule_form_shared_by_builder_and_map(self):
        mp = rotation_builder.MAP_UI_PATH.read_text(encoding="utf-8")
        js = rotation_builder.RULE_FORM_JS_PATH.read_text(encoding="utf-8")
        for page in (self.builder, mp):
            self.assertIn('<script src="rule_form.js"></script>', page)
            self.assertIn("RuleForm.fieldsHtml(", page)
            self.assertIn("RuleForm.readValue(key)", page)
        # the form's element ids exist only in the shared script
        self.assertIn('"ruleBuffInput"', js)
        self.assertNotIn("ruleBuffInput", self.builder)
        build = (rotation_builder.SWTORSIM_ROOT / "tools" / "build_web_release.py").read_text(encoding="utf-8")
        self.assertIn('DIST_DIR / "rule_form.js"', build)

    def test_builder_undo_tracks_every_rotation_change(self):
        # renderTimeline queues vizOnRotationChanged, which records the undo snapshot before broadcasting.
        self.assertRegex(self.builder, r"function vizOnRotationChanged\(\) \{\s+undoTrack\(\);\s+vizMapRev \+= 1;")
        self.assertIn("queueMicrotask(vizOnRotationChanged);", self.builder)
        self.assertEqual(self.builder.count("undoResetHistory();"), 2)  # server load and local file import

    def test_step_index_skips_loop_anchor_on_both_sides(self):
        # Dry-run step_index counts executable steps only (Rotation.build_steps skips loop_anchor).
        self.assertIn('if (s.type === "loop_anchor") { loopStart = out.length; return; }', self.builder)
        self.assertIn('if (s.type === "loop_anchor") { loopStart = seq.length; return; }', self.timeline)


def _dry_run(config_path, duration=30.0):
    import contextlib
    import io
    import json

    from data.rotation_builder import run_dry_run_preview

    root = rotation_builder.SWTORSIM_ROOT
    cfg = json.loads((root / config_path).read_text(encoding="utf-8"))
    rot = json.loads((root / cfg["rotation_path"]).read_text(encoding="utf-8"))
    payload = dict(cfg)
    if isinstance(rot, dict):
        payload["rotation"] = rot.get("sequence") or rot.get("steps") or []
        payload["pre_combat"] = rot.get("pre_combat")
        for k in ("pull_conditions", "pull_max_wait"):
            if k in rot:
                payload[k] = rot[k]
    else:
        payload["rotation"] = rot
    payload["env"] = "live"
    payload["duration"] = duration
    # The preview sets process-wide engine toggles (stem matching); restore them so later tests see the defaults.
    saved_settings = settings.snapshot_engine_settings()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return run_dry_run_preview(payload)
    finally:
        settings.apply_engine_settings(saved_settings)


class DryRunActivationTimingTests(unittest.TestCase):
    """Dry-run casts carry activation kind, real GCD, busy time and end time for the Cast Timeline."""

    @classmethod
    def setUpClass(cls):
        cls.sniper = _dry_run("data/run_config/Marksmanship.json")
        cls.hatred = _dry_run("data/run_config/Hatred.json")

    def _check_common(self, casts):
        for c in casts:
            self.assertIn(c["activation"], ("instant", "cast", "channel"))
            self.assertGreaterEqual(c["busy"], 0.0)
            # "time" is rounded to 0.01s, "end_time" to 0.001s
            self.assertGreaterEqual(c["end_time"] + 0.01, c["time"])
            self.assertAlmostEqual(c["combat_end_time"] - c["combat_time"], c["end_time"] - c["time"], delta=0.02)
            if c["activation"] == "instant":
                self.assertEqual(c["busy"], 0.0)
                self.assertFalse(c["clipped"])
            if not c["clipped"]:
                self.assertAlmostEqual(c["end_time"] - c["time"], c["busy"], delta=0.01)
            if c["triggers_gcd"]:
                self.assertGreater(c["gcd"], 0.0)
            else:
                self.assertEqual(c["gcd"], 0.0)

    def test_sniper_has_casts_and_channels_with_ticks(self):
        casts = self.sniper["casts"]
        self._check_common(casts)
        kinds = {c["activation"] for c in casts}
        self.assertIn("cast", kinds)
        self.assertIn("channel", kinds)
        for c in casts:
            if c["activation"] == "channel":
                self.assertGreater(c["ticks_total"], 0)
                self.assertGreater(c["tick_interval"], 0.0)
                self.assertAlmostEqual(c["ticks_total"] * c["tick_interval"], c["busy"], delta=0.02)
                self.assertLessEqual(c["ticks"], c["ticks_total"])

    def test_next_gcd_cast_never_starts_before_previous_activation_ends(self):
        gcd_casts = [c for c in self.sniper["casts"] if c["triggers_gcd"]]
        for prev, nxt in zip(gcd_casts, gcd_casts[1:]):
            self.assertGreaterEqual(nxt["time"] + 0.01, prev["end_time"], f"{prev['ability']} -> {nxt['ability']}")
            self.assertGreaterEqual(nxt["time"] + 0.01, prev["time"] + prev["gcd"], f"{prev['ability']} -> {nxt['ability']}")

    def test_instant_only_rotation(self):
        casts = self.hatred["casts"]
        self._check_common(casts)
        self.assertEqual({c["activation"] for c in casts}, {"instant"})


class SimulatorCastTimelineTests(unittest.TestCase):
    """Combat Simulator single run carries a cast_timeline payload; its server serves the page."""

    @classmethod
    def setUpClass(cls):
        import contextlib
        import io
        import os

        from src.swtorsim.config_load import load_from_run_config
        from src.swtorsim.run_config import load_run_config
        from src.swtorsim.web_gui import _run_single_test_detailed

        root = rotation_builder.SWTORSIM_ROOT
        prev = os.getcwd()
        # Loading the run config sets process-wide engine toggles; restore them so later tests see the defaults.
        saved_settings = settings.snapshot_engine_settings()
        os.chdir(root)
        try:
            cfg = load_run_config(str(root / "data/run_config/Marksmanship.json"))
            cfg.duration = 20
            inputs = load_from_run_config(cfg)
            with contextlib.redirect_stdout(io.StringIO()):
                cls.result = _run_single_test_detailed(
                    cfg,
                    {
                        "rotation_config": inputs.rotation_config,
                        "stats_config": inputs.stats_config,
                        "loadout_blueprints": inputs.loadout_blueprints,
                        "debuff_module": inputs.debuff_module,
                    },
                )
        finally:
            settings.apply_engine_settings(saved_settings)
            os.chdir(prev)

    def test_cast_timeline_payload(self):
        ct = self.result["cast_timeline"]
        casts = ct["casts"]
        log_casts = [ev for ev in self.result["combat_log"] if ev["category"] == "cast"]
        self.assertEqual(len(casts), len(log_casts))
        self.assertTrue(ct["rotation"])
        kinds = {c["activation"] for c in casts}
        self.assertIn("cast", kinds)
        self.assertIn("channel", kinds)
        for c in casts:
            self.assertIn("combat_time", c)
            self.assertIn("combat_end_time", c)
            self.assertIn(c["slug"], ct["names"])
        # every rotation ability id maps to a slug; icons resolve for the abilities actually cast
        for step in ct["rotation"]:
            for p in step.get("pool") or [step]:
                if p.get("ability_id"):
                    self.assertIn(p["ability_id"], ct["slugs"])
        self.assertTrue(any(c["slug"] in ct["icons"] for c in casts))
        for b in ct["buff_windows"]:
            for start, end in b["windows"]:
                self.assertLessEqual(start, end)

    def test_cast_times_match_combat_log(self):
        log_times = sorted(ev["time"] for ev in self.result["combat_log"] if ev["category"] == "cast")
        tl_times = sorted(c["combat_time"] for c in self.result["cast_timeline"]["casts"])
        for a, b in zip(log_times, tl_times):
            self.assertAlmostEqual(a, b, delta=0.011)

    def test_simulator_server_serves_timeline_page(self):
        from src.swtorsim.web_gui import SimulatorRequestHandler

        server = ThreadingHTTPServer(("127.0.0.1", 0), SimulatorRequestHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/timeline.html?source=sim"
            with urllib.request.urlopen(url, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                self.assertIn(b"<title>SwtorSim - Cast Timeline</title>", resp.read())
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
