"""Ability display names prefer the conditional slot for the ability's own discipline."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from extractor.abilities import _ability_name
from extractor.graph import NodeIndexEntry, NodeRecord
from extractor.node import ParsedNode

HEART_BEAT_KEY = "6338941111150498357"
SNAKE_EYES_KEY = "15685385242400905286"
TARGET_HACK_KEY = "1"
BLOOD_SIGHTS_KEY = "2"


def _record(fqn: str, fields: list[dict]) -> NodeRecord:
    return NodeRecord(
        entry=NodeIndexEntry(
            node_id="1",
            fqn=fqn,
            base_class_id="0",
            base_class_name="ablAbility",
            bucket_path="",
            stream_style=1,
            bitset=0,
            content_offset=0,
        ),
        parsed=ParsedNode(),
        resolved_fields=fields,
    )


def _loc(resolved_text: str, by_key: dict[str, str]) -> dict:
    return {
        "name": "locTextRetrieverMap",
        "value": {"resolved_text": resolved_text, "resolved_by_key": by_key},
    }


def _conditionals(*pairs: tuple[str, str]) -> dict:
    return {
        "name": "ablNameConditionalIds",
        "value": [{"key": condition, "value": key} for condition, key in pairs],
    }


class AbilityNameTests(unittest.TestCase):
    def test_dirty_fighting_plus_uses_conditional_name(self):
        record = _record(
            "abl.smuggler.skill.dirty_fighting.blood_sights_plus",
            [
                _loc(
                    "Snake Eyes",
                    {SNAKE_EYES_KEY: "Snake Eyes", HEART_BEAT_KEY: "Heart Beat Acquired"},
                ),
                _conditionals(
                    (
                        "cnd.trp.discipline.gunslinger.is_dirty_fighting",
                        HEART_BEAT_KEY,
                    )
                ),
            ],
        )
        self.assertEqual(_ability_name(record), "Heart Beat Acquired")

    def test_saboteur_plus_uses_its_own_conditional(self):
        record = _record(
            "abl.smuggler.skill.saboteur.target_hack_plus",
            [
                _loc("Snake Eyes", {SNAKE_EYES_KEY: "Snake Eyes", "9": "Exploit Vulnerability"}),
                _conditionals(("cnd.trp.discipline.gunslinger.is_saboteur", "9")),
            ],
        )
        self.assertEqual(_ability_name(record), "Exploit Vulnerability")

    def test_shared_plus_keeps_the_matching_spec_name(self):
        record = _record(
            "abl.smuggler.skill.sharpshooter.smugglers_luck_plus",
            [
                _loc(
                    "Snake Eyes",
                    {
                        SNAKE_EYES_KEY: "Snake Eyes",
                        TARGET_HACK_KEY: "Target Hack",
                        BLOOD_SIGHTS_KEY: "Blood Sights",
                    },
                ),
                _conditionals(
                    ("cnd.trp.discipline.gunslinger.is_sharpshooter", SNAKE_EYES_KEY),
                    ("cnd.trp.discipline.gunslinger.is_saboteur", TARGET_HACK_KEY),
                    ("cnd.trp.discipline.gunslinger.is_dirty_fighting", BLOOD_SIGHTS_KEY),
                ),
            ],
        )
        self.assertEqual(_ability_name(record), "Snake Eyes")

    def test_mirror_class_conditional_does_not_replace_the_default(self):
        record = _record(
            "abl.sith_inquisitor.skill.darkness.redirected_wrath",
            [
                _loc("Redirected Wrath", {"3": "Redirected Retribution"}),
                _conditionals(("cnd.classes.is_jedi_consular_shadow", "3")),
            ],
        )
        self.assertEqual(_ability_name(record), "Redirected Wrath")

    def test_english_name_when_no_conditional_field(self):
        record = _record(
            "abl.agent.adrenaline_probe",
            [_loc("Adrenaline Probe", {})],
        )
        self.assertEqual(_ability_name(record), "Adrenaline Probe")


if __name__ == "__main__":
    unittest.main()
