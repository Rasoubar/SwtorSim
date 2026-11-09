import os
import sys
import unittest
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.swtorsim.abilities import Ability
from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.run_config import load_run_config
from src.swtorsim.setup import prepare_simulation

RUN_CONFIG_PATH = (
    ROOT / "data" / "run_config" / "hatred_14gcd.json"
    if (ROOT / "data" / "run_config" / "hatred_14gcd.json").exists()
    else ROOT / "data" / "run_config" / "first_test.json"
)


class AbilityExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def setUp(self):
        """Prepares a fresh simulation, player, and target dummy for each test."""
        config = load_run_config(str(RUN_CONFIG_PATH))
        inputs = load_from_run_config(config)
        self.sim, self.player, self.target = prepare_simulation(
            inputs.rotation_config,
            inputs.stats_config,
            inputs.loadout_blueprints,
            config.dummy_hp,
            inputs.debuff_module,
        )

    def _find_ability(self, predicate: Callable[[Ability], bool]) -> Ability:
        """Finds a distinct ability from the player's database matching a condition."""
        for ability in self.player.ability_db.values():
            if predicate(ability):
                return ability
        self.fail("Could not find an ability matching test criteria in the current loadout.")

    # --- 1. Cast Validation & Resource Deduction ---

    def test_cast_spends_resources(self):
        """Verifies that casting an ability deducts resources from the player."""
        ability = self._find_ability(
            lambda a: a.type == "active" and a.energy_cost > 0 and a.triggers_gcd
        )

        initial_resource = self.player.resource.current_value
        self.assertTrue(
            ability.can_cast(self.player, self.target, self.sim),
            f"Ability {ability.name} should be ready to cast",
        )

        success = ability.cast(self.player, self.target, self.sim)
        self.assertTrue(success, f"Failed to cast {ability.name}")

        # Verify resource was spent
        self.assertLess(
            self.player.resource.current_value,
            initial_resource,
            "Player resource was not deducted after casting",
        )

    def test_insufficient_resource_blocks_cast(self):
        """Verifies that an ability cannot be cast if the player cannot afford the cost."""
        ability = self._find_ability(
            lambda a: a.type == "active" and a.energy_cost > 0
        )

        # Force resource to 0
        self.player.resource.spend(self.player.resource.current_value)

        self.assertFalse(
            ability.can_cast(self.player, self.target, self.sim),
            f"{ability.name} should not be castable with 0 energy",
        )
        self.assertFalse(
            ability.cast(self.player, self.target, self.sim),
            f"{ability.name} cast should have failed due to insufficient resources",
        )

    # --- 2. Global Cooldown (GCD) Locks ---

    def test_gcd_lockout_prevents_simultaneous_casts(self):
        """Verifies that abilities that trigger GCD advance next_gcd and lock subsequent casts."""
        ability = self._find_ability(
            lambda a: a.type == "active" and a.triggers_gcd
        )

        cast_time = self.sim.current_time
        success = ability.cast(self.player, self.target, self.sim)
        self.assertTrue(success)

        # Assert next_gcd moved into the future
        self.assertGreater(
            self.player.next_gcd,
            cast_time,
            "next_gcd was not pushed into the future after casting an active ability",
        )

        # Verify other active abilities on the GCD cannot be cast immediately
        other_ability = self._find_ability(
            lambda a: a.type == "active" and a.triggers_gcd and a.name != ability.name
        )
        self.assertFalse(
            other_ability.can_cast(self.player, self.target, self.sim),
            f"{other_ability.name} should be blocked while player is under GCD",
        )

    # --- 3. Ability-Specific Cooldowns ---

    def test_ability_cooldown_enforcement(self):
        """Verifies that abilities place an entry in caster.cooldowns preventing immediate recast."""
        ability = self._find_ability(
            lambda a: a.type == "active" and a.cooldown > 0 and not a.has_charges
        )

        success = ability.cast(self.player, self.target, self.sim)
        self.assertTrue(success)

        # Cooldown should now be recorded in player's cooldown dictionary
        cd_expiration = self.player.cooldowns.get(ability.name)
        self.assertIsNotNone(
            cd_expiration,
            f"Cooldown for {ability.name} was not recorded in player.cooldowns",
        )
        self.assertGreater(cd_expiration, self.sim.current_time)

        # Fast-forward GCD past lockout to verify cooldown specifically blocks recasting
        self.player.next_gcd = self.sim.current_time
        self.assertFalse(
            ability.can_cast(self.player, self.target, self.sim),
            f"{ability.name} should still be blocked by its individual cooldown even after GCD expires",
        )

    # --- 4. Charge System ---

    def test_charge_consumption(self):
        """Verifies that charge-based abilities decrement charges on cast."""
        try:
            ability = self._find_ability(lambda a: a.has_charges)
        except AssertionError:
            self.skipTest("No charge-based ability found in current run configuration loadout.")

        initial_charges = ability.charges
        self.assertGreater(initial_charges, 0)

        success = ability.cast(self.player, self.target, self.sim)
        self.assertTrue(success)

        self.assertEqual(
            ability.charges,
            initial_charges - 1,
            f"{ability.name} charges should have decremented by 1",
        )

    # --- 5. Damage Execution ---

    def test_damage_action_reduces_target_health(self):
        """Verifies that executing an attack ability inflicts damage to the target dummy."""
        attack_ability = self._find_ability(
            lambda a: a.type == "active"
            and any(
                branch.is_attack
                for eff in a.effects.values()
                for branch in eff.branches
            )
        )

        initial_hp = getattr(self.target, "current_hp", None)
        if initial_hp is None:
            initial_hp = getattr(self.target, "hp", 0)

        success = attack_ability.cast(self.player, self.target, self.sim)
        self.assertTrue(success, f"Attack ability {attack_ability.name} failed to cast")

        # Resolve any scheduled hit events in the event queue
        if hasattr(self.sim, "run_until"):
            self.sim.run_until(self.sim.current_time + 0.1)

        current_hp = getattr(self.target, "current_hp", getattr(self.target, "hp", 0))
        self.assertLess(
            current_hp,
            initial_hp,
            f"Target HP did not decrease after taking damage from {attack_ability.name}",
        )


    def test_modify_recharge_time_advances_charge_restore_event(self):
        """Verifies that modify_recharge_time reduces in-flight recharge timer on charge-based abilities."""
        from src.swtorsim.abilities import handle_cooldown_modification
        charge_abl = self._find_ability(lambda a: a.has_charges and a.charges > 0)
        initial_charges = charge_abl.charges

        # Consume 1 charge to start recharge chain
        charge_abl.consume_charge(self.player, self.sim)
        self.assertEqual(charge_abl.charges, initial_charges - 1)
        self.assertIsNotNone(charge_abl.active_charge_event)
        orig_target_time = charge_abl.recharge_target_time

        # Apply modify_recharge_time action of -2.0s
        action = {
            "action_type": "modify_recharge_time",
            "floats": {"amount": -2.0},
            "ints": {"ability_spec": charge_abl.fqn},
            "bools": {"is_percentage": False},
        }
        handle_cooldown_modification(self.sim, self.player, action)
        self.assertAlmostEqual(charge_abl.recharge_target_time, orig_target_time - 2.0, places=3)

    def test_weapon_mode_wildcard_trigger_rejects_periodic_dots(self):
        """Verifies that weapon_mode: 3 triggers (e.g. Lazer Focus) reject DoTs (weapon_mode: 0) and accept weapon hits."""
        proc_count = 0
        class MockBranch:
            triggers = [{
                "trigger": "on_damage_dealt",
                "ints": {"actor": 1, "damage_type": 5, "weapon_mode": 3, "spell_type": 1},
                "floats": {"proc_chance_percent": 100.0},
            }]
            def execute(self, inner_sim, caster, target, context=None, ability=None):
                nonlocal proc_count
                proc_count += 1
        branch = MockBranch()
        class MockAbl:
            def execute_branch(self, sim, branch, caster, target, context=None):
                branch.execute(sim, caster, target, context=context)
                return True
        self.sim.triggers.subscribe("test_owner", MockAbl(), branch, self.player, self.player)

        # 1. Periodic DoT event: weapon_mode = 0, is_periodic = True
        dot_ctx = {
            "caster": self.player,
            "target": self.target,
            "is_periodic": True,
            "is_weapon_attack": False,
            "weapon_mode": 0,
            "damage_type": 4,
            "spell_type": 2,
        }
        self.sim.triggers.dispatch("on_damage_dealt", self.sim, dot_ctx)
        self.assertEqual(proc_count, 0, "DoT tick with weapon_mode=0 must NOT proc weapon_mode=3 trigger!")

        # 2. Melee weapon attack: weapon_mode = 2 (attack_type=1)
        melee_ctx = {
            "caster": self.player,
            "target": self.target,
            "is_periodic": False,
            "is_weapon_attack": True,
            "weapon_mode": 2,
            "damage_type": 1,
            "spell_type": 1,
        }
        self.sim.triggers.dispatch("on_damage_dealt", self.sim, melee_ctx)
        self.assertEqual(proc_count, 0, "Melee weapon hit (weapon_mode=2) must NOT proc weapon_mode=3 (Ranged) trigger!")

        # 3. Direct Ranged weapon attack: weapon_mode = 3 (attack_type=2)
        ranged_ctx = {
            "caster": self.player,
            "target": self.target,
            "is_periodic": False,
            "is_weapon_attack": True,
            "weapon_mode": 3,
            "damage_type": 1,
            "spell_type": 1,
        }
        self.sim.triggers.dispatch("on_damage_dealt", self.sim, ranged_ctx)
        self.assertEqual(proc_count, 1, "Ranged weapon hit (weapon_mode=3) must proc weapon_mode=3 trigger!")

if __name__ == "__main__":
    unittest.main()