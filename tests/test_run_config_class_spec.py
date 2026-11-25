"""Saved run configs keep a single class key and a single spec key."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.swtorsim.web_gui import load_run_config_bundle, normalize_saved_run_config

MARKSMANSHIP_SPEC = "data/extractor/live/disciplines/sniper/marksmanship.json"


class RunConfigClassSpecTests(unittest.TestCase):
    def test_placeholder_pair_is_replaced_from_the_discipline(self):
        body = {
            "class": "",
            "class_name": "",
            "spec": "-- Select Discipline --",
            "spec_name": "-- Select Discipline --",
            "spec_path": MARKSMANSHIP_SPEC,
            "stats_path": "data/builds/L80_14gcd_yellow.json",
        }
        out = normalize_saved_run_config(body)
        self.assertIs(out, body)
        self.assertEqual(list(out)[:2], ["class", "spec"])
        self.assertEqual(out["class"], "Sniper")
        self.assertEqual(out["spec"], "Marksmanship")
        self.assertNotIn("class_name", out)
        self.assertNotIn("spec_name", out)
        self.assertEqual(out["spec_path"], MARKSMANSHIP_SPEC)
        self.assertEqual(out["stats_path"], "data/builds/L80_14gcd_yellow.json")

    def test_explicit_class_and_spec_win_and_name_copies_are_dropped(self):
        body = {
            "spec_path": MARKSMANSHIP_SPEC,
            "class": "Gunslinger",
            "class_name": "Sniper",
            "spec": "Dirty Fighting",
            "spec_name": "Marksmanship",
        }
        out = normalize_saved_run_config(body)
        self.assertEqual(out["class"], "Gunslinger")
        self.assertEqual(out["spec"], "Dirty Fighting")
        self.assertNotIn("class_name", out)
        self.assertNotIn("spec_name", out)
        self.assertEqual(list(out)[:2], ["class", "spec"])

    def test_legacy_name_keys_fold_into_class_and_spec(self):
        body = {"class_name": "Sniper", "spec_name": "Marksmanship", "seed": 42}
        out = normalize_saved_run_config(body)
        self.assertEqual(out, {"class": "Sniper", "spec": "Marksmanship", "seed": 42})

    def test_bundle_does_not_inject_duplicate_keys(self):
        bundle = load_run_config_bundle("data/run_config/Marksmanship.json")
        raw = bundle["run_config"]
        self.assertEqual(raw["class"], "Sniper")
        self.assertEqual(raw["spec"], "Marksmanship")
        self.assertNotIn("class_name", raw)
        self.assertNotIn("spec_name", raw)
        self.assertEqual(bundle["class_name"], "Sniper")
        self.assertEqual(bundle["spec"], "Marksmanship")

    def test_bundle_still_reads_legacy_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.json"
            path.write_text(
                json.dumps({"class_name": "Sniper", "spec_name": "Marksmanship", "seed": 7}),
                encoding="utf-8",
            )
            bundle = load_run_config_bundle(str(path))
        raw = bundle["run_config"]
        self.assertEqual(bundle["class_name"], "Sniper")
        self.assertEqual(bundle["spec"], "Marksmanship")
        self.assertEqual(raw["class_name"], "Sniper")
        self.assertEqual(raw["spec_name"], "Marksmanship")
        self.assertNotIn("class", raw)
        self.assertNotIn("spec", raw)

    def test_shipped_run_configs_use_one_class_and_one_spec(self):
        files = sorted((ROOT / "data" / "run_config").glob("*.json"))
        self.assertTrue(files)
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("class", data, path.name)
            self.assertIn("spec", data, path.name)
            self.assertNotIn("class_name", data, path.name)
            self.assertNotIn("spec_name", data, path.name)
            self.assertFalse(str(data["class"]).lower().startswith("-- select"), path.name)
            self.assertFalse(str(data["spec"]).lower().startswith("-- select"), path.name)


if __name__ == "__main__":
    unittest.main()
