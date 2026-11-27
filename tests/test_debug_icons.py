"""Debugger icons: lookup is safe, the name-to-icon map is built from the loadout, and the server serves PNGs only."""

import http.client
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.swtorsim.debug import debug_api
from src.swtorsim.debug.web_debugger import DebuggerRequestHandler

CONFIG = Path(__file__).resolve().parents[1] / "data" / "run_config" / "Hatred.json"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _bp(name, icon, effects=()):
    return SimpleNamespace(name=name, icon=icon, effects={i + 1: e for i, e in enumerate(effects)})


class IconLookupTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        for name in ("strike.png", "buff.png", "Mixed.PNG"):
            (Path(self.dir.name) / name).write_bytes(PNG)
        patcher = patch.object(debug_api, "ICON_DIRS", (Path(self.dir.name),))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_only_bare_png_names_resolve(self):
        self.assertIsNotNone(debug_api.find_icon("strike.png"))
        for bad in ("", "../strike.png", "a/strike.png", "..\\strike.png", "strike.txt", "strike", "strike.png/../x.png"):
            self.assertIsNone(debug_api.find_icon(bad), bad)

    def test_a_missing_file_is_not_found(self):
        self.assertIsNone(debug_api.find_icon("nope.png"))

    def test_map_names_abilities_and_effects_and_skips_missing_files(self):
        effect = SimpleNamespace(name="Strike Buff", icon="buff.png")
        no_icon_effect = SimpleNamespace(name="Inherits", icon=None)
        missing_effect = SimpleNamespace(name="Ghost", icon="ghost.png")
        blueprints = {"abl.strike": _bp("Strike", "strike.png", [effect, no_icon_effect, missing_effect])}
        icons = debug_api.icon_map(blueprints)
        self.assertEqual(icons["Strike"], "strike.png")
        self.assertEqual(icons["Strike Buff"], "buff.png")
        self.assertEqual(icons["Inherits"], "strike.png")  # an effect without its own icon uses its ability's
        self.assertNotIn("Ghost", icons)

    def test_an_ability_keeps_its_own_icon_over_a_same_named_effect(self):
        effect = SimpleNamespace(name="Strike", icon="buff.png")
        icons = debug_api.icon_map({"abl.strike": _bp("Strike", "strike.png", [effect])})
        self.assertEqual(icons["Strike"], "strike.png")


@unittest.skipUnless(CONFIG.is_file(), "Hatred run config not present")
class TraceIconTests(unittest.TestCase):
    def test_every_cast_and_hit_name_in_a_real_trace_has_an_icon(self):
        trace = debug_api.handle("trace", {"config": "Hatred"})
        icons = trace["icons"]
        self.assertTrue(icons)
        names = {e["ability"] for e in trace["events"] if e["type"] in ("cast_start", "damage_hit")}
        self.assertEqual([n for n in sorted(names) if n not in icons], [])
        for file in icons.values():
            self.assertIsNotNone(debug_api.find_icon(file), file)


class IconRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        (Path(cls.tmp.name) / "strike.png").write_bytes(PNG)
        cls.patch = patch.object(debug_api, "ICON_DIRS", (Path(cls.tmp.name),))
        cls.patch.start()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), DebuggerRequestHandler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.patch.stop()
        cls.tmp.cleanup()

    def _get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        conn.request("GET", path)
        res = conn.getresponse()
        body = res.read()
        conn.close()
        return res.status, res.getheader("Content-Type"), res.getheader("Cache-Control"), body

    def test_serves_a_png_with_caching(self):
        status, ctype, cache, body = self._get("/icons/strike.png")
        self.assertEqual((status, ctype), (200, "image/png"))
        self.assertIn("max-age", cache)
        self.assertEqual(body, PNG)

    def test_unknown_and_escaping_names_are_404(self):
        for path in ("/icons/nope.png", "/icons/..%2FCHANGELOG.md", "/icons/../CHANGELOG.md", "/icons/%2e%2e%2fstrike.png",
                     "/icons/strike.txt"):
            self.assertEqual(self._get(path)[0], 404, path)


if __name__ == "__main__":
    unittest.main()
