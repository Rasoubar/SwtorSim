"""Regression tests for bug-hunt Medium #11-#13 (Pyodide bridge parity, WASM save routes, custom file delete/sync)."""

import json
import re
import unittest
from pathlib import Path

from src.swtorsim import pyodide_bridge, web_gui

ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _route_block(js, route_marker, length=2600):
    start = js.index(route_marker)
    return js[start : start + length]


class BridgeBuildStatsParityTests(unittest.TestCase):
    """#11: GET_BUILD_STATS returns the same raw build JSON as the native /api/build_stats route."""

    def test_bridge_returns_raw_build_without_force_tech_expansion(self):
        rel = "data/builds/L80_14gcd_yellow.json"
        out = json.loads(pyodide_bridge.dispatch("GET_BUILD_STATS", json.dumps({"path": rel})))
        native = web_gui.load_json_file(str(web_gui._resolve_workspace_path(rel)))
        self.assertEqual(out["stats"], native)
        self.assertIn("Force-Tech Power", out["stats"])
        self.assertNotIn("Tech Power", out["stats"])

    def test_bridge_missing_build_reports_error(self):
        out = json.loads(pyodide_bridge.dispatch("GET_BUILD_STATS", json.dumps({"path": "data/builds/nope.json"})))
        self.assertIn("error", out)

    def test_builder_run_config_prefers_choices_override(self):
        from data import rotation_builder as rb

        res = rb.load_builder_run_config("data/run_config/Hatred.json")
        raw = res["run_config"]
        expected = raw.get("choices_override") or raw.get("choices") or {}
        self.assertEqual(res["choices"], {str(k): v for k, v in expected.items()})


class WasmSaveRouteTests(unittest.TestCase):
    """#12: saving a run config or build in the browser build stores it and returns a path."""

    def setUp(self):
        self.js = _read("tools/web/pyodide_client.js")
        self.block = _route_block(self.js, 'pathname === "/api/run_config/save"')

    def test_save_response_carries_a_path(self):
        self.assertRegex(self.block, r"ok: true,\s*path")
        self.assertNotIn("{ ok: true, filename, downloaded: true }", self.block)

    def test_save_targets_custom_folders(self):
        self.assertIn("data/builds/custom/", self.block)
        self.assertIn("data/run_config/custom/", self.block)

    def test_save_persists_and_syncs_workers(self):
        self.assertIn("state.customFiles[", self.block)
        self.assertIn("saveCustomFilesToStorage(", self.block)
        self.assertIn("pushFileToWorkers(", self.block)


class WasmCustomFileDeleteTests(unittest.TestCase):
    """#13: delete removes only the chosen path; workers drop files deleted in another tab."""

    def setUp(self):
        self.js = _read("tools/web/pyodide_client.js")

    def test_delete_does_not_match_by_basename(self):
        block = _route_block(self.js, 'pathname === "/api/custom_file/delete"', 1200)
        self.assertNotIn('endsWith("/" + filename)', block)
        self.assertIn("delete state.customFiles[vPath]", block)

    def test_sync_removes_files_no_longer_stored(self):
        start = self.js.index("async function syncCustomFilesToWorker")
        end = self.js.index("function callSpecificWorker")
        body = self.js[start:end]
        self.assertIn("DELETE_VIRTUAL_FILE", body)
        self.assertIn("syncedPaths", body)

    def test_each_worker_tracks_synced_paths(self):
        start = self.js.index("const wState = {")
        self.assertIn("syncedPaths: new Set()", self.js[start : start + 600])

    def test_storage_snapshot_updated_on_local_save(self):
        start = self.js.index("function saveCustomFilesToStorage")
        self.assertIn("lastStorageSnapshot =", self.js[start : start + 400])
        decl = re.search(r"let lastStorageSnapshot", self.js)
        self.assertLess(decl.start(), start)


if __name__ == "__main__":
    unittest.main()
