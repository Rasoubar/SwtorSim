"""Hit math sources: the traced hit functions record who contributed, change nothing, and run for the whole fight."""

import contextlib
import io
import random
import unittest
from collections import Counter
from pathlib import Path

from src.swtorsim.debug import debug_api
from src.swtorsim.debug.proc_measure import make_sim_builder

RUN_CONFIGS = Path(__file__).resolve().parents[1] / "data" / "run_config"
HATRED = RUN_CONFIGS / "Hatred.json"


def _plain_run(config_path):
    """The real engine, no debug code installed: (total damage, random state after the fight)."""
    from src.swtorsim.config_load import load_from_run_config
    from src.swtorsim.run_config import load_run_config
    from src.swtorsim.setup import prepare_simulation

    cfg = load_run_config(str(config_path), environment="live")  # the debugger builds on live data
    with contextlib.redirect_stdout(io.StringIO()):
        inputs = load_from_run_config(cfg)
        sim, _player, target = prepare_simulation(
            inputs.rotation_config, inputs.stats_config, inputs.loadout_blueprints, cfg.dummy_hp, inputs.debuff_module,
            seed=cfg.seed, config=cfg, gcd_stall=float(getattr(cfg, "gcd_stall", 0.0) or 0.0),
            incoming_attack_interval=float(getattr(cfg, "incoming_attack_interval", 0.0) or 0.0),
        )
        sim.verbose = False
        sim.run_timed(duration=float(getattr(cfg, "duration", 300.0) or 300.0), target=target)
    return sim.tracker.total_damage, random.getstate()


def _traced_run(config_path):
    """The same fight through the debug builder (traced engine, tracer on)."""
    build_sim, _seed, duration = make_sim_builder(str(config_path), with_tracer=True)
    sim = build_sim()
    with contextlib.redirect_stdout(io.StringIO()):
        sim.run_timed(duration=duration, target=sim.incoming_attack_attacker)
    return sim.tracker.total_damage, random.getstate()


@unittest.skipUnless(HATRED.is_file(), "Hatred run config not present")
class SourceConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = debug_api.handle("trace", {"config": "Hatred"})
        cls.hits = [e for e in cls.trace["events"] if e["type"] == "damage_hit"]

    def test_every_hit_records_sources_and_its_crit_roll(self):
        self.assertTrue(self.hits)
        for hit in self.hits:
            self.assertIn("sources", hit["math"], hit)
            self.assertIsNotNone(hit["math"]["crit"], hit)

    def test_bucket_sources_add_up_to_the_engines_buckets(self):
        for hit in self.hits:
            math = hit["math"]
            for key, value in math["buckets"].items():
                total = 1.0 + sum(s["value"] for s in math["sources"] if s["kind"] == "bucket" and s["bucket"] == key)
                self.assertAlmostEqual(total, value, places=3, msg=f"{hit['ability']} at {hit['t']} {key}")

    def test_crit_chance_and_modifier_sources_add_up(self):
        for hit in self.hits:
            math, crit = hit["math"], hit["math"]["crit"]
            chance = sum(s["value"] for s in math["sources"] if s["kind"] == "crit_chance")
            modifier = sum(s["value"] for s in math["sources"] if s["kind"] == "crit_modifier")
            self.assertAlmostEqual(crit["bonus_chance"], chance, places=3, msg=hit)
            self.assertAlmostEqual(crit["bonus_modifier"], modifier, places=3, msg=hit)
            self.assertAlmostEqual(crit["chance"], crit["stat_chance"] + crit["bonus_chance"], places=6)

    def test_the_recorded_roll_matches_whether_it_crit(self):
        for hit in self.hits:
            crit = hit["math"]["crit"]
            self.assertEqual(crit["crit"], hit["is_crit"])
            self.assertEqual(crit["roll"] < crit["chance"], hit["is_crit"])
            self.assertEqual(crit["multiplier"] is not None, hit["is_crit"])

    def test_every_hit_lies_inside_its_own_damage_range(self):
        """min / max come from the engine's own mitigation, multiplier and crit function; a hit must fall inside."""
        self.assertTrue(self.hits)
        for hit in self.hits:
            rng = hit["math"]["range"]
            self.assertLessEqual(rng["base_min"], hit["math"]["base_damage"])
            self.assertLessEqual(hit["math"]["base_damage"], rng["base_max"])
            low, high = rng["min"], rng["max"]
            if hit["is_crit"]:
                low, high = low * rng["crit_multiplier"], high * rng["crit_multiplier"]
            self.assertGreaterEqual(hit["damage"], int(low) - 1, hit)
            self.assertLessEqual(hit["damage"], int(high) + 1, hit)

    def test_the_probed_crit_multiplier_equals_the_one_a_real_crit_used(self):
        crits = [h for h in self.hits if h["is_crit"]]
        self.assertTrue(crits)
        for hit in crits:
            self.assertAlmostEqual(hit["math"]["range"]["crit_multiplier"], hit["math"]["crit"]["multiplier"], places=9)

    def test_abilities_with_a_spread_have_one(self):
        spreads = {h["ability"] for h in self.hits if h["math"]["range"]["max"] > h["math"]["range"]["min"]}
        self.assertTrue(spreads)

    def test_sources_are_named_and_labelled(self):
        sources = [s for hit in self.hits[:200] for s in hit["math"]["sources"]]
        self.assertTrue(sources)
        for source in sources:
            self.assertTrue(source["effect"])
            self.assertTrue(source["label"])
            self.assertIn(source["where"], ("caster", "target"))

    def test_lifecycle_procs_are_traced_while_the_fight_runs_not_only_at_setup(self):
        """Regression: the traced engine used to be installed only while the simulation was built."""
        rules = {r["id"]: r for r in self.trace["proc"]["rules"]}
        counts = Counter((rules[e[2]]["kind"], e[1] > 1.0) for e in self.trace["proc"]["evals"])
        self.assertGreater(counts[("lifecycle", True)], 0)


class ParityTests(unittest.TestCase):
    def test_traced_runs_match_the_plain_engine_on_several_configs(self):
        compared = 0
        for name in ("Hatred", "Darkness", "Carnage", "Lethality", "Marksmanship", "Immortal"):
            path = RUN_CONFIGS / f"{name}.json"
            if not path.is_file():
                continue
            try:
                plain = _plain_run(path)
            except Exception:
                continue  # a config that does not load on this data set is not a parity case
            traced = _traced_run(path)
            self.assertEqual(plain[0], traced[0], f"{name}: total damage differs")
            self.assertEqual(plain[1], traced[1], f"{name}: the number of random draws differs")
            compared += 1
        self.assertGreaterEqual(compared, 3)


class StatLabelTests(unittest.TestCase):
    def test_numeric_ids_become_names_and_names_pass_through(self):
        self.assertEqual(debug_api._stat_label("79"), "STAT_cbt_damage_done_modifier_percentage")
        self.assertEqual(debug_api._stat_label("STAT_cbt_force_critical_chance"), "STAT_cbt_force_critical_chance")


if __name__ == "__main__":
    unittest.main()
