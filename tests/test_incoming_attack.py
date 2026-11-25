"""Incoming melee swings on the player: scheduling, trigger filters, and config."""

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.swtorsim.abilities import Branch
from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.events import ApplyDamageLand, IncomingAttack
from src.swtorsim.run_config import load_run_config, validate_run_config, _require_non_negative_float
from src.swtorsim.setup import prepare_simulation

RUN_CONFIG_PATH = ROOT / "data" / "run_config" / "Hatred.json"
SABER = {"steps": [{"type": "fixed", "ability_id": "saber_strike"}]}
RETALIATION = [{
    "action_type": "damage",
    "coeff": 1.0,
    "shp_min": 100.0,
    "shp_max": 100.0,
    "amp": 0.0,
    "hand": "main",
    "slots": ["3"],
    "tags": [],
}]


class _Probe:
    """Records each time a subscribed branch is asked to run."""

    def __init__(self, name):
        self.name = name
        self.fqn = name
        self.times = []

    def execute_branch(self, sim, branch, caster, target, context=None):
        self.times.append(sim.current_time)
        ran, _success = branch.execute(sim, caster, target, context=context, ability=self)
        return ran


def _listener(name, trigger, ints=None, actions=None, target_overrides=None, tags=None):
    probe = _Probe(name)
    raw = {"trigger": trigger}
    if ints:
        raw["ints"] = ints
    if tags:
        raw["tags"] = list(tags)
    branch = Branch(
        index=1,
        triggers=[raw],
        actions=list(actions or []),
        target_overrides=list(target_overrides or []),
    )
    return probe, branch


class IncomingAttackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)
        cls.config = load_run_config(str(RUN_CONFIG_PATH))
        cls.inputs = load_from_run_config(cls.config)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def _prepare(self, interval, rotation=None, pre_combat=None):
        sim, player, target = prepare_simulation(
            rotation if rotation is not None else {"steps": []},
            self.inputs.stats_config,
            self.inputs.loadout_blueprints,
            self.config.dummy_hp,
            {},
            verbose=False,
            seed=self.config.seed,
            config=self.config,
            pre_combat=pre_combat,
            incoming_attack_interval=interval,
        )
        player.stats["Melee Accuracy"] = 2.0
        player.stats["Main Accuracy"] = 2.0
        target.stats["Defense Chance"] = 0.0
        target.stats["Resistance"] = 0.0
        return sim, player, target

    def _subscribe(self, sim, player, probe, branch, owner):
        sim.triggers.subscribe(owner, probe, branch, player, player)

    def _open_combat(self, sim, player, target, at=0.0):
        """Drops the prepared rotation and lands a zero-damage hit so the fight clock starts."""
        sim.queue.clear()
        sim.schedule_absolute(
            at,
            ApplyDamageLand(player, target, 0.0, False, "Opener", attack_type=1, damage_type=1),
        )

    def test_missing_key_is_zero_and_negative_fails_validation(self):
        self.assertEqual(self.config.incoming_attack_interval, 0.0)
        self.assertEqual(_require_non_negative_float({}, "incoming_attack_interval", 0.0), 0.0)
        with self.assertRaises(ValueError):
            _require_non_negative_float({"incoming_attack_interval": True}, "incoming_attack_interval", 0.0)
        self.config.incoming_attack_interval = -1.5
        with self.assertRaises(ValueError) as raised:
            validate_run_config(self.config)
        self.assertIn("incoming_attack_interval", str(raised.exception))
        self.config.incoming_attack_interval = 0.0

    def test_zero_interval_schedules_no_swing_and_adds_no_damage(self):
        hooked, _player_a, target_a = self._prepare(0.0, rotation=SABER)
        hooked.run_timed(6.0, target_a)
        plain, _player_b, target_b = self._prepare(0.0, rotation=SABER)
        del plain.incoming_attack_interval
        del plain.incoming_attack_attacker
        del plain.incoming_attack_victim
        plain.run_timed(6.0, target_b)
        self.assertEqual(hooked.tracker.total_damage, plain.tracker.total_damage)
        self.assertFalse(any(isinstance(item[2], IncomingAttack) for item in hooked.queue))

        sim, player, target = self._prepare(0.0)
        retaliate, branch = _listener(
            "retaliate",
            "on_damage_taken",
            actions=RETALIATION,
            target_overrides=[{"type": "trigger_caster"}],
        )
        self._subscribe(sim, player, retaliate, branch, "retaliate")
        hp = target.hp
        self._open_combat(sim, player, target)
        sim.run_timed(5.0, target)
        self.assertEqual(retaliate.times, [])
        self.assertEqual(sim.tracker.total_damage, 0.0)
        self.assertEqual(target.hp, hp)
        self.assertNotIn("Incoming Attack", sim.tracker.breakdown)

    def test_swings_land_on_the_interval_after_combat_starts(self):
        sim, player, target = self._prepare(1.5)
        wildcard, wild_branch = _listener(
            "wildcard",
            "on_damage_taken",
            ints={"actor": 1, "damage_type": 5, "weapon_mode": 1, "spell_type": 1},
        )
        melee, melee_branch = _listener(
            "melee",
            "on_damage_taken",
            ints={"weapon_mode": 2},
        )
        force, force_branch = _listener(
            "force",
            "on_damage_taken",
            ints={"spell_type": 3},
        )
        pre, pre_branch = _listener("pre", "on_pre_damage_taken")
        self._subscribe(sim, player, wildcard, wild_branch, "wildcard")
        self._subscribe(sim, player, melee, melee_branch, "melee")
        self._subscribe(sim, player, force, force_branch, "force")
        self._subscribe(sim, player, pre, pre_branch, "pre")
        self._open_combat(sim, player, target)
        sim.run_timed(4.0, target)

        expected = [1.5, 3.0]
        for probe in (wildcard, melee, pre):
            self.assertEqual(len(probe.times), len(expected), probe.name)
            for got, want in zip(probe.times, expected):
                self.assertAlmostEqual(got, want, places=6, msg=probe.name)
        self.assertNotIn(0.0, wildcard.times)
        self.assertEqual(force.times, [])
        self.assertEqual(sim.tracker.total_damage, 0.0)
        self.assertNotIn("Incoming Attack", sim.tracker.breakdown)

    def test_no_swings_during_pre_combat(self):
        sim, player, target = self._prepare(1.5, rotation=SABER, pre_combat=[{"wait": 2.0}])
        probe, branch = _listener("wildcard", "on_damage_taken")
        self._subscribe(sim, player, probe, branch, "wildcard")
        sim.run_until(1.9)
        self.assertIsNone(sim.combat_start_time)
        self.assertEqual(probe.times, [])
        sim.run_timed(6.0, target)
        self.assertIsNotNone(sim.combat_start_time)
        self.assertTrue(probe.times)
        for landed in probe.times:
            self.assertGreaterEqual(landed, sim.combat_start_time + 1.5 - 1e-9)
        self.assertAlmostEqual(probe.times[0], sim.combat_start_time + 1.5, places=6)

    def test_trigger_caster_damage_hits_the_dummy(self):
        sim, player, target = self._prepare(1.5)
        retaliate, branch = _listener(
            "retaliate",
            "on_damage_taken",
            actions=RETALIATION,
            target_overrides=[{"type": "trigger_caster"}],
        )
        self._subscribe(sim, player, retaliate, branch, "retaliate")
        player_hp = player.hp
        dummy_hp = target.hp
        self._open_combat(sim, player, target)
        sim.run_timed(2.0, target)
        self.assertEqual(len(retaliate.times), 1)
        self.assertAlmostEqual(retaliate.times[0], 1.5, places=6)
        self.assertGreater(sim.tracker.total_damage, 0.0)
        self.assertLess(target.hp, dummy_hp)
        self.assertEqual(player.hp, player_hp)
        self.assertNotIn("Incoming Attack", sim.tracker.breakdown)

    def test_area_tag_listeners_fire_and_other_tags_do_not(self):
        sim, player, target = self._prepare(1.5)
        area, area_branch = _listener(
            "area",
            "on_damage_taken",
            tags=["tag.abl.utility.is_aoe"],
        )
        other, other_branch = _listener(
            "other",
            "on_damage_taken",
            tags=["tag.abl.debuff.damage_over_time"],
        )
        self._subscribe(sim, player, area, area_branch, "area")
        self._subscribe(sim, player, other, other_branch, "other")
        self._open_combat(sim, player, target)
        sim.run_timed(4.0, target)
        self.assertEqual(len(area.times), 2)
        self.assertEqual(other.times, [])

    def test_pyrotech_yield_stacks_and_close_and_personal_reflects(self):
        config = load_run_config("data/run_config/Pyrotech.json")
        inputs = load_from_run_config(config)
        sim, player, target = prepare_simulation(
            inputs.rotation_config,
            inputs.stats_config,
            inputs.loadout_blueprints,
            config.dummy_hp,
            inputs.debuff_module,
            verbose=False,
            seed=config.seed,
            config=config,
            gcd_stall=0.0,
            incoming_attack_interval=1.5,
        )
        yield_key = "abl.bounty_hunter.skill.firebug.mods.special.thermal_yield:2"
        watch = {"applied": None, "still_up": None, "stacks": None}

        class _Watch:
            def resolve(self, sim):
                eff = player.effects.get(yield_key)
                if eff is None or getattr(eff, "is_expired", False):
                    if sim.current_time < 80.0:
                        sim.schedule_absolute(sim.current_time + 0.5, self)
                    return
                if watch["applied"] is None:
                    watch["applied"] = sim.current_time
                    sim.schedule_absolute(sim.current_time + 5.0, _Later())

        class _Later:
            def resolve(self, sim):
                eff = player.effects.get(yield_key)
                watch["still_up"] = eff is not None and not getattr(eff, "is_expired", False)
                watch["stacks"] = getattr(eff, "stacks", None)

        sim.schedule_absolute(0.5, _Watch())
        sim.run_timed(120.0, target)
        sim.tracker.finalize_effects(sim.current_time)

        self.assertIsNotNone(watch["applied"])
        self.assertTrue(watch["still_up"])
        self.assertGreater(watch["stacks"], 1)
        windows = sim.tracker.effect_history.get((player.name, "Thermal Yield"), [])
        self.assertTrue(windows)
        self.assertGreater(max(row["max_stacks"] for row in windows), 1)
        reflected = sim.tracker.breakdown.get("Close and Personal")
        self.assertIsNotNone(reflected)
        self.assertGreater(reflected["total_damage"], 0.0)

    def test_boiling_point_raises_thermal_yield_cap_to_six(self):
        config = load_run_config("data/run_config/Pyrotech.json")
        inputs = load_from_run_config(config)
        yield_key = "abl.bounty_hunter.skill.firebug.mods.special.thermal_yield:2"

        def fight():
            sim, player, target = prepare_simulation(
                {"steps": []},
                inputs.stats_config,
                inputs.loadout_blueprints,
                config.dummy_hp,
                {},
                verbose=False,
                seed=config.seed,
                config=config,
                incoming_attack_interval=1.5,
            )
            return sim, player, target

        plain, plain_player, plain_target = fight()
        self._open_combat(plain, plain_player, plain_target)
        self.assertTrue(plain_player.ability_db["thermal_yield"].cast(plain_player, plain_target, plain))
        self.assertEqual(plain_player.effects[yield_key].max_stacks, 5)

        sim, player, target = fight()
        self._open_combat(sim, player, target)
        self.assertTrue(player.ability_db["kolto_overload"].cast(player, target, sim))
        self.assertTrue(player.ability_db["thermal_yield"].cast(player, target, sim))
        self.assertEqual(player.effects[yield_key].max_stacks, 6)
        sim.run_timed(12.0, target)
        boosted = player.effects[yield_key]
        self.assertEqual(boosted.max_stacks, 6)
        self.assertEqual(boosted.stacks, 6)


if __name__ == "__main__":
    unittest.main()
