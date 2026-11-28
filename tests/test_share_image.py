"""Share Image: results carry a rotation_snapshot (structure + icon/name/off-GCD maps) for the PNG card."""

import contextlib
import io
import os
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.swtorsim import settings
from src.swtorsim.cast_timeline import rotation_snapshot, rotation_steps_of

ROOT = Path(__file__).resolve().parents[1]


def _abl(name, fqn, icon=None, triggers_gcd=True):
    return SimpleNamespace(name=name, fqn=fqn, blueprint=SimpleNamespace(icon=icon), triggers_gcd=triggers_gcd)


class RotationSnapshotUnitTests(unittest.TestCase):
    def setUp(self):
        self.player = SimpleNamespace(
            ability_db={
                "channel_hatred": _abl("Channel Hatred", "abl.a.channel_hatred", "ico_hatred"),
                "force_camouflage": _abl("Force Camouflage", "abl.a.force_camouflage", "ico_camo", False),
                "rupture": _abl("Rupture", "abl.a.rupture", "ico_rupture"),
                "berserk": _abl("Berserk", "abl.a.berserk", None, False),
            }
        )
        self.config = {
            "pre_combat": [
                {"ability": "channel_hatred"},
                {"swap_tactical": "abl.itm.tactical.x"},
                {"ability": "force_camouflage"},
                {"wait": 8},
            ],
            "sequence": [
                {"type": "fixed", "ability_id": "rupture"},
                {"type": "loop_anchor"},
                {"type": "priority_block", "name": "W", "pool": [{"ability_id": "berserk", "rules": {}}]},
            ],
            "weave": [{"ability_id": "berserk", "rules": {}}],
        }

    def test_structure_is_passed_through(self):
        snap = rotation_snapshot(self.config, self.player)
        self.assertEqual(snap["pre_combat"], self.config["pre_combat"])
        self.assertEqual(snap["sequence"], rotation_steps_of(self.config))
        self.assertEqual(snap["weave"], self.config["weave"])

    def test_pre_combat_and_sequence_abilities_get_names_and_icons(self):
        snap = rotation_snapshot(self.config, self.player)
        for aid in ("channel_hatred", "force_camouflage", "rupture", "berserk"):
            self.assertIn(aid, snap["slugs"])
        self.assertEqual(snap["names"]["channel_hatred"], "Channel Hatred")
        self.assertEqual(snap["icons"]["channel_hatred"], "ico_hatred")
        self.assertNotIn("berserk", snap["icons"])  # no icon in the blueprint

    def test_off_gcd_lists_only_referenced_off_gcd_abilities(self):
        snap = rotation_snapshot(self.config, self.player)
        self.assertEqual(snap["off_gcd"], {"force_camouflage": True, "berserk": True})

    def test_plain_list_rotation(self):
        snap = rotation_snapshot([{"type": "fixed", "ability_id": "rupture"}], self.player)
        self.assertEqual(snap["pre_combat"], [])
        self.assertEqual(snap["weave"], [])
        self.assertEqual(len(snap["sequence"]), 1)


class ResultRotationSnapshotTests(unittest.TestCase):
    """TEST and BATCH simulator results both carry rotation_snapshot."""

    @classmethod
    def setUpClass(cls):
        from src.swtorsim.config_load import load_from_run_config
        from src.swtorsim.run_config import load_run_config
        from src.swtorsim.web_gui import _run_batch_monte_carlo_detailed, _run_single_test_detailed

        prev = os.getcwd()
        saved_settings = settings.snapshot_engine_settings()
        os.chdir(ROOT)
        try:
            cfg = load_run_config(str(ROOT / "data/run_config/Marksmanship.json"))
            cfg.duration = 20
            cfg.iterations = 1
            inputs = load_from_run_config(cfg)
            sim_inputs = {
                "rotation_config": inputs.rotation_config,
                "stats_config": inputs.stats_config,
                "loadout_blueprints": inputs.loadout_blueprints,
                "debuff_module": inputs.debuff_module,
            }
            cls.rotation_config = inputs.rotation_config
            with contextlib.redirect_stdout(io.StringIO()):
                cls.test_result = _run_single_test_detailed(cfg, sim_inputs)
                cls.batch_result = _run_batch_monte_carlo_detailed(cfg, sim_inputs)
        finally:
            settings.apply_engine_settings(saved_settings)
            os.chdir(prev)

    def _check(self, snap):
        self.assertEqual(snap["sequence"], rotation_steps_of(self.rotation_config))
        for step in snap["sequence"]:
            for p in step.get("pool") or [step]:
                if p.get("ability_id"):
                    self.assertIn(p["ability_id"], snap["slugs"])
        self.assertTrue(snap["icons"])

    def test_test_result_has_snapshot(self):
        self._check(self.test_result["rotation_snapshot"])

    def test_batch_result_has_snapshot(self):
        self.assertEqual(self.batch_result["mode"], "BATCH")
        self._check(self.batch_result["rotation_snapshot"])


class ShareImageUiContractTests(unittest.TestCase):
    """tools/share_image.js draws the images; the simulator and the builder load it and open it."""

    @staticmethod
    def _read(*parts):
        return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")

    def test_dashboard_wires_share_image(self):
        html = self._read("tools", "simulator_ui.html")
        self.assertIn('<script src="share_image.js"></script>', html)
        self.assertIn('id="shareImageBtn"', html)
        self.assertIn("function openShareImage()", html)
        self.assertIn("ShareImage.open(ACTIVE_RESULT, { placement: true", html)
        self.assertIn("ACTIVE_RESULT._shareContext = captureShareContext(payload);", html)

    def test_builder_wires_rotation_image(self):
        html = self._read("tools", "rotation_builder_ui.html")
        self.assertIn('<script src="share_image.js"></script>', html)
        self.assertIn('id="rotationImageBtn"', html)
        self.assertIn("function builderRotationSnapshot()", html)
        self.assertIn("rotation_snapshot: builderRotationSnapshot()", html)
        self.assertIn("ShareImage.open(", html)

    def test_shared_script_dialog_choices(self):
        js = self._read("tools", "share_image.js")
        self.assertIn("global.ShareImage = { open: openShareDialog", js)
        for needle in (
            'id="shareOptRotation"',
            '<option value="card">',
            '<option value="separate">',
            '<option value="off">',
            'id="shareOptStyle"',
            '<option value="compact">',
            'kind: "rotation"',
        ):
            self.assertIn(needle, js)
        # The ability breakdown is always on the summary card.
        self.assertNotIn("shareOptBreakdown", js)

    def test_web_release_copies_share_image(self):
        self.assertIn('DIST_DIR / "share_image.js"', self._read("tools", "build_web_release.py"))


class ShareImageScriptRouteTests(unittest.TestCase):
    """Both local servers serve /share_image.js."""

    def _get_script(self, handler_cls):
        import threading
        import urllib.request
        from http.server import ThreadingHTTPServer

        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/share_image.js"
            with urllib.request.urlopen(url, timeout=5) as resp:
                return resp.status, resp.headers.get("Content-Type", ""), resp.read().decode("utf-8")
        finally:
            server.shutdown()
            server.server_close()

    def _check(self, handler_cls):
        status, ctype, body = self._get_script(handler_cls)
        self.assertEqual(status, 200)
        self.assertIn("javascript", ctype)
        self.assertIn("global.ShareImage", body)

    def test_simulator_serves_share_image_js(self):
        from src.swtorsim.web_gui import SimulatorRequestHandler

        self._check(SimulatorRequestHandler)

    def test_builder_serves_share_image_js(self):
        from src.swtorsim.rotation_builder import RotationBuilderRequestHandler

        self._check(RotationBuilderRequestHandler)


if __name__ == "__main__":
    unittest.main()
