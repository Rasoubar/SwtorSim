"""Unit tests verifying rotation stall and deadlock telemetry, diagnostic tracking, and RNG seed logging."""

import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from src.swtorsim.abilities import Ability
from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.engine import Simulation
from src.swtorsim.events import PlayerReady
from src.swtorsim.run_config import load_run_config
from src.swtorsim.rotation import Rotation
from src.swtorsim.setup import prepare_simulation

RUN_CONFIG_PATH = (
    ROOT / "data" / "run_config" / "Hatred.json"
    if (ROOT / "data" / "run_config" / "Hatred.json").exists()
    else ROOT / "data" / "run_config" / "first_test.json"
)


class RotationStallTelemetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def setUp(self):
        self.config = load_run_config(str(RUN_CONFIG_PATH))
        self.inputs = load_from_run_config(self.config)

    def test_smooth_rotation_has_no_stalls(self):
        """Verifies that a valid looping rotation produces zero stall events and zero stalled time."""
        sim, player, target = prepare_simulation(
            self.inputs.rotation_config,
            self.inputs.stats_config,
            self.inputs.loadout_blueprints,
            self.config.dummy_hp,
            self.inputs.debuff_module,
            verbose=False,
            seed=1337,
        )
        self.assertEqual(sim.seed, 1337)
        self.assertEqual(sim.tracker.seed, 1337)

        sim.run_timed(duration=10.0, target=target)

        self.assertEqual(len(sim.tracker.stall_events), 0)
        self.assertEqual(sim.tracker.total_stalled_time, 0.0)
        self.assertFalse(sim.tracker.permanent_stall)

    def test_transient_stall_is_logged_with_seed_and_step_info(self):
        """Verifies that a temporary rotation gap logs stall start, end, duration, step, and RNG seed."""
        sim, player, target = prepare_simulation(
            self.inputs.rotation_config,
            self.inputs.stats_config,
            self.inputs.loadout_blueprints,
            self.config.dummy_hp,
            self.inputs.debuff_module,
            verbose=False,
            seed=777,
        )

        saber_id = next(k for k, v in player.ability_db.items() if "saber_strike" in k.lower())
        saber_abl = player.ability_db[saber_id]

        custom_rotation_config = [
            {"type": "fixed", "ability_id": saber_id},
        ]
        player.rotation = Rotation(name="Stall Test", steps_config=custom_rotation_config, loop=True)

        # Cast at 0.0s, and put on cooldown until 2.5s so step stalls from the GCD end to 2.5s
        gcd = player.calculate_gcd()
        sim.run_timed(duration=0.5, target=target)
        player.cooldowns[saber_abl.name] = 2.5

        # Run past the cooldown
        sim.run_timed(duration=5.0, target=target)

        self.assertEqual(len(sim.tracker.stall_events), 1)
        stall = sim.tracker.stall_events[0]
        self.assertEqual(stall["seed"], 777)
        self.assertTrue(stall["recovered"])
        self.assertAlmostEqual(stall["start"], gcd, delta=0.01)
        self.assertAlmostEqual(stall["end"], 2.5, delta=0.01)
        self.assertAlmostEqual(stall["duration"], 2.5 - gcd, delta=0.01)
        self.assertIn("FixedAbilityStep:Saber Strike", stall["step_info"])
        self.assertFalse(sim.tracker.permanent_stall)

    def test_permanent_rotation_deadlock_finalizes_at_duration(self):
        """Verifies that a rotation that exhausts its steps or blocks permanently marks permanent_stall=True."""
        sim, player, target = prepare_simulation(
            self.inputs.rotation_config,
            self.inputs.stats_config,
            self.inputs.loadout_blueprints,
            self.config.dummy_hp,
            self.inputs.debuff_module,
            verbose=False,
            seed=9999,
        )

        first_abl_id = next(k for k, v in player.ability_db.items() if getattr(v, "triggers_gcd", True))

        # Single non-looping step: will run out of steps after step 0
        single_step_config = [
            {"type": "fixed", "ability_id": first_abl_id},
        ]
        player.rotation = Rotation(name="Deadlock Test", steps_config=single_step_config, loop=False)

        sim.run_timed(duration=6.0, target=target)

        self.assertTrue(sim.tracker.permanent_stall)
        self.assertGreater(len(sim.tracker.stall_events), 0)
        last_stall = sim.tracker.stall_events[-1]
        self.assertFalse(last_stall["recovered"])
        self.assertEqual(last_stall["end"], 6.0)
        self.assertEqual(last_stall["seed"], 9999)
        self.assertIn("End of sequence", last_stall["step_info"])
