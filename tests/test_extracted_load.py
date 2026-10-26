import json
import os
import sys
import unittest
from pathlib import Path
from typing import Any

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
RUN_CONFIG_PATH = (
    ROOT / "data" / "run_config" / "hatred_14gcd.json"
    if (ROOT / "data" / "run_config" / "hatred_14gcd.json").exists()
    else ROOT / "data" / "run_config" / "first_test.json"
)

_SENTINEL = object()


def _parsed_path(fqn: str) -> Path:
    return PARSED_DIR / Path(*fqn.split(".")).with_suffix(".json")


def _load_json(path: Path) -> Any:
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


def _float_or_zero(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def _is_passive_initializer(initializers: list | None) -> bool:
    return any(
        init.get("initializer_type") == "eff_initializer__set_passive"
        and init.get("bools", {}).get("is_passive", False)
        for init in initializers or []
        if isinstance(init, dict)
    )


def _compare_attrs(target: Any, checks: tuple[tuple[str, Any, str], ...], prefix: str = "") -> list[str]:
    """Safely compares expected values against object attributes without crashing on missing attrs."""
    problems = []
    full_prefix = f"{prefix} " if prefix else ""
    for label, expected, attr_name in checks:
        if not hasattr(target, attr_name):
            problems.append(f"{full_prefix}{label} (missing attribute '{attr_name}')")
            continue
        actual = getattr(target, attr_name)
        if actual != expected:
            problems.append(f"{full_prefix}{label} (expected={expected!r}, actual={actual!r})")
    return problems


def _check_branch(raw: dict, branch: Any) -> list[str]:
    b_idx = getattr(branch, "index", raw.get("index", "?"))
    checks = (
        ("index", raw.get("index", 0), "index"),
        ("triggers", raw.get("triggers", []), "triggers"),
        ("conditions", raw.get("conditions"), "conditions"),
        ("actions", raw.get("actions", []), "actions"),
        ("target_overrides", raw.get("target_overrides", []), "target_overrides"),
        ("run_if_none_ran", raw.get("run_if_none_ran", []), "run_if_none_ran"),
        (
            "is_attack",
            bool(raw["is_attack"])
            if "is_attack" in raw
            else any(
                isinstance(a, dict) and a.get("action_type") == "damage"
                for a in raw.get("actions", [])
            ),
            "is_attack",
        ),
    )
    return _compare_attrs(branch, checks, prefix=f"branch {b_idx}")


def _check_effect(raw: dict, effect: Any) -> list[str]:
    eff_num = getattr(effect, "number", raw.get("number", "?"))
    initializers = list(raw.get("initializers") or [])
    checks = (
        ("entry", bool(raw.get("entry", False)), "entry"),
        ("name", raw.get("name"), "name"),
        ("icon", raw.get("icon"), "icon"),
        ("tags", raw.get("tags") or [], "tags"),
        ("duration", _float_or_zero(raw.get("duration")), "duration"),
        ("tick_interval", _float_or_zero(raw.get("tick_interval")), "tick_interval"),
        ("eff_ignore_alacrity", bool(raw.get("effIgnoreAlacrity", False)), "eff_ignore_alacrity"),
        ("is_passive", _is_passive_initializer(initializers), "is_passive"),
        ("stack_charge", raw.get("stack_charge"), "stack_charge"),
        ("conditions", raw.get("conditions"), "conditions"),
        ("target_overrides", list(raw.get("target_overrides") or []), "target_overrides"),
        ("initializers", initializers, "initializers"),
    )
    problems = _compare_attrs(effect, checks, prefix=f"effect {eff_num}")

    raw_branches = raw.get("branches") or []
    actual_branches = getattr(effect, "branches", [])
    if len(actual_branches) != len(raw_branches):
        problems.append(
            f"effect {eff_num} branch count (expected={len(raw_branches)}, actual={len(actual_branches)})"
        )
    for raw_branch, branch in zip(raw_branches, actual_branches):
        problems.extend(
            f"effect {eff_num} {item}" for item in _check_branch(raw_branch, branch)
        )
    return problems


def _check_blueprint(data: dict, blueprint: AbilityBlueprint, expected_path: Path | None = None) -> list[str]:
    raw_cost = data.get("energy_cost")
    raw_cd = data.get("cooldown")
    raw_charges = data.get("max_charges")
    checks = [
        ("fqn", data.get("fqn") or "", "fqn"),
        ("name", data.get("name") or "Unknown Ability", "name"),
        ("type", _expected_type(data), "type"),
        ("energy_cost", float(raw_cost) if raw_cost is not None else 0.0, "energy_cost"),
        ("base_gcd", _expected_base_gcd(data), "base_gcd"),
        ("cooldown", float(raw_cd) if raw_cd is not None else 0.0, "cooldown"),
        ("tags", data.get("tags") or [], "tags"),
        ("icon", data.get("icon"), "icon"),
        ("max_charges", int(raw_charges) if raw_charges is not None else None, "max_charges"),
        ("abl_ignore_alacrity", bool(data.get("ablIgnoreAlacrity", False)), "abl_ignore_alacrity"),
        ("triggers_gcd", _expected_triggers_gcd(data), "triggers_gcd"),
        ("activation", data.get("activation"), "activation"),
        ("conditions", data.get("conditions"), "conditions"),
        ("stat_changes", list(data.get("stat_changes") or []), "stat_changes"),
    ]
    if expected_path is not None:
        checks.append(("file_path", expected_path, "file_path"))

    problems = _compare_attrs(blueprint, tuple(checks))

    raw_effects = data.get("effects") or []
    actual_effects = getattr(blueprint, "effects", {})
    if len(actual_effects) != len(raw_effects):
        expected_nums = [e.get("number") for e in raw_effects]
        actual_nums = list(actual_effects.keys())
        problems.append(f"effect count (expected={expected_nums}, actual={actual_nums})")

    for raw_effect in raw_effects:
        number = raw_effect.get("number")
        effect = actual_effects.get(number)
        if effect is None:
            problems.append(f"missing effect {number}")
            continue
        problems.extend(_check_effect(raw_effect, effect))
    return problems


def _discipline_fqns(spec_data: dict) -> list[str]:
    fqns = list(spec_data.get("active_abilities") or [])
    fqns.extend(spec_data.get("passive_abilities") or [])
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
    return sorted({fqn for fqn in fqns if not _parsed_path(fqn).is_file()})


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
            rel_path = path.relative_to(ROOT)
            try:
                data = _load_json(path)
                blueprint = AbilityBlueprint.from_file(path)
                if not isinstance(data, dict):
                    mismatches.append(f"{rel_path}: JSON root is not an object")
                    continue
                problems = _check_blueprint(data, blueprint, expected_path=path)
            except Exception as exc:
                mismatches.append(f"{rel_path}: {type(exc).__name__}: {exc}")
                continue

            if problems:
                mismatches.append(f"{rel_path}: {', '.join(problems)}")

            for change in getattr(blueprint, "stat_changes", []):
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

        for path in sorted(disciplines.rglob("*.json")):
            with self.subTest(catalog="discipline", file=path.name):
                fqns = _discipline_fqns(_load_json(path))
                self.assertEqual(
                    _missing_fqns(fqns),
                    [],
                    f"Missing FQNs in discipline file {path.name}",
                )

        with self.subTest(catalog="relics"):
            relics = _load_json(ROOT / RELICS_PATH)
            self.assertIsInstance(relics, list)
            self.assertEqual(_missing_fqns(relics), [], "Missing FQNs in relics catalog")

        with self.subTest(catalog="adrenals"):
            adrenals = _load_json(ADRENALS_PATH)
            self.assertIsInstance(adrenals, list)
            self.assertEqual(_missing_fqns(adrenals), [], "Missing FQNs in adrenals catalog")

        with self.subTest(catalog="gear"):
            gear = _load_json(ROOT / GEAR_PATH)
            self.assertIsInstance(gear, dict)
            present_gear = [fqn for fqn in gear.values() if _parsed_path(fqn).is_file()]
            self.assertGreater(len(present_gear), 0, "No valid gear FQNs resolved on disk")

    def test_hatred_run_config_loads(self):
        config = load_run_config(str(RUN_CONFIG_PATH))
        inputs = load_from_run_config(config)
        self.assertEqual(set(inputs.loadout_blueprints), set(selected_fqns_from_config(config)))

        for fqn, blueprint in inputs.loadout_blueprints.items():
            if fqn.startswith("tal."):
                with self.subTest(talent_fqn=fqn):
                    raw_data = _load_json(_parsed_path(fqn))
                    self.assertEqual(
                        blueprint.type,
                        "passive",
                        f"Talent '{fqn}' resolved to type={blueprint.type!r} "
                        f"(raw JSON 'type'={raw_data.get('type')!r})",
                    )
                    self.assertIsInstance(blueprint.stat_changes, list, f"Failed on {fqn}")

        sim, player, target = prepare_simulation(
            inputs.rotation_config,
            inputs.stats_config,
            inputs.loadout_blueprints,
            config.dummy_hp,
            inputs.debuff_module,
        )
        self.assertIsNotNone(sim)
        self.assertIsNotNone(target)

        unique_abilities = {id(ability): ability for ability in player.ability_db.values()}
        self.assertGreater(len(unique_abilities), 0)
        for ability in unique_abilities.values():
            fqn = getattr(ability.blueprint, "fqn", "unknown_fqn")
            with self.subTest(ability_fqn=fqn):
                self.assertIsInstance(ability, Ability)
                source = _load_json(ability.blueprint.file_path)
                self.assertEqual(ability.conditions, {})
                expected_charges = source.get("max_charges")
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