"""Unit tests for the extracted ``random_chance`` condition (extractor field is ``percent_chance``)."""

import random
import unittest
from unittest import mock

from src.swtorsim.requirements import evaluate_single_extracted_condition


def _roll(floats, roll):
    """Evaluates a random_chance condition with random.random() pinned to ``roll``."""
    item = {"type": "random_chance", "negated": False, "floats": floats}
    with mock.patch("src.swtorsim.requirements.random.random", return_value=roll):
        return evaluate_single_extracted_condition(item, None, None)


class RandomChanceConditionTests(unittest.TestCase):
    def test_percent_chance_is_a_percent_not_a_fraction(self):
        """10.0 means 10%: a roll of 0.05 passes, 0.15 fails (it used to always pass)."""
        self.assertTrue(_roll({"percent_chance": 10.0}, 0.05))
        self.assertFalse(_roll({"percent_chance": 10.0}, 0.15))

    def test_percent_chance_extremes(self):
        self.assertTrue(_roll({"percent_chance": 100.0}, 0.999999))
        self.assertFalse(_roll({"percent_chance": 0.0}, 0.0))

    def test_legacy_fraction_key_still_honored(self):
        self.assertTrue(_roll({"chance": 0.3}, 0.2))
        self.assertFalse(_roll({"chance": 0.3}, 0.4))

    def test_missing_chance_defaults_to_always(self):
        self.assertTrue(_roll({}, 0.999999))

    def test_pass_rate_matches_percent(self):
        """Unpinned RNG: a 10% condition passes roughly 10% of the time."""
        item = {"type": "random_chance", "negated": False, "floats": {"percent_chance": 10.0}}
        random.seed(1234)
        passes = sum(evaluate_single_extracted_condition(item, None, None) for _ in range(20000))
        self.assertAlmostEqual(passes / 20000, 0.10, delta=0.01)


if __name__ == "__main__":
    unittest.main()
