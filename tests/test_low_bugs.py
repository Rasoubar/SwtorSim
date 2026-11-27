"""Regression tests for bug-hunt Low #29-#31 (explicit empty pre-combat, stale recharge state, stealth exit actions).

Low #28 (simulator UI seed 0 / iterations clamp) was set aside."""

import contextlib
import io
import unittest
from pathlib import Path

import src.swtorsim.config_load as cl
import src.swtorsim.run_config as rc
import src.swtorsim.setup as su
from src.swtorsim.abilities import Ability, AbilityBlueprint

ROOT = Path(__file__).resolve().parents[1]
ABL = ROOT / "data" / "extractor" / "live" / "parsed" / "abl"


def _sim(config, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        cfg = rc.load_run_config(str(ROOT / "data/run_config" / config))
        _rot, stats, bps, debuffs = cl.load_from_run_config(cfg)
        return su.prepare_simulation([], stats, bps, 1000000, debuffs, seed=1, **kw)


class ExplicitEmptyPreCombatTests(unittest.TestCase):
    """#29: an explicit empty pre_combat / precast overrides the rotation file's own steps."""

    def _prepare(self, rotation, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            cfg = rc.load_run_config(str(ROOT / "data/run_config/Hatred.json"))
            stats = cl.load_character_stats_from_json(cfg.class_name, cfg.stats_path, cfg.level)
            bp = AbilityBlueprint.from_file(ABL / "sith_inquisitor/affliction.json")
            _sim_, player, _t = su.prepare_simulation(
                rotation, stats, {bp.fqn: bp}, 10000, {}, verbose=False, seed=42, **kw
            )
        return player, bp

    def _rotation(self, bp, **extra):
        return {"sequence": [{"type": "fixed", "ability_id": bp.fqn}], **extra}

    def test_file_pre_combat_is_used_when_nothing_is_passed(self):
        bp = AbilityBlueprint.from_file(ABL / "sith_inquisitor/affliction.json")
        player, _ = self._prepare(self._rotation(bp, pre_combat=[{"wait": 5.0}]))
        self.assertEqual(player.pre_combat.steps, [{"wait": 5.0}])

    def test_empty_pre_combat_list_overrides_the_file(self):
        bp = AbilityBlueprint.from_file(ABL / "sith_inquisitor/affliction.json")
        player, _ = self._prepare(self._rotation(bp, pre_combat=[{"wait": 5.0}]), pre_combat=[])
        self.assertFalse(getattr(player.pre_combat, "steps", None))

    def test_empty_precast_overrides_the_file(self):
        bp = AbilityBlueprint.from_file(ABL / "sith_inquisitor/affliction.json")
        player, _ = self._prepare(self._rotation(bp, precast="affliction"), precast="")
        self.assertFalse(getattr(player.pre_combat, "steps", None))


class ChargeCapRecoveryTests(unittest.TestCase):
    """#30: when a lost charge bonus leaves an ability at its new maximum, no recharge stays scheduled."""

    def _laze_with_double_laze(self):
        sim, p, d = _sim("Marksmanship.json")
        with contextlib.redirect_stdout(io.StringIO()):
            dl = Ability(AbilityBlueprint.from_file(ABL / "agent/skill/marksmanship/double_laze.json"))
            dl.effects[1].execute(sim, p, p, ability=dl)
            p.recalculate_stats()
            laze = p.ability_db["abl.agent.laze_target"]
            laze.cast(p, d, sim)  # 2 -> 1 charge, recharge running
        return sim, p, d, laze

    def _drop_double_laze(self, p, laze):
        with contextlib.redirect_stdout(io.StringIO()):
            p.cleanup_expired_effects([k for k in p.effects if "double_laze" in k])
            p.recalculate_stats()
            laze.apply_charge_modifiers(p)

    def test_recharge_is_cleared_when_the_cap_leaves_the_ability_full(self):
        _sim_, p, _d, laze = self._laze_with_double_laze()
        self.assertIsNotNone(laze.active_charge_event)
        self._drop_double_laze(p, laze)
        self.assertEqual((laze.charges, laze.max_charges), (1, 1))
        self.assertIsNone(laze.active_charge_event)
        self.assertIsNone(laze.recharge_target_time)

    def test_recharge_keeps_running_while_the_ability_is_below_its_new_maximum(self):
        sim, p, d, laze = self._laze_with_double_laze()
        with contextlib.redirect_stdout(io.StringIO()):
            p.next_gcd = 0.0
            p.cooldowns.pop(laze.fqn, None)
            p.cooldowns.pop(laze.name, None)
            laze.cast(p, d, sim)  # 1 -> 0 charges
        self.assertEqual(laze.charges, 0)
        self._drop_double_laze(p, laze)
        self.assertEqual((laze.charges, laze.max_charges), (0, 1))
        self.assertIsNotNone(laze.active_charge_event)
        self.assertIsNotNone(laze.recharge_target_time)


class BreakStealthExitActionsTests(unittest.TestCase):
    """#31: breaking stealth runs the stealth effect's on_pre_remove branches (its 6 s cooldown)."""

    def test_break_stealth_applies_the_stealth_cooldown(self):
        sim, p, d = _sim("Dirty Fighting.json")
        with contextlib.redirect_stdout(io.StringIO()):
            stealth = Ability(AbilityBlueprint.from_file(ABL / "smuggler/stealth.json"))
            p.ability_db[stealth.fqn] = stealth
            stealth.cast(p, d, sim)
        self.assertTrue(p.is_stealthed)
        self.assertNotIn(stealth.name, p.cooldowns)
        with contextlib.redirect_stdout(io.StringIO()):
            p.break_stealth(sim)
        self.assertFalse(p.is_stealthed)
        self.assertFalse([k for k in p.effects if "stealth" in k])
        remaining = p.cooldowns[stealth.name] - sim.current_time
        self.assertGreater(remaining, 0.0)
        self.assertLessEqual(remaining, 6.0)  # the 6 s base, shortened by the player's Alacrity (ignore_alacrity is off)

    def test_break_stealth_without_a_sim_still_removes_the_effects(self):
        sim, p, d = _sim("Dirty Fighting.json")
        with contextlib.redirect_stdout(io.StringIO()):
            stealth = Ability(AbilityBlueprint.from_file(ABL / "smuggler/stealth.json"))
            p.ability_db[stealth.fqn] = stealth
            stealth.cast(p, d, sim)
            p.break_stealth()
        self.assertFalse(p.is_stealthed)
        self.assertFalse([k for k in p.effects if "stealth" in k])


if __name__ == "__main__":
    unittest.main()
