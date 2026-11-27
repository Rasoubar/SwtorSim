"""An effect (re)applied during an activation must not hear that activation's on_ability_post_activate,
except the activating ability's own entry effects.

- Lightning Effusion (proc): a Force-attack crit grants 2 charges consumed on post-activate; the procing cast
  must not eat one of them.
- Translocate's Benign Presence (called effect): removed on an aggressive action, and Translocate is one; it
  must survive the swap that applied it.
- Thundering Blast_7 (entry effect of Thundering Blast): rolls the 25% Forked Darkness echo on Thundering
  Blast's own post-activate, so it must still hear it.
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.swtorsim.triggers import TriggerManager

EFFUSION_FQN = "abl.sith_inquisitor.skill.lightning.lightning_effusion"
BOLT_FQN = "abl.sith_inquisitor.skill.lightning.lightning_bolt"
TRANSLOCATE_FQN = "abl.bounty_hunter.skill.shield_tech.translocate"
THUNDERING_BLAST_FQN = "abl.sith_inquisitor.skill.lightning.thundering_blast"
EFFECT_KEY = "owner_effect"


class _RecordingAbility:
    def __init__(self, fqn):
        self.fqn = fqn
        self.name = fqn.split(".")[-1]
        self.calls = 0

    def execute_branch(self, sim, branch, caster, target, context=None):
        self.calls += 1
        return True


class PostActivateSameActivationTests(unittest.TestCase):
    def _setup(self, owner_fqn, applied_activation, entry=False):
        tm = TriggerManager()
        ability = _RecordingAbility(owner_fqn)
        player = SimpleNamespace(effects={})
        player.effects[EFFECT_KEY] = SimpleNamespace(
            is_expired=False, stacks=2, applied_activation=applied_activation, scales_with_stacks=False,
            effect_blueprint=SimpleNamespace(entry=entry),
        )
        branch = SimpleNamespace(triggers=[{"trigger": "on_ability_post_activate"}])
        tm.subscribe("owner", ability, branch, player, player, effect_key=EFFECT_KEY)
        sim = SimpleNamespace(current_time=0.0, tracer=None)
        return tm, ability, player, sim

    def _dispatch(self, tm, sim, player, activation, ability_spec):
        tm.dispatch("on_ability_post_activate", sim, {
            "caster": player, "target": player, "ability_spec": ability_spec,
            "tags": (), "from_actor": 2, "activation": activation,
        })

    def test_proc_applied_in_same_activation_is_skipped(self):
        token = object()
        tm, ability, player, sim = self._setup(EFFUSION_FQN, token)
        self._dispatch(tm, sim, player, token, BOLT_FQN)
        self.assertEqual(ability.calls, 0)

    def test_effect_from_earlier_activation_still_consumed(self):
        tm, ability, player, sim = self._setup(EFFUSION_FQN, object())
        self._dispatch(tm, sim, player, object(), BOLT_FQN)
        self.assertEqual(ability.calls, 1)

    def test_activating_ability_called_effect_is_skipped(self):
        token = object()
        tm, ability, player, sim = self._setup(TRANSLOCATE_FQN, token, entry=False)
        self._dispatch(tm, sim, player, token, TRANSLOCATE_FQN)
        self.assertEqual(ability.calls, 0)

    def test_activating_ability_entry_effect_still_hears_it(self):
        token = object()
        tm, ability, player, sim = self._setup(THUNDERING_BLAST_FQN, token, entry=True)
        self._dispatch(tm, sim, player, token, THUNDERING_BLAST_FQN)
        self.assertEqual(ability.calls, 1)

    def test_entry_effect_of_other_ability_is_skipped(self):
        token = object()
        tm, ability, player, sim = self._setup(THUNDERING_BLAST_FQN, token, entry=True)
        self._dispatch(tm, sim, player, token, BOLT_FQN)
        self.assertEqual(ability.calls, 0)


if __name__ == "__main__":
    unittest.main()
