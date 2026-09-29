import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.swtorsim.abilities import Ability, AbilityBlueprint
from src.swtorsim.config_load import load_from_run_config, selected_fqns_from_config
from src.swtorsim.run_config import (
    DISCIPLINES_DIR,
    GEAR_PATH,
    RELICS_PATH,
    load_run_config,
)
from src.swtorsim.setup import prepare_simulation

PARSED_DIR = ROOT / "data" / "extractor" / "parsed"
ADRENALS_PATH = ROOT / "data" / "extractor" / "adrenals.json"
RUN_CONFIG_PATH = ROOT / "data" / "run_config" / "first_test.json"


def _parsed_path(fqn: str) -> Path:
    return PARSED_DIR / Path(*fqn.split(".")).with_suffix(".json")


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _expected_type(data: dict) -> str:
    return data.get("type") or "passive"


def _expected_triggers_gcd(data: dict) -> bool:
    if "triggers_gcd" in data:
        return bool(data["triggers_gcd"])
    return _expected_type(data) == "active"


def _expected_base_gcd(data: dict) -> float:
    raw = data.get("base_gcd")
    if raw is not None:
        return float(raw)
    if _expected_type(data) == "active":
        return 1.5
    return 0.0


def _float_or_zero(value) -> float:
    if value is None:
        return 0.0
    return float(value)


def _is_passive_initializer(initializers) -> bool:
    return any(
        init.get("initializer_type") == "eff_initializer__set_passive"
        and init.get("bools", {}).get("is_passive", False)
        for init in initializers or []
        if isinstance(init, dict)
    )


def _check_branch(raw: dict, branch) -> list[str]:
    problems = []
    checks = (
        ("index", raw.get("index", 0), branch.index),
        ("triggers", raw.get("triggers", []), branch.triggers),
        ("conditions", raw.get("conditions"), branch.conditions),
        ("actions", raw.get("actions", []), branch.actions),
        ("target_overrides", raw.get("target_overrides", []), branch.target_overrides),
        ("run_if_none_ran", raw.get("run_if_none_ran", []), branch.run_if_none_ran),
        ("is_attack", raw.get("is_attack", False), branch.is_attack),
    )
    for label, expected, actual in checks:
        if actual != expected:
            problems.append(f"branch {branch.index} {label}")
    return problems


def _check_effect(raw: dict, effect) -> list[str]:
    problems = []
    initializers = list(raw.get("initializers") or [])
    checks = (
        ("entry", bool(raw.get("entry", False)), effect.entry),
        ("name", raw.get("name"), effect.name),
        ("icon", raw.get("icon"), effect.icon),
        ("tags", raw.get("tags") or [], effect.tags),
        ("duration", _float_or_zero(raw.get("duration")), effect.duration),
        ("tick_interval", _float_or_zero(raw.get("tick_interval")), effect.tick_interval),
        ("eff_ignore_alacrity", bool(raw.get("effIgnoreAlacrity", False)), effect.eff_ignore_alacrity),
        ("is_passive", _is_passive_initializer(initializers), effect.is_passive),
        ("stack_charge", raw.get("stack_charge"), effect.stack_charge),
        ("conditions", raw.get("conditions"), effect.conditions),
        ("target_overrides", list(raw.get("target_overrides") or []), effect.target_overrides),
        ("initializers", initializers, effect.initializers),
    )
    for label, expected, actual in checks:
        if actual != expected:
            problems.append(f"effect {effect.number} {label}")

    raw_branches = raw.get("branches") or []
    if len(effect.branches) != len(raw_branches):
        problems.append(f"effect {effect.number} branch count")
    else:
        for raw_branch, branch in zip(raw_branches, effect.branches):
            problems.extend(
                f"effect {effect.number} {item}" for item in _check_branch(raw_branch, branch)
            )
    return problems


def _check_blueprint(data: dict, blueprint: AbilityBlueprint) -> list[str]:
    problems = []
    raw_cost = data.get("energy_cost")
    raw_cd = data.get("cooldown")
    raw_charges = data.get("max_charges")
    checks = (
        ("fqn", data.get("fqn") or "", blueprint.fqn),
        ("name", data.get("name") or "Unknown Ability", blueprint.name),
        ("type", _expected_type(data), blueprint.type),
        ("energy_cost", float(raw_cost) if raw_cost is not None else 0.0, blueprint.energy_cost),
        ("base_gcd", _expected_base_gcd(data), blueprint.base_gcd),
        ("cooldown", float(raw_cd) if raw_cd is not None else 0.0, blueprint.cooldown),
        ("tags", data.get("tags") or [], blueprint.tags),
        ("icon", data.get("icon"), blueprint.icon),
        ("max_charges", int(raw_charges) if raw_charges is not None else None, blueprint.max_charges),
        ("abl_ignore_alacrity", bool(data.get("ablIgnoreAlacrity", False)), blueprint.abl_ignore_alacrity),
        ("triggers_gcd", _expected_triggers_gcd(data), blueprint.triggers_gcd),
        ("activation", data.get("activation"), blueprint.activation),
        ("conditions", data.get("conditions"), blueprint.conditions),
        ("stat_changes", list(data.get("stat_changes") or []), blueprint.stat_changes),
    )
    for label, expected, actual in checks:
        if actual != expected:
            problems.append(label)

    raw_effects = data.get("effects") or []
    if len(blueprint.effects) != len(raw_effects):
        problems.append("effect count")
    else:
        for raw_effect in raw_effects:
            number = raw_effect.get("number")
            effect = blueprint.effects.get(number)
            if effect is None:
                problems.append(f"missing effect {number}")
                continue
            problems.extend(_check_effect(raw_effect, effect))
    return problems


def _discipline_fqns(spec_data: dict) -> list[str]:
    fqns = list(spec_data.get("active_abilities") or [])
    skill_tree = spec_data.get("skill_tree") or {}
    if isinstance(skill_tree, dict):
        for choices in skill_tree.values():
            if not isinstance(choices, dict):
                continue
            for options in choices.values():
                if isinstance(options, list):
                    fqns.extend(options)
    return [fqn for fqn in fqns if isinstance(fqn, str)]


def _missing_fqns(fqns) -> list[str]:
    return sorted(fqn for fqn in fqns if not _parsed_path(fqn).is_file())


class ExtractedLoadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._previous_cwd = Path.cwd()
        os.chdir(ROOT)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._previous_cwd)

    def test_every_parsed_file_round_trips(self):
        self.assertTrue(PARSED_DIR.is_dir(), f"Parsed directory not found: {PARSED_DIR}")
        files = sorted(PARSED_DIR.rglob("*.json"))
        self.assertGreater(len(files), 0, "No parsed JSON files to load")

        mismatches = []
        saw_null_impact = False
        saw_requires_tag = False
        saw_non_numeric_value = False

        for path in files:
            try:
                data = _load_json(path)
                blueprint = AbilityBlueprint.from_file(path)
            except Exception as exc:
                mismatches.append(f"{path.relative_to(ROOT)}: {type(exc).__name__}: {exc}")
                continue
            if not isinstance(data, dict):
                mismatches.append(f"{path.relative_to(ROOT)}: JSON root is not an object")
                continue
            problems = _check_blueprint(data, blueprint)
            if problems:
                mismatches.append(f"{path.relative_to(ROOT)}: {', '.join(problems)}")
            for change in blueprint.stat_changes:
                if not isinstance(change, dict):
                    continue
                if change.get("impact") is None:
                    saw_null_impact = True
                if "requires_tag" in change:
                    saw_requires_tag = True
                if not isinstance(change.get("value"), (int, float)):
                    saw_non_numeric_value = True

        self._assert_no_mismatches(mismatches)
        self.assertTrue(saw_null_impact, "No talent stat change with a null impact was loaded")
        self.assertTrue(saw_requires_tag, "No talent stat change with requires_tag was loaded")
        self.assertTrue(
            saw_non_numeric_value,
            "No talent stat change with a non-numeric value was loaded",
        )

    def test_catalog_fqns_resolve(self):
        disciplines = ROOT / DISCIPLINES_DIR
        self.assertTrue(disciplines.is_dir(), f"Discipline directory not found: {disciplines}")
        discipline_fqns = []
        for path in sorted(disciplines.rglob("*.json")):
            discipline_fqns.extend(_discipline_fqns(_load_json(path)))
        self.assertEqual(_missing_fqns(discipline_fqns), [])

        relics = _load_json(ROOT / RELICS_PATH)
        self.assertIsInstance(relics, list)
        self.assertEqual(_missing_fqns(relics), [])

        adrenals = _load_json(ADRENALS_PATH)
        self.assertIsInstance(adrenals, list)
        self.assertEqual(_missing_fqns(adrenals), [])

        gear = _load_json(ROOT / GEAR_PATH)
        self.assertIsInstance(gear, dict)
        present_gear = [fqn for fqn in gear.values() if _parsed_path(fqn).is_file()]
        self.assertGreater(len(present_gear), 0)

    def test_hatred_run_config_loads(self):
        config = load_run_config(str(RUN_CONFIG_PATH))
        inputs = load_from_run_config(config)
        self.assertEqual(set(inputs.loadout_blueprints), set(selected_fqns_from_config(config)))

        for fqn, blueprint in inputs.loadout_blueprints.items():
            if fqn.startswith("tal."):
                self.assertEqual(blueprint.type, "passive")
                self.assertIsInstance(blueprint.stat_changes, list)

        sim, player, _target = prepare_simulation(
            inputs.rotation_config,
            inputs.stats_config,
            inputs.loadout_blueprints,
            config.dummy_hp,
            inputs.debuff_module,
        )
        self.assertIsNotNone(sim)

        unique_abilities = {id(ability): ability for ability in player.ability_db.values()}
        self.assertGreater(len(unique_abilities), 0)
        for ability in unique_abilities.values():
            self.assertIsInstance(ability, Ability)
            self.assertEqual(ability.conditions, {})
            source = _load_json(ability.blueprint.file_path)
            expected_charges = source.get("max_charges") or 0
            self.assertEqual(ability.max_charges, expected_charges)
            self.assertEqual(ability.triggers_gcd, _expected_triggers_gcd(source))
            self.assertEqual(
                ability.abl_ignore_alacrity,
                bool(source.get("ablIgnoreAlacrity", False)),
            )

    def _assert_no_mismatches(self, mismatches: list[str]) -> None:
        if not mismatches:
            return
        preview = "\n".join(mismatches[:30])
        extra = len(mismatches) - 30
        suffix = f"\n... {extra} more" if extra > 0 else ""
        self.fail(f"{len(mismatches)} parsed files did not round-trip:\n{preview}{suffix}")


if __name__ == "__main__":
    unittest.main()
