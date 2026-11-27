"""Loadout loading pulls in abilities that loaded abilities trigger by name (execute_ability / custom hook)."""

import unittest
from pathlib import Path

from src.swtorsim.config_load import _referenced_ability_fqns, load_complete_loadout

ROOT = Path(__file__).resolve().parent.parent
LIVE_PARSED = str(ROOT / "data" / "extractor" / "live" / "parsed")
PTS_PARSED = str(ROOT / "data" / "extractor" / "pts" / "parsed")


class ReferencedAbilityScanTests(unittest.TestCase):
    def test_scan_finds_execute_ability_and_custom_hook_targets(self):
        node = {"effects": [{"branches": [{"actions": [
            {"action_type": "execute_ability", "ints": {"ability_spec": "abl.a.b", "from_actor": 2}},
            {"action_type": "custom", "ints": {"param1": 6855115466292073041, "param2": "abl.c.d"}},
            {"action_type": "custom", "ints": {"param1": 1, "param2": "abl.ignored"}},
            {"action_type": "execute_ability", "ints": {"ability_spec": 0}},
        ]}]}]}
        self.assertEqual(_referenced_ability_fqns(node), ["abl.a.b", "abl.c.d"])


class LoadoutResolutionTests(unittest.TestCase):
    def test_live_shoulder_cannon_loads_custom_sub_ability(self):
        bps = load_complete_loadout(["abl.bounty_hunter.shoulder_cannon"], parsed_dir=LIVE_PARSED)
        self.assertIn("abl.bounty_hunter.shoulder_cannon_custom", bps)

    def test_pts_pyro_shoulder_cannon_loads_damage_sub_ability(self):
        bps = load_complete_loadout(
            ["abl.bounty_hunter.skill.firebug.shoulder_cannon_pyro"], parsed_dir=PTS_PARSED
        )
        self.assertIn("abl.bounty_hunter.skill.firebug.shoulder_cannon_pyro_damage", bps)

    def test_selected_ability_indexes_after_same_named_sub_ability(self):
        from src.swtorsim.entities import Player

        bps = load_complete_loadout(["abl.bounty_hunter.shoulder_cannon"], parsed_dir=LIVE_PARSED)
        self.assertEqual(list(bps)[-1], "abl.bounty_hunter.shoulder_cannon")
        db = Player.build_ability_db(bps)
        self.assertEqual(db["shoulder_cannon"], bps["abl.bounty_hunter.shoulder_cannon"])


if __name__ == "__main__":
    unittest.main()
