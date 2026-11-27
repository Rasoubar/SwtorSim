"""Bug-hunt High #10: triggered branches must scale with the owning effect's stacks (Weakening Blast, Poison Choke)."""

import contextlib
import io
import random
import unittest
from pathlib import Path
from types import SimpleNamespace

import src.swtorsim.config_load as cl
import src.swtorsim.run_config as rc
import src.swtorsim.setup as su
from src.swtorsim import settings
from src.swtorsim import abilities as ab
from src.swtorsim.abilities import Ability, AbilityBlueprint, handle_modify_stack_charge
from src.swtorsim.requirements import owner_effect_stacks
from src.swtorsim.triggers import TriggerManager

ROOT = Path(__file__).resolve().parents[1]
INQ = ROOT / "data/extractor/pts/parsed/abl/sith_inquisitor"
HUNGERING_BLADE = ROOT / "data/extractor/pts/parsed/abl/itm/tactical/sow/inq_con/sin_shad/hat_sen/dps_burst_01.json"
BURST = ROOT / "data/extractor/pts/parsed/abl/itm/tactical/sow/age_smu/sni_gun/vir_dir/dmg_burst_01.json"
WEAKENING_BLAST = "abl.agent.skill.virulence.weakening_blast"


def _burst_setup():
    # Dirty Fighting is a PTS run config; load it (and its data) as PTS, like the UI does
    previous_env = settings.get_data_environment()
    settings.set_data_environment("pts")
    try:
        return _burst_setup_in_env()
    finally:
        settings.set_data_environment(previous_env)


def _burst_setup_in_env():
    with contextlib.redirect_stdout(io.StringIO()):
        cfg = rc.load_run_config(str(ROOT / "data/run_config/Dirty Fighting.json"))
        _rot, stats, bps, debuffs = cl.load_from_run_config(cfg)
        sim, player, dummy = su.prepare_simulation([], stats, bps, 10_000_000, debuffs, seed=100)
        abl = Ability(AbilityBlueprint.from_file(BURST))
        abl.effects[2].execute(sim, player, dummy, ability=abl)
    return sim, player, dummy, abl


def _dispatch_damage(sim, player, dummy, stacks, abl):
    active = dummy.effects[abl.fqn + ":2"]
    active.stacks = stacks
    random.seed(7)
    hp = dummy.hp
    with contextlib.redirect_stdout(io.StringIO()):
        sim.triggers.dispatch(
            "on_damage_taken",
            sim,
            {
                "caster": player,
                "target": dummy,
                "ability_spec": WEAKENING_BLAST,
                "damage_type": 2,
                "tags": {"tag.abl.agent.weakening_blast_initial_dmg"},
            },
        )
    return hp - dummy.hp


class TriggeredDamageScalesWithStacksTests(unittest.TestCase):
    def test_effect_scales_with_stack_charge(self):
        _sim, _p, dummy, abl = _burst_setup()
        self.assertTrue(dummy.effects[abl.fqn + ":2"].scales_with_stacks)

    def test_triggered_damage_scales_linearly_with_stacks(self):
        sim, player, dummy, abl = _burst_setup()
        one = _dispatch_damage(sim, player, dummy, 1, abl)
        # a fresh setup so the trigger's internal cooldown cannot suppress the second proc
        sim, player, dummy, abl = _burst_setup()
        eight = _dispatch_damage(sim, player, dummy, 8, abl)
        self.assertGreater(one, 0)
        self.assertAlmostEqual(eight / one, 8.0, delta=0.05)


class DispatchContextTests(unittest.TestCase):
    """Unit level: the branch context carries the owner effect's stacks; non-scaling effects do not multiply."""

    class _Ability:
        fqn = "abl.test"

        def __init__(self):
            self.contexts = []

        def execute_branch(self, sim, branch, caster, target, context=None):
            self.contexts.append(context)
            return True

    def _dispatch(self, effect, inherited=None):
        owner = SimpleNamespace(effects={"abl.test:1": effect} if effect is not None else {})
        ability = self._Ability()
        mgr = TriggerManager()
        branch = SimpleNamespace(triggers=[{"trigger": "on_damage_taken"}])
        mgr.subscribe("o1", ability, branch, owner, owner, effect_key="abl.test:1")
        ctx = {"caster": owner, "target": owner, "tags": set()}
        ctx.update(inherited or {})
        sim = SimpleNamespace(current_time=0.0, tracer=None)
        mgr.dispatch("on_damage_taken", sim, ctx)
        return ability.contexts

    def test_scaling_effect_passes_its_stacks(self):
        effect = SimpleNamespace(stacks=5, scales_with_stacks=True, is_expired=False)
        (ctx,) = self._dispatch(effect)
        self.assertEqual((ctx["stack_multiplier"], ctx["current_stacks"]), (5, 5))

    def test_branch_context_carries_the_owner_active_effect(self):
        effect = SimpleNamespace(stacks=2, scales_with_stacks=False, is_expired=False)
        (ctx,) = self._dispatch(effect)
        self.assertIs(ctx["active_effect"], effect)

    def test_owner_without_active_effect_gets_no_active_effect(self):
        (ctx,) = self._dispatch(None)
        self.assertNotIn("active_effect", ctx)

    def test_non_scaling_effect_does_not_multiply_but_reports_stacks(self):
        effect = SimpleNamespace(stacks=5, scales_with_stacks=False, is_expired=False)
        (ctx,) = self._dispatch(effect)
        self.assertEqual((ctx["stack_multiplier"], ctx["current_stacks"]), (1, 5))

    def test_event_context_multiplier_does_not_leak_into_owner_branch(self):
        effect = SimpleNamespace(stacks=3, scales_with_stacks=False, is_expired=False)
        (ctx,) = self._dispatch(effect, inherited={"stack_multiplier": 9})
        self.assertEqual(ctx["stack_multiplier"], 1)

    def test_owner_without_active_effect_does_not_inherit_a_multiplier(self):
        # A passive owner has no stacks: the triggering event's multiplier must not scale its branch.
        (ctx,) = self._dispatch(None, inherited={"stack_multiplier": 4})
        self.assertEqual(ctx["stack_multiplier"], 1)


def _pts_sim():
    """A PTS Darkness simulation with no rotation, as the UI loads it."""
    previous_env = settings.get_data_environment()
    settings.set_data_environment("pts")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            cfg = rc.load_run_config(str(ROOT / "data/run_config/Darkness.json"))
            _rot, stats, bps, debuffs = cl.load_from_run_config(cfg)
            sim, player, dummy = su.prepare_simulation([], stats, bps, 10_000_000, debuffs, seed=1)
        sim.verbose = False
        return sim, player, dummy
    finally:
        settings.set_data_environment(previous_env)


class StackChargeReadsOwnerEffectTests(unittest.TestCase):
    """if_stack_charge and the on_stack_charge_increased count gate read the stacks of the effect that owns the
    branch, not a stack field the context carried (1 for non-scaling effects, or a calling branch's count)."""

    def _consumed_branches(self, stacks):
        """Renewing Darkness (Force Cloak effect 3) at ``stacks``, consumed by Stealth effect 6
        (tag renewing_darkness_trigger) on the trigger manager; returns the consume branches that ran."""
        sim, player, _dummy = _pts_sim()
        cloak = Ability(AbilityBlueprint.from_file(INQ / "force_cloak.json"))
        stealth = Ability(AbilityBlueprint.from_file(INQ / "stealth.json"))
        ran = []
        original = ab.Branch.execute

        def spy(branch, sim_, caster, target, context=None, ability=None, proc_chance=None):
            result = original(branch, sim_, caster, target, context=context, ability=ability, proc_chance=proc_chance)
            if result[0] and (context or {}).get("trigger_name") == "on_effect_received" \
                    and (context or {}).get("owner_effect_key") == cloak.fqn + ":3":
                ran.append(branch.index)
            return result

        ab.Branch.execute = spy
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                for _ in range(stacks):
                    cloak.effects[3].execute(sim, player, player, ability=cloak)
                self.assertEqual(player.effects[cloak.fqn + ":3"].stacks, stacks)
                stealth.effects[6].execute(sim, player, player, ability=stealth)
        finally:
            ab.Branch.execute = original
        return ran

    def test_renewing_darkness_consumes_with_its_stack_count(self):
        # Data: branches 3..7 check if_stack_charge 1..5 and heal 4/8/12/16/20%
        for stacks in range(1, 6):
            with self.subTest(stacks=stacks):
                self.assertEqual(self._consumed_branches(stacks), [2 + stacks])

    def test_count_gate_after_modify_stack_charge_reads_the_new_count(self):
        # Hungering Blade (effect 2) removes itself on reaching 4 stacks (on_stack_charge_increased, count 4).
        # The +1 comes from a calling branch whose context carries another effect's count (1).
        sim, player, _dummy = _pts_sim()
        blade = Ability(AbilityBlueprint.from_file(HUNGERING_BLADE))
        key = blade.fqn + ":2"
        with contextlib.redirect_stdout(io.StringIO()):
            blade.effects[2].execute(sim, player, player, ability=blade)
            player.effects[key].stacks = 3
            action = {"action_type": "modify_stack_charge", "tags": ["tag.abl.sith_inquisitor.hungering_blade_buff"],
                      "floats": {"amount_min": 1.0, "amount_max": 1.0}, "ints": {"ability_spec": 0}}
            calling_ctx = {"owner_entity": player, "owner_effect_key": "abl.other:1", "current_stacks": 1}
            handle_modify_stack_charge(sim, player, player, action, context=calling_ctx)
        self.assertNotIn(key, player.effects)

    def test_count_gate_below_the_count_keeps_the_effect(self):
        sim, player, _dummy = _pts_sim()
        blade = Ability(AbilityBlueprint.from_file(HUNGERING_BLADE))
        key = blade.fqn + ":2"
        with contextlib.redirect_stdout(io.StringIO()):
            blade.effects[2].execute(sim, player, player, ability=blade)
            player.effects[key].stacks = 2
            action = {"action_type": "modify_stack_charge", "tags": ["tag.abl.sith_inquisitor.hungering_blade_buff"],
                      "floats": {"amount_min": 1.0, "amount_max": 1.0}, "ints": {"ability_spec": 0}}
            handle_modify_stack_charge(sim, player, player, action,
                                       context={"owner_entity": player, "owner_effect_key": "abl.other:1",
                                                "current_stacks": 5})
        self.assertIn(key, player.effects)
        self.assertEqual(player.effects[key].stacks, 3)


class LifecycleMultiplierTests(unittest.TestCase):
    """Effect lifecycle branches (on_refresh, on_stack_charge_increased) multiply damage by the effect's stacks
    only when its stacks scale damage (scales_with_stack_charge), as the trigger manager and DoT ticks do."""

    def _lifecycle_multipliers(self, path, number, applications, on_dummy):
        sim, player, dummy = _pts_sim()
        abl = Ability(AbilityBlueprint.from_file(path))
        target = dummy if on_dummy else player
        seen = []
        original = ab.Effect.execute_triggered_branches

        def spy(effect, trigger_name, sim_, caster, tgt, context=None, **kw):
            if getattr(effect, "number", None) == number and trigger_name in ("on_refresh", "on_stack_charge_increased"):
                seen.append((trigger_name, (context or {}).get("stack_multiplier")))
            return original(effect, trigger_name, sim_, caster, tgt, context=context, **kw)

        ab.Effect.execute_triggered_branches = spy
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                for _ in range(applications):
                    abl.effects[number].execute(sim, player, target, ability=abl)
        finally:
            ab.Effect.execute_triggered_branches = original
        return seen, target.effects[abl.fqn + f":{number}"]

    def test_scaling_effect_multiplies_by_its_stacks(self):
        # Deadly Saber's bleed (effect 2) scales with stacks; its on_stack_charge_increased branch deals damage.
        seen, eff = self._lifecycle_multipliers(
            ROOT / "data/extractor/pts/parsed/abl/sith_warrior/skill/annihilation/deadly_saber.json", 2, 3, True)
        self.assertTrue(eff.scales_with_stacks)
        self.assertEqual(eff.stacks, 3)
        self.assertIn(("on_stack_charge_increased", 3), seen)

    def test_non_scaling_effect_does_not_multiply(self):
        # Renewing Darkness (Force Cloak effect 3) stacks to 5 but its stacks do not scale damage.
        seen, eff = self._lifecycle_multipliers(INQ / "force_cloak.json", 3, 3, False)
        self.assertFalse(eff.scales_with_stacks)
        self.assertEqual(eff.stacks, 3)
        self.assertTrue(seen)
        self.assertEqual({m for _t, m in seen}, {1})


class DamageStackMultiplierTests(unittest.TestCase):
    def test_scaling_effect_returns_its_stacks(self):
        from src.swtorsim.effects import damage_stack_multiplier
        self.assertEqual(damage_stack_multiplier(SimpleNamespace(stacks=4, scales_with_stacks=True)), 4)

    def test_non_scaling_effect_returns_one(self):
        from src.swtorsim.effects import damage_stack_multiplier
        self.assertEqual(damage_stack_multiplier(SimpleNamespace(stacks=4, scales_with_stacks=False)), 1)


class OwnerEffectStacksTests(unittest.TestCase):
    def _entity(self, **effects):
        from src.swtorsim.effects import EffectCollection
        coll = EffectCollection()
        coll.update(effects)
        return SimpleNamespace(effects=coll)

    def test_reads_the_exact_key(self):
        ent = self._entity(**{"abl.x:1": SimpleNamespace(stacks=4, is_expired=False, name="X", fqn="abl.x")})
        self.assertEqual(owner_effect_stacks({"owner_entity": ent, "owner_effect_key": "abl.x:1"}), 4)

    def test_reads_a_zero_stack_effect_not_yet_cleaned_up(self):
        ent = self._entity(**{"abl.x:1": SimpleNamespace(stacks=0, is_expired=True, name="X", fqn="abl.x")})
        self.assertEqual(owner_effect_stacks({"owner_entity": ent, "owner_effect_key": "abl.x:1"}), 0)

    def test_no_owner_effect_returns_none(self):
        ent = self._entity()
        self.assertIsNone(owner_effect_stacks({"owner_entity": ent, "owner_effect_key": "abl.x:1"}))
        self.assertIsNone(owner_effect_stacks({"stack_multiplier": 3}))
        self.assertIsNone(owner_effect_stacks(None))

    def test_does_not_match_another_effect_by_name(self):
        ent = self._entity(**{"abl.y:2": SimpleNamespace(stacks=5, is_expired=False, name="Shared", fqn="abl.y")})
        self.assertIsNone(owner_effect_stacks({"owner_entity": ent, "owner_effect_key": "Shared"}))


if __name__ == "__main__":
    unittest.main()
