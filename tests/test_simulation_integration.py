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
        with self.subTest("proc_registry_populated"):
            self.assertIn("Bloodletting", self.player.proc_registry)
            self.assertEqual(self.player.proc_registry["Bloodletting"]["kind"], "lockout_effect")
            self.assertEqual(self.player.proc_registry["Bloodletting"]["effect_name"], "Bloodletting_3")
            self.assertIn("Languishing Lashes", self.player.proc_registry)
            self.assertEqual(self.player.proc_registry["Languishing Lashes"]["kind"], "trigger_icd")

        with self.subTest("bloodletting_proc_cooldown_check_evaluates_lockout"):
            rule = {"proc_cooldown_above": {"name": "Bloodletting", "value": 1.5}}
            result_initial = validate_all(rule, self.player, self.target, sim=self.sim)
            self.assertFalse(result_initial, "Should be False before Bloodletting lockout is applied")

            # Apply Bloodletting_3 lockout effect directly via the Bloodletting passive ability
            bl_passive = self.player.passive_db["bloodletting"]
            bl_passive.execute_effect(3, self.player, self.player, self.sim)
            self.assertIn("Bloodletting_3", self.player.effects)
            result_locked = validate_all(rule, self.player, self.target, sim=self.sim)
            self.assertTrue(result_locked, "Should be True when Bloodletting_3 lockout has >1.5s remaining and buff is absent")

        with self.subTest("ability_cooldown_above_and_under_evaluation"):
            # When Eradicate is off cooldown (cooldown remaining <= 0)
            self.assertTrue(
                validate_all({"ability_cooldown_under": {"name": "Eradicate", "value": 2.0}}, self.player, self.target, sim=self.sim),
                "ability_cooldown_under should be True when ability is off cooldown",
            )
            self.assertFalse(
                validate_all({"ability_cooldown_above": {"name": "Eradicate", "value": 2.0}}, self.player, self.target, sim=self.sim),
                "ability_cooldown_above should be False when ability is off cooldown",
            )

            # When Eradicate has 5.0 seconds remaining on cooldown
            self.player.cooldowns["Eradicate"] = self.sim.current_time + 5.0
            self.assertTrue(
                validate_all({"ability_cooldown_above": {"name": "Eradicate", "value": 2.0}}, self.player, self.target, sim=self.sim),
                "ability_cooldown_above should be True when 5.0s > 2.0s",
            )
            self.assertFalse(
                validate_all({"ability_cooldown_above": {"name": "Eradicate", "value": 6.0}}, self.player, self.target, sim=self.sim),
                "ability_cooldown_above should be False when 5.0s < 6.0s",
            )
            self.assertFalse(
                validate_all({"ability_cooldown_under": {"name": "Eradicate", "value": 2.0}}, self.player, self.target, sim=self.sim),
                "ability_cooldown_under should be False when 5.0s > 2.0s",
            )
            self.assertTrue(
                validate_all({"ability_cooldown_under": {"name": "Eradicate", "value": 6.0}}, self.player, self.target, sim=self.sim),
                "ability_cooldown_under should be True when 5.0s < 6.0s",
            )

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

        with self.subTest("phantom_stride_cast_via_proc_cooldown_above"):
            history_names = {name for (_entity, name) in self.sim.tracker.effect_history}
            self.assertIn(
                "Phantom Stride",
                history_names,
                "Expected Phantom Stride to be cast during BasicMaliPS rotation once Bloodletting lockout is active",
            )

    def test_08_permanent_and_proper_named_effects_logged_in_metrics(self):
        """Verifies permanent passives/debuffs with proper names are tracked in metrics while _x effects are excluded."""
        from src.swtorsim.metrics import has_proper_effect_name

        self.assertTrue(has_proper_effect_name("Lightning Charge"))
        self.assertTrue(has_proper_effect_name("Mark of Power"))
        self.assertTrue(has_proper_effect_name("Training Dummy Armor Debuff"))
        self.assertFalse(has_proper_effect_name("Assassin's Training_1"))
        self.assertFalse(has_proper_effect_name("Raze_2"))
        self.assertFalse(has_proper_effect_name("Creeping Terror_10"))
        self.assertFalse(has_proper_effect_name("abl.sith_inquisitor.lightning_charge:1"))

        self.sim.run_timed(duration=10.0, target=self.target)
        self.sim.tracker.finalize_effects(self.sim.current_time)

        history_names = {name for (_entity, name) in self.sim.tracker.effect_history}
        self.assertIn("Lightning Charge", history_names)
        self.assertIn("Mark of Power", history_names)
        self.assertIn("Thrashing Blades", history_names)
        for expected_debuff in (
            "Sundered (Physical)",
            "Beat Down (Physical)",
            "Marked (Physical)",
            "Vulnerable (Force)",
            "Susceptible (Tech)",
            "Assailable (Mental)",
            "Overwhelmed (Mental)",
        ):
            self.assertIn(expected_debuff, history_names)
        for name in history_names:
            self.assertTrue(
                has_proper_effect_name(name),
                f"Unnamed or _x suffixed effect '{name}' should not be stored in effect_history",
            )

    def test_09_high_energy_gas_cylinder_conditional_branch_hydration(self):
        """Verifies mutually exclusive branch resolution (conditions + run_if_none_ran) on High Energy Gas Cylinder."""
        import json
        from src.swtorsim.abilities import Ability, AbilityBlueprint
        from src.swtorsim.effects import ActiveEffect
        from src.swtorsim.entities import Player

        parsed_base = (
            ROOT / "data" / "extractor" / "live" / "parsed"
            if (ROOT / "data" / "extractor" / "live" / "parsed").exists()
            else ROOT / "data" / "extractor" / "parsed"
        )
        hegc_path = (
            parsed_base
            / "abl"
            / "bounty_hunter"
            / "skill"
            / "advanced_prototype"
            / "high_energy_gas_cylinder.json"
        )
        bt_path = (
            parsed_base
            / "tal"
            / "bounty_hunter"
            / "skill"
            / "advanced_prototype"
            / "blood_tracker.json"
        )
        hegc_raw = json.loads(hegc_path.read_text(encoding="utf-8"))
        eff1_node = hegc_raw["effects"][0]
        hegc_bp = AbilityBlueprint.from_file(hegc_path)
        bt_bp = AbilityBlueprint.from_file(bt_path)
        energy_stat = "stat_cbt_damage_dealt_scale_type_energy_modifier_percentage"

        with self.subTest("case_a_player_has_blood_tracker"):
            player_with_bt = Player(
                name="Powertech",
                passives={hegc_bp.fqn: hegc_bp, bt_bp.fqn: bt_bp},
            )
            player_with_bt.passive_db[bt_bp.fqn] = Ability(bt_bp)

            eff_from_node = ActiveEffect.from_effect_node(
                hegc_bp.fqn,
                hegc_bp.name,
                eff1_node,
                caster=player_with_bt,
            )
            energy_mods_node = [m for m in eff_from_node.modifiers if m.stat == energy_stat]
            self.assertEqual(len(energy_mods_node), 1)
            self.assertAlmostEqual(energy_mods_node[0].value, 0.07, places=5)

            hegc_abl = Ability(hegc_bp)
            hegc_abl.execute_effect(1, player_with_bt, player_with_bt, self.sim)
            active_eff = player_with_bt.effects["High Energy Gas Cylinder_1"]
            energy_mods_live = [m for m in active_eff.modifiers if m.stat == energy_stat]
            self.assertEqual(len(energy_mods_live), 1)
            self.assertAlmostEqual(energy_mods_live[0].value, 0.07, places=5)

        with self.subTest("case_b_player_does_not_have_blood_tracker"):
            player_no_bt = Player(
                name="Powertech",
                passives={hegc_bp.fqn: hegc_bp},
            )

            eff_from_node = ActiveEffect.from_effect_node(
                hegc_bp.fqn,
                hegc_bp.name,
                eff1_node,
                caster=player_no_bt,
            )
            energy_mods_node = [m for m in eff_from_node.modifiers if m.stat == energy_stat]
            self.assertEqual(len(energy_mods_node), 1)
            self.assertAlmostEqual(energy_mods_node[0].value, 0.05, places=5)

            hegc_abl = Ability(hegc_bp)
            hegc_abl.execute_effect(1, player_no_bt, player_no_bt, self.sim)
            active_eff = player_no_bt.effects["High Energy Gas Cylinder_1"]
            energy_mods_live = [m for m in active_eff.modifiers if m.stat == energy_stat]
            self.assertEqual(len(energy_mods_live), 1)
            self.assertAlmostEqual(energy_mods_live[0].value, 0.05, places=5)


    def test_10_call_effect_actor_1_routes_to_target(self):
        """Verifies call_effect with to_actor='actor_1' routes to the target, not the caster."""
        action = {
            "action_type": "call_effect",
            "effect": 2,
            "from_actor": "caster",
            "to_actor": "actor_1",
        }
        called_targets = []

        class MockAbility:
            def execute_effect(self, eff_id, c, t, sim, context=None):
                called_targets.append(t)

        execute_single_action(self.sim, self.player, self.target, action, "test_action", ability=MockAbility())
        self.assertEqual(called_targets, [self.target], "to_actor='actor_1' must route to target, not caster")


    def test_11_unpredicted_damage_modifier_raises_runtime_error(self):
        """Verifies that any damage modifier lacking an authoritative bucket raises an immediate RuntimeError."""
        from src.swtorsim.combat_math import _add_to_bucket
        test_buckets = {}
        with self.assertRaises(RuntimeError) as ctx:
            _add_to_bucket(
                test_buckets,
                None,
                0.15,
                stat_identifier="STAT_unmapped_mystery_stat",
                context_desc="Test Mock Buff",
            )
        self.assertIn("FATAL: UNPREDICTED DAMAGE MODIFIER", str(ctx.exception))
        self.assertIn("STAT_unmapped_mystery_stat", str(ctx.exception))

    def test_12_agitating_energies_refreshes_dot_and_triggers_damage(self):
        """Verifies Agitating Energies tactical refreshes Corrosive Dart duration and ticks extra damage on Followthrough."""
        from src.swtorsim.config_load import load_complete_loadout
        from src.swtorsim.effects import ActiveEffect

        loadout = load_complete_loadout([
            "abl.agent.corrosive_dart",
            "abl.agent.skill.marksmanship.followthrough",
            "abl.itm.tactical.sow.age_smu.sni_gun.mark_sharp.dmg_sust_01",
        ])
        stats_config = {"class_name": "sniper", "level": 80, "stats": {}}
        sim, player, target = prepare_simulation([], stats_config, loadout, 1000000, {}, verbose=False)
        player.stats["Ranged Accuracy"] = 1.10
        player.stats["Main Accuracy"] = 1.10
        player.stats["Tech Accuracy"] = 1.10
        player.stats["Ranged Damage Min"] = 2000
        player.stats["Ranged Damage Max"] = 2000
        player.stats["Bonus Damage (Ranged)"] = 3000
        player.stats["Bonus Damage (Tech)"] = 3000

        cd = player.ability_db["abl.agent.corrosive_dart"]
        ft = player.ability_db["abl.agent.skill.marksmanship.followthrough"]

        cd.cast(player, target, sim)
        sim.run_timed(duration=5.0, target=target)

        cd_eff = target.effects.get("Corrosive Dart") or list(target.effects.values())[0]
        self.assertEqual(cd_eff.expires_at, 18.0)
        hits_before = sim.tracker.breakdown["Corrosive Dart"]["hit_count"]

        # Followthrough requires tag.abl.agent.follow_through proc
        player.effects["follow_through_proc"] = ActiveEffect(
            fqn="mock", name="mock", number=1, tags=frozenset(["tag.abl.agent.follow_through"])
        )
        ft.cast(player, target, sim)
        sim.run_timed(duration=6.0, target=target)

        # Duration should be refreshed to 5.0 + 18.0 = 23.0s
        self.assertEqual(cd_eff.expires_at, 23.0)
        hits_after = sim.tracker.breakdown["Corrosive Dart"]["hit_count"]
        self.assertGreater(hits_after, hits_before, "Followthrough must trigger an extra tick of Corrosive Dart")

    def test_24_energy_tanks_max_energy_scaling(self):
        """Verifies tal.agent.energy_tanks increases Sniper max energy from 100 to 110."""
        from src.swtorsim.config_load import load_complete_loadout
        loadout = load_complete_loadout([
            "tal.agent.energy_tanks",
        ])
        stats_config = {"class_name": "sniper", "level": 80, "stats": {}}
        sim, player, target = prepare_simulation([], stats_config, loadout, 1000000, {}, verbose=False)
        self.assertEqual(player.resource.pool_type.lower(), "energy")
        self.assertEqual(player.resource.max_value, 110.0)
        self.assertEqual(player.resource.current_value, 110.0)

        # Spend 30 energy, energy drops to 80
        player.resource.spend(30.0)
        self.assertEqual(player.resource.current_value, 80.0)

        # Generate 50 energy, energy caps at 110
        player.resource.generate(50.0)
        self.assertEqual(player.resource.current_value, 110.0)

        # Also test Force Attunement (Sorcerer)
        sorc_loadout = load_complete_loadout([
            "tal.sith_inquisitor.skill.force_attunement",
        ])
        sorc_stats = {"class_name": "sorcerer", "level": 80, "stats": {}}
        _, sorc_player, _ = prepare_simulation([], sorc_stats, sorc_loadout, 1000000, {}, verbose=False)
        self.assertEqual(sorc_player.resource.pool_type.lower(), "force")
        self.assertEqual(sorc_player.resource.max_value, 600.0)
        self.assertEqual(sorc_player.resource.current_value, 600.0)

    def test_25_energy_barrel_channeled_cost_scaling(self):
        """Verifies Energy Barrel (+10 cost) properly applies to Penetrating Blasts and Gunslinger mirror."""
        from src.swtorsim.config_load import load_complete_loadout
        loadout = load_complete_loadout([
            "abl.agent.skill.marksmanship.penetrating_blasts",
            "abl.agent.skill.marksmanship.mods.tier3.efficient_shots",
            "abl.agent.laze_target",
        ])
        stats_config = {"class_name": "sniper", "level": 80, "stats": {}}
        sim, player, target = prepare_simulation([], stats_config, loadout, 1000000, {}, verbose=False)

        pb = player.ability_db["abl.agent.skill.marksmanship.penetrating_blasts"]
        laze = player.ability_db["abl.agent.laze_target"]

        # Base cost of PB is 0.0; with Energy Barrel active, modified cost must be 10.0
        pb_cost = player.calculate_resource_cost(pb.name, pb.energy_cost)
        self.assertEqual(pb_cost, 10.0, "Energy Barrel must increase Penetrating Blasts cost by 10.0")

        # Zero-cost ability with no modifiers remains 0.0
        laze_cost = player.calculate_resource_cost(laze.name, laze.energy_cost)
        self.assertEqual(laze_cost, 0.0, "Unmodified zero-cost ability must remain 0.0")

        # can_cast rejects when energy is insufficient for the upfront cost
        player.resource.current_value = 5.0
        self.assertFalse(pb.can_cast(player, target, sim), "PB must not be castable with insufficient energy for upfront cost")

        # can_cast allows when energy >= upfront cost
        player.resource.current_value = 50.0
        self.assertTrue(pb.can_cast(player, target, sim), "PB must be castable when energy >= upfront cost")

        # Casting PB deducts 10.0 upfront (+ 4.0 on entry tick)
        pb.cast(player, target, sim)
        self.assertEqual(player.resource.current_value, 36.0, "PB cast must deduct 10 upfront plus 4 entry tick energy")

        # Also verify Gunslinger mirror (Sharpshooter Energy Barrels on Penetrating Rounds)
        gs_loadout = load_complete_loadout([
            "abl.smuggler.skill.sharpshooter.penetrating_rounds",
            "abl.smuggler.skill.sharpshooter.mods.tier3.energy_barrels",
        ])
        gs_stats = {"class_name": "gunslinger", "level": 80, "stats": {}}
        _, gs_player, _ = prepare_simulation([], gs_stats, gs_loadout, 1000000, {}, verbose=False)
        pr = gs_player.ability_db["abl.smuggler.skill.sharpshooter.penetrating_rounds"]
        gs_cost = gs_player.calculate_resource_cost(pr.name, pr.energy_cost)
        self.assertEqual(gs_cost, 10.0, "Energy Barrels must increase Penetrating Rounds cost by 10.0 on Gunslinger")


if __name__ == "__main__":
    unittest.main()
