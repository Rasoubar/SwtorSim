"""Instant effects (no duration, not passive) are announced with on_effect_applied / on_effect_received.

Lasting effects are announced from Entity.apply_effect; an instant effect never goes there. Tactical Advantage (PTS
`abl.agent.tactical_advantage` effect 1) only gains a stack when it receives an effect tagged `ta_granter`, and every
`ta_granter` effect in the data is instant (Corrosive Return effect 2, Fatality effect 4, Lethal Strike effect 5, ...).
Without the announcement none of those grants could land.

Corrosive Return (PTS `...lethality.mods.tier2.corrosive_return`): on a Corrosive Assault hit (tag
`corrosive_assault_tick`), if the operative has no `finishing_move` effect (Tactical Advantage), call the instant
`ta_granter` effect; 10s rate limit.
"""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.swtorsim.abilities import Ability, AbilityBlueprint, Effect
from src.swtorsim.engine import Simulation
from src.swtorsim.entities import Dummy, Player
from src.swtorsim.triggers import TriggerManager

ROOT = Path(__file__).resolve().parents[1]
PTS = ROOT / "data" / "extractor" / "pts" / "parsed" / "abl" / "agent"
TA_PATH = PTS / "tactical_advantage.json"
CR_PATH = PTS / "skill" / "lethality" / "mods" / "tier2" / "corrosive_return.json"

TA_STACKS = "abl.agent.tactical_advantage:2"
CA_HIT_TAGS = frozenset({"tag.abl.agent.corrosive_assault_tick", "tag.abl.agent.tactic"})


def _ability(path):
    return Ability(AbilityBlueprint.from_dict(json.loads(path.read_text(encoding="utf-8"))))


@unittest.skipUnless(TA_PATH.exists() and CR_PATH.exists(), "PTS data missing")
class TacticalAdvantageGranterTests(unittest.TestCase):
    def setUp(self):
        self.sim = Simulation(verbose=False, seed=1)
        self.player = Player("operative")
        self.target = Dummy("Target Dummy", hp=10_000_000)
        self.player.current_target = self.target
        self.ta = _ability(TA_PATH)
        self.cr = _ability(CR_PATH)
        # Passive entry effects, as setup loads them: applied to the player and subscribed to the bus.
        self.ta.execute_effect(1, self.player, self.player, self.sim)
        self.cr.execute_effect(1, self.player, self.player, self.sim)

    def _ta(self):
        eff = self.player.effects.get(TA_STACKS)
        return 0 if eff is None or eff.is_expired else eff.stacks

    def _corrosive_assault_hit(self):
        self.sim.triggers.dispatch("on_damage_dealt", self.sim, {
            "caster": self.player, "target": self.target, "enemy_target": self.target, "tags": CA_HIT_TAGS,
            "damage_type": 2, "attack_type": 2, "spell_type": 1, "weapon_mode": 3, "is_crit": False,
        })

    def test_instant_granter_received_by_the_player_grants_a_stack(self):
        self.cr.execute_effect(2, self.player, self.player, self.sim)

        self.assertEqual(self._ta(), 1)

    def test_instant_granter_received_by_the_dummy_grants_nothing(self):
        self.cr.execute_effect(2, self.player, self.target, self.sim)

        self.assertEqual(self._ta(), 0)

    def test_corrosive_return_grants_when_no_tactical_advantage_is_left(self):
        self._corrosive_assault_hit()

        self.assertEqual(self._ta(), 1)

    def test_corrosive_return_does_nothing_while_tactical_advantage_is_up(self):
        self.ta.execute_effect(2, self.player, self.player, self.sim)  # one stack

        self._corrosive_assault_hit()

        self.assertEqual(self._ta(), 1)

    def test_corrosive_return_rate_limit(self):
        self._corrosive_assault_hit()
        self.player.effects[TA_STACKS].is_expired = True  # stack spent again

        self.sim.current_time += 5.0
        self._corrosive_assault_hit()

        self.assertEqual(self._ta(), 0)


class _RecordingAbility:
    def __init__(self):
        self.fqn = "abl.test.listener"
        self.name = "Listener"
        self.calls = []

    def execute_branch(self, sim, branch, caster, target, context=None):
        self.calls.append(context.get("trigger_name"))
        return True


class InstantEffectAnnouncementTests(unittest.TestCase):
    def _setup(self, conditions=None):
        sim = SimpleNamespace(current_time=0.0, tracer=None, triggers=TriggerManager(), loading=False)
        player = Player("operative")
        listener = _RecordingAbility()
        for trigger in ("on_effect_applied", "on_effect_received"):
            branch = SimpleNamespace(triggers=[{"trigger": trigger, "tags": ["tag.test.signal"]}])
            sim.triggers.subscribe("listener", listener, branch, player, player)
        effect = Effect.from_dict({
            "number": 2, "name": "Signal", "tags": ["tag.test.signal"], "conditions": conditions,
            "branches": [{"index": 2, "triggers": [{"trigger": "on_apply"}],
                          "actions": [{"action_type": "custom", "ints": {"param1": 0}}]}],
        })
        source = SimpleNamespace(fqn="abl.test.source", name="Source", blueprint=None)
        return sim, player, listener, effect, source

    def test_instant_effect_is_announced_to_its_receiver(self):
        sim, player, listener, effect, source = self._setup()

        effect.execute(sim, player, player, ability=source)

        self.assertEqual(listener.calls, ["on_effect_applied", "on_effect_received"])

    def test_instant_effect_whose_conditions_fail_is_not_announced(self):
        failing = {"list": [{"id": "1", "type": "has_effect", "negated": False, "actor": "caster",
                             "count": 1, "tags": ["tag.test.missing"]}], "logic": {"condition": "1"}}
        sim, player, listener, effect, source = self._setup(conditions=failing)

        effect.execute(sim, player, player, ability=source)

        self.assertEqual(listener.calls, [])


if __name__ == "__main__":
    unittest.main()
