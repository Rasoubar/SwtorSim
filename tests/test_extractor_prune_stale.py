"""Extractor: parsed ability / talent files from an earlier extraction are deleted when the node is gone."""

import sys
import tempfile
import unittest
from pathlib import Path

SWTORSIM_ROOT = Path(__file__).resolve().parents[1]
if str(SWTORSIM_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(SWTORSIM_ROOT / "src"))

from extractor.bkt import fqn_to_relative_path, prune_stale_json


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    return path


class PruneStaleJsonTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "parsed"

    def tearDown(self):
        self._tmp.cleanup()

    def test_deletes_unwritten_files_and_empty_dirs(self):
        kept = _touch(self.root / fqn_to_relative_path("abl.agent.skill.lethality.corrosive_dart"))
        stale = _touch(self.root / fqn_to_relative_path("abl.agent.stim_boost_plus"))
        stale_deep = _touch(self.root / fqn_to_relative_path("abl.trooper.skill.old_tree.shoulder_cannon_x"))
        removed = prune_stale_json(self.root / "abl", {kept})
        self.assertEqual(removed, 2)
        self.assertTrue(kept.exists())
        self.assertFalse(stale.exists())
        self.assertFalse(stale_deep.exists())
        self.assertFalse(stale_deep.parent.exists(), "empty directory left behind")
        self.assertTrue((self.root / "abl").exists())

    def test_empty_written_set_deletes_nothing(self):
        stale = _touch(self.root / fqn_to_relative_path("abl.agent.stim_boost_plus"))
        self.assertEqual(prune_stale_json(self.root / "abl", set()), 0)
        self.assertTrue(stale.exists())

    def test_non_json_files_and_missing_root_untouched(self):
        kept = _touch(self.root / "abl" / "a.json")
        note = self.root / "abl" / "notes.txt"
        note.write_text("x", encoding="utf-8")
        self.assertEqual(prune_stale_json(self.root / "abl", {kept}), 0)
        self.assertTrue(note.exists())
        self.assertEqual(prune_stale_json(self.root / "missing", {kept}), 0)


if __name__ == "__main__":
    unittest.main()
