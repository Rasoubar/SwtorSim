"""'What changed': the diff of two state snapshots, and the replay behind it."""

import unittest
from pathlib import Path

from src.swtorsim.debug import debug_api
from src.swtorsim.debug.inspect_state import diff_snapshots

CONFIG = Path(__file__).resolve().parents[1] / "data" / "run_config" / "Hatred.json"


def snap(resource=50.0, gcd=0.0, hp=1000.0, abilities=(), effects=(), icds=(), stats=None, casting=None):
    return {
        "resource": {"type": "StandardPool", "current": resource, "max": 100.0},
        "gcd_remaining": gcd, "casting": casting, "channeling": None,
        "target": {"hp": hp, "max_hp": 1000.0},
        "abilities": list(abilities), "effects": list(effects), "icds": list(icds), "stats": stats or {},
    }


def ability(name, ready=True, ready_in=0.0, charges=None, recharge_in=None):
    return {"name": name, "ready": ready, "ready_in": ready_in, "charges": charges,
            "max_charges": None if charges is None else 2, "recharge_in": recharge_in, "cooldown": 10.0, "on_gcd": True}


def effect(name, stacks=1, remaining=10.0, entity="Player", permanent=False):
    return {"entity": entity, "key": name, "name": name, "stacks": stacks, "max_stacks": 5,
            "remaining": None if permanent else remaining, "permanent": permanent, "passive": False, "tags": []}


def icd(source, remaining, event="on_damage_dealt"):
    return {"source": source, "event": event, "remaining": remaining}


class DiffTests(unittest.TestCase):
    def test_nothing_happening_is_no_change(self):
        before = snap(abilities=[ability("A", False, 5.0)], effects=[effect("Buff", remaining=10.0)], icds=[icd("P", 4.0)], gcd=1.0)
        after = snap(abilities=[ability("A", False, 3.0)], effects=[effect("Buff", remaining=8.0)], icds=[icd("P", 2.0)], gcd=0.0)
        d = diff_snapshots(before, after, elapsed=2.0)
        self.assertEqual((d["abilities"], d["icds"]), ([], []))
        self.assertEqual(d["effects"], {"added": [], "removed": [], "changed": []})
        self.assertEqual(d["resource"]["delta"], 0)
        self.assertEqual(d["gcd"], {"before": 0.0, "after": 0.0})  # a 1s GCD aged by 2s

    def test_resource_gcd_and_target_hp(self):
        d = diff_snapshots(snap(resource=46.4, hp=1000.0), snap(resource=54.4, gcd=1.4, hp=900.0))
        self.assertEqual(d["resource"]["delta"], 8.0)
        self.assertEqual(d["gcd"], {"before": 0.0, "after": 1.4})
        self.assertEqual(d["target_hp"]["delta"], -100.0)

    def test_a_cooldown_that_started_or_was_cut_is_reported(self):
        before = snap(abilities=[ability("Strike"), ability("Reck", False, 40.0), ability("Charged", True, 0.0, 1, 6.0)])
        after = snap(abilities=[ability("Strike", False, 20.0), ability("Reck", False, 31.0), ability("Charged", False, 0.0, 0, 6.0)])
        d = diff_snapshots(before, after, elapsed=1.5)
        changed = {a["name"]: a for a in d["abilities"]}
        self.assertEqual(set(changed), {"Strike", "Reck", "Charged"})  # Reck: 40 aged to 38.5, now 31 -> cut by 7.5
        self.assertTrue(changed["Strike"]["before"]["ready"] and not changed["Strike"]["after"]["ready"])
        self.assertEqual(changed["Charged"]["after"]["charges"], 0)

    def test_effects_gained_lost_stacked_and_refreshed(self):
        before = snap(effects=[effect("Gone"), effect("Stacky", 1), effect("Refresh", remaining=3.0), effect("Perm", permanent=True)])
        after = snap(effects=[effect("New", entity="Target"), effect("Stacky", 3), effect("Refresh", remaining=10.0), effect("Perm", permanent=True)])
        d = diff_snapshots(before, after)["effects"]
        self.assertEqual([e["name"] for e in d["added"]], ["New"])
        self.assertEqual([e["name"] for e in d["removed"]], ["Gone"])
        changed = {e["name"]: e for e in d["changed"]}
        self.assertEqual((changed["Stacky"]["stacks_before"], changed["Stacky"]["stacks_after"]), (1, 3))
        self.assertTrue(changed["Refresh"]["refreshed"])
        self.assertNotIn("Perm", changed)

    def test_icds_started_and_restarted(self):
        before = snap(icds=[icd("Old", 4.0)])
        after = snap(icds=[icd("Old", 6.0), icd("New", 3.0)])
        started = {i["source"]: i for i in diff_snapshots(before, after, elapsed=1.0)["icds"]}
        self.assertEqual(set(started), {"Old", "New"})
        self.assertTrue(started["Old"]["restarted"] and not started["New"]["restarted"])

    def test_stat_changes_and_casting(self):
        d = diff_snapshots(snap(stats={"Alacrity": 0.1, "Power": 5.0}, casting=None), snap(stats={"Alacrity": 0.2, "Power": 5.0}, casting="Bolt"))
        self.assertEqual(d["stats"], [{"stat": "Alacrity", "before": 0.1, "after": 0.2}])
        self.assertEqual(d["casting"], {"before": None, "after": "Bolt"})


@unittest.skipUnless(CONFIG.is_file(), "Hatred run config not present")
class ChangeReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = debug_api.handle("trace", {"config": "Hatred"})
        cls.casts = [e for e in cls.trace["events"] if e["type"] == "cast_start" and e["t"] > 30]
        cls.hit = next(e for e in cls.trace["events"] if e["type"] == "damage_hit" and e["t"] > 30)

    def test_a_cast_shows_its_gcd_and_the_replay_is_repeatable(self):
        cast = self.casts[0]
        first = debug_api.handle("change", {"config": "Hatred", "at": cast["raw"]})
        again = debug_api.handle("change", {"config": "Hatred", "at": cast["raw"]})
        self.assertEqual(first, again)
        gcd = first["diff"]["gcd"]
        self.assertGreater(gcd["after"], gcd["before"])

    def test_the_state_before_excludes_the_event_itself(self):
        """The anchor is the tracer's rounded time; the replay must still read the state before the hit lands."""
        result = debug_api.handle("change", {"config": "Hatred", "at": self.hit["raw"]})
        self.assertGreaterEqual(abs(result["diff"]["target_hp"]["delta"]), self.hit["damage"])

    def test_a_window_covers_the_following_events(self):
        cast = self.casts[0]
        narrow = debug_api.handle("change", {"config": "Hatred", "at": cast["raw"], "window": 0.0})["diff"]
        wide = debug_api.handle("change", {"config": "Hatred", "at": cast["raw"], "window": 3.0})["diff"]
        self.assertEqual(wide["elapsed"], 3.0)
        self.assertGreater(abs(wide["target_hp"]["delta"]), abs(narrow["target_hp"]["delta"]))


if __name__ == "__main__":
    unittest.main()
