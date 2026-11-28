"""Rotation-wide default lead time: engine default 0.1s, overridable by the rotation file's default_lead_time."""

import re
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.swtorsim.rotation_builder import build_rotation_file_data, normalize_default_lead
from src.swtorsim.entities import Dummy, Player
from src.swtorsim.rotation import DEFAULT_OFF_GCD_LEAD_TIME, Rotation, resolve_default_lead_time

ROOT = Path(__file__).resolve().parents[1]
BUILDER_UI = ROOT / "tools" / "rotation_builder_ui.html"

STEPS = [{"type": "fixed", "ability_id": "off"}]


def _gcd_player():
    p = Player("T")
    p.ability_db["filler"] = SimpleNamespace(name="filler", fqn="abl.test.filler", triggers_gcd=True)
    p.ability_db["off"] = SimpleNamespace(name="off", fqn="abl.test.off", triggers_gcd=False)
    p.current_target = Dummy("D", 1000)
    return p


class EngineDefaultLeadTests(unittest.TestCase):
    def setUp(self):
        self.p = _gcd_player()
        self.sim = SimpleNamespace(current_time=1.0)

    def lead(self, config):
        return Rotation("r", config).get_next_lead_time(self.p, 1.0, self.sim)

    def test_engine_default_is_point_one(self):
        self.assertEqual(DEFAULT_OFF_GCD_LEAD_TIME, 0.1)
        self.assertEqual(self.lead(STEPS), 0.1)
        self.assertEqual(self.lead({"sequence": STEPS}), 0.1)

    def test_rotation_default_applies_to_steps_without_lead(self):
        self.assertEqual(self.lead({"sequence": STEPS, "default_lead_time": 0.3}), 0.3)
        optional = [{"type": "optional", "ability_id": "off", "rules": {}}]
        self.assertEqual(self.lead({"sequence": optional, "default_lead_time": 0.25}), 0.25)

    def test_rotation_default_applies_to_priority_pool(self):
        block = {"type": "priority_block", "name": "PB", "pool": [{"ability_id": "off"}, {"ability_id": "filler"}]}
        self.assertEqual(self.lead({"sequence": [block], "default_lead_time": 0.3}), 0.3)
        # The block's own lead still wins over the rotation default.
        self.assertEqual(self.lead({"sequence": [dict(block, lead_time=0.2)], "default_lead_time": 0.3}), 0.2)

    def test_rotation_default_applies_to_weave_entry(self):
        config = {"sequence": [{"type": "fixed", "ability_id": "filler"}],
                  "weave": [{"ability_id": "off", "rules": {}}], "default_lead_time": 0.35}
        self.assertEqual(self.lead(config), 0.35)

    def test_step_lead_overrides_rotation_default(self):
        steps = [{"type": "fixed", "ability_id": "off", "lead_time": 0.05}]
        self.assertEqual(self.lead({"sequence": steps, "default_lead_time": 0.3}), 0.05)
        zero = [{"type": "fixed", "ability_id": "off", "lead_time": 0}]
        self.assertEqual(self.lead({"sequence": zero, "default_lead_time": 0.3}), 0.0)

    def test_on_gcd_step_has_no_lead_regardless_of_default(self):
        steps = [{"type": "fixed", "ability_id": "filler"}]
        self.assertEqual(self.lead({"sequence": steps, "default_lead_time": 0.3}), 0.0)

    def test_invalid_default_falls_back_to_engine_default(self):
        for bad in (-0.2, "abc", None):
            self.assertEqual(resolve_default_lead_time({"sequence": STEPS, "default_lead_time": bad}), 0.1)
        self.assertEqual(resolve_default_lead_time({"sequence": STEPS, "default_lead_time": 0}), 0.0)


class BuilderDefaultLeadTests(unittest.TestCase):
    def test_normalize_default_lead(self):
        self.assertEqual(normalize_default_lead({"default_lead_time": "0.2"}), {"default_lead_time": 0.2})
        self.assertEqual(normalize_default_lead({"default_lead_time": 0}), {"default_lead_time": 0.0})
        self.assertEqual(normalize_default_lead({}), {})
        self.assertEqual(normalize_default_lead({"default_lead_time": -1}), {})
        self.assertEqual(normalize_default_lead({"default_lead_time": "x"}), {})
        self.assertEqual(normalize_default_lead(STEPS), {})

    def test_file_data_wraps_when_default_lead_set(self):
        self.assertEqual(build_rotation_file_data(STEPS, None), STEPS)
        self.assertEqual(
            build_rotation_file_data(STEPS, None, default_lead_time=0.2),
            {"default_lead_time": 0.2, "sequence": STEPS},
        )

    def test_file_data_round_trips_into_rotation(self):
        data = build_rotation_file_data(STEPS, None, default_lead_time=0.45)
        self.assertEqual(Rotation("r", data).default_lead_time, 0.45)

    def test_builder_ui_default_matches_engine(self):
        html = BUILDER_UI.read_text(encoding="utf-8")
        match = re.search(r"const ENGINE_DEFAULT_LEAD_TIME = ([0-9.]+);", html)
        self.assertIsNotNone(match)
        self.assertEqual(float(match.group(1)), DEFAULT_OFF_GCD_LEAD_TIME)


if __name__ == "__main__":
    unittest.main()
