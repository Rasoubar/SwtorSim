"""Regression tests for bug-hunt High #1-#3 (Pyodide CSV bundle, dry-run env/debuffs, UI stats load)."""

import contextlib
import importlib.util
import io
import re
import unittest
from pathlib import Path

from data import rotation_builder
from data.rotation_builder import run_dry_run_preview
from src.swtorsim import settings

ROOT = Path(__file__).resolve().parents[1]
CHOICES = {"23": 2, "27": 3, "39": 2, "43": 1, "51": 1, "64": 1, "68": 3, "73": 1}


def _preview(payload):
    with contextlib.redirect_stdout(io.StringIO()):
        return run_dry_run_preview(payload)


class PyodideBundleIncludesStatMapTests(unittest.TestCase):
    """#1: WASM has no stat map without the CSV, so stats 65/67 stay raw numeric IDs."""

    def test_modifier_id_mapping_is_bundled(self):
        spec = importlib.util.spec_from_file_location("bundle_pyodide_assets", ROOT / "tools" / "bundle_pyodide_assets.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        pairs = dict(mod.INCLUDE_FILES)
        self.assertEqual(pairs.get("data/modifier_id_mapping.csv"), "data/modifier_id_mapping.csv")
        self.assertTrue((ROOT / "data" / "modifier_id_mapping.csv").is_file())


class DryRunPreviewEnvironmentTests(unittest.TestCase):
    """#2: the dry-run preview must honor the payload environment and the decomposed raid debuffs."""

    def setUp(self):
        self.addCleanup(settings.set_data_environment, settings.get_data_environment())
        self.addCleanup(settings.set_stem_matching, settings.is_stem_matching_enabled())

    def test_pts_payload_sets_global_environment(self):
        settings.set_data_environment("live")
        _preview(
            {
                "env": "pts",
                "level": 85,
                "spec_path": "data/extractor/pts/disciplines/assassin/hatred.json",
                "choices": CHOICES,
                "rotation": [{"type": "fixed", "ability_id": "thrash"}],
                "duration": 10,
            }
        )
        self.assertEqual(settings.get_data_environment(), "pts")

    def test_live_payload_resets_environment_from_pts(self):
        settings.set_data_environment("pts")
        _preview(
            {
                "env": "live",
                "spec_path": "data/extractor/live/disciplines/assassin/hatred.json",
                "choices": CHOICES,
                "rotation": [{"type": "fixed", "ability_id": "thrash"}],
                "duration": 10,
            }
        )
        self.assertEqual(settings.get_data_environment(), "live")

    def test_target_has_debuff_matches_canonical_raid_debuff(self):
        result = _preview(
            {
                "env": "live",
                "spec_path": "data/extractor/live/disciplines/assassin/hatred.json",
                "choices": CHOICES,
                "rotation": [
                    {
                        "type": "optional",
                        "ability_id": "thrash",
                        "rules": {"target_has_debuff": "Assailable (Mental)"},
                    },
                    {"type": "fixed", "ability_id": "saber_strike"},
                ],
                "duration": 10,
            }
        )
        names = [c["ability"] for c in result["casts"]]
        self.assertIn("Thrash", names)


class SimulatorUiStatsLoadTests(unittest.TestCase):
    """#3: a partial stats_override must not be re-applied on top of the merged bundle.stats."""

    def test_override_only_applied_when_bundle_stats_missing(self):
        html = (ROOT / "tools" / "simulator_ui.html").read_text(encoding="utf-8")
        start = html.index("async function applyPresetRunConfig")
        body = html[start : start + 4000]
        m = re.search(r"if \(bundle\.stats\) \{(.*?)\n      \} else \{(.*?)\n      \}\n", body, re.S)
        self.assertIsNotNone(m, "bundle.stats branch with an else fallback not found")
        self.assertIn("applyStatsToInputs(bundle.stats)", m.group(1))
        self.assertNotIn("rawStatsOverride", m.group(1))
        self.assertIn("applyStatsToInputs(rawStatsOverride)", m.group(2))


if __name__ == "__main__":
    unittest.main()
