"""Extractor condition-logic filtering: dropped conditions (range, alive, enemy, ...) count as satisfied."""

import json
import sys
import unittest
from pathlib import Path

SWTORSIM_ROOT = Path(__file__).resolve().parents[1]
if str(SWTORSIM_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(SWTORSIM_ROOT / "src"))

from extractor.abilities import ALWAYS_TRUE_LOGIC, _branch_conditions, _filter_condition_logic

KEPT = {"suit", "charges"}


def leaf(cid):
    return {"condition": cid}


class FilterConditionLogicTests(unittest.TestCase):
    def test_or_with_dropped_leaf_is_true(self):
        # InRange OR (InRange2 AND HasAbility)  ->  true (in range is assumed)
        logic = {"op": "or", "operands": [leaf("range10"), {"op": "and", "operands": [leaf("range20"), leaf("suit")]}]}
        self.assertIs(_filter_condition_logic(logic, KEPT), ALWAYS_TRUE_LOGIC)

    def test_and_drops_dropped_leaf(self):
        logic = {"op": "and", "operands": [leaf("alive"), leaf("charges")]}
        self.assertEqual(_filter_condition_logic(logic, KEPT), leaf("charges"))

    def test_and_with_true_or_keeps_other_operands(self):
        # charges AND (InRange OR (InRange2 AND suit))  ->  charges
        logic = {"op": "and", "operands": [
            leaf("charges"),
            {"op": "or", "operands": [leaf("range10"), {"op": "and", "operands": [leaf("range20"), leaf("suit")]}]},
        ]}
        self.assertEqual(_filter_condition_logic(logic, KEPT), leaf("charges"))

    def test_or_of_kept_leaves_unchanged(self):
        logic = {"op": "or", "operands": [leaf("charges"), leaf("suit")]}
        self.assertEqual(_filter_condition_logic(logic, KEPT), logic)

    def test_none_logic_stays_none(self):
        self.assertIsNone(_filter_condition_logic(None, KEPT))


class ShoulderCannonMissileGateTests(unittest.TestCase):
    RAW = SWTORSIM_ROOT / "data" / "extractor" / "live" / "extracted" / "abl" / "bounty_hunter" / "shoulder_cannon_custom_17_1.json"

    @unittest.skipUnless(RAW.is_file(), "live extracted data not present")
    def test_missile_header_has_no_efficient_suit_gate(self):
        # Raw gate: IsAlive AND IsEnemy AND (InRange[10m] OR (InRange[20m] AND HasAbility efficient_suit)).
        data = json.loads(self.RAW.read_text(encoding="utf-8"))
        subs = next(f for f in data["fields"] if f["name"] == "effSubEffects")["value"]["list"]
        _marker, conditions = _branch_conditions(subs[0], context="test")
        self.assertIsNone(conditions)


if __name__ == "__main__":
    unittest.main()
