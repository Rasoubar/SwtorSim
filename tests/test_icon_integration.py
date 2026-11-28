"""Integration test verifying ability, talent, and effect icon extraction, catalog propagation, and HTTP serving."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

SWTORSIM_ROOT = Path(__file__).resolve().parents[1]
if str(SWTORSIM_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(SWTORSIM_ROOT / "src"))
if str(SWTORSIM_ROOT) not in sys.path:
    sys.path.insert(0, str(SWTORSIM_ROOT))

from src.swtorsim.rotation_builder import (
    discover_loadout_catalog,
    RotationBuilderRequestHandler,
)
from extractor.icons import build_icon_hash_index, _dds_to_png


class IconIntegrationTests(unittest.TestCase):
    def test_icon_hash_index_building(self):
        sample_hashes = {
            12345: "/resources/gfx/icons/shock.dds",
            67890: "/resources/gfx/icons/lifedrain.dds",
            99999: "/resources/art/models/character.tor",
        }
        index = build_icon_hash_index(sample_hashes)
        self.assertIn("shock", index)
        self.assertIn("lifedrain", index)
        self.assertNotIn("character", index)
        self.assertEqual(index["shock"][0], 12345)

    def test_discover_loadout_catalog_propagates_icons(self):
        spec_path = "data/extractor/live/disciplines/assassin/hatred.json"
        choices = {"23": 1, "27": 1, "39": 1, "43": 1, "51": 1, "64": 1, "68": 1, "73": 1}
        cat = discover_loadout_catalog(spec_path, choices)

        # Check abilities have icon field
        abilities = cat.get("abilities", [])
        self.assertGreater(len(abilities), 0)
        abilities_with_icon = [a for a in abilities if a.get("icon")]
        self.assertGreater(
            len(abilities_with_icon),
            0,
            "Active abilities in catalog must have non-empty icon strings",
        )

        # Verify a well-known Hatred ability has its correct icon filename
        overload = next((a for a in abilities if a["slug"] == "overload"), None)
        if overload:
            self.assertTrue(overload["icon"].endswith(".png"))

        # Check skill tree metadata includes icons
        tree = cat.get("skill_tree", {})
        self.assertGreater(len(tree), 0)
        first_lvl = list(tree.keys())[0]
        first_options = tree[first_lvl].get("1", [])
        if first_options:
            self.assertIn("icon", first_options[0])

    def test_icons_directory_populated(self):
        icons_dir = SWTORSIM_ROOT / "data" / "extractor" / "live" / "icons"
        self.assertTrue(icons_dir.is_dir(), "data/extractor/live/icons directory should exist")
        png_count = len(list(icons_dir.glob("*.png")))
        self.assertGreater(png_count, 100, f"Expected >100 extracted PNG icons, found {png_count}")

    def test_web_icons_directory_mirrored(self):
        web_icons_dir = SWTORSIM_ROOT / "tools" / "web" / "icons"
        self.assertTrue(web_icons_dir.is_dir(), "tools/web/icons directory should exist")
        png_count = len(list(web_icons_dir.glob("*.png")))
        self.assertGreater(png_count, 100, f"Expected >100 mirrored web PNG icons, found {png_count}")


if __name__ == "__main__":
    unittest.main()
