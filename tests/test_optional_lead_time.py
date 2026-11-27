"""Unit tests for off-GCD ability lead_time / pre-cast rotational evaluation across Fixed, Optional, and Priority steps."""

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.events import Event
from src.swtorsim.rotation import (
    DEFAULT_OFF_GCD_LEAD_TIME, Rotation, FixedAbilityStep, OptionalAbilityStep, PriorityBlockStep,
)
from src.swtorsim.run_config import load_run_config
from src.swtorsim.setup import prepare_simulation

RUN_CONFIG_PATH = (
    ROOT / "data" / "run_config" / "Hatred.json"
    if (ROOT / "data" / "run_config" / "Hatred.json").exists()
    else ROOT / "data" / "run_config" / "first_test.json"
)


class OffGcdLeadTimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def _setup_sim(self, steps_config, verbose=False):
        config = load_run_config(str(RUN_CONFIG_PATH))
        inputs = load_from_run_config(config)
        sim, player, target = prepare_simulation(
            steps_config,
            inputs.stats_config,
            inputs.loadout_blueprints,
            config.dummy_hp,
            inputs.debuff_module,
        )
        sim.verbose = verbose
        # GCD of the loaded build (the run config's alacrity), so expected times follow the config.
        self.gcd = round(player.calculate_gcd(), 4)
        return sim, player, target

    def test_optional_step_with_lead_time_casts_before_gcd(self):
        """Verifies that an optional off-GCD ability with explicit lead_time=0.25 executes 0.25s before next GCD."""
        cast_log = []

        steps = [
            {"type": "fixed", "ability_id": "eradicate"},
            {"type": "optional", "ability_id": "recklessness", "lead_time": 0.25, "rules": {}},
            {"type": "fixed", "ability_id": "discharge"},
        ]

        sim, player, target = self._setup_sim(steps)

        original_cast_reck = player.ability_db["recklessness"].cast
        def logged_cast_reck(*args, **kwargs):
            cast_log.append(("recklessness", round(sim.current_time, 4), round(player.next_gcd, 4)))
            return original_cast_reck(*args, **kwargs)
        player.ability_db["recklessness"].cast = logged_cast_reck

        original_cast_discharge = player.ability_db["discharge"].cast
        def logged_cast_discharge(*args, **kwargs):
            cast_log.append(("discharge", round(sim.current_time, 4)))
            return original_cast_discharge(*args, **kwargs)
        player.ability_db["discharge"].cast = logged_cast_discharge

        sim.run_timed(duration=2.0, target=target)

        self.assertGreaterEqual(len(cast_log), 2)
        reck_time = cast_log[0][1]
        next_gcd_during_reck = cast_log[0][2]
        discharge_time = cast_log[1][1]

        expected_reck_time = round(discharge_time - 0.25, 4)
        self.assertAlmostEqual(reck_time, expected_reck_time, places=3)
        self.assertEqual(next_gcd_during_reck, discharge_time)

    def test_fixed_step_with_off_gcd_ability_automatically_casts_early_by_default_lead(self):
        """Verifies that even if a step is 'fixed', an off-GCD ability is detected and cast early by the default lead."""
        cast_log = []

        steps = [
            {"type": "fixed", "ability_id": "eradicate"},
            {"type": "fixed", "ability_id": "recklessness"},  # Fixed step, off-GCD, no explicit lead_time
            {"type": "fixed", "ability_id": "discharge"},
        ]

        sim, player, target = self._setup_sim(steps)

        original_cast_reck = player.ability_db["recklessness"].cast
        def logged_cast_reck(*args, **kwargs):
            cast_log.append(("recklessness", round(sim.current_time, 4), round(player.next_gcd, 4)))
            return original_cast_reck(*args, **kwargs)
        player.ability_db["recklessness"].cast = logged_cast_reck

        original_cast_discharge = player.ability_db["discharge"].cast
        def logged_cast_discharge(*args, **kwargs):
            cast_log.append(("discharge", round(sim.current_time, 4)))
            return original_cast_discharge(*args, **kwargs)
        player.ability_db["discharge"].cast = logged_cast_discharge

        sim.run_timed(duration=2.0, target=target)

        self.assertGreaterEqual(len(cast_log), 2)
        reck_time = cast_log[0][1]
        discharge_time = cast_log[1][1]

        expected_reck_time = round(discharge_time - DEFAULT_OFF_GCD_LEAD_TIME, 4)
        self.assertAlmostEqual(reck_time, expected_reck_time, places=3)

    def test_fixed_step_off_gcd_explicit_zero_lead_time_waits_for_gcd(self):
        """Verifies that setting lead_time=0.0 on an off-GCD fixed step disables early cast and casts at GCD."""
        cast_log = []

        steps = [
            {"type": "fixed", "ability_id": "eradicate"},
            {"type": "fixed", "ability_id": "recklessness", "lead_time": 0.0},
            {"type": "fixed", "ability_id": "discharge"},
        ]

        sim, player, target = self._setup_sim(steps)

        original_cast_reck = player.ability_db["recklessness"].cast
        def logged_cast_reck(*args, **kwargs):
            cast_log.append(("recklessness", round(sim.current_time, 4)))
            return original_cast_reck(*args, **kwargs)
        player.ability_db["recklessness"].cast = logged_cast_reck

        original_cast_discharge = player.ability_db["discharge"].cast
        def logged_cast_discharge(*args, **kwargs):
            cast_log.append(("discharge", round(sim.current_time, 4)))
            return original_cast_discharge(*args, **kwargs)
        player.ability_db["discharge"].cast = logged_cast_discharge

        sim.run_timed(duration=2.0, target=target)

        self.assertGreaterEqual(len(cast_log), 2)
        reck_time = cast_log[0][1]
        discharge_time = cast_log[1][1]
        self.assertEqual(reck_time, discharge_time)

    def test_on_gcd_priority_block_never_casts_early(self):
        """Verifies that on-GCD abilities inside priority blocks wait for full GCD (never cast early)."""
        cast_log = []

        steps = [
            {"type": "fixed", "ability_id": "eradicate"},
            {
                "type": "priority_block",
                "name": "Standard Attack Pool",
                "pool": [
                    {"ability_id": "assassinate", "rules": {"target_hp_below_pct": 0.3}},
                    {"ability_id": "discharge", "rules": {}},
                    {"ability_id": "saber_strike", "rules": {}},
                ],
            },
        ]

        sim, player, target = self._setup_sim(steps)

        original_cast_discharge = player.ability_db["discharge"].cast
        def logged_cast_discharge(*args, **kwargs):
            cast_log.append(("discharge", round(sim.current_time, 4), round(player.next_gcd, 4)))
            return original_cast_discharge(*args, **kwargs)
        player.ability_db["discharge"].cast = logged_cast_discharge

        sim.run_timed(duration=2.0, target=target)

        self.assertGreaterEqual(len(cast_log), 1)
        discharge_time = cast_log[0][1]
        self.assertEqual(
            discharge_time,
            self.gcd,
            f"On-GCD ability in priority block must execute at exact GCD ({self.gcd}s), got {discharge_time}s",
        )

    def test_on_gcd_ability_never_casts_early_even_if_lead_time_configured(self):
        """Verifies safety invariant: an on-GCD ability is never cast early before next_gcd."""
        cast_log = []

        # Discharge is on-GCD. Setting lead_time=0.5 must NOT cause discharge to cast before GCD
        steps = [
            {"type": "fixed", "ability_id": "eradicate"},
            {"type": "fixed", "ability_id": "discharge", "lead_time": 0.5},
        ]

        sim, player, target = self._setup_sim(steps)

        original_cast_discharge = player.ability_db["discharge"].cast
        def logged_cast_discharge(*args, **kwargs):
            cast_log.append(("discharge", round(sim.current_time, 4), round(player.next_gcd, 4)))
            return original_cast_discharge(*args, **kwargs)
        player.ability_db["discharge"].cast = logged_cast_discharge

        sim.run_timed(duration=2.0, target=target)

        self.assertGreaterEqual(len(cast_log), 1)
        discharge_time = cast_log[0][1]
        self.assertEqual(discharge_time, self.gcd, f"On-GCD ability Discharge must wait for full GCD ({self.gcd}s), got {discharge_time}s")

    def test_optional_step_lead_time_retries_at_gcd_if_not_ready_early(self):
        """Verifies that if an off-GCD ability cannot cast early, it retries and casts at next_gcd."""
        cast_log = []

        steps = [
            {"type": "fixed", "ability_id": "eradicate"},
            {
                "type": "optional",
                "ability_id": "recklessness",
                "lead_time": 0.3,
                "rules": {"caster_has_buff": "ReadyToGo"},
            },
            {"type": "fixed", "ability_id": "discharge"},
        ]

        sim, player, target = self._setup_sim(steps)

        original_cast_reck = player.ability_db["recklessness"].cast
        def logged_cast_reck(*args, **kwargs):
            cast_log.append(("recklessness", round(sim.current_time, 4)))
            return original_cast_reck(*args, **kwargs)
        player.ability_db["recklessness"].cast = logged_cast_reck

        original_cast_discharge = player.ability_db["discharge"].cast
        def logged_cast_discharge(*args, **kwargs):
            cast_log.append(("discharge", round(sim.current_time, 4)))
            return original_cast_discharge(*args, **kwargs)
        player.ability_db["discharge"].cast = logged_cast_discharge

        # Grant the buff after the early lead check (GCD - 0.3s) and before the GCD ends
        class GrantBuffEvent(Event):
            def resolve(self, s):
                player.effects["ReadyToGo"] = "active"

        sim.schedule_absolute(self.gcd - 0.15, GrantBuffEvent("GrantBuff"))
        sim.run_timed(duration=2.0, target=target)

        self.assertGreaterEqual(len(cast_log), 2)
        reck_time = cast_log[0][1]
        discharge_time = cast_log[1][1]
        self.assertEqual(
            reck_time,
            self.gcd,
            f"Recklessness should have retried and cast at next_gcd ({self.gcd}s), got {reck_time}s",
        )
        self.assertEqual(discharge_time, self.gcd)

    def test_priority_block_option_lead_time(self):
        """Verifies that an off-GCD option inside a priority block honors its individual lead_time."""
        cast_log = []
        steps = [
            {"type": "fixed", "ability_id": "eradicate"},
            {
                "type": "priority_block",
                "name": "Weave Prio",
                "pool": [
                    {"ability_id": "recklessness", "lead_time": 0.5},
                    {"ability_id": "discharge"},
                ],
            },
            {"type": "fixed", "ability_id": "creeping_terror"},
        ]

        sim, player, target = self._setup_sim(steps)

        original_cast = player.ability_db["recklessness"].cast
        def logged_cast(*args, **kwargs):
            cast_log.append(("recklessness", round(sim.current_time, 4)))
            return original_cast(*args, **kwargs)
        player.ability_db["recklessness"].cast = logged_cast

        sim.run_timed(duration=2.0, target=target)

        self.assertGreaterEqual(len(cast_log), 1)
        # With lead_time=0.5 on the option, the cast lands 0.5s before the GCD ends
        self.assertAlmostEqual(cast_log[0][1], self.gcd - 0.5, places=4)

    def test_priority_block_step_level_lead_time_fallback(self):
        """Verifies that if option has no lead_time, it falls back to block-level lead_time."""
        cast_log = []
        steps = [
            {"type": "fixed", "ability_id": "eradicate"},
            {
                "type": "priority_block",
                "name": "Weave Prio",
                "lead_time": 0.35,
                "pool": [
                    {"ability_id": "recklessness"},
                    {"ability_id": "discharge"},
                ],
            },
            {"type": "fixed", "ability_id": "creeping_terror"},
        ]

        sim, player, target = self._setup_sim(steps)

        original_cast = player.ability_db["recklessness"].cast
        def logged_cast(*args, **kwargs):
            cast_log.append(("recklessness", round(sim.current_time, 4)))
            return original_cast(*args, **kwargs)
        player.ability_db["recklessness"].cast = logged_cast

        sim.run_timed(duration=2.0, target=target)

        self.assertGreaterEqual(len(cast_log), 1)
        # With lead_time=0.35 on the block, the cast lands 0.35s before the GCD ends
        self.assertAlmostEqual(cast_log[0][1], self.gcd - 0.35, places=4)


    def test_optional_off_gcd_waits_for_active_channel_and_does_not_skip(self):
        """Verifies that an optional off-GCD ability following a channeled ability waits for the channel to finish and does not skip."""
        from src.swtorsim.effects import ActiveChannel
        cast_log = []
        steps = [
            {"type": "fixed", "ability_id": "eradicate"},
            {"type": "optional", "ability_id": "recklessness", "rules": {}},
            {"type": "fixed", "ability_id": "discharge"},
        ]

        sim, player, target = self._setup_sim(steps)

        original_cast_reck = player.ability_db["recklessness"].cast
        def logged_cast_reck(*args, **kwargs):
            cast_log.append(("recklessness", round(sim.current_time, 4)))
            return original_cast_reck(*args, **kwargs)
        player.ability_db["recklessness"].cast = logged_cast_reck

        # Simulate a channel that started at 0.0s and lasts until 2.0s (past the first GCD)
        dummy_channel = ActiveChannel(
            name="TestChannel",
            caster=player,
            target=target,
            duration=2.0,
            tick_interval=0.5,
            total_ticks=4,
            action_data={},
            ability=None,
        )
        player.active_channel = dummy_channel
        player.is_channeling = True

        # End the channel at t = 1.80s via a scheduled event
        class EndChannelEvent(Event):
            def resolve(self, s):
                player.active_channel = None
                player.is_channeling = False
                s.schedule_absolute(s.current_time, PlayerReady(player, target))

        from src.swtorsim.events import PlayerReady
        sim.schedule_absolute(1.80, EndChannelEvent("EndChannel"))

        sim.run_timed(duration=3.5, target=target)

        # Recklessness must NOT be skipped while the channel blocks the rotation. Eradicate casts at 1.80s
        # once the channel ends (next GCD 1.80s + GCD), so Recklessness weaves that much minus the default lead.
        reck_casts = [c for c in cast_log if c[0] == "recklessness"]
        self.assertEqual(len(reck_casts), 1)
        self.assertAlmostEqual(reck_casts[0][1], 1.80 + self.gcd - DEFAULT_OFF_GCD_LEAD_TIME, places=2)

if __name__ == "__main__":
    unittest.main()
