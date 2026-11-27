"""Unit tests: the lead-time preview evaluates priority-pool rules with the simulation clock."""

import unittest
from types import SimpleNamespace

from src.swtorsim.engine import Simulation
from src.swtorsim.entities import Player
from src.swtorsim.events import schedule_next_decision
from src.swtorsim.rotation import DEFAULT_OFF_GCD_LEAD_TIME, Rotation


def _pool_rotation(rules):
    """Priority block: an off-GCD option guarded by ``rules``, then an on-GCD filler."""
    return Rotation("preview", [
        {
            "type": "priority_block",
            "name": "Pool",
            "pool": [
                {"ability_id": "weave", "rules": rules},
                {"ability_id": "filler"},
            ],
        },
    ])


def _player(rotation):
    player = Player("Tester")
    player.ability_db["weave"] = SimpleNamespace(name="weave", fqn="abl.test.weave", triggers_gcd=False)
    player.ability_db["filler"] = SimpleNamespace(name="filler", fqn="abl.test.filler", triggers_gcd=True)
    player.rotation = rotation
    player.next_gcd = 11.4
    return player


class LeadTimePreviewTests(unittest.TestCase):
    def test_ability_cooldown_rule_is_previewed_against_the_clock(self):
        rotation = _pool_rotation({"ability_cooldown_above": {"name": "big_hit", "value": 10}})
        player = _player(rotation)
        player.cooldowns["big_hit"] = 30.0

        # 30 - 15 = 15s left: rule passes, the off-GCD option is next.
        self.assertEqual(
            rotation.get_next_lead_time(player, 15.0, SimpleNamespace(current_time=15.0)),
            DEFAULT_OFF_GCD_LEAD_TIME,
        )
        # 30 - 25 = 5s left: rule fails, the on-GCD filler is next.
        self.assertEqual(rotation.get_next_lead_time(player, 25.0, SimpleNamespace(current_time=25.0)), 0.0)

    def test_proc_cooldown_rule_reads_the_trigger_lockout(self):
        rotation = _pool_rotation({"proc_cooldown_above": {"name": "Test Proc", "value": 3}})
        player = _player(rotation)
        player.proc_registry["Test Proc"] = {"kind": "trigger_icd", "source_fqn": "abl.test.proc"}
        remaining = [6.0]
        sim = SimpleNamespace(
            current_time=100.0,
            triggers=SimpleNamespace(get_remaining_icd=lambda fqn, now, caster=None: remaining[0]),
        )

        self.assertEqual(rotation.get_next_lead_time(player, 100.0, sim), DEFAULT_OFF_GCD_LEAD_TIME)
        remaining[0] = 1.0
        self.assertEqual(rotation.get_next_lead_time(player, 100.0, sim), 0.0)

    def test_next_action_time_passes_the_sim_to_the_preview(self):
        rotation = _pool_rotation({"ability_cooldown_above": {"name": "big_hit", "value": 10}})
        player = _player(rotation)
        player.cooldowns["big_hit"] = 30.0

        early = player.get_next_action_time(10.0, SimpleNamespace(current_time=10.0))

        self.assertAlmostEqual(early, 11.4 - DEFAULT_OFF_GCD_LEAD_TIME)

    def test_schedule_next_decision_previews_with_the_sim(self):
        rotation = _pool_rotation({"ability_cooldown_above": {"name": "big_hit", "value": 10}})
        player = _player(rotation)
        player.cooldowns["big_hit"] = 30.0
        sim = Simulation(verbose=False, seed=1)
        sim.current_time = 10.0

        schedule_next_decision(player, None, sim)

        self.assertEqual(len(sim.queue), 1)
        self.assertAlmostEqual(sim.queue[0][0], 11.4 - DEFAULT_OFF_GCD_LEAD_TIME)


if __name__ == "__main__":
    unittest.main()
