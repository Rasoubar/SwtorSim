import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.swtorsim.abilities import execute_single_action
from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.requirements import validate_all
from src.swtorsim.run_config import load_run_config
from src.swtorsim.setup import prepare_simulation

RUN_CONFIG_PATH = (
    ROOT / "data" / "run_config" / "hatred_14gcd.json"
    if (ROOT / "data" / "run_config" / "hatred_14gcd.json").exists()
    else ROOT / "data" / "run_config" / "first_test.json"
)


class SimulationIntegrationTests(unittest.TestCase):
    """Integration and regression suite covering completed fixes and remaining simulation milestones."""

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
        self.sim, self.player, self.target = prepare_simulation(
            self.inputs.rotation_config,
            self.inputs.stats_config,
            self.inputs.loadout_blueprints,
            self.config.dummy_hp,
            self.inputs.debuff_module,
        )

    # -------------------------------------------------------------------------
    # 1. Completed Fixes Verification
    # -------------------------------------------------------------------------

    def test_01_extracted_condition_logic_evaluation(self):
        """Verifies extracted AST condition trees (if_toughness, has_ability, has_effect) evaluate properly."""
        with self.subTest("target_dummy_is_boss_toughness"):
            cond = {
                "list": [
                    {
                        "id": "c1",
                        "type": "if_toughness",
                        "negated": True,
                        "actor": "target",
                        "comparison": "lte",
                        "ints": {"toughness": 3},
                    }
                ],
                "logic": {"condition": "c1"},
            }
            self.assertTrue(validate_all(cond, self.player, self.target, sim=self.sim))

        with self.subTest("has_ability_matches_loadout"):
            cond = {
                "list": [
                    {
                        "id": "c2",
                        "type": "has_ability",
                        "negated": False,
                        "actor": "caster",
                        "comparison": "gte",
                        "ability_spec": "abl.sith_inquisitor.skill.hatred.eradicate",
                        "ints": {"rank": 1},
                    }
                ],
                "logic": {"condition": "c2"},
            }
            self.assertTrue(validate_all(cond, self.player, self.target, sim=self.sim))

    def test_02_persistent_dot_lifecycle_and_ticks(self):
        """Verifies DoTs apply on_apply sub-effects, tick periodic damage, and expire cleanly."""
        self.sim.queue.clear()
        eradicate = self.player.ability_db["eradicate"]
        self.assertTrue(eradicate.cast(self.player, self.target, self.sim))

        with self.subTest("dot_and_on_apply_vulnerability_applied"):
            self.assertTrue(
                self.target.has_effect("Crushed (Eradicate)"),
                "Crushed (Eradicate) DoT should be active on target immediately after cast",
            )
            self.assertTrue(
                self.target.has_effect("Vulnerable (Force)"),
                "Vulnerable (Force) should be applied via Crushed (Eradicate)'s on_apply branch",
            )

        with self.subTest("dot_ticks_six_times_and_expires"):
            self.sim.run_timed(duration=6.5, target=self.target)
            eradicate_metrics = self.sim.tracker.breakdown.get("Eradicate", {})
            self.assertEqual(
                eradicate_metrics.get("hit_count", 0),
                7,
                "Eradicate should record 1 initial hit + 6 periodic DoT ticks (7 total hits)",
            )
            self.assertFalse(
                self.target.has_effect("Crushed (Eradicate)"),
                "Crushed (Eradicate) should be expired and removed after 6 ticks",
            )

    def test_02b_creeping_terror_dot_lifecycle_and_ticks(self):
        """Verifies Creeping Terror applies DoT, ticks 6 periodic damage hits + 1 initial hit, and lasts full duration."""
        self.sim.queue.clear()
        self.target.effects.clear()
        ct = self.player.ability_db["creeping_terror"]
        self.assertTrue(ct.cast(self.player, self.target, self.sim))

        with self.subTest("creeping_terror_applied_to_target"):
            self.assertTrue(
                self.target.has_effect("Creeping Terror"),
                "Creeping Terror DoT should be active on target immediately after cast",
            )

        with self.subTest("creeping_terror_ticks_and_expires_at_full_duration"):
            # 1 initial hit + 6 periodic DoT ticks over ~16.6s with alacrity
            self.sim.run_timed(duration=18.0, target=self.target)
            ct_metrics = self.sim.tracker.breakdown.get("Creeping Terror", {})
            self.assertEqual(
                ct_metrics.get("hit_count", 0),
                7,
                "Creeping Terror should record 1 initial hit + 6 periodic DoT ticks (7 total hits)",
            )
            self.assertFalse(
                self.target.has_effect("Creeping Terror"),
                "Creeping Terror should be expired and removed after 6 ticks",
            )

    def test_03_extracted_combat_action_handlers(self):
        """Verifies extracted resource recovery, cooldown modification, charge modification, and dispel."""
        with self.subTest("energy_recovery_and_regen_force"):
            self.player.resource.spend(50.0)
            before = self.player.resource.current_value
            execute_single_action(
                self.sim,
                self.player,
                self.target,
                {"action_type": "energy_recovery", "min": 15.0, "max": 15.0, "percent": 0.0},
                "TestRecovery",
            )
            self.assertAlmostEqual(self.player.resource.current_value, before + 15.0)

        with self.subTest("modify_cooldown_percentage_reset"):
            self.player.cooldowns["Leeching Strike"] = 12.0
            execute_single_action(
                self.sim,
                self.player,
                self.target,
                {
                    "action_type": "modify_cooldown",
                    "floats": {"amount": -1.0, "amount_min": 0.0},
                    "ints": {"ability_spec": "abl.sith_inquisitor.skill.hatred.leeching_strike"},
                    "bools": {"is_percentage": True},
                    "strings": {"tag": "", "tags": ""},
                },
                "MaliciousnessProc",
            )
            self.assertNotIn("Leeching Strike", self.player.cooldowns)

        with self.subTest("dispel_removes_tagged_effect"):
            eradicate = self.player.ability_db["eradicate"]
            eradicate.cast(self.player, self.target, self.sim)
            self.assertTrue(self.target.has_effect("Crushed (Eradicate)"))
            execute_single_action(
                self.sim,
                self.player,
                self.target,
                {
                    "action_type": "dispel",
                    "tags": ["tag.abl.sith_inquisitor.demolish_dot"],
                    "floats": {"amount_max": 1.0, "amount_min": 1.0},
                    "ints": {"ability_spec": 0},
                },
                "TestDispel",
            )
            self.assertFalse(self.target.has_effect("Crushed (Eradicate)"))

    # -------------------------------------------------------------------------
    # 2. Tests for Remaining Milestones (TODO #6, #7, #8 & Full Simulation)
    # -------------------------------------------------------------------------

    def test_04_self_buff_application_recklessness(self):
        """[TODO #7] Verifies Recklessness applies its buff to the caster, not the enemy target."""
        self.sim.queue.clear()
        recklessness = self.player.ability_db["recklessness"]
        self.assertTrue(recklessness.cast(self.player, self.target, self.sim))

        self.assertTrue(
            self.player.has_effect("Recklessness"),
            "Casting Recklessness must apply the 'Recklessness' buff to the player (caster)",
        )
        self.assertFalse(
            self.target.has_effect("Recklessness"),
            "Recklessness is a self-buff and should not be applied to the target dummy",
        )
        self.assertTrue(
            validate_all({"caster_has_buff": "Recklessness"}, self.player, self.target, sim=self.sim),
            "Rotation rule {'caster_has_buff': 'Recklessness'} must evaluate to True after casting Recklessness",
        )

    def test_05_saber_strike_effect_conditions_and_nonzero_damage(self):
        """[TODO #8] Verifies Saber Strike evaluates effect-level conditions and deals >0 damage per hit."""
        self.sim.queue.clear()
        # Ensure 100% hit chance for deterministic multi-hit testing
        self.player.base_stats["Accuracy Rating"] = 999999
        self.player.recalculate_stats()
        self.player.stats["Main Accuracy"] = 2.0
        self.player.stats["Off Accuracy"] = 2.0

        saber_strike = self.player.ability_db["saber_strike"]
        self.assertTrue(saber_strike.cast(self.player, self.target, self.sim))

        ss_metrics = self.sim.tracker.breakdown.get("Saber Strike", {})
        hit_count = ss_metrics.get("hit_count", 0)
        total_damage = ss_metrics.get("total_damage", 0)

        with self.subTest("mutually_exclusive_entry_effects_do_not_both_fire"):
            self.assertEqual(
                hit_count,
                3,
                f"Saber Strike armed entry effect should deal exactly 3 flurry sub-hits (1 from branch 2 + 2 from branch 3); got {hit_count}",
            )

        with self.subTest("no_zero_damage_hits"):
            self.assertGreater(total_damage, 0, "Saber Strike should deal positive total damage")
            eff1 = saber_strike.effects[1]
            for branch in eff1.branches:
                hp_before = self.target.hp
                branch.execute(self.sim, self.player, self.target, ability=saber_strike)
                dealt = hp_before - self.target.hp
                self.assertGreater(
                    dealt,
                    0,
                    f"Saber Strike Effect 1 Branch {branch.index} dealt 0 damage (hand={branch.actions[0].get('hand')})",
                )

    def test_06_passive_registration_and_proc_icd_tracking(self):
        """[TODO #6] Verifies passives/procs (e.g. Bloodletting) are registered and proc_cooldown_above works."""
        with self.subTest("bloodletting_proc_cooldown_check_does_not_crash"):
            rule = {"proc_cooldown_above": {"name": "Bloodletting", "value": 1.5}}
            try:
                result = validate_all(rule, self.player, self.target, sim=self.sim)
            except AttributeError as exc:
                self.fail(
                    f"validate_all crashed on 'proc_cooldown_above' for 'Bloodletting': {exc}. "
                    f"Passives/procs in player.passive_blueprints need to populate player.procs or handle missing procs."
                )
            self.assertIsInstance(result, bool)

    def test_07_full_hatred_rotation_simulation_run(self):
        """[End-to-End] Runs a 30-second Hatred Assassin simulation and validates rotational execution."""
        try:
            self.sim.run_timed(duration=30.0, target=self.target)
        except Exception as exc:
            self.fail(f"30-second Hatred rotation simulation crashed at t={self.sim.current_time:.2f}s: {type(exc).__name__}: {exc}")

        breakdown = self.sim.tracker.breakdown

        with self.subTest("simulation_reaches_full_duration"):
            self.assertGreaterEqual(self.sim.current_time, 28.0)

        with self.subTest("core_rotational_abilities_dealt_damage"):
            expected_abilities = [
                "Eradicate",
                "Creeping Terror",
                "Discharge",
                "Leeching Strike",
                "Death Field",
            ]
            for ability_name in expected_abilities:
                with self.subTest(ability=ability_name):
                    self.assertIn(
                        ability_name,
                        breakdown,
                        f"Expected rotational ability '{ability_name}' to be cast and deal damage during 30s run",
                    )
                    self.assertGreater(
                        breakdown[ability_name]["total_damage"],
                        0,
                        f"'{ability_name}' dealt 0 total damage",
                    )

        with self.subTest("total_dps_is_positive"):
            dps = self.sim.tracker.total_damage / max(1.0, self.sim.current_time)
            self.assertGreater(dps, 5000.0, f"Expected meaningful DPS (>5,000), got {dps:.1f}")


if __name__ == "__main__":
    unittest.main()
