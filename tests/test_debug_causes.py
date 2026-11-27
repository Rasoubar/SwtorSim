"""Cause links: every traced event knows the event that caused it, and the wrapping that records them leaves no trace."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import src.swtorsim.abilities as abilities  # noqa: E402
import src.swtorsim.engine as engine  # noqa: E402
import src.swtorsim.events as events  # noqa: E402
from src.swtorsim.debug import debug_api  # noqa: E402
from src.swtorsim.debug.tracer import CombatTracer  # noqa: E402
from src.swtorsim.debug.traced_run import traced_engine  # noqa: E402


class TracerFrameTests(unittest.TestCase):
    def test_an_event_takes_the_innermost_cause_that_has_an_id(self):
        tracer = CombatTracer()
        cast = tracer.begin_cause()  # a cast: has no id until its cast_start is recorded
        tracer.record_cast_start(1.0, "P", "Strike", "abl.strike", 0.0)
        cast_id = tracer.events[-1]["id"]
        tracer.record_resource_change(1.0, "P", "Rage", 10.0, -5.0, "Cast Strike")
        self.assertEqual(tracer.events[-1]["cause"], cast_id)
        tracer.end_cause(cast)
        tracer.record_resource_change(2.0, "P", "Rage", 12.0, 2.0, "Regen")
        self.assertIsNone(tracer.events[-1]["cause"])

    def test_a_proc_takes_its_reserved_id_and_what_it_did_points_at_it(self):
        tracer = CombatTracer()
        cast = tracer.begin_cause()
        tracer.record_cast_start(1.0, "P", "Strike", "abl.strike", 0.0)
        cast_id = tracer.events[-1]["id"]
        frame = tracer.begin_cause(reserve=True)
        tracer.record_buff_applied(1.0, "P", "Surge")
        tracer.record_proc_dispatch(1.0, "on_damage_dealt", "Surge Proc", "Surge", True, "ok", cause_frame=frame)
        proc = tracer.events[-1]
        buff = next(e for e in tracer.events if e["type"] == "buff_apply")
        self.assertEqual(proc["type"], "proc_fire")
        self.assertEqual(proc["cause"], cast_id)
        self.assertEqual(buff["cause"], proc["id"])
        self.assertEqual(tracer.active_buff_windows[0]["cause"], proc["id"])
        tracer.end_cause(cast)

    def test_a_proc_that_recorded_nothing_hands_its_events_back_to_the_cause_it_stood_in_for(self):
        tracer = CombatTracer()
        cast = tracer.begin_cause()
        tracer.record_cast_start(1.0, "P", "Strike", "abl.strike", 0.0)
        cast_id = tracer.events[-1]["id"]
        frame = tracer.begin_cause(reserve=True)
        tracer.record_buff_applied(1.0, "P", "Surge")
        tracer.end_cause(frame)  # the branch ran but the proc event was never recorded
        tracer.end_cause(cast)
        self.assertEqual(tracer.to_dict()["events"][-1]["cause"], cast_id)

    def test_a_hit_lists_the_applications_of_the_effects_that_shaped_it(self):
        tracer = CombatTracer()
        tracer.record_buff_applied(1.0, "P", "Surge")
        applied = tracer.events[-1]["id"]
        audit = {"sources": [{"effect": "Surge"}, {"effect": "Passive thing"}]}
        tracer.record_damage_hit(2.0, "Strike", 100, False, "Dummy", 900, math_audit=audit)
        self.assertEqual(tracer.events[-1]["shaped_by"], [{"id": applied, "effect": "Surge"}])

    def test_a_proc_heard_after_a_hit_answers_to_that_hit_and_a_buff_it_consumes_ends_under_the_proc(self):
        tracer = CombatTracer()
        tracer.record_buff_applied(0.5, "P", "Challenge")
        cast = tracer.begin_cause()
        tracer.record_cast_start(1.0, "P", "Slash", "abl.slash", 0.0)
        tracer.record_damage_hit(1.0, "Slash", 100, False, "Dummy", 900)
        hit_id = tracer.events[-1]["id"]
        frame = tracer.begin_cause(reserve=True, trigger="on_damage_dealt")
        tracer.record_buff_expired(1.0, "P", "Challenge")
        tracer.record_proc_dispatch(1.0, "on_damage_dealt", "Dispatcher", "Dispatcher:2", True, "ok", cause_frame=frame)
        proc = next(e for e in tracer.events if e["type"] == "proc_fire")
        window = tracer.active_buff_windows[0]
        self.assertEqual(proc["cause"], hit_id)
        self.assertEqual(window["end_cause"], proc["id"])
        self.assertIsNotNone(window["end_id"])
        tracer.end_cause(cast)

    def test_a_held_dispatch_is_linked_to_its_own_hit_not_the_last_one_recorded(self):
        """A branch with several hits holds their damage-dealt dispatches until it ends (HitGroup)."""
        tracer = CombatTracer()
        first_context, second_context = {"hit": 1}, {"hit": 2}
        tracer.record_damage_hit(1.0, "Strike", 100, False, "Dummy", 900)
        first_id = tracer.events[-1]["id"]
        tracer.note_parked_hit(first_context)
        tracer.record_damage_hit(1.0, "Strike", 90, False, "Dummy", 810)
        second_id = tracer.events[-1]["id"]
        tracer.note_parked_hit(second_context)
        for context, expected in ((first_context, first_id), (second_context, second_id)):
            frame = tracer.begin_cause(reserve=True, trigger="on_damage_dealt", context=context)
            tracer.record_proc_dispatch(1.0, "on_damage_dealt", "Proc", "Proc:1", True, "ok", cause_frame=frame)
            self.assertEqual(tracer.events[-1]["cause"], expected)

    def test_a_choice_recorded_after_its_cast_becomes_the_cast_cause(self):
        tracer = CombatTracer()
        tracer.record_cast_start(1.0, "P", "Strike", "abl.strike", 0.0)
        tracer.record_rotation_evaluation(1.0, 0, "priority_block", "Block", [], chosen_ability="Strike")
        self.assertEqual(tracer.events[0]["cause"], tracer.events[1]["id"])


class TracedFightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = debug_api.run_trace(config="Hatred", environment="pts", duration=60)
        cls.by_id = {e["id"]: e for e in cls.trace["events"]}

    def test_every_event_has_an_id_and_every_cause_is_an_event_that_happened_no_later(self):
        for event in self.trace["events"]:
            self.assertIn("id", event)
            cause = event.get("cause")
            if cause is not None:
                self.assertIn(cause, self.by_id)
                self.assertLessEqual(self.by_id[cause]["t"], event["t"] + 1e-6)

    def test_hits_come_from_a_cast_or_a_proc_and_casts_from_a_rotation_choice(self):
        kinds = {"damage_hit": set(), "cast_start": set()}
        for event in self.trace["events"]:
            if event["type"] in kinds and event.get("cause") is not None:
                kinds[event["type"]].add(self.by_id[event["cause"]]["type"])
        self.assertTrue(kinds["damage_hit"] <= {"cast_start", "proc_fire"})
        self.assertIn("cast_start", kinds["damage_hit"])
        self.assertEqual(kinds["cast_start"], {"rotation_eval"})

    def test_procs_name_the_cast_hit_or_proc_they_answer_to_and_what_they_granted_points_back_at_them(self):
        procs = [e for e in self.trace["events"] if e["type"] == "proc_fire"]
        self.assertTrue(procs)
        self.assertTrue(all(self.by_id[p["cause"]]["type"] in ("cast_start", "proc_fire", "damage_hit") for p in procs if p["cause"] is not None))
        fired = {row[10] for row in self.trace["proc"]["evals"] if row[10] is not None}
        self.assertTrue(fired)
        self.assertTrue(fired <= set(self.by_id))

    def test_damage_dealt_procs_are_linked_to_the_hit_and_buff_windows_say_what_ended_them(self):
        hits_cause = [p for p in self.trace["events"] if p["type"] == "proc_fire" and p["trigger"] == "on_damage_dealt"]
        self.assertTrue(hits_cause)
        self.assertGreater(sum(1 for p in hits_cause if self.by_id[p["cause"]]["type"] == "damage_hit"), len(hits_cause) // 2)
        ended = [w for w in self.trace["buff_windows"] if w.get("end_id") is not None]
        self.assertTrue(ended)

    def test_some_procs_answer_to_an_earlier_hit_than_the_last_one_recorded(self):
        """Held dispatches (a branch with several hits) run after all its hits landed; each still names its own hit."""
        last, older = None, 0
        for event in self.trace["events"]:
            if event["type"] == "damage_hit":
                last = event
            elif event["type"] == "proc_fire" and event["trigger"] == "on_damage_dealt":
                cause = self.by_id[event["cause"]]
                self.assertEqual(cause["type"], "damage_hit")
                older += cause is not last
        self.assertGreater(older, 0)

    def test_hits_say_which_buff_applications_shaped_them(self):
        shaped = [h for h in self.trace["events"] if h["type"] == "damage_hit" and h.get("shaped_by")]
        self.assertTrue(shaped)
        for hit in shaped:
            for link in hit["shaped_by"]:
                self.assertIsInstance(link["id"], int)
                self.assertLessEqual(link["id"], hit["id"])


class WrappingTests(unittest.TestCase):
    def test_the_wrapping_lasts_only_for_the_block(self):
        cast, relative, absolute = abilities.Ability.cast, engine.Simulation.schedule_relative, engine.Simulation.schedule_absolute
        park = events.HitGroup.park
        with traced_engine():
            self.assertIsNot(abilities.Ability.cast, cast)
            self.assertIsNot(engine.Simulation.schedule_relative, relative)
            self.assertIsNot(events.HitGroup.park, park)
        self.assertIs(events.HitGroup.park, park)
        self.assertIs(abilities.Ability.cast, cast)
        self.assertIs(engine.Simulation.schedule_relative, relative)
        self.assertIs(engine.Simulation.schedule_absolute, absolute)


if __name__ == "__main__":
    unittest.main()
