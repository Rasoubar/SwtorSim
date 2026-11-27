"""Unit tests for instant pre-combat tactical swaps (swap_tactical steps)."""

import copy
import os
from pathlib import Path
import unittest

from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.effects import ActiveEffect
from src.swtorsim.run_config import load_run_config, normalize_pre_combat
from src.swtorsim.setup import prepare_simulation, swap_tactical

ROOT = Path(__file__).resolve().parents[1]
RUN_CONFIG_PATH = ROOT / "data" / "run_config" / "Hatred.json"
# Must differ from the run config's own tactical (Hatred.json starts on the generic damage tactical).
NEW_TACTICAL = "abl.itm.tactical.sow.inq_con.sin_shad.hat_sen.dmg_sust_01"


def _listener_fqns(sim) -> list:
    return [
        getattr(sub.get("ability"), "fqn", None)
        for entries in sim.triggers._listeners.values()
        for sub in entries
    ]


def _effect_keys_from(entity, fqn: str) -> list:
    return [k for k in entity.effects.keys() if str(k).startswith(f"{fqn}:")]


@unittest.skipUnless(RUN_CONFIG_PATH.exists(), "Hatred run config not available")
class TacticalSwapTests(unittest.TestCase):
    """Covers equip/unequip bookkeeping for zero-cost, off-GCD tactical swaps."""

    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)
        cls.config = load_run_config(str(RUN_CONFIG_PATH))
        cls.inputs = load_from_run_config(cls.config)
        cls.old_tactical = cls.config.tactical_fqn

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def _prepare(self, pre_combat=None, rotation=None):
        return prepare_simulation(
            rotation or [{"type": "fixed", "ability_id": "thrash"}],
            self.inputs.stats_config,
            self.inputs.loadout_blueprints,
            self.config.dummy_hp,
            copy.deepcopy(self.inputs.debuff_module),
            verbose=False,
            seed=1,
            config=self.config,
            pre_combat=pre_combat,
        )

    def test_normalize_accepts_swap_step(self):
        res = normalize_pre_combat(pre_combat=[{"swap_tactical": NEW_TACTICAL}, "stealth"])
        self.assertEqual(res, [{"swap_tactical": NEW_TACTICAL}, {"ability": "stealth"}])

    def test_initial_tactical_tracked(self):
        _sim, player, _target = self._prepare()
        self.assertEqual(player.tactical_fqn, self.old_tactical)

    def test_pre_combat_swap_unequips_old_and_equips_new(self):
        sim, player, target = self._prepare(pre_combat=[{"swap_tactical": NEW_TACTICAL}])
        self.assertIn(self.old_tactical, _listener_fqns(sim))
        sim.run_timed(duration=1.0, target=target)

        self.assertEqual(player.tactical_fqn, NEW_TACTICAL)
        self.assertNotIn(self.old_tactical, player.passive_db)
        self.assertIn(NEW_TACTICAL, player.passive_db)
        self.assertNotIn(self.old_tactical, _listener_fqns(sim))
        self.assertEqual(
            [k for k in _effect_keys_from(player, self.old_tactical) if player.effects[k].expires_at is None],
            [],
        )
        self.assertTrue(_effect_keys_from(player, NEW_TACTICAL), "New tactical entry effect must be applied")
        self.assertFalse(
            any(i.get("source_fqn") == self.old_tactical for i in player.proc_registry.values())
        )

    def test_swap_is_instant_and_off_gcd(self):
        sim, player, target = self._prepare(pre_combat=[{"swap_tactical": NEW_TACTICAL}])
        sim.run_timed(duration=0.5, target=target)
        # Swap consumed no GCD: rotation (thrash) began at t=0 and combat started on the first hit
        self.assertAlmostEqual(sim.combat_start_time, 0.0, places=2)

    def test_round_trip_restores_baseline_state(self):
        sim, player, target = self._prepare()
        base_stats = dict(player.stats)
        base_listeners = sorted(str(f) for f in _listener_fqns(sim))

        self.assertTrue(swap_tactical(player, NEW_TACTICAL, sim))
        self.assertTrue(swap_tactical(player, self.old_tactical, sim))

        self.assertEqual(player.tactical_fqn, self.old_tactical)
        self.assertEqual(sorted(str(f) for f in _listener_fqns(sim)), base_listeners)
        for key, val in base_stats.items():
            self.assertAlmostEqual(player.stats.get(key), val, places=9, msg=key)

    def test_swap_always_keeps_timed_effects_of_old_tactical(self):
        sim, player, _target = self._prepare()
        timed_key = f"{self.old_tactical}:900"
        permanent_key = f"{self.old_tactical}:901"
        player.effects[timed_key] = ActiveEffect(
            fqn=self.old_tactical, name="Timed Test Buff", number=900,
            expires_at=sim.current_time + 30.0, duration=30.0,
        )
        player.effects[permanent_key] = ActiveEffect(fqn=self.old_tactical, name="Permanent Test Buff", number=901)

        self.assertTrue(swap_tactical(player, NEW_TACTICAL, sim))

        self.assertIn(timed_key, player.effects, "Timed buffs the old tactical produced must survive the swap")
        self.assertNotIn(permanent_key, player.effects, "Permanent effects of the old tactical must be removed")

    def test_swap_to_same_tactical_is_noop(self):
        sim, player, _target = self._prepare()
        self.assertFalse(swap_tactical(player, self.old_tactical, sim))

    def test_invalid_swap_target_rejected(self):
        with self.assertRaises(ValueError):
            self._prepare(pre_combat=[{"swap_tactical": "abl.inquisitor.thrash"}])

    def test_force_camouflage_hidden_power_swap_persists_across_damage(self):
        """Force Camouflage cast with Hidden Power creates a 10s buff that survives tactical swap and damage dealt."""
        from data.rotation_builder import load_json_file
        import json

        rot_file = ROOT / "data" / "rotations" / "custom" / "marauder" / "annihilation" / "Annihilation_Rotation.json"
        if not rot_file.is_file():
            self.skipTest("Annihilation rotation fixture not present")
        with open(rot_file, encoding="utf-8") as f:
            rot = json.load(f)
        spec_data = load_json_file(str(ROOT / "data" / "extractor" / "live" / "disciplines" / "marauder" / "annihilation.json"))
        choices = {str(lvl): 1 for lvl in spec_data.get("skill_tree", {})}

        from data.rotation_builder import run_dry_run_preview
        payload = {
            "env": "live",
            "spec_path": "data/extractor/live/disciplines/marauder/annihilation.json",
            "choices": choices,
            "tactical_fqn": "abl.itm.tactical.sow.war_kni.mar_sen.utl_regen_01",
            "legendary_fqns": [],
            "relic_fqns": [],
            "rotation": rot["sequence"],
            "pre_combat": rot["pre_combat"],
            "duration": 28.0,
        }
        res = run_dry_run_preview(payload)
        # Verify Force Camouflage_6 persisted after Rupture dealt direct damage at 16.10s
        camo6_casts = [c for c in res["casts"] if "Force Camouflage_6" in c.get("buffs", [])]
        self.assertGreater(len(camo6_casts), 3, "Force Camouflage_6 must persist across multiple damage casts")
        # Rupture at 16.10s and subsequent Vicious Slash casts should see Force Camouflage_6
        post_open_casts = [c for c in res["casts"] if c["time"] > 16.0 and c["time"] < 25.0]
        for c in post_open_casts:
            self.assertIn("Force Camouflage_6", c.get("buffs", []), f"Cast at {c['time']}s must retain Force Camouflage_6")


ANNI_SPEC = ROOT / "data" / "extractor" / "live" / "disciplines" / "marauder" / "annihilation.json"
PINNED_BUILD = ROOT / "data" / "builds" / "L80_14gcd_red.json"
ANNI_ROT = ROOT / "data" / "rotations" / "custom" / "marauder" / "annihilation" / "Annihilation_Rotation.json"


@unittest.skipUnless(
    ANNI_SPEC.exists() and ANNI_ROT.exists() and PINNED_BUILD.exists(),
    "Annihilation fixtures not available",
)
class ByTagReplacementCleanupTests(unittest.TestCase):
    """Force Camouflage :3 replaces :2 by tag; :2's triggers must not outlive it, and remove_effect
    for a vanished owner must not sweep sibling effects (Hidden Power :6)."""

    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def _prepare(self):
        import json
        from data.rotation_builder import load_json_file, loadout_fqns
        from src.swtorsim.config_load import load_character_stats_from_json, load_complete_loadout

        with open(ANNI_ROT, encoding="utf-8") as f:
            rot = json.load(f)
        spec = load_json_file(str(ANNI_SPEC))
        choices = {str(lvl): 1 for lvl in spec.get("skill_tree", {})}
        fqns = loadout_fqns(
            spec, choices,
            tactical_fqn="abl.itm.tactical.sow.war_kni.mar_sen.utl_regen_01",
            legendary_fqns=[], relic_fqns=[],
        )
        bps = load_complete_loadout(fqns, parsed_dir=str(ROOT / "data" / "extractor" / "live" / "parsed"))
        stats = load_character_stats_from_json("Marauder", str(PINNED_BUILD), 80)
        return prepare_simulation(
            rot["sequence"], stats, bps, 10_000_000, {}, verbose=False, seed=1, pre_combat=rot["pre_combat"]
        )

    def _run_until_effect(self, sim, player, target, key, limit=40.0, step=0.25):
        """Advances the sim until `key` is active (setup precondition), instead of assuming a fixed time."""
        t = 0.0
        while key not in player.effects and t < limit:
            t += step
            sim.run_until(t, target=target)
        self.assertIn(key, player.effects, f"Setup: {key} never became active within {limit}s")

    def test_by_tag_replaced_effect_loses_its_triggers(self):
        sim, player, target = self._prepare()
        self._run_until_effect(sim, player, target, "abl.sith_warrior.force_camouflage:3")
        self.assertNotIn("abl.sith_warrior.force_camouflage:2", player.effects)
        orphans = [
            sub["owner_id"] for entries in sim.triggers._listeners.values() for sub in entries
            if str(sub["owner_id"]).endswith("force_camouflage:2")
        ]
        self.assertEqual(orphans, [], "Replaced effect must not keep trigger subscriptions")

    def test_remove_effect_with_vanished_owner_is_noop(self):
        from src.swtorsim.abilities import handle_buff_remove_action

        sim, player, target = self._prepare()
        self._run_until_effect(sim, player, target, "abl.sith_warrior.force_camouflage:3")
        camo = player.ability_db["force_camouflage"]
        self.assertIn("abl.sith_warrior.force_camouflage:6", player.effects)
        effects_before = set(player.effects)
        handle_buff_remove_action(
            sim, player, target, {"action_type": "remove_effect"}, ability=camo,
            context={"owner_effect_key": "abl.sith_warrior.force_camouflage:2", "owner_entity": player},
        )
        self.assertIn("abl.sith_warrior.force_camouflage:6", player.effects)
        self.assertIn("abl.sith_warrior.force_camouflage:3", player.effects)
        self.assertEqual(set(player.effects), effects_before, "No-op removal must not change active effects")


if __name__ == "__main__":
    unittest.main()
