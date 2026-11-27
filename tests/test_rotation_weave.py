"""Tests for the loop-only "always weave" list of a rotation (engine, builder backend, cast timeline)."""

import os
import unittest
from pathlib import Path

from data.rotation_builder import (
    build_rotation_file_data,
    normalize_rotation_steps,
    normalize_weave_steps,
    run_dry_run_preview,
)
from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.rotation import OptionalAbilityStep, Rotation
from src.swtorsim.run_config import load_run_config
from src.swtorsim.setup import prepare_simulation

ROOT = Path(__file__).resolve().parents[1]
RUN_CONFIG_PATH = ROOT / "data" / "run_config" / "Hatred.json"
SEQUENCE = [
    {"type": "fixed", "ability_id": "opener_a"},
    {"type": "loop_anchor"},
    {"type": "fixed", "ability_id": "loop_a"},
    {"type": "fixed", "ability_id": "loop_b"},
]
WEAVE = [{"ability_id": "weave_x", "rules": {}}]


class _Sim:
    current_time = 0.0
    tracer = None


class _Ability:
    """Instant ability stub: castable when `ready`, records every cast."""

    def __init__(self, name, log, triggers_gcd=True):
        self.name = name
        self.log = log
        self.triggers_gcd = triggers_gcd
        self.ready = True

    def can_cast(self, player, target, sim):
        return self.ready

    def cast(self, player, target, sim):
        self.log.append(self.name)
        return True


class _Player:
    next_gcd = 0.0
    active_channel = None
    active_cast = None

    def __init__(self, log):
        self.ability_db = {
            "opener_a": _Ability("opener_a", log),
            "loop_a": _Ability("loop_a", log),
            "loop_b": _Ability("loop_b", log),
            "weave_x": _Ability("weave_x", log, triggers_gcd=False),
        }


def _run(rotation, player, evaluations):
    sim = _Sim()
    for _ in range(evaluations):
        rotation.evaluate(player, None, sim)


class RotationWeaveEngineTests(unittest.TestCase):
    def test_bare_list_and_dict_without_weave_have_no_weave(self):
        self.assertEqual(Rotation("r", SEQUENCE).weave, [])
        self.assertEqual(Rotation("r", {"sequence": SEQUENCE}).weave, [])

    def test_weave_is_loop_only_and_fires_before_every_loop_step(self):
        log = []
        rot = Rotation("r", {"sequence": SEQUENCE, "weave": WEAVE})
        self.assertEqual(len(rot.sequence), 3)  # weave entries never enter the sequence
        self.assertIsInstance(rot.weave[0], OptionalAbilityStep)
        _run(rot, _Player(log), 9)
        self.assertEqual(
            log,
            ["opener_a", "weave_x", "loop_a", "weave_x", "loop_b", "weave_x", "loop_a", "weave_x", "loop_b"],
        )

    def test_matches_hand_placed_optional_steps(self):
        hand = [
            {"type": "fixed", "ability_id": "opener_a"},
            {"type": "loop_anchor"},
            {"type": "optional", "ability_id": "weave_x", "rules": {}},
            {"type": "fixed", "ability_id": "loop_a"},
            {"type": "optional", "ability_id": "weave_x", "rules": {}},
            {"type": "fixed", "ability_id": "loop_b"},
        ]
        log_hand, log_weave = [], []
        _run(Rotation("hand", hand), _Player(log_hand), 13)
        _run(Rotation("weave", {"sequence": SEQUENCE, "weave": WEAVE}), _Player(log_weave), 13)
        self.assertEqual(log_weave, log_hand)

    def test_unready_weave_is_skipped_without_blocking(self):
        log = []
        player = _Player(log)
        player.ability_db["weave_x"].ready = False
        _run(Rotation("r", {"sequence": SEQUENCE, "weave": WEAVE}), player, 7)
        self.assertEqual(log, ["opener_a", "loop_a", "loop_b", "loop_a"])

    def test_lead_time_applies_to_pending_weave_only_in_loop(self):
        player = _Player([])
        rot = Rotation("r", {"sequence": SEQUENCE, "weave": [{"ability_id": "weave_x", "rules": {}, "lead_time": 0.2}]})
        self.assertEqual(rot.get_next_lead_time(player), 0.0)  # opener step, on GCD
        rot.evaluate(player, None, _Sim())
        self.assertAlmostEqual(rot.get_next_lead_time(player), 0.2)  # off-GCD weave entry is next
        rot.evaluate(player, None, _Sim())
        self.assertEqual(rot.get_next_lead_time(player), 0.0)  # loop_a, on GCD


class RotationWeaveBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def test_file_round_trip(self):
        weave = [{"ability_id": "laze_target", "rules": {"caster_energy_above": 20}, "lead_time": 0.2}]
        data = build_rotation_file_data(SEQUENCE, [], weave=weave)
        self.assertEqual(data, {"weave": weave, "sequence": SEQUENCE})
        steps, _warnings = normalize_rotation_steps(data)
        self.assertEqual(steps, SEQUENCE)
        self.assertEqual(normalize_weave_steps(data), weave)

    def test_no_weave_keeps_bare_array(self):
        self.assertEqual(build_rotation_file_data(SEQUENCE, [], weave=[]), SEQUENCE)
        self.assertEqual(normalize_weave_steps(SEQUENCE), [])

    def test_normalize_drops_invalid_entries_and_fills_rules(self):
        raw = {"weave": ["laze_target", {"rules": {}}, {"ability_id": "laze_target"}]}
        self.assertEqual(normalize_weave_steps(raw), [{"ability_id": "laze_target", "rules": {}}])

    @unittest.skipUnless(RUN_CONFIG_PATH.exists(), "Hatred run config not available")
    def test_preview_marks_weave_casts_and_matches_hand_placed_steps(self):
        cfg = load_run_config(str(RUN_CONFIG_PATH))
        inputs = load_from_run_config(cfg)
        _sim, player, _target = prepare_simulation(
            [{"type": "fixed", "ability_id": "thrash"}], inputs.stats_config, inputs.loadout_blueprints,
            cfg.dummy_hp, inputs.debuff_module, verbose=False, seed=1,
        )
        off_gcd = "recklessness"
        self.assertFalse(player.ability_db[off_gcd].triggers_gcd)
        base = {
            "spec_path": cfg.spec_path,
            "choices": cfg.choices,
            "tactical_fqn": cfg.tactical_fqn,
            "legendary_fqns": cfg.legendary_fqns,
            "relic_fqns": cfg.relic_fqns,
            "duration": 30.0,
        }
        woven = run_dry_run_preview(dict(
            base,
            rotation=[{"type": "fixed", "ability_id": "thrash"}],
            weave=[{"ability_id": off_gcd, "rules": {}}],
        ))
        hand = run_dry_run_preview(dict(
            base,
            rotation=[
                {"type": "optional", "ability_id": off_gcd, "rules": {}},
                {"type": "fixed", "ability_id": "thrash"},
            ],
        ))
        weave_rows = [c for c in woven["casts"] if c["phase"] == "weave"]
        self.assertGreater(len(weave_rows), 0)
        self.assertTrue(all(c["slug"] == off_gcd and c["step_index"] == 1 for c in weave_rows))
        self.assertTrue(all(c["slug"] == "thrash" for c in woven["casts"] if c["phase"] == "rotation"))
        self.assertEqual(
            [(c["time"], c["slug"]) for c in woven["casts"]],
            [(c["time"], c["slug"]) for c in hand["casts"]],
        )
        self.assertEqual(woven["total_damage"], hand["total_damage"])


if __name__ == "__main__":
    unittest.main()
