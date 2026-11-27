import unittest
from unittest.mock import MagicMock

from src.swtorsim.class_buffs import (
    CLASS_BUFF_SOURCES,
    HIDDEN_BONUSES,
    MIRROR_CLASS_BUFFS,
    apply_class_buffs,
    clear_class_buff_cache,
)
from src.swtorsim.effects import ActiveEffect


class TestClassBuffs(unittest.TestCase):
    def setUp(self):
        clear_class_buff_cache()

    def tearDown(self):
        clear_class_buff_cache()

    def _make_dummy_player(self, name: str = "TestPlayer"):
        player = MagicMock()
        player.name = name
        player.effects = {}
        player.permanent_bonuses = {}
        return player

    def test_apply_class_buffs_to_fresh_player(self):
        player = self._make_dummy_player()
        added = apply_class_buffs(player)

        expected_buffs = [b[0] for b in CLASS_BUFF_SOURCES]
        self.assertEqual(len(added), 4)
        for name in expected_buffs:
            self.assertIn(name, added)
            self.assertIn(name, player.effects)
            effect = player.effects[name]
            self.assertTrue(effect.is_passive)
            self.assertIsNone(effect.expires_at)

        self.assertEqual(player.permanent_bonuses, HIDDEN_BONUSES)
        self.assertAlmostEqual(player.permanent_bonuses["Accuracy"], 0.01)
        self.assertAlmostEqual(player.permanent_bonuses["Critical Chance"], 0.01)
        self.assertAlmostEqual(player.permanent_bonuses["Critical Modifier"], 0.01)

    def test_no_duplicate_when_buff_already_present(self):
        player = self._make_dummy_player()
        dummy_effect = ActiveEffect(fqn="test.fqn", name="Unnatural Might", is_passive=True)
        player.effects["Unnatural Might"] = dummy_effect

        added = apply_class_buffs(player)
        self.assertNotIn("Unnatural Might", added)
        self.assertIs(player.effects["Unnatural Might"], dummy_effect)
        self.assertEqual(len(added), 3)

    def test_mirror_buff_deduplication(self):
        mirror_pairs = [
            ("Unnatural Might", "Force Might"),
            ("Mark of Power", "Force Valor"),
            ("Coordination", "Lucky Shots"),
            ("Hunter's Boon", "Trooper's Fortitude"),
        ]
        for imperial_name, republic_name in mirror_pairs:
            player = self._make_dummy_player()
            dummy_effect = ActiveEffect(fqn="test.fqn", name=republic_name, is_passive=True)
            player.effects[republic_name] = dummy_effect

            added = apply_class_buffs(player)
            self.assertNotIn(
                imperial_name,
                added,
                f"Imperial buff '{imperial_name}' was added despite Republic mirror '{republic_name}' present",
            )
            self.assertNotIn(imperial_name, player.effects)
            self.assertIn(republic_name, player.effects)

    def test_independent_instances_not_mutated(self):
        p1 = self._make_dummy_player("P1")
        p2 = self._make_dummy_player("P2")

        apply_class_buffs(p1)
        apply_class_buffs(p2)

        # Ensure modifying p1's effect does not contaminate p2
        p1.effects["Unnatural Might"].stacks = 99
        self.assertEqual(p2.effects["Unnatural Might"].stacks, 1)

    def test_cache_clearing(self):
        from src.swtorsim import class_buffs
        self.assertEqual(len(class_buffs._BUFF_TEMPLATES_CACHE), 0)
        player = self._make_dummy_player()
        apply_class_buffs(player)
        self.assertGreater(len(class_buffs._BUFF_TEMPLATES_CACHE), 0)
        clear_class_buff_cache()
        self.assertEqual(len(class_buffs._BUFF_TEMPLATES_CACHE), 0)


if __name__ == "__main__":
    unittest.main()
