import unittest


class TestFullyPassiveFormat(unittest.TestCase):
    def test_passive_dict_structure(self):
        # Dictionary structure exactly as defined
        passive_node = {
            "fqn": "abl.sith_inquisitor.passive.mark_of_the_assassin",
            "name": "Mark of the Assassin",
            "tags": ["Passive", "Class"],
            "stat_changes": [
                {
                    "name": "Critical Chance",
                    "value": 0.05,
                    "stackable": False,
                    "requires_tag": ["Melee", "Force"],
                    "impact": {
                        "fqn": "eff.sith_inquisitor.passive.mark_of_the_assassin_crit"
                    },
                }
            ],
        }

        # Validate top-level keys and types
        self.assertIsInstance(passive_node["fqn"], str)
        self.assertIsInstance(passive_node["name"], str)
        self.assertIsInstance(passive_node["tags"], list)
        self.assertIsInstance(passive_node["stat_changes"], list)

        # Validate stat_changes items
        change = passive_node["stat_changes"][0]
        self.assertIsInstance(change["name"], str)
        self.assertIsInstance(change["value"], (int, float))
        self.assertIn("stackable", change)
        self.assertIsInstance(change["requires_tag"], (str, list))
        self.assertIsInstance(change["impact"], dict)
        self.assertIn("fqn", change["impact"])


if __name__ == "__main__":
    unittest.main()