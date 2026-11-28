"""Browser build of the debugger: the page, the client routes, the bridge actions and the bundle agree with each other."""

import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import build_web_release  # noqa: E402
from tools.bundle_pyodide_assets import build_asset_bundle  # noqa: E402
from src.swtorsim.debug.debug_bridge import ACTIONS  # noqa: E402

CLIENT_JS = (ROOT / "tools" / "web" / "pyodide_client.js").read_text(encoding="utf-8")
DEBUGGER_HTML = (ROOT / "tools" / "debugger_ui.html").read_text(encoding="utf-8")
SIMULATOR_HTML = (ROOT / "tools" / "simulator_ui.html").read_text(encoding="utf-8")


class ClientBridgeAgreementTests(unittest.TestCase):
    def test_every_action_the_client_sends_exists_in_the_bridge(self):
        used = set(re.findall(r'"(DEBUG_[A-Z_]+)"', CLIENT_JS))
        self.assertTrue(used)
        self.assertEqual(sorted(used - set(ACTIONS)), [])

    def test_every_bridge_action_is_used_by_the_client(self):
        used = set(re.findall(r'"(DEBUG_[A-Z_]+)"', CLIENT_JS))
        self.assertEqual(sorted(set(ACTIONS) - used), [])

    def test_the_client_answers_every_route_the_page_calls(self):
        called = set(re.findall(r'api\("(/api/[a-z_]+)"', DEBUGGER_HTML))
        routes = set(re.findall(r'"(/api/[a-z_]+)"', CLIENT_JS))
        self.assertTrue(called)
        self.assertEqual(sorted(called - routes), [])

    def test_the_debugger_starts_only_one_worker_until_a_measurement_needs_more(self):
        self.assertIn('window.location.pathname.includes("debugger")', CLIENT_JS)
        self.assertIn("isBuilderPage || isDebuggerPage", CLIENT_JS)


class PageHandshakeTests(unittest.TestCase):
    def test_both_pages_use_the_same_messages(self):
        for name in ("swtorsim-debugger-ready", "swtorsim-debugger-setup"):
            self.assertIn(name, DEBUGGER_HTML)
            self.assertIn(name, SIMULATOR_HTML)

    def test_each_side_only_answers_the_window_it_dealt_with(self):
        self.assertIn("ev.source !== window.opener", DEBUGGER_HTML)
        self.assertIn("ev.source !== debuggerWindow", SIMULATOR_HTML)
        self.assertIn("debuggerOrigin", SIMULATOR_HTML)  # never "*" when handing over the setup

    def test_the_browser_build_also_hands_the_setup_over_through_local_storage(self):
        """No opener is needed (a reused tab or a blocked pop-up): same origin, so local storage carries it."""
        self.assertIn("swtorsim_debug_setup", DEBUGGER_HTML)
        self.assertIn("swtorsim_debug_setup", SIMULATOR_HTML)
        self.assertIn("?setup=1", SIMULATOR_HTML)
        self.assertIn('get("setup") === "1"', DEBUGGER_HTML)

    def test_the_native_simulator_starts_the_debugger_itself(self):
        """Pressing Debug must not ask the user to start anything: the page asks the server, which spawns the process."""
        self.assertIn("/api/launch_debugger", SIMULATOR_HTML)
        self.assertRegex(SIMULATOR_HTML, r'fetch\("/api/launch_debugger", \{ method: "POST"')  # the launch routes are POST routes
        self.assertNotIn("The debugger is not running", SIMULATOR_HTML)

    def test_the_debugger_shows_the_stat_sheet_and_gear_it_runs_with(self):
        self.assertIn('id="character"', DEBUGGER_HTML)
        self.assertIn("renderCharacter()", DEBUGGER_HTML)
        for field in ("d.mastery", "d.crit_rating", "d.alacrity_rating", "d.accuracy_rating", "g.tactical", "g.legendaries", "g.relics"):
            self.assertIn(field, DEBUGGER_HTML)

    def test_every_press_of_debug_opens_a_new_tab(self):
        self.assertIn('window.open(url, "_blank")', SIMULATOR_HTML)
        self.assertIn('window.open("about:blank", "_blank")', SIMULATOR_HTML)
        self.assertNotIn("swtorsim_debugger\"", SIMULATOR_HTML)  # no shared window name that would reuse a tab

    def test_the_debugger_shows_what_caused_each_event_and_orders_the_moment_box_by_it(self):
        for text in ("function causeHtml()", "Caused by", "shaped it", "function causeTree(", "kidsOf", "a.nodelink"):
            self.assertIn(text, DEBUGGER_HTML)
        self.assertIn("w.end_cause", DEBUGGER_HTML)  # a buff's end hangs under what ended it
        self.assertNotIn("CASCADE_INDENT", DEBUGGER_HTML)  # the fixed indent by kind is gone

    def test_both_pages_show_missed_hits(self):
        self.assertIn("data-logfilter=\"miss\"", SIMULATOR_HTML)
        self.assertIn('ev.category === "miss"', SIMULATOR_HTML)
        self.assertIn('id="ev-miss"', DEBUGGER_HTML)
        self.assertIn('e.type === "miss"', DEBUGGER_HTML)

    def test_the_simulator_has_the_button(self):
        self.assertIn('id="openDebuggerBtn"', SIMULATOR_HTML)

    def test_icons_are_relative_so_a_sub_path_deployment_works(self):
        self.assertIn('"icons/" + encodeURIComponent', DEBUGGER_HTML)
        self.assertNotIn('"/icons/"', DEBUGGER_HTML)
        self.assertIn("iconUrl(name, true)", DEBUGGER_HTML)

    def test_build_copies_pts_icons_and_lowercases_filenames(self):
        src = (ROOT / "tools" / "build_web_release.py").read_text(encoding="utf-8")
        self.assertIn('"pts" / "icons"', src)
        self.assertIn("icon_file.name.lower()", src)


class BuildTests(unittest.TestCase):
    def test_the_generated_engine_copy_is_current(self):
        self.assertTrue(build_web_release.check_debug_engine_is_current())

    def test_the_debugger_page_is_written_with_the_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(build_web_release.write_debugger_page(Path(tmp), 123))
            html = (Path(tmp) / "debugger.html").read_text(encoding="utf-8")
        self.assertIn('src="pyodide_client.js?v=123"', html)
        self.assertIn("<title>SwtorSim Debugger</title>", html)

    def test_the_asset_bundle_carries_the_debugger_and_its_generated_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_asset_bundle(Path(tmp) / "assets.zip")
            with zipfile.ZipFile(bundle) as zf:
                names = set(zf.namelist())
        expected = {
            "src/swtorsim/debug/debug_api.py",
            "src/swtorsim/debug/debug_bridge.py",
            "src/swtorsim/debug/debug_slices.py",
            "src/swtorsim/debug/generated/triggers_traced.py",
            "src/swtorsim/debug/generated/abilities_traced.py",
            "src/swtorsim/debug/generated/combat_math_traced.py",
        }
        self.assertEqual(sorted(expected - names), [])


if __name__ == "__main__":
    unittest.main()
