"""Integration: Leeching Strike restores 4/8/12 Force by the number of sinister_succor_dot effects up."""

import os
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.debug.tracer import CombatTracer
from src.swtorsim.run_config import load_run_config
from src.swtorsim.tester import Tester

RUN_CONFIG_PATH = ROOT / "data" / "run_config" / "Hatred.json"


@unittest.skipUnless(RUN_CONFIG_PATH.exists(), "Hatred run config not present")
class LeechingStrikeForceRestoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def test_leeching_strike_restores_12_with_three_dots_up(self):
        config = load_run_config(str(RUN_CONFIG_PATH))
        config.dummy_hp = 30_000_000
        config.duration = 120
        inputs = load_from_run_config(config)
        tracer = CombatTracer()
        tester = Tester(
            rotation_config=inputs.rotation_config,
            stats_config=inputs.stats_config,
            loadout_blueprints=inputs.loadout_blueprints,
            duration=config.duration,
            dummy_hp=config.dummy_hp,
            debuff_module=inputs.debuff_module,
            enable_stem_matching=getattr(config, "enable_stem_matching", True),
            gcd_stall=getattr(config, "gcd_stall", 0.0),
        )
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            tester.run_test(show_buffs=False, tracer=tracer, config=config)

        restores = [
            e["delta"] for e in tracer.events
            if e.get("type") == "resource" and e.get("reason") == "Leeching Strike"
        ]
        self.assertGreater(len(restores), 3)
        counts = Counter(restores)
        self.assertTrue(set(counts) <= {4.0, 8.0, 12.0}, counts)
        # Creeping Terror, Discharge and Crushed (Eradicate) are normally all up in this rotation.
        self.assertGreaterEqual(counts[12.0] / len(restores), 0.8, counts)


if __name__ == "__main__":
    unittest.main()
