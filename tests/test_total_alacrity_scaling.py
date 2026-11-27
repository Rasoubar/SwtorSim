"""Unit tests for total-Alacrity scaling of effect durations, proc cooldowns and periodic procs.

Total Alacrity = the Alacrity stat plus the unconditional instant-reduction bonuses (stat 274), the same total the
GCD uses. Passive tick intervals keep the Alacrity stat only.
"""

import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]

from src.swtorsim.abilities import Ability, AbilityBlueprint
from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.events import DotTick
from src.swtorsim.modifiers import Modifier
from src.swtorsim.run_config import load_run_config
from src.swtorsim.setup import _equip_passive, prepare_simulation, schedule_periodic
from src.swtorsim.triggers import TriggerManager

RUN_CONFIG_PATH = ROOT / "data" / "run_config" / "Hatred.json"
TERMINAL_VELOCITY = "data/extractor/live/parsed/abl/bounty_hunter/skill/arsenal/terminal_velocity.json"
INSTANT_REDUCTION = "stat_cbt_instant_reduction_percentage"
TIMED_EFFECT = {
    "fqn": "abl.test.timed_buff",
    "name": "Timed Buff",
    "type": "active",
    "cooldown": 0.0,
    "effects": [
        {
            "number": 1,
            "entry": True,
            "name": "Timed Buff_1",
            "duration": 6.0,
            "branches": [{"index": 2, "actions": [], "triggers": [{"trigger": "on_apply"}]}],
            "effIgnoreAlacrity": False,
        }
    ],
}


def _bonus_effect(value, targets=(), expired=False):
    mod = Modifier(stat=INSTANT_REDUCTION, value=value, targets=frozenset(targets))
    return SimpleNamespace(is_expired=expired, get_effective_modifiers=lambda: [mod])


class TotalAlacrityScalingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def setUp(self):
        config = load_run_config(str(RUN_CONFIG_PATH))
        inputs = load_from_run_config(config)
        self.sim, self.player, self.target = prepare_simulation(
            inputs.rotation_config,
            inputs.stats_config,
            inputs.loadout_blueprints,
            config.dummy_hp,
            inputs.debuff_module,
            verbose=False,
            seed=4242,
        )
        self.sim.queue.clear()
        self.sim.current_time = 0.0
        self.player.stats["Alacrity"] = 0.10
        self.base_bonus = self.player.instant_reduction_bonus()

    def test_bonus_sums_only_unconditional_active_instant_reduction(self):
        self.player.effects["gas_cylinder"] = _bonus_effect(0.03)
        self.player.effects["stacking_buff"] = _bonus_effect(0.04)
        self.player.effects["ability_specific"] = _bonus_effect(0.50, targets=["abl.test.only_this"])
        self.player.effects["expired_buff"] = _bonus_effect(0.20, expired=True)
        self.assertAlmostEqual(self.player.instant_reduction_bonus(), self.base_bonus + 0.07)

    def test_scale_time_total_adds_the_bonus_to_the_alacrity_stat(self):
        self.player.effects["gas_cylinder"] = _bonus_effect(0.05)
        total = 1.0 + 0.10 + self.base_bonus + 0.05
        self.assertAlmostEqual(self.player.scale_time_total(6.0), 6.0 / total)
        self.assertAlmostEqual(self.player.scale_time_modifier(6.0), 6.0 / 1.10)

    def test_effect_duration_follows_total_alacrity(self):
        self.player.effects["improved_vents"] = _bonus_effect(0.10)
        ability = Ability(AbilityBlueprint.from_dict(TIMED_EFFECT))
        ability.execute_effect(1, self.player, self.player, self.sim)
        timed = [e for k, e in self.player.effects.items() if "timed_buff" in str(k)]
        self.assertEqual(len(timed), 1)
        total = 1.0 + 0.10 + self.base_bonus + 0.10
        self.assertAlmostEqual(timed[0].expires_at, 6.0 / total, places=3)

    def test_passive_tick_applied_while_loading_uses_the_alacrity_stat(self):
        self.player.effects["improved_vents"] = _bonus_effect(0.10)
        self.sim.loading = True
        _equip_passive(self.player, AbilityBlueprint.from_file(ROOT / TERMINAL_VELOCITY), self.sim)
        self.sim.loading = False
        ticks = [t for (t, _s, ev) in self.sim.queue if isinstance(ev, DotTick)]
        self.assertEqual(len(ticks), 1)
        self.assertAlmostEqual(ticks[0], 1.5 / 1.10, places=3)

    def test_passive_tick_applied_after_loading_uses_total_alacrity(self):
        """A passive tick applied later by a trigger counts the instant-reduction bonuses like any other effect."""
        self.player.effects["improved_vents"] = _bonus_effect(0.10)
        _equip_passive(self.player, AbilityBlueprint.from_file(ROOT / TERMINAL_VELOCITY), self.sim)
        ticks = [t for (t, _s, ev) in self.sim.queue if isinstance(ev, DotTick)]
        self.assertEqual(len(ticks), 1)
        total = 1.0 + 0.10 + self.base_bonus + 0.10
        self.assertAlmostEqual(ticks[0], 1.5 / total, places=3)

    def test_effect_duration_while_loading_uses_the_alacrity_stat(self):
        self.player.effects["improved_vents"] = _bonus_effect(0.10)
        self.sim.loading = True
        Ability(AbilityBlueprint.from_dict(TIMED_EFFECT)).execute_effect(1, self.player, self.player, self.sim)
        self.sim.loading = False
        timed = [e for k, e in self.player.effects.items() if "timed_buff" in str(k)]
        self.assertEqual(len(timed), 1)
        self.assertAlmostEqual(timed[0].expires_at, 6.0 / 1.10, places=3)

    def test_prepare_simulation_clears_the_loading_flag(self):
        self.assertFalse(self.sim.loading)

    def test_proc_cooldown_follows_total_alacrity(self):
        """A 6s limit at 20% total Alacrity is 5s: open again at 5.1s, which the Alacrity stat alone (5.71s) is not."""

        class _Branch:
            triggers = [{"trigger": "on_damage_dealt", "tags": [], "intervals": {"interval_61": 6.0}}]

        class _Ability:
            fqn = name = "abl.test.icd"
            runs = 0

            def execute_branch(self, sim, branch, caster, target, context=None):
                self.runs += 1
                return True

        caster = SimpleNamespace(
            effects={},
            scale_time_total=lambda base_time: base_time / 1.20,
            scale_time_modifier=lambda base_time: base_time / 1.05,
        )
        target = SimpleNamespace(effects={})
        triggers = TriggerManager()
        ability = _Ability()
        triggers.subscribe("icd", ability, _Branch(), caster, target)
        for now in (0.0, 5.1):
            triggers.dispatch(
                "on_damage_dealt",
                SimpleNamespace(current_time=now, tracer=None),
                {"caster": caster, "target": target, "tags": []},
            )
        self.assertEqual(ability.runs, 2)

    def test_periodic_proc_interval_follows_total_alacrity(self):
        scheduled = []
        sim = SimpleNamespace(schedule_absolute=lambda when, event: scheduled.append(when))
        proc = SimpleNamespace(trigger="periodic", affected_by_cdr=True, icd=6.0, name="p")
        player = SimpleNamespace(name="Player", procs={"p": proc}, scale_time_total=lambda base_time: base_time / 1.20)
        with mock.patch("src.swtorsim.setup.random.uniform", lambda lo, hi: hi):
            schedule_periodic(player, None, sim)
        self.assertEqual(len(scheduled), 1)
        self.assertAlmostEqual(scheduled[0], 5.0)


if __name__ == "__main__":
    unittest.main()
