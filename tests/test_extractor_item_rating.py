"""Unit tests for the extractor's item-rating default (relic/adrenal amounts: PTS 380, otherwise 344)."""

import sys
import unittest
from pathlib import Path
from unittest import mock

SWTORSIM_ROOT = Path(__file__).resolve().parents[1]
if str(SWTORSIM_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(SWTORSIM_ROOT / "src"))

from extractor import cli
from extractor.config import DEFAULT_ITEM_RATING, PTS_ITEM_RATING, default_item_rating


def _config_for(argv):
    """Runs cli.main with extraction stubbed out and returns the ExtractorConfig it built."""
    with mock.patch.object(cli, "run_extraction") as run:
        self_code = cli.main(["--assets", "assets"] + argv)
    assert self_code == 0
    return run.call_args.args[0]


class ExtractorItemRatingTests(unittest.TestCase):
    def test_default_rating_helper(self):
        self.assertEqual(default_item_rating(False), DEFAULT_ITEM_RATING)
        self.assertEqual(default_item_rating(True), PTS_ITEM_RATING)
        self.assertEqual((DEFAULT_ITEM_RATING, PTS_ITEM_RATING), (344, 380))

    def test_live_run_defaults_to_344(self):
        self.assertEqual(_config_for([]).item_rating, 344)

    def test_pts_run_defaults_to_380(self):
        self.assertEqual(_config_for(["--pts"]).item_rating, 380)

    def test_explicit_rating_wins_on_both_environments(self):
        self.assertEqual(_config_for(["--item-rating", "340"]).item_rating, 340)
        self.assertEqual(_config_for(["--pts", "--item-rating", "362"]).item_rating, 362)


if __name__ == "__main__":
    unittest.main()
