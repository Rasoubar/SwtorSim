"""Ability display names with stray whitespace (e.g. "Halted Offensive ") must still resolve by rotation slug."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.swtorsim.cast_timeline import ability_name_to_slug
from src.swtorsim.debug.tracer import CombatTracer
from src.swtorsim.entities import Player
from src.swtorsim.rotation import PriorityBlockStep

HALTED_FQN = "abl.sith_inquisitor.skill.lightning.mods.tier1.halted_offensive"


class AbilityDbWhitespaceNameTests(unittest.TestCase):
    def test_trailing_space_name_indexed_by_rotation_slug(self):
        abl = SimpleNamespace(name="Halted Offensive ", fqn=HALTED_FQN)
        db = Player.build_ability_db({HALTED_FQN: abl})
        slug = ability_name_to_slug(abl.name, abl.fqn)
        self.assertEqual(slug, "halted_offensive")
        self.assertIs(db.get(slug), abl)
        self.assertIs(db.get(HALTED_FQN), abl)

    def test_trailing_space_name_still_resolves_for_name_based_lookups(self):
        # calculate_resource_cost / cast / cooldown helpers look up name.lower().replace(" ", "_");
        # without this key the ability resolves to None and tag-scoped modifiers (e.g. Lightning
        # Effusion's -75% Force cost on Force attacks) are silently skipped.
        abl = SimpleNamespace(name="Halted Offensive ", fqn=HALTED_FQN)
        db = Player.build_ability_db({HALTED_FQN: abl})
        self.assertIs(db.get(abl.name.lower().replace(" ", "_")), abl)


class PriorityBlockMissingAbilityTraceTests(unittest.TestCase):
    def test_missing_ability_is_traced_not_silently_dropped(self):
        tracer = CombatTracer()
        sim = SimpleNamespace(current_time=0.0, tracer=tracer)
        player = SimpleNamespace(next_gcd=0.0, ability_db={})
        step = PriorityBlockStep("Window 1", [{"ability_id": "does_not_exist", "rules": {}}])

        self.assertFalse(step.evaluate(player, None, sim))

        candidates = tracer.rotation_decisions[-1]["candidates"]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["ability"], "does_not_exist")
        self.assertEqual(candidates[0]["reason"], "Ability not found in loadout")
        self.assertFalse(candidates[0]["accepted"])


if __name__ == "__main__":
    unittest.main()
