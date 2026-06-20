from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from extractor.graph import NodeRecord


def _field_value(record: NodeRecord, name: str) -> Any:
    for field in record.resolved_fields:
        if field.get("name") == name:
            return field["value"]
    return None


def _lookup_list_to_dict(entries: list[dict[str, Any]] | None) -> dict[str, Any]:
    if not entries:
        return {}
    return {str(entry["key"]): entry["value"] for entry in entries}


def _active_abilities_from_apc(record: NodeRecord | None) -> list[str]:
    if record is None:
        return []
    for field in record.resolved_fields:
        if field.get("name") == "ablPackageActiveAbilitiesList":
            value = field["value"]
            if isinstance(value, dict) and "list" in value:
                return list(value["list"])
    return []


def _union_active_abilities(
    records_by_fqn: dict[str, NodeRecord],
    *apc_fqns: str,
) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for fqn in apc_fqns:
        for ability in _active_abilities_from_apc(records_by_fqn.get(fqn)):
            if ability not in seen:
                seen.add(ability)
                result.append(ability)
    return result


def _build_skill_tree(
    abilities_list: dict[str, str],
    level_to_abilities: list[dict[str, Any]],
) -> dict[str, dict[str, list[str]]]:
    skill_tree: dict[str, dict[str, list[str]]] = {}
    for entry in level_to_abilities:
        level = str(entry["key"])
        indices = entry["value"]
        if not isinstance(indices, dict) or "list" not in indices:
            continue
        level_choices = skill_tree.setdefault(level, {})
        for choice_idx, index in enumerate(indices["list"], start=1):
            ability = abilities_list.get(str(index))
            if ability is None:
                continue
            level_choices.setdefault(str(choice_idx), []).append(ability)
    return skill_tree


def _find_replacement_record(
    records: dict[str, NodeRecord],
) -> NodeRecord | None:
    for record in records.values():
        if record.entry.base_class_name == "ablAbilityReplacementInfo":
            return record
    return None


def _replacements_for_apcs(
    replacement_record: NodeRecord | None,
    apc_fqns: tuple[str, ...],
) -> list[tuple[str, str]]:
    if replacement_record is None:
        return []
    replacement_map = _field_value(replacement_record, "ablAbilityReplacementMap")
    if not replacement_map:
        return []
    apc_set = set(apc_fqns)
    pairs: list[tuple[str, str]] = []
    for entry in replacement_map:
        apc = entry.get("key")
        if apc not in apc_set:
            continue
        value = entry.get("value")
        if not isinstance(value, list):
            continue
        for pair in value:
            new_ability = pair.get("key")
            old_ability = pair.get("value")
            if new_ability and old_ability:
                pairs.append((new_ability, old_ability))
    return pairs


def _find_skill_tree_location(
    skill_tree: dict[str, dict[str, list[str]]],
    ability: str,
) -> tuple[str, str] | None:
    for level, choices in skill_tree.items():
        for choice, abilities in choices.items():
            if ability in abilities:
                return choice, level
    return None


def _apply_replacements(
    active_abilities: list[str],
    skill_tree: dict[str, dict[str, list[str]]],
    replacements: list[tuple[str, str]],
) -> None:
    active_set = set(active_abilities)
    news_replacing: dict[str, set[str]] = {}
    for new_ability, old_ability in replacements:
        news_replacing.setdefault(old_ability, set()).add(new_ability)

    for new_ability, old_ability in replacements:
        if new_ability in active_set:
            if old_ability in active_set:
                active_abilities.remove(old_ability)
                active_set.remove(old_ability)
            continue

        location = _find_skill_tree_location(skill_tree, new_ability)
        if location is None:
            continue

        choice, level = location
        if old_ability in active_set:
            active_abilities.remove(old_ability)
            active_set.remove(old_ability)

        replacers = news_replacing.get(old_ability, set())
        level_choices = skill_tree.setdefault(level, {})
        for other_choice in ("1", "2", "3"):
            if other_choice == choice:
                continue
            other_abilities = level_choices.get(other_choice, [])
            if any(abl in replacers for abl in other_abilities):
                continue
            bucket = level_choices.setdefault(other_choice, [])
            if old_ability not in bucket:
                bucket.append(old_ability)


def _apc_bases_from_discipline_apc(discipline_apc: str) -> tuple[str, str]:
    parts = discipline_apc.split(".")
    if len(parts) < 4 or parts[0] != "apc":
        raise ValueError(f"Invalid discipline APC FQN: {discipline_apc}")
    class_base = f"apc.{parts[1]}.base"
    style_base = f"apc.{parts[1]}.{parts[2]}.base"
    return class_base, style_base


def _discipline_output_path(dis_fqn: str) -> Path:
    parts = [p for p in dis_fqn.split(".") if p]
    if len(parts) < 2 or parts[0] != "dis":
        raise ValueError(f"Invalid discipline FQN: {dis_fqn}")
    return Path(*parts[1:]).with_suffix(".json")


def _build_discipline_payload(
    record: NodeRecord,
    records_by_fqn: dict[str, NodeRecord],
    replacement_record: NodeRecord | None,
) -> dict[str, Any]:
    tab_name = _field_value(record, "disDisciplineTabName")
    package_name = _field_value(record, "disDisciplinePackageName")

    package_ids = _field_value(record, "disDisciplinePackageIds")
    if not isinstance(package_ids, dict) or not package_ids.get("list"):
        raise ValueError(
            f"Missing disDisciplinePackageIds on {record.entry.fqn}"
        )
    discipline_apc = package_ids["list"][0]

    mods_apc = _field_value(record, "disAbilityPackageChooseableAbilities")
    class_base, style_base = _apc_bases_from_discipline_apc(discipline_apc)

    active_abilities = _union_active_abilities(
        records_by_fqn,
        class_base,
        style_base,
        discipline_apc,
    )

    abilities_list = _lookup_list_to_dict(_field_value(record, "disAbilitiesList"))
    level_to_abilities = _field_value(record, "disLevelToAbilities") or []
    skill_tree = _build_skill_tree(abilities_list, level_to_abilities)

    replacements = _replacements_for_apcs(
        replacement_record,
        (class_base, style_base, discipline_apc, mods_apc),
    )
    _apply_replacements(active_abilities, skill_tree, replacements)

    return {
        "tab_name": tab_name,
        "package_name": package_name,
        "active_abilities": active_abilities,
        "skill_tree": skill_tree,
    }


def build_disciplines(
    records: dict[str, NodeRecord],
    output_dir: Path,
) -> int:
    """Build trimmed discipline JSON files from extracted node records."""
    output_dir.mkdir(parents=True, exist_ok=True)
    records_by_fqn = {record.entry.fqn: record for record in records.values()}
    replacement_record = _find_replacement_record(records)

    count = 0
    for record in records.values():
        if not record.entry.fqn.startswith("dis."):
            continue
        payload = _build_discipline_payload(
            record,
            records_by_fqn,
            replacement_record,
        )
        rel_path = _discipline_output_path(record.entry.fqn)
        dest = output_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        count += 1
    return count
