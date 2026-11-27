"""Automated verification suite validating combat_math.py against all 17 empirical tests in docs/modifier_bucketing_log.md."""

import unittest
from types import SimpleNamespace
from src.swtorsim.combat_math import handle_modifiers, calculate_base_damage, handle_mitigation, calculate_crit
from src.swtorsim.effects import ActiveEffect, Modifier

def make_mod(stat, value, targets=None, conditional_tag=None, actor=None):
    return Modifier(
        stat=str(stat),
        value=float(value),
        is_percent=True,
        targets=frozenset(targets) if targets else frozenset(),
        conditional_tag=conditional_tag,
        actor=actor,
    )

def make_effect(name, modifiers, tags=None):
    return ActiveEffect(
        fqn=f"eff.test.{name.lower().replace(' ', '_')}",
        name=name,
        modifiers=modifiers,
        tags=frozenset(tags) if tags else frozenset(),
        is_passive=True,
    )

class TestEmpiricalModifierParity(unittest.TestCase):
    """Asserts that combat_math.handle_modifiers produces the exact multiplier predicted for all 17 tests."""

    def test_01_stat_79_tag_vs_ability(self):
        """Test 1: STAT_cbt_damage_done_modifier_percentage (79).
        Expected Multiplier: 1.150000x (Baseline + 15% from Tactical Advantage / Corrosive Dart)
        """
        caster = SimpleNamespace(effects={
            "TA": make_effect("TA", [make_mod(79, 0.05)]),
            "Potent Brew": make_effect("Potent Brew", [make_mod(79, 0.10, targets=["abl.agent.corrosive_dart"])])
        })
        target = SimpleNamespace(effects={})
        action = {"ability_fqn": "abl.agent.corrosive_dart", "attack_type": 4, "damage_type": 4, "tags": []}
        mods = handle_modifiers(caster, target, action)
        self.assertAlmostEqual(mods["total_multiplier"], 1.150000, places=5)

    def test_02_force_and_internal_vulnerabilities(self):
        """Test 2: Force Vuln (386, +5%) + Internal Vuln (376, +7%) + Caster Done (79, +5%).
        Expected Multiplier: 1.0 + 0.05 + 0.05 + 0.07 = 1.170000x (BUCKET_1 Additive)
        """
        caster = SimpleNamespace(effects={"Buff": make_effect("Buff", [make_mod(79, 0.05)])})
        target = SimpleNamespace(effects={
            "Vulnerable (Force)": make_effect("Vulnerable (Force)", [make_mod(386, 0.05)]),
            "Assailable (Internal)": make_effect("Assailable (Internal)", [make_mod(376, 0.07)])
        })
        action = {"ability_fqn": "abl.test.force_dot", "attack_type": 3, "damage_type": 4, "tags": []}
        mods = handle_modifiers(caster, target, action)
        self.assertAlmostEqual(mods["total_multiplier"], 1.170000, places=5)

    def test_03_aoe_vulnerability_overwhelmed(self):
        """Test 3: Overwhelmed (46, +10% AoE) vs BUCKET_1.
        Expected Multiplier: (1.0 + 0.05_Done) * (1.0 + 0.10_AoE) = 1.05 * 1.10 = 1.155000x
        """
        caster = SimpleNamespace(effects={"Buff": make_effect("Buff", [make_mod(79, 0.05)])})
        target = SimpleNamespace(effects={
            "Overwhelmed": make_effect("Overwhelmed", [make_mod(46, 0.10, targets=["tag.abl.utility.is_aoe"])])
        })
        action = {"ability_fqn": "abl.test.aoe", "attack_type": 3, "damage_type": 2, "tags": ["tag.abl.utility.is_aoe"]}
        mods = handle_modifiers(caster, target, action)
        self.assertAlmostEqual(mods["total_multiplier"], 1.155000, places=5)

    def test_04_low_health_execute_inevitable_demise(self):
        """Test 4: Inevitable Demise (220, +25% execute) vs BUCKET_1.
        Expected Multiplier: (1.0 + 0.05_Done + 0.05_Vuln) * (1.0 + 0.25_Execute) = 1.10 * 1.25 = 1.375000x
        """
        caster = SimpleNamespace(effects={
            "Buff": make_effect("Buff", [make_mod(79, 0.05)]),
            "Execute": make_effect("Execute", [make_mod(220, 0.25)])
        })
        target = SimpleNamespace(hp_ratio=0.25, effects={
            "Vulnerable": make_effect("Vulnerable", [make_mod(386, 0.05)])
        })
        action = {"ability_fqn": "abl.test.exec", "attack_type": 3, "damage_type": 4, "tags": []}
        mods = handle_modifiers(caster, target, action)
        self.assertAlmostEqual(mods["total_multiplier"], 1.375000, places=5)

    def test_05_cross_bucket_aoe_vs_execute(self):
        """Test 5: BUCKET_1 (1.10) * BUCKET_2 (1.10 AoE) * BUCKET_3 (1.25 Execute).
        Expected Multiplier: 1.10 * 1.10 * 1.25 = 1.512500x
        """
        caster = SimpleNamespace(effects={
            "Done": make_effect("Done", [make_mod(79, 0.05)]),
            "Execute": make_effect("Execute", [make_mod(220, 0.25)])
        })
        target = SimpleNamespace(hp_ratio=0.20, effects={
            "Vuln": make_effect("Vuln", [make_mod(386, 0.05)]),
            "Overwhelmed": make_effect("Overwhelmed", [make_mod(46, 0.10, targets=["tag.abl.utility.is_aoe"])])
        })
        action = {"ability_fqn": "abl.test.death_field", "attack_type": 3, "damage_type": 4, "tags": ["tag.abl.utility.is_aoe"]}
        mods = handle_modifiers(caster, target, action)
        self.assertAlmostEqual(mods["total_multiplier"], 1.512500, places=5)

    def test_06_target_melee_vulnerability_beat_down(self):
        """Test 6: Beat Down (384, +5% Melee) pools additively into BUCKET_1.
        Baseline: 1.0 + 0.03_Form + 0.05_BeatDown = 1.080000x
        """
        caster = SimpleNamespace(effects={"Shii-Cho": make_effect("Shii-Cho", [make_mod(79, 0.03)])})
        target = SimpleNamespace(effects={"Beat Down": make_effect("Beat Down", [make_mod(384, 0.05)])})
        action = {"ability_fqn": "abl.test.melee_hit", "attack_type": 1, "damage_type": 1, "tags": []}
        mods = handle_modifiers(caster, target, action)
        self.assertAlmostEqual(mods["total_multiplier"], 1.080000, places=5)

    def test_07_target_state_accuracy_reduced_torment(self):
        """Test 7: Torment (389, +15% Accuracy Reduced) is BUCKET_4.
        Expected Multiplier: BUCKET_1 (1.05) * BUCKET_4 (1.15) = 1.207500x
        """
        caster = SimpleNamespace(effects={"Torment": make_effect("Torment", [make_mod(389, 0.15)])})
        target = SimpleNamespace(effects={
            "AccDebuff": make_effect("AccDebuff", [], tags=["accuracy_reduced"]),
            "Vuln": make_effect("Vuln", [make_mod(386, 0.05)])
        })
        action = {"ability_fqn": "abl.test.force", "attack_type": 3, "damage_type": 4, "tags": []}
        mods = handle_modifiers(caster, target, action)
        self.assertAlmostEqual(mods["total_multiplier"], 1.207500, places=5)

    def test_08_assailable_elemental_and_tech_vulnerability(self):
        """Test 8: Assailable Elemental (370, +7%) + Susceptible Tech (388, +5%).
        Expected Multiplier: 1.0 + 0.07 + 0.05 = 1.120000x (BUCKET_1 Additive)
        """
        caster = SimpleNamespace(effects={})
        target = SimpleNamespace(effects={
            "Assailable": make_effect("Assailable", [make_mod(370, 0.07)]),
            "Susceptible": make_effect("Susceptible", [make_mod(388, 0.05)])
        })
        action = {"ability_fqn": "abl.test.tech_elem", "attack_type": 4, "damage_type": 3, "tags": []}
        mods = handle_modifiers(caster, target, action)
        self.assertAlmostEqual(mods["total_multiplier"], 1.120000, places=5)

    def test_09_marked_ranged_vulnerability(self):
        """Test 9: Marked (382, +5% Ranged) + Ironsights (79, +10%) + Supercharge (79, +1%).
        Expected Multiplier: 1.0 + 0.10 + 0.01 + 0.05 = 1.160000x (BUCKET_1 Additive)
        """
        caster = SimpleNamespace(effects={
            "Ironsights": make_effect("Ironsights", [make_mod(79, 0.10)]),
            "Supercharge": make_effect("Supercharge", [make_mod(79, 0.01)])
        })
        target = SimpleNamespace(effects={"Marked": make_effect("Marked", [make_mod(382, 0.05)])})
        action = {"ability_fqn": "abl.test.ranged", "attack_type": 2, "damage_type": 2, "tags": []}
        mods = handle_modifiers(caster, target, action)
        self.assertAlmostEqual(mods["total_multiplier"], 1.160000, places=5)

    def test_10_dual_wield_damage_done_stat_127(self):
        """Test 10: STAT_cbt_dual_wield_damage_done_modifier_percentage (127).
        Modifies offhand scalar to (0.25 + val), does NOT enter multiplicative damage buckets.
        """
        caster = SimpleNamespace(effects={"DualWield": make_effect("DualWield", [make_mod(127, 0.25)])})
        target = SimpleNamespace(effects={})
        action_main = {"ability_fqn": "abl.test.strike", "attack_type": 1, "damage_type": 1, "hand": "main", "tags": []}
        action_off = {"ability_fqn": "abl.test.strike", "attack_type": 1, "damage_type": 1, "hand": "off", "tags": []}
        mods_main = handle_modifiers(caster, target, action_main)
        mods_off = handle_modifiers(caster, target, action_off)
        self.assertEqual(mods_main["total_multiplier"], 1.0)
        self.assertEqual(mods_off["total_multiplier"], 1.0)
        self.assertEqual(mods_off["dual_wield_damage_modifier"], 0.25)

    def test_11_caster_channel_dealt_scale_melee_stat_407(self):
        """Test 11: Melee Dealt Scale (407, +5% Ravager) + Shien (79, +6%) + Beat Down (384, +5%).
        Expected Multiplier: 1.0 + 0.06 + 0.05 + 0.05 = 1.160000x (BUCKET_1 Additive)
        """
        caster = SimpleNamespace(effects={
            "Shien": make_effect("Shien", [make_mod(79, 0.06)]),
            "Ravager": make_effect("Ravager", [make_mod(407, 0.05)])
        })
        target = SimpleNamespace(effects={"Beat Down": make_effect("Beat Down", [make_mod(384, 0.05)])})
        action = {"ability_fqn": "abl.test.vicious_slash", "attack_type": 1, "damage_type": 2, "tags": []}
        mods = handle_modifiers(caster, target, action)
        self.assertAlmostEqual(mods["total_multiplier"], 1.160000, places=5)

    def test_12_and_14_target_state_bleeding_stat_221(self):
        """Tests 12 & 14: Target State Bleeding (221, +3% Blood Tracker) is BUCKET_5.
        Expected Multiplier: (1.0 + 0.10_PowerBracer + 0.10_ShockTrooper + 0.05_Susceptible + 0.07_HEGC) * 1.03_Bleed
        = 1.320000 * 1.03 = 1.359600x
        """
        caster = SimpleNamespace(effects={
            "Power Bracer": make_effect("Power Bracer", [make_mod(79, 0.10)]),
            "Shock Trooper": make_effect("Shock Trooper", [make_mod(79, 0.10)]),
            "HEGC": make_effect("HEGC", [make_mod(395, 0.07)]),
            "Blood Tracker": make_effect("Blood Tracker", [make_mod(221, 0.03)])
        })
        target = SimpleNamespace(effects={
            "Susceptible": make_effect("Susceptible", [make_mod(388, 0.05)]),
            "BleedDebuff": make_effect("BleedDebuff", [], tags=["bleed"])
        })
        action = {"ability_fqn": "abl.test.mag_blast", "attack_type": 4, "damage_type": 2, "tags": []}
        mods = handle_modifiers(caster, target, action)
        self.assertAlmostEqual(mods["total_multiplier"], 1.359600, places=5)

    def test_13_caster_type_dealt_scale_energy_kinetic_stat_395_397(self):
        """Test 13: HEGC (395 Energy, +7%) + Power Bracer (79, +10%) + Shock Trooper (79, +10%) + Susceptible (388, +5%).
        Expected Multiplier: 1.0 + 0.10 + 0.10 + 0.07 + 0.05 = 1.320000x (BUCKET_1 Additive)
        """
        caster = SimpleNamespace(effects={
            "Power Bracer": make_effect("Power Bracer", [make_mod(79, 0.10)]),
            "Shock Trooper": make_effect("Shock Trooper", [make_mod(79, 0.10)]),
            "HEGC": make_effect("HEGC", [make_mod(395, 0.07), make_mod(397, 0.07)])
        })
        target = SimpleNamespace(effects={"Susceptible": make_effect("Susceptible", [make_mod(388, 0.05)])})
        action = {"ability_fqn": "abl.test.mag_blast", "attack_type": 4, "damage_type": 2, "tags": []}
        mods = handle_modifiers(caster, target, action)
        self.assertAlmostEqual(mods["total_multiplier"], 1.320000, places=5)

    def test_15_caster_channel_dealt_scale_force_stat_409(self):
        """Test 15: Force Dealt Scale (409, +3% Shii-Cho Mastery) + Shii-Cho (79, +3%) + Vulnerable (386, +5%).
        Expected Multiplier: 1.0 + 0.03 + 0.03 + 0.05 = 1.110000x (BUCKET_1 Additive)
        """
        caster = SimpleNamespace(effects={
            "Shii-Cho Form": make_effect("Shii-Cho Form", [make_mod(79, 0.03)]),
            "Shii-Cho Mastery": make_effect("Shii-Cho Mastery", [make_mod(409, 0.03)])
        })
        target = SimpleNamespace(effects={"Vulnerable": make_effect("Vulnerable", [make_mod(386, 0.05)])})
        action = {"ability_fqn": "abl.test.force_choke", "attack_type": 3, "damage_type": 1, "tags": []}
        mods = handle_modifiers(caster, target, action)
        self.assertAlmostEqual(mods["total_multiplier"], 1.110000, places=5)

    def test_16_target_state_burning_stat_250(self):
        """Test 16: Burning Storm (250, +25% on fire) is BUCKET_6.
        Expected Multiplier: BUCKET_1 (1.16) * BUCKET_2 (1.10 AoE) * BUCKET_6 (1.25 On Fire) = 1.595000x
        """
        caster = SimpleNamespace(effects={
            "Master Focus": make_effect("Master Focus", [make_mod(407, 0.05)]),
            "Shien Form": make_effect("Shien Form", [make_mod(79, 0.06)]),
            "Burning Storm": make_effect("Burning Storm", [make_mod(250, 0.25)])
        })
        target = SimpleNamespace(effects={
            "Beat Down": make_effect("Beat Down", [make_mod(384, 0.05)]),
            "Overwhelmed": make_effect("Overwhelmed", [make_mod(46, 0.10, targets=["tag.abl.utility.is_aoe"])]),
            "BurnDebuff": make_effect("BurnDebuff", [], tags=["burn"])
        })
        action = {"ability_fqn": "abl.test.cyclone_slash", "attack_type": 1, "damage_type": 2, "tags": ["tag.abl.utility.is_aoe"]}
        mods = handle_modifiers(caster, target, action)
        self.assertAlmostEqual(mods["total_multiplier"], 1.595000, places=5)

    def test_17_caster_flat_damage_stat_78_is_noop_multiplier(self):
        """Test 17: Pull and Pummel (78, fixed 0.20) does NOT modify percentage multiplier.
        Baseline Tactics Stockstrike: 1.0 + 0.10_FocusedImpact + 0.10_RiotAugs + 0.05_HEC = 1.250000x
        With Pull and Pummel active: Still 1.250000x (0% multiplier change)
        """
        caster = SimpleNamespace(effects={
            "Focused Impact": make_effect("Focused Impact", [make_mod(79, 0.10, targets=["abl.trooper.stockstrike"])]),
            "Riot Augs": make_effect("Riot Augs", [make_mod(79, 0.10, targets=["abl.trooper.stockstrike"])]),
            "High Energy Cell": make_effect("High Energy Cell", [make_mod(397, 0.05)]),
            "Pull and Pummel": make_effect("Pull and Pummel", [make_mod(78, 0.20, targets=["tag.abl.trooper.stockstrike"])])
        })
        target = SimpleNamespace(effects={})
        action = {"ability_fqn": "abl.trooper.stockstrike", "attack_type": 4, "damage_type": 1, "tags": ["tag.abl.trooper.stockstrike"]}
        mods = handle_modifiers(caster, target, action)
        self.assertAlmostEqual(mods["total_multiplier"], 1.250000, places=5)

if __name__ == "__main__":
    unittest.main()
