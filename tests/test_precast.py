"""Unit tests for pre-cast options, pre-combat sequencing, and first-damage combat clock activation."""

import copy
import os
from pathlib import Path
import unittest

from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.entities import Player, Dummy
from src.swtorsim.events import PreCombatEvent, PlayerReady
from src.swtorsim.run_config import RunConfig, load_run_config, normalize_pre_combat
from src.swtorsim.settings import set_projectile_flight_time
from src.swtorsim.setup import prepare_simulation

ROOT = Path(__file__).resolve().parents[1]
RUN_CONFIG_PATH = (
    ROOT / "data" / "run_config" / "Hatred.json"
    if (ROOT / "data" / "run_config" / "Hatred.json").exists()
    else ROOT / "data" / "run_config" / "first_test.json"
)


class PreCastCombatClockTests(unittest.TestCase):
    """Test suite covering pre-cast abilities, pre-combat buff staging, and 1st damage clock triggers."""

    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def setUp(self):
        self.base_config = load_run_config(str(RUN_CONFIG_PATH))
        self.inputs = load_from_run_config(self.base_config)

    def test_normalize_pre_combat_formats(self):
        """Verifies normalize_pre_combat accepts strings, dicts, and mixed sequences."""
        with self.subTest("single_string_precast"):
            res = normalize_pre_combat(precast="snipe")
            self.assertEqual(res, [{"ability": "snipe"}])

        with self.subTest("single_dict_precast"):
            res = normalize_pre_combat(precast={"ability": "lightning_bolt", "target": "target"})
            self.assertEqual(res, [{"ability": "lightning_bolt", "target": "target"}])

        with self.subTest("pre_combat_list_of_strings"):
            res = normalize_pre_combat(pre_combat=["stealth", "recklessness", "eradicate"])
            self.assertEqual(
                res,
                [{"ability": "stealth"}, {"ability": "recklessness"}, {"ability": "eradicate"}],
            )

        with self.subTest("precast_as_list_of_multiple_abilities"):
            res = normalize_pre_combat(precast=["stealth", "recklessness", "snipe"])
            self.assertEqual(
                res,
                [{"ability": "stealth"}, {"ability": "recklessness"}, {"ability": "snipe"}],
            )

        with self.subTest("pre_combat_and_precast_deduplication"):
            # When precast duplicates the last item in pre_combat, it should not be repeated
            res = normalize_pre_combat(precast="eradicate", pre_combat=["stealth", "eradicate"])
            self.assertEqual(
                res,
                [{"ability": "stealth"}, {"ability": "eradicate"}],
            )

    def test_normalize_pre_combat_rejects_unknown_or_invalid_steps(self):
        """Unsupported steps raise ValueError instead of silently vanishing from the sequence."""
        bad_cases = {
            "unknown_kind": [{"wait_untill": {"caster_energy_above": 6}}],
            "empty_ability_dict": [{"ability": ""}],
            "blank_string": ["  "],
            "empty_swap": [{"swap_tactical": ""}],
            "wait_not_number": [{"wait": "soon"}],
            "wait_zero": [{"wait": 0}],
            "wait_until_not_rules": [{"wait_until": "rage>=6"}],
            "bad_max_wait": [{"wait_until": {}, "max_wait": -1}],
            "unsupported_type": [42],
        }
        for name, pre in bad_cases.items():
            with self.subTest(name):
                with self.assertRaises(ValueError) as ctx:
                    normalize_pre_combat(pre_combat=pre)
                self.assertIn("step 1", str(ctx.exception))

        with self.subTest("prepare_simulation_refuses_unknown_step"):
            with self.assertRaises(ValueError):
                prepare_simulation(
                    [{"type": "fixed", "ability_id": "thrash"}],
                    self.inputs.stats_config,
                    self.inputs.loadout_blueprints,
                    self.base_config.dummy_hp,
                    self.inputs.debuff_module,
                    verbose=False,
                    pre_combat=["stealth", {"mystery_step": True}],
                )

    def test_precast_hardcast_ability_starts_clock_at_damage_land(self):
        """Verifies that a hard-cast ability takes time to cast, and combat starts when damage lands."""
        # Configure a simple 1-step loop rotation for after pre-cast
        rotation = [{"type": "fixed", "ability_id": "thrash"}]

        sim, player, target = prepare_simulation(
            rotation,
            self.inputs.stats_config,
            self.inputs.loadout_blueprints,
            self.base_config.dummy_hp,
            self.inputs.debuff_module,
            verbose=False,
            precast="eradicate",
        )

        # Give Eradicate a 2.0s base cast time to test cast timing
        erad = player.ability_db["eradicate"]
        erad.activation = {"type": "cast", "duration": 2.0}
        expected_cast_dur = player.calculate_cast_time(2.0, ability=erad)

        self.assertIsNone(sim.combat_start_time, "Combat start time must be None before simulation runs")

        # Run 5.0 seconds of combat
        sim.run_timed(duration=5.0, target=target)

        # Eradicate cast for expected_cast_dur and dealt no damage; the rotation's first hit starts the clock
        self.assertIsNotNone(sim.combat_start_time, "Combat start time must be set after damage lands")
        self.assertGreaterEqual(sim.combat_start_time, expected_cast_dur - 1e-6)
        self.assertLessEqual(sim.combat_start_time, expected_cast_dur + 0.1)

        # Combat started at the first rotation hit and lasts 5.0s: all events up to stop_time are resolved
        stop_time = sim.combat_start_time + 5.0
        self.assertLessEqual(sim.current_time, stop_time)
        if sim.queue:
            self.assertGreater(sim.queue[0][0], stop_time)
        # The rotation's first hit (not the pre-cast) starts the clock, so the last event sits within one GCD of the stop
        self.assertGreaterEqual(sim.get_combat_duration(), 4.5)

        # Metrics tracker should calculate duration relative to 1st damage
        self.assertAlmostEqual(sim.tracker.combat_start_time, sim.combat_start_time, places=2)
        self.assertAlmostEqual(sim.tracker.get_combat_duration(stop_time), 5.0, places=2)
        self.assertGreaterEqual(sim.tracker.get_combat_duration(sim.current_time), 4.5)

    def test_precast_never_damages_dummy_and_rotation_starts_clock(self):
        """Pre-combat hits are dropped (even delayed ones); the first rotation hit starts the fight clock."""
        rotation = [{"type": "fixed", "ability_id": "thrash"}]
        sim, player, target = prepare_simulation(
            rotation,
            self.inputs.stats_config,
            self.inputs.loadout_blueprints,
            self.base_config.dummy_hp,
            self.inputs.debuff_module,
            verbose=False,
            precast="eradicate",
        )
        erad = player.ability_db["eradicate"]
        erad.activation = {"type": "cast", "duration": 2.0}
        cast_dur = player.calculate_cast_time(2.0, ability=erad)
        hp_before = target.hp

        sim.run_until(cast_dur - 0.05, target=target)
        self.assertEqual(target.hp, hp_before, "No damage may land while the pre-cast is in flight")
        self.assertIsNone(sim.combat_start_time)

        sim.run_timed(duration=3.0, target=target)
        self.assertGreaterEqual(sim.combat_start_time, cast_dur - 1e-6)
        self.assertFalse([n for n in sim.tracker.breakdown if "Eradicate" in n])
        self.assertIn("Thrash", sim.tracker.breakdown)
        self.assertEqual(hp_before - target.hp, sim.tracker.total_damage)

    def test_pre_combat_buff_staging_and_stealth_break(self):
        """Verifies pre-combat buff sequence (stealth + recklessness) executes and breaks on 1st damage."""
        rotation = [{"type": "fixed", "ability_id": "thrash"}]

        sim, player, target = prepare_simulation(
            rotation,
            self.inputs.stats_config,
            self.inputs.loadout_blueprints,
            self.base_config.dummy_hp,
            self.inputs.debuff_module,
            verbose=False,
            pre_combat=["stealth", "recklessness", "eradicate"],
        )

        # Give Eradicate a 1.5s cast time
        erad = player.ability_db["eradicate"]
        erad.activation = {"type": "cast", "duration": 1.5}
        expected_cast_dur = player.calculate_cast_time(1.5, ability=erad)
        # Stealth incurs 1 GCD (1.4s), then Recklessness is off-GCD, then Eradicate casts
        stealth_gcd = player.calculate_gcd(1.5, ability=player.ability_db.get("stealth"))
        expected_hit_time = stealth_gcd + expected_cast_dur

        # Advance the raw clock to t=0.1s (during Stealth GCD); run_timed never stops inside pre-combat
        sim.run_until(0.1, target=target)

        # At t=0.1s, player should be stealthed and combat not yet started
        self.assertTrue(player.is_stealthed or any("stealth" in str(e).lower() for e in player.effects.keys()))
        self.assertIsNone(sim.combat_start_time, "Combat clock must not start during cast before damage")

        # Continue simulation to 5.0s of combat
        sim.run_timed(duration=5.0, target=target)

        # When Eradicate finished and dealt damage, breaking stealth and consuming Recklessness
        self.assertFalse(player.is_stealthed, "Stealth must break once the pre-cast starts")
        # The pre-cast deals no damage: combat starts with the first rotation hit, once the cast is done
        self.assertGreaterEqual(sim.combat_start_time, expected_hit_time - 1e-6)
        self.assertLessEqual(sim.combat_start_time, expected_hit_time + 0.1)
        self.assertNotIn("Eradicate", sim.tracker.breakdown)

    def test_no_precast_defaults_to_first_hit(self):
        """Verifies that with no pre-cast configured, behavior is fully backwards compatible."""
        rotation = [{"type": "fixed", "ability_id": "eradicate"}]

        sim, player, target = prepare_simulation(
            rotation,
            self.inputs.stats_config,
            self.inputs.loadout_blueprints,
            self.base_config.dummy_hp,
            self.inputs.debuff_module,
            verbose=False,
        )

        # Eradicate is instant by default in loadout
        sim.run_timed(duration=2.0, target=target)

        self.assertAlmostEqual(sim.combat_start_time, 0.0, places=2)
        self.assertGreater(sim.current_time, 1.5)
        self.assertLessEqual(sim.current_time, 2.0)
        self.assertAlmostEqual(sim.get_combat_duration(), sim.current_time, places=2)

    def test_run_config_has_no_opener_fields(self):
        """Openers belong to the rotation file: RunConfig carries no precast / pre_combat."""
        self.assertFalse(hasattr(self.base_config, "precast"))
        self.assertFalse(hasattr(self.base_config, "pre_combat"))

        normalized = normalize_pre_combat("snipe", ["stealth", "snipe"])
        self.assertEqual(normalized, [{"ability": "stealth"}, {"ability": "snipe"}])

    def test_rotation_dict_wrapper_with_multiple_pre_combat_abilities(self):
        """Verifies a rotation JSON dictionary containing multiple pre-combat abilities works seamlessly."""
        rot_dict = {
            "name": "Opener Dict Test",
            "pre_combat": ["stealth", "recklessness"],
            "precast": "eradicate",
            "sequence": [{"type": "fixed", "ability_id": "thrash"}],
        }

        sim, player, target = prepare_simulation(
            rot_dict,
            self.inputs.stats_config,
            self.inputs.loadout_blueprints,
            self.base_config.dummy_hp,
            self.inputs.debuff_module,
            verbose=False,
        )

        # Rotation steps should be cleanly unpacked from 'sequence'
        self.assertEqual(len(player.rotation.sequence), 1)
        self.assertEqual(player.rotation.sequence[0].ability_id, "thrash")

        # Run 2 seconds of combat
        sim.run_timed(duration=2.0, target=target)

        # Pre-combat abilities and the precast executed, but the precast dealt no damage to the dummy
        self.assertIsNotNone(sim.combat_start_time)
        self.assertIn("Thrash", sim.tracker.breakdown)
        self.assertFalse([n for n in sim.tracker.breakdown if "Eradicate" in n])

    def test_channel_concludes_before_subsequent_precast_ability(self):
        """Verifies that channeled pre-combat steps finalize cleanly before subsequent steps execute."""
        marauder_cfg_path = ROOT / "data" / "run_config" / "Carnage.json"
        if not marauder_cfg_path.exists():
            return
        m_cfg = load_run_config(str(marauder_cfg_path))
        inputs = load_from_run_config(m_cfg)
        sim, player, target = prepare_simulation(
            [{"type": "fixed", "ability_id": "assault"}],
            inputs.stats_config,
            inputs.loadout_blueprints,
            1_000_000,
            {},
            verbose=False,
            config=m_cfg,
            pre_combat=["channel_hatred", "berserk"],
        )
        sim.run_timed(duration=30.0, target=target)
        # Berserk buff should have been applied at conclusion of Channel Hatred channel
        berserk_buffs = [
            k for k, eff in player.effects.items()
            if any("berserk" in str(tag).lower() or "furies" in str(tag).lower() for tag in getattr(eff, "tags", ()))
        ]
        self.assertTrue(len(berserk_buffs) > 0 or "Assault" in sim.tracker.breakdown, "Berserk must cast successfully after Channel Hatred")
        self.assertIn("Assault", sim.tracker.breakdown)


# Must differ from the run config's own tactical (Hatred.json starts on the generic damage tactical).
SWAP_TACTICAL = "abl.itm.tactical.sow.inq_con.sin_shad.hat_sen.dmg_sust_01"


class PreCombatRunnerTests(unittest.TestCase):
    """Covers the time-driven PreCombatRunner: channel completion, single decision owner, waits, swaps, tracer times."""

    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)
        cls.config = load_run_config(str(RUN_CONFIG_PATH))
        cls.inputs = load_from_run_config(cls.config)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def _prepare(self, pre_combat, rotation=None, tracer=None):
        return prepare_simulation(
            rotation or [{"type": "fixed", "ability_id": "thrash"}],
            self.inputs.stats_config,
            self.inputs.loadout_blueprints,
            self.config.dummy_hp,
            copy.deepcopy(self.inputs.debuff_module),
            verbose=False,
            seed=7,
            config=self.config,
            pre_combat=pre_combat,
            tracer=tracer,
        )

    @staticmethod
    def _record_casts(player, sim):
        log = []
        for abl in set(player.ability_db.values()):
            orig = abl.cast

            def _wrap(caster, tgt, s, allow_clip=False, _a=abl, _fn=orig):
                ok = _fn(caster, tgt, s, allow_clip=allow_clip)
                if ok:
                    log.append((round(s.current_time, 4), _a.name))
                return ok

            abl.cast = _wrap
        return log

    def test_pre_combat_channel_runs_every_tick_before_next_step(self):
        """A pre-combat channel (Seethe) completes all ticks; the next step starts only after it ends."""
        sim, player, target = self._prepare(["seethe", "force_speed"])
        casts = self._record_casts(player, sim)
        sim.run_until(0.01, target=target)
        channel = player.active_channel
        self.assertIsNotNone(channel, "Seethe must be channeling at t=0")
        sim.run_timed(duration=3.0, target=target)

        self.assertTrue(channel.is_finished)
        self.assertEqual(channel.current_tick, channel.total_ticks, "Every channel tick must fire")
        speed_times = [t for t, name in casts if name == "Force Speed"]
        self.assertEqual(len(speed_times), 1)
        self.assertGreaterEqual(speed_times[0], round(channel.duration, 4) - 1e-3)
        self.assertFalse(player.pre_combat.active)

    def test_rotation_never_evaluates_during_pre_combat(self):
        """PlayerReady never runs the rotation while the runner owns decisions, and only one loop follows."""
        sim, player, target = self._prepare(["seethe", "force_speed"])
        evals = []
        orig_eval = player.rotation.evaluate

        def _spy(p, t, s):
            evals.append(round(s.current_time, 4))
            return orig_eval(p, t, s)

        player.rotation.evaluate = _spy
        sim.run_timed(duration=6.0, target=target)
        end = player.pre_combat.end_time
        self.assertIsNotNone(end)
        self.assertTrue(evals, "Rotation must take over after pre-combat")
        self.assertGreaterEqual(min(evals), end)
        self.assertEqual(len(evals), len(set(evals)), "Exactly one decision loop: no duplicate evaluations")

    def test_wait_step_delays_pull_and_fight_clock_starts_at_first_damage(self):
        """A wait step advances the clock; fight duration is measured from the first hit."""
        sim, player, target = self._prepare([{"wait": 2.0}])
        sim.run_timed(duration=5.0, target=target)
        self.assertAlmostEqual(sim.pre_combat_end_time, 2.0, places=3)
        self.assertGreaterEqual(sim.combat_start_time, 2.0)
        self.assertLessEqual(sim.current_time, sim.combat_start_time + 5.0 + 1e-6)
        self.assertGreaterEqual(sim.get_combat_duration(), 4.5)

    def test_wait_for_cooldown_holds_step_until_ready(self):
        """wait_for_cooldown recasts after the cooldown; without it the step is skipped."""
        sim, player, target = self._prepare(["force_speed", {"ability": "force_speed", "wait_for_cooldown": True}])
        casts = self._record_casts(player, sim)
        sim.run_timed(duration=1.0, target=target)
        times = [t for t, name in casts if name == "Force Speed"]
        self.assertEqual(len(times), 2)
        expected = player.calculate_cooldown(player.ability_db["force_speed"].cooldown, ability=player.ability_db["force_speed"])
        self.assertAlmostEqual(times[1] - times[0], expected, places=2)

        # Dict steps (consecutive identical string steps are de-duplicated by normalize_pre_combat)
        sim2, player2, target2 = self._prepare([{"ability": "force_speed"}, {"ability": "force_speed"}])
        sim2.run_timed(duration=1.0, target=target2)
        self.assertEqual(len(player2.pre_combat.skipped), 1)
        self.assertTrue(player2.pre_combat.skipped[0]["reason"].startswith("On cooldown"))

    def test_swap_after_combat_started_is_rejected(self):
        """Tactical swaps are out-of-combat only; a swap after the opener hit is skipped."""
        sim, player, target = self._prepare(["eradicate", {"swap_tactical": SWAP_TACTICAL}])
        start_tac = player.tactical_fqn
        sim.run_timed(duration=2.0, target=target)
        self.assertEqual(player.tactical_fqn, start_tac)
        self.assertEqual(len(player.pre_combat.skipped), 1)
        self.assertIn("in combat", player.pre_combat.skipped[0]["reason"])

    def test_swap_before_pull_is_recorded(self):
        """A pre-pull swap is applied, logged on the runner, and visible to the tracer with a negative time."""
        from src.swtorsim.debug.tracer import CombatTracer

        tracer = CombatTracer()
        sim, player, target = self._prepare([{"wait": 1.0}, {"swap_tactical": SWAP_TACTICAL}, {"wait": 0.5}], tracer=tracer)
        sim.run_timed(duration=3.0, target=target)
        self.assertEqual(player.tactical_fqn, SWAP_TACTICAL)
        self.assertEqual(player.starting_tactical_fqn, self.config.tactical_fqn)
        self.assertEqual([s["to"] for s in player.pre_combat.swaps], [SWAP_TACTICAL])

        data = tracer.to_dict()
        swaps = [e for e in data["events"] if e["type"] == "tactical_swap"]
        self.assertEqual(len(swaps), 1)
        self.assertLess(swaps[0]["t"], 0.0, "Pre-pull events are reported relative to T0 (negative)")
        self.assertLessEqual(data["summary"]["t_start"], swaps[0]["t"])
        # Report duration is combat time (from T0), never including the pre-pull phase
        self.assertGreater(data["summary"]["duration"], 2.5)
        self.assertLessEqual(data["summary"]["duration"], 3.0 + 1e-6)


FS_READY = {"ability_cooldown_under": {"name": "Force Speed", "value": 0.05}}


class WaitUntilAndPullGateTests(unittest.TestCase):
    """Covers conditional waits (wait_until steps) and the fight-start (pull) gate."""

    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)
        cls.config = load_run_config(str(RUN_CONFIG_PATH))
        cls.inputs = load_from_run_config(cls.config)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def _prepare_gate(self, pre_combat, pull=None, pull_max_wait=None, rotation=None):
        return prepare_simulation(
            rotation or [{"type": "fixed", "ability_id": "thrash"}],
            self.inputs.stats_config,
            self.inputs.loadout_blueprints,
            self.config.dummy_hp,
            copy.deepcopy(self.inputs.debuff_module),
            verbose=False,
            seed=7,
            config=self.config,
            pre_combat=pre_combat,
            pull_conditions=pull,
            pull_max_wait=pull_max_wait,
        )

    def _force_speed_cd(self, player):
        abl = player.ability_db["force_speed"]
        return player.calculate_cooldown(abl.cooldown, ability=abl)

    def test_wait_until_holds_sequence_until_rules_pass(self):
        sim, player, target = self._prepare_gate(["force_speed", {"wait_until": FS_READY}])
        sim.run_timed(duration=1.0, target=target)
        cd = self._force_speed_cd(player)
        self.assertEqual(player.pre_combat.skipped, [])
        self.assertGreaterEqual(sim.pre_combat_end_time, cd - 0.05)
        self.assertLessEqual(sim.pre_combat_end_time, cd + 0.15)

    def test_wait_until_times_out_and_skips(self):
        sim, player, target = self._prepare_gate(
            [{"wait_until": {"caster_has_buff": "No Such Buff"}, "max_wait": 1.0}]
        )
        sim.run_timed(duration=1.0, target=target)
        self.assertEqual(len(player.pre_combat.skipped), 1)
        self.assertIn("conditions not met", player.pre_combat.skipped[0]["reason"])
        self.assertAlmostEqual(sim.pre_combat_end_time, 1.0, delta=0.11)

    def test_pull_conditions_hold_the_fight_start(self):
        sim, player, target = self._prepare_gate(["force_speed"], pull=FS_READY)
        sim.run_timed(duration=2.0, target=target)
        cd = self._force_speed_cd(player)
        self.assertIsNotNone(player.pre_combat.pull_time)
        self.assertGreaterEqual(sim.combat_start_time, cd - 0.05)
        self.assertGreaterEqual(player.pre_combat.pull_time, cd - 0.05)

    def test_pull_conditions_from_rotation_file_wrapper(self):
        rot = {
            "pre_combat": ["force_speed"],
            "pull_conditions": FS_READY,
            "pull_max_wait": 30,
            "sequence": [{"type": "fixed", "ability_id": "thrash"}],
        }
        sim, player, target = self._prepare_gate(None, rotation=rot)
        self.assertEqual(player.pre_combat.pull_conditions, FS_READY)
        self.assertEqual(player.pre_combat.pull_max_wait, 30.0)
        sim.run_timed(duration=1.0, target=target)
        self.assertGreaterEqual(sim.combat_start_time, self._force_speed_cd(player) - 0.05)

    def test_pull_gate_without_steps_still_gates(self):
        sim, player, target = self._prepare_gate(None, pull={"caster_energy_above": 50})
        self.assertIsNotNone(player.pre_combat)
        sim.run_timed(duration=1.0, target=target)
        self.assertAlmostEqual(player.pre_combat.pull_time, 0.0, places=3)

    def test_unmet_pull_conditions_fail_the_run(self):
        from src.swtorsim.events import PullConditionsNotMetError

        sim, player, target = self._prepare_gate(None, pull={"caster_has_buff": "No Such Buff"}, pull_max_wait=2.0)
        with self.assertRaises(PullConditionsNotMetError):
            sim.run_timed(duration=5.0, target=target)
        self.assertIsNone(sim.combat_start_time)
        self.assertGreaterEqual(sim.current_time, 2.0 - 1e-6)

    def test_unknown_condition_key_rejected_at_setup(self):
        with self.assertRaises(ValueError):
            self._prepare_gate([{"wait_until": {"not_a_condition": 1}}])
        with self.assertRaises(ValueError):
            self._prepare_gate(None, pull={"not_a_condition": 1})


class FightRelativeTimeOutputTests(unittest.TestCase):
    """0.00 = first damage everywhere; pre-combat output is negative (display-only offset)."""

    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)
        cls.config = load_run_config(str(RUN_CONFIG_PATH))
        cls.inputs = load_from_run_config(cls.config)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    PRE = ["force_speed", {"wait": 2.0}]
    ROT = [{"type": "fixed", "ability_id": "thrash"}]

    def test_console_lines_are_relative_to_first_damage(self):
        import io
        from contextlib import redirect_stdout

        sim, player, target = prepare_simulation(
            self.ROT,
            self.inputs.stats_config,
            self.inputs.loadout_blueprints,
            self.config.dummy_hp,
            copy.deepcopy(self.inputs.debuff_module),
            verbose=True,
            seed=7,
            config=self.config,
            pre_combat=self.PRE,
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            sim.run_timed(duration=2.0, target=target)
        lines = [ln for ln in buf.getvalue().splitlines() if ln.startswith("[")]
        speed = next(ln for ln in lines if "casts Force Speed" in ln)
        first_hit = next(ln for ln in lines if " deals " in ln)
        self.assertTrue(speed.startswith("[-2.00s]"), speed)
        self.assertTrue(first_hit.startswith("[0.00s]"), first_hit)
        self.assertLess(lines.index(speed), lines.index(first_hit), "Buffered pre-combat lines print first")
        self.assertAlmostEqual(sim.relative_time(sim.combat_start_time), 0.0)

    def test_simulator_single_run_reports_relative_times(self):
        from src.swtorsim.web_gui import _run_single_test_detailed

        cfg = copy.deepcopy(self.config)
        cfg.duration = 4
        result = _run_single_test_detailed(
            cfg,
            {
                "rotation_config": {"pre_combat": self.PRE, "sequence": self.ROT},
                "stats_config": self.inputs.stats_config,
                "loadout_blueprints": self.inputs.loadout_blueprints,
                "debuff_module": copy.deepcopy(self.inputs.debuff_module),
            },
        )
        log = result["combat_log"]
        speed = next(ev for ev in log if ev["category"] == "cast" and ev["ability"] == "Force Speed")
        first_dmg = next(ev for ev in log if ev["category"] == "damage")
        self.assertAlmostEqual(speed["time"], -2.0, places=2)
        self.assertAlmostEqual(first_dmg["time"], 0.0, places=2)
        self.assertAlmostEqual(result["pre_combat_duration"], 2.0, places=2)
        self.assertLessEqual(result["duration"], 4.0 + 1e-6)
        for row in result["buffs"]:
            self.assertLessEqual(row["total_uptime"], result["duration"] + 0.01, row["name"])


if __name__ == "__main__":
    unittest.main()
