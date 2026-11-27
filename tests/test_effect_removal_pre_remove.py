"""Tests: effects removed before their natural expiry run their on_pre_remove branches, exactly once.

Also covers the custom ability-trigger hook passing the branch target through (Shoulder Cannon).
"""

import os
import unittest
from pathlib import Path

from src.swtorsim.abilities import Ability, AbilityBlueprint, execute_single_action, handle_buff_remove_action
from src.swtorsim.engine import Simulation
from src.swtorsim.entities import Dummy, Player

ROOT = Path(__file__).resolve().parents[1]

FQN = "abl.test.bomb"
KEY = f"{FQN}:1"
TAG = "tag.abl.test.bomb"
GAIN = {"action_type": "energy_recovery", "min": 2.0, "max": 2.0}
REMOVE = {"action_type": "remove_effect"}
DISPEL = {
    "action_type": "dispel",
    "tags": [TAG],
    "floats": {"amount_min": 0.0, "amount_max": 0.0},
    "ints": {"ability_spec": 0},
}
CONSUME = {"action_type": "modify_stack_charge", "floats": {"amount_min": -1.0, "amount_max": -1.0}}
SET_ZERO = {"action_type": "set_effect_stack_charge", "floats": {"amount": 0.0}, "ints": {"ability_spec": 0}}
OWNER = {"owner_effect_key": KEY}

HOOK_FQN = "abl.test.hook"
SUB_FQN = "abl.test.hook_sub"
SUB_KEY = f"{SUB_FQN}:1"
HOOK_ACTION = {"action_type": "custom", "ints": {"param1": 6855115466292073041, "param2": SUB_FQN}}


def _pre_remove(index, actions):
    return {"index": index, "triggers": [{"trigger": "on_pre_remove"}], "actions": actions}


def _setup(branches, stacks=1, duration=30.0):
    """A timed, tagged effect with ``stacks`` charges on the dummy, cast by the player (Force at 50)."""
    blueprint = AbilityBlueprint.from_dict({
        "fqn": FQN,
        "name": "Bomb",
        "type": "active",
        "effects": [{
            "number": 1,
            "entry": True,
            "name": "Bomb",
            "duration": duration,
            "tags": [TAG],
            "stack_charge": {"initial": stacks, "max": stacks},
            "branches": branches,
        }],
    })
    sim = Simulation(verbose=False, seed=1)
    player = Player("assassin")
    target = Dummy("Target Dummy", hp=1_000_000)
    player.current_target = target
    player.resource.current_value = 50.0
    Ability(blueprint).execute_effect(1, player, target, sim)
    return sim, player, target


def _act(sim, player, target, action):
    context = {"owner_entity": target, **OWNER}
    execute_single_action(sim, player, target, action, "Bomb", context=context)


class EarlyRemovalRunsPreRemoveTests(unittest.TestCase):
    def test_remove_effect_runs_on_pre_remove(self):
        sim, player, target = _setup([_pre_remove(2, [GAIN])])

        _act(sim, player, target, REMOVE)

        self.assertEqual(player.resource.current_value, 52.0)
        self.assertNotIn(KEY, target.effects)

    def test_dispel_runs_on_pre_remove(self):
        sim, player, target = _setup([_pre_remove(2, [GAIN])])

        execute_single_action(sim, player, target, DISPEL, "Bomb")

        self.assertEqual(player.resource.current_value, 52.0)
        self.assertNotIn(KEY, target.effects)

    def test_losing_the_last_stack_runs_on_pre_remove(self):
        sim, player, target = _setup([_pre_remove(2, [GAIN])], stacks=2)

        _act(sim, player, target, CONSUME)
        self.assertEqual(player.resource.current_value, 50.0, "one stack left: the effect is not removed yet")
        self.assertIn(KEY, target.effects)

        _act(sim, player, target, CONSUME)
        self.assertEqual(player.resource.current_value, 52.0)
        self.assertNotIn(KEY, target.effects)

    def test_setting_stacks_to_zero_runs_on_pre_remove(self):
        sim, player, target = _setup([_pre_remove(2, [GAIN])], stacks=3)

        _act(sim, player, target, SET_ZERO)

        self.assertEqual(player.resource.current_value, 52.0)
        self.assertNotIn(KEY, target.effects)

    def test_early_removal_does_not_fire_again_at_the_original_expiry(self):
        sim, player, target = _setup([_pre_remove(2, [GAIN])], duration=5.0)

        _act(sim, player, target, REMOVE)
        sim.run_until(10.0)

        self.assertEqual(player.resource.current_value, 52.0)


class PreRemoveRunsOnceTests(unittest.TestCase):
    def test_natural_expiry_runs_on_pre_remove_once(self):
        sim, player, target = _setup([_pre_remove(2, [GAIN])], duration=5.0)

        sim.run_until(10.0)

        self.assertEqual(player.resource.current_value, 52.0)
        self.assertNotIn(KEY, target.effects)

    def test_branch_removing_its_own_effect_runs_once_on_expiry(self):
        # Shape of the Firefall legendary: the on_pre_remove branch ends with remove_effect.
        sim, player, target = _setup([_pre_remove(2, [GAIN, REMOVE])], duration=5.0)

        sim.run_until(10.0)

        self.assertEqual(player.resource.current_value, 52.0)
        self.assertNotIn(KEY, target.effects)

    def test_branch_removing_its_own_effect_runs_once_on_early_removal(self):
        sim, player, target = _setup([_pre_remove(2, [GAIN, REMOVE])], duration=5.0)

        _act(sim, player, target, DISPEL)
        sim.run_until(10.0)

        self.assertEqual(player.resource.current_value, 52.0)
        self.assertNotIn(KEY, target.effects)


class CustomHookTargetTests(unittest.TestCase):
    def _setup(self):
        sub = AbilityBlueprint.from_dict({
            "fqn": SUB_FQN,
            "name": "Hook Sub",
            "type": "active",
            "effects": [{"number": 1, "entry": True, "name": "Hook Sub", "duration": 10.0, "branches": []}],
        })
        sim = Simulation(verbose=False, seed=1)
        player = Player("powertech")
        target = Dummy("Target Dummy", hp=1_000_000)
        player.current_target = target
        player.ability_db[SUB_FQN] = Ability(sub)
        return sim, player, target

    def test_hook_runs_the_sub_ability_on_the_branch_target(self):
        sim, player, target = self._setup()

        execute_single_action(sim, player, target, HOOK_ACTION, "Hook")

        self.assertIn(SUB_KEY, target.effects)
        self.assertNotIn(SUB_KEY, player.effects)

    def test_hook_stays_on_the_caster_when_the_branch_targets_the_caster(self):
        sim, player, target = self._setup()

        execute_single_action(sim, player, player, HOOK_ACTION, "Hook")

        self.assertIn(SUB_KEY, player.effects)
        self.assertNotIn(SUB_KEY, target.effects)


class ExtractedBlueprintRemovalTests(unittest.TestCase):
    """The same behaviour on real extracted blueprints (Bounty Hunter)."""

    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def _make(self, fqns):
        from src.swtorsim.config_load import load_complete_loadout
        from src.swtorsim.setup import prepare_simulation

        loadout = load_complete_loadout(fqns)
        stats_config = {"class_name": "powertech", "level": 80, "stats": {}}
        sim, player, target = prepare_simulation([], stats_config, loadout, 10_000_000, {}, verbose=False)
        for key in ("Ranged Accuracy", "Main Accuracy", "Tech Accuracy", "Melee Accuracy", "Force Accuracy"):
            player.stats[key] = 1.10
        player.stats["Bonus Damage (Tech)"] = 3000
        return sim, player, target

    @staticmethod
    def _advance(sim, target, time):
        sim.run_until(time, target=target)
        sim.current_time = time

    def test_thermal_detonator_removed_early_detonates_once(self):
        fqn = "abl.bounty_hunter.skill.advanced_prototype.thermal_detonator"
        sim, player, target = self._make([fqn])
        detonator = player.ability_db[fqn]
        self.assertTrue(detonator.cast(player, target, sim))
        self._advance(sim, target, 1.0)
        key = next(k for k in dict.keys(target.effects) if "thermal_detonator" in k)

        handle_buff_remove_action(
            sim, player, target, {"action_type": "remove_effect"}, ability=detonator,
            context={"owner_effect_key": key, "owner_entity": target},
        )

        hits = lambda: sim.tracker.breakdown.get("Thermal Detonator", {}).get("hit_count", 0)
        self.assertEqual(hits(), 1, "the explosion lives in on_pre_remove and must fire on early removal")
        self._advance(sim, target, 6.0)
        self.assertEqual(hits(), 1, "no second explosion at the original 3.4s expiry")

    def test_shoulder_cannon_hits_the_enemy_and_starts_its_cooldown_on_the_last_missile(self):
        cannon_fqn = "abl.bounty_hunter.shoulder_cannon"
        charges_tag = "tag.abl.bounty_hunter.shoulder_cannon_charges"
        sim, player, target = self._make([
            cannon_fqn,
            "abl.bounty_hunter.shoulder_cannon_custom",
            "tal.bounty_hunter.skill.utility.efficient_suit",
        ])
        cannon = player.ability_db[cannon_fqn]

        def missiles():
            return next(
                (e for e in dict.values(player.effects)
                 if not e.is_expired and charges_tag in getattr(e, "tags", ())),
                None,
            )

        player_hp, target_hp = player.hp, target.hp
        self.assertTrue(cannon.cast(player, target, sim))
        self._advance(sim, target, 20.0)  # Missile Loader (18s) has finished
        self.assertEqual(missiles().stacks, 4)

        fired, time = 0, 20.0
        while missiles() is not None and fired < 6:
            if cannon.cast(player, target, sim):
                fired += 1
            time += 2.0
            self._advance(sim, target, time)

        self.assertEqual(fired, 4)
        self.assertEqual(player.hp, player_hp, "missiles must not hit the caster")
        self.assertLess(target.hp, target_hp, "missiles must hit the enemy")
        remaining = player.cooldowns.get(cannon.name, 0.0) - sim.current_time
        self.assertGreater(remaining, 80.0, "the 90s cooldown starts when the last missile is fired")


if __name__ == "__main__":
    unittest.main()
