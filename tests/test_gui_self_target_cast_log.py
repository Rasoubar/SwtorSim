"""Web GUI TEST run survives a pre-combat step cast on the caster ("target": "self").

The TEST-mode cast wrapper read `tgt.hp_ratio` from the cast's target. A self-target pre-combat step hands it the
Player, which has no `hp_ratio`, so the run crashed with "'Player' object has no attribute 'hp_ratio'" at the first
pre-combat cast. The cast log's HP columns now read the dummy, as the stall/deadlock rows already did.
"""

import contextlib
import io
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_CONFIG = ROOT / "data" / "run_config" / "Marksmanship.json"


@unittest.skipUnless(RUN_CONFIG.is_file(), "Marksmanship run config missing")
class GuiSelfTargetCastLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.swtorsim import settings
        from src.swtorsim.config_load import load_from_run_config
        from src.swtorsim.run_config import load_run_config
        from src.swtorsim.web_gui import _run_single_test_detailed

        prev = os.getcwd()
        # Loading the run config sets process-wide engine toggles; restore them so later tests see the defaults.
        saved_settings = settings.snapshot_engine_settings()
        os.chdir(ROOT)
        try:
            cfg = load_run_config(str(RUN_CONFIG))
            cfg.duration = 20
            inputs = load_from_run_config(cfg)
            rotation = dict(inputs.rotation_config)
            rotation["pre_combat"] = [{"ability": "laze_target", "target": "self"}]
            with contextlib.redirect_stdout(io.StringIO()):
                cls.result = _run_single_test_detailed(
                    cfg,
                    {
                        "rotation_config": rotation,
                        "stats_config": inputs.stats_config,
                        "loadout_blueprints": inputs.loadout_blueprints,
                        "debuff_module": inputs.debuff_module,
                    },
                )
        finally:
            settings.apply_engine_settings(saved_settings)
            os.chdir(prev)

    def test_self_target_pre_combat_cast_is_logged_with_dummy_hp(self):
        casts = [ev for ev in self.result["combat_log"] if ev["category"] == "cast"]
        self.assertTrue(casts)
        first = casts[0]
        self.assertEqual(first["ability"], "Laze Target")
        self.assertEqual(first["target_hp_pct"], 100.0)
        self.assertGreater(first["target_hp"], 0)

    def test_run_continues_into_the_rotation(self):
        log = self.result["combat_log"]
        self.assertTrue(any(ev["category"] == "damage" for ev in log))


if __name__ == "__main__":
    unittest.main()
