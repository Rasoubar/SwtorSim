"""Missed hits are logged by the simulator's combat log and by the debugger, without changing the fight."""

import contextlib
import io
import json
import unittest
from pathlib import Path

import src.swtorsim.abilities as abilities
from src.swtorsim.debug import debug_api
from src.swtorsim.miss_log import ability_name, log_misses

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data" / "run_config" / "Annihilation.json"
needs_annihilation = unittest.skipUnless(CONFIG.is_file(), "Annihilation run config not present")


class _Sim:
    current_time = 12.5


class _Blueprint:
    name = "Vicious Slash"


class WrapperTests(unittest.TestCase):
    def test_it_reports_only_failed_rolls_and_returns_the_engines_answer_unchanged(self):
        answers = iter([True, False, False])
        calls = []

        def fake_roll(source, hand="main", attack_type=1, ability_fqn=None, action_tags=frozenset(), target=None):
            calls.append((hand, attack_type, ability_fqn))
            return next(answers)

        records = []
        real = abilities.accuracy_roll
        abilities.accuracy_roll = fake_roll
        try:
            with log_misses(_Sim(), {"abl.x": _Blueprint()}, records.append):
                results = [abilities.accuracy_roll(None, hand=h, attack_type=1, ability_fqn="abl.x", target=None)
                           for h in ("main", "off", "main")]
            self.assertIs(abilities.accuracy_roll, fake_roll)  # restored
        finally:
            abilities.accuracy_roll = real
        self.assertEqual(results, [True, False, False])
        self.assertEqual(len(calls), 3)  # one engine roll per attempt: the random stream is untouched
        self.assertEqual([(r["ability"], r["hand"], r["time"]) for r in records],
                         [("Vicious Slash", "off", 12.5), ("Vicious Slash", "main", 12.5)])

    def test_it_is_restored_when_the_block_raises(self):
        real = abilities.accuracy_roll
        with self.assertRaises(RuntimeError):
            with log_misses(_Sim(), {}, lambda r: None):
                raise RuntimeError
        self.assertIs(abilities.accuracy_roll, real)

    def test_names_fall_back_to_the_fqn_tail(self):
        self.assertEqual(ability_name({}, "abl.mar.vicious_slash"), "Vicious Slash")
        self.assertEqual(ability_name({"a.b": _Blueprint()}, "a.b"), "Vicious Slash")


@needs_annihilation
class FightTests(unittest.TestCase):
    """Annihilation dual wields, so its off-hand attacks miss; the simulator and the debugger must agree on them."""

    @classmethod
    def setUpClass(cls):
        from src.swtorsim import web_gui

        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        keys = ("spec_path", "stats_path", "rotation_path", "tactical_fqn", "legendary_fqns", "relic_fqns", "level", "seed",
                "dummy_hp", "class", "spec", "main_hand", "off_hand", "training_dummy_armor_debuff", "enable_stem_matching",
                "enable_projectile_flight_time", "in_flashpoint_operation", "combat_distance", "gcd_stall",
                "incoming_attack_interval")
        setup = {k: cfg[k] for k in keys if k in cfg}
        setup.update(choices=cfg["choices"], choices_override=cfg["choices"], duration=120, environment="live",
                     spec_path=cfg["spec_path"].replace("/pts/", "/live/"))
        with contextlib.redirect_stdout(io.StringIO()):
            config, inputs = web_gui._resolve_simulation_inputs_from_payload(dict(setup, mode="TEST"))
            cls.simulator = web_gui._run_single_test_detailed(config, inputs)
        cls.debugger = debug_api.run_trace(setup=setup, environment="live")

    def test_the_simulator_logs_its_misses(self):
        misses = self.simulator["misses"]
        logged = [e for e in self.simulator["combat_log"] if e["category"] == "miss"]
        self.assertGreater(misses["total"], 0)
        self.assertEqual(len(logged), misses["total"])
        self.assertEqual(sum(row["misses"] for row in misses["by_ability"]), misses["total"])
        self.assertTrue(all(e["text"].endswith("missed") or "missed (" in e["text"] for e in logged))
        attempts = self.simulator["total_hits"] + misses["total"]
        self.assertAlmostEqual(misses["pct"], round(misses["total"] / attempts * 100.0, 2))

    def test_the_debugger_logs_the_same_misses(self):
        events = [e for e in self.debugger["events"] if e["type"] == "miss"]
        self.assertEqual(len(events), self.debugger["summary"]["misses"])
        self.assertEqual(len(events), self.simulator["misses"]["total"])
        self.assertEqual(sorted(e["ability"] for e in events),
                         sorted(e["ability"] for e in self.simulator["combat_log"] if e["category"] == "miss"))
        self.assertTrue(all("raw" in e for e in events))  # the exact clock time that state replays anchor on

    def test_logging_does_not_change_the_fight(self):
        self.assertEqual(self.simulator["total_damage"], self.debugger["summary"]["total_damage"])

    def test_the_engines_accuracy_function_is_back_after_the_runs(self):
        from src.swtorsim.combat_math import accuracy_roll

        self.assertIs(abilities.accuracy_roll, accuracy_roll)


if __name__ == "__main__":
    unittest.main()
