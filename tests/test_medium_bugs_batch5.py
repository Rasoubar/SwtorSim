"""Regression tests for bug-hunt Medium #26 (effect refresh) and #27 (natural expiry runs remove_effect on the expiring
effect only)."""

import contextlib
import io
import unittest
from pathlib import Path

import src.swtorsim.config_load as cl
import src.swtorsim.run_config as rc
import src.swtorsim.setup as su
from src.swtorsim.abilities import Ability, AbilityBlueprint, handle_buff_remove_action

ROOT = Path(__file__).resolve().parents[1]
SHOCK_TROOPER = ROOT / "data/extractor/live/parsed/abl/itm/legendary/bh_tr/powertech/shock_trooper.json"
HYDRAULIC_OVERRIDES = ROOT / "data/extractor/live/parsed/abl/bounty_hunter/hydraulic_overrides.json"


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class ExpiryRemovesOnlyItsOwnEffectTests(unittest.TestCase):
    """#27: Firefall's and Ionfall's own remove_effect (on_pre_remove) must not strip the Freefall effects that
    the same expiry just applied (effects 4 and 5), nor each other's outcome."""

    def test_both_freefall_effects_survive_the_natural_expiry(self):
        with contextlib.redirect_stdout(io.StringIO()):
            cfg = rc.load_run_config(str(ROOT / "data/run_config/Carnage.json"))
            _rot, stats, bps, debuffs = cl.load_from_run_config(cfg)
            sim, p, _d = su.prepare_simulation([], stats, bps, 1000000, debuffs, seed=1)
            abl = Ability(AbilityBlueprint.from_file(SHOCK_TROOPER))
            abl.effects[2].execute(sim, p, p, ability=abl)  # Firefall, 15 s
            abl.effects[3].execute(sim, p, p, ability=abl)  # Ionfall, 15 s
            sim.run_until(16.0)
        keys = {k for k in p.effects if k.startswith(abl.fqn + ":")}
        self.assertEqual(keys, {abl.fqn + ":4", abl.fqn + ":5"})  # both Freefall effects, applied by the expiries

    def test_expiry_contexts_name_the_expiring_effect(self):
        events = _read("src/swtorsim/events.py")
        blocks = events.split("expire_ctx = {")[1:]
        self.assertEqual(len(blocks), 2)  # EffectExpire.resolve and DotTick.resolve
        for block in blocks:
            body = block[: block.index("}")]
            self.assertIn('"owner_effect_key"', body)
            self.assertIn('"effect"', body)


class RemoveEffectWithoutOwnerTests(unittest.TestCase):
    """remove_effect names nothing in the game data (no parameters), so with no owning effect it does nothing: an
    instant sub-effect (Volatile Substance's explosion) must not sweep the ability's other effects."""

    def test_instant_sub_effect_remove_effect_leaves_sibling_effects(self):
        path = ROOT / "data/extractor/live/parsed/abl/agent/skill/concealment/volatile_substance.json"
        with contextlib.redirect_stdout(io.StringIO()):
            cfg = rc.load_run_config(str(ROOT / "data/run_config/Carnage.json"))
            _rot, stats, bps, debuffs = cl.load_from_run_config(cfg)
            sim, p, d = su.prepare_simulation([], stats, bps, 1000000, debuffs, seed=1)
            abl = Ability(AbilityBlueprint.from_file(path))
            abl.effects[1].execute(sim, d, d, ability=abl)  # the unexploded DoT, 15 s
            abl.effects[2].execute(sim, d, d, ability=abl)  # Assailable (Mental), 45 s
            before = {k for k in d.effects if k.startswith(abl.fqn + ":")}
            handle_buff_remove_action(sim, p, d, {"action_type": "remove_effect"}, ability=abl, context={})
        after = {k for k in d.effects if k.startswith(abl.fqn + ":")}
        self.assertEqual(len(before), 2)
        self.assertEqual(after, before)


def _sim(config):
    with contextlib.redirect_stdout(io.StringIO()):
        cfg = rc.load_run_config(str(ROOT / "data/run_config" / config))
        _rot, stats, bps, debuffs = cl.load_from_run_config(cfg)
        return su.prepare_simulation([], stats, bps, 1000000, debuffs, seed=1)


class RefreshKeepsGrantedImmunitiesTests(unittest.TestCase):
    """#26a: re-applying an effect keeps the immunities its first application granted."""

    def test_immunities_survive_a_refresh(self):
        sim, p, d = _sim("Carnage.json")
        with contextlib.redirect_stdout(io.StringIO()):
            ho = Ability(AbilityBlueprint.from_file(HYDRAULIC_OVERRIDES))
            ho.effects[1].execute(sim, p, p, ability=ho)
            first = set(p.immunities)
            ho.effects[1].execute(sim, p, p, ability=ho)  # refresh
        self.assertIn("tag.abl.debuff.knockdown", first)
        self.assertEqual(set(p.immunities), first)


class RefreshKeepsTriggerCooldownsTests(unittest.TestCase):
    """#26b: a refresh keeps the effect's running trigger ICDs; a genuinely new application starts fresh."""

    @staticmethod
    def _icds(sim):
        return [s["next_allowed_time"] for s in sim.triggers._listeners.get("on_damage_taken", []) if "corrosive_dart" in s["owner_id"]]

    def _setup(self):
        sim, p, d = _sim("Marksmanship.json")
        for key in ("Ranged Accuracy", "Main Accuracy", "Tech Accuracy", "Melee Accuracy", "Force Accuracy"):
            p.stats[key] = 1.10  # every dart lands
        p.resource.current = p.resource.max_value
        dart = p.ability_db["abl.agent.corrosive_dart"]
        with contextlib.redirect_stdout(io.StringIO()):
            dart.cast(p, d, sim)
            sim.run_until(1.0)
            sim.triggers.dispatch(
                "on_damage_taken", sim,
                {"caster": p, "target": d, "ability_spec": "x", "damage_type": 2, "tags": {"tag.abl.agent.followthrough_dmg"}},
            )
        return sim, p, d, dart

    def test_running_icd_survives_a_refresh(self):
        sim, p, d, dart = self._setup()
        running = self._icds(sim)
        self.assertTrue(any(v > sim.current_time for v in running), running)
        with contextlib.redirect_stdout(io.StringIO()):
            p.next_gcd = 0.0
            p.resource.current = p.resource.max_value
            dart.cast(p, d, sim)  # refresh while the ICD is running
            sim.run_until(sim.current_time + 3.0)
        self.assertEqual(self._icds(sim), running)

    def test_a_new_application_starts_with_fresh_icds(self):
        sim, p, d, dart = self._setup()
        self.assertTrue(any(v > 0.0 for v in self._icds(sim)))
        with contextlib.redirect_stdout(io.StringIO()):
            d.cleanup_expired_effects([k for k in d.effects if "corrosive_dart" in k])  # the dart is gone
            p.next_gcd = 0.0
            p.resource.current = p.resource.max_value
            dart.cast(p, d, sim)  # a brand new application
            sim.run_until(sim.current_time + 3.0)
        self.assertTrue(self._icds(sim))
        self.assertTrue(all(v == 0.0 for v in self._icds(sim)), self._icds(sim))


if __name__ == "__main__":
    unittest.main()
