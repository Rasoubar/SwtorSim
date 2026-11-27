import math
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.swtorsim.config_load import load_from_run_config
from src.swtorsim.run_config import load_run_config
from src.swtorsim.setup import prepare_simulation

RUN_CONFIG_PATH = (
    ROOT / "data" / "run_config" / "Hatred.json"
    if (ROOT / "data" / "run_config" / "Hatred.json").exists()
    else ROOT / "data" / "run_config" / "first_test.json"
)


class CooldownIgnoreAlacrityTests(unittest.TestCase):
    """calculate_cooldown must skip Alacrity for abilities flagged ablIgnoreAlacrity (e.g. Thermal Yield)."""

    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def setUp(self):
        config = load_run_config(str(RUN_CONFIG_PATH))
        inputs = load_from_run_config(config)
        self.sim, self.player, self.target = prepare_simulation(
            inputs.rotation_config,
            inputs.stats_config,
            inputs.loadout_blueprints,
            config.dummy_hp,
            inputs.debuff_module,
        )
        self.player.stats["Alacrity"] = 0.10
        self.ability = next(
            (a for a in self.player.ability_db.values() if a.type == "active" and (a.cooldown or 0) > 0),
            None,
        )
        if self.ability is None:
            self.fail("No active ability with a cooldown in the loadout.")

    def test_flag_off_scales_with_alacrity(self):
        self.ability.abl_ignore_alacrity = False
        expected = round(math.ceil((60.0 / 1.10) * 10) / 10, 2)
        self.assertAlmostEqual(self.player.calculate_cooldown(60.0, ability=self.ability), expected, places=2)

    def test_flag_on_ignores_alacrity(self):
        self.ability.abl_ignore_alacrity = True
        self.assertAlmostEqual(self.player.calculate_cooldown(60.0, ability=self.ability), 60.0, places=2)

    def test_flag_on_keeps_flat_cooldown_modifiers(self):
        from src.swtorsim.effects import ActiveEffect
        from src.swtorsim.modifiers import Modifier

        self.ability.abl_ignore_alacrity = True
        self.player.effects["test_cd_flat:1"] = ActiveEffect(
            fqn="abl.test.cd_flat",
            name="CD Flat",
            number=1,
            modifiers=[Modifier(stat="STAT_abl_time_cooldown", value=-2.0, targets=frozenset({self.ability.fqn}))],
            is_passive=True,
        )
        self.assertAlmostEqual(self.player.calculate_cooldown(60.0, ability=self.ability), 58.0, places=2)

    def test_flag_on_via_string_lookup(self):
        self.ability.abl_ignore_alacrity = True
        key = next(k for k, v in self.player.ability_db.items() if v is self.ability)
        self.assertAlmostEqual(self.player.calculate_cooldown(60.0, ability=key), 60.0, places=2)


if __name__ == "__main__":
    unittest.main()
