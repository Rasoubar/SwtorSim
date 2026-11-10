"""Transforms raw GOM talent (`tal.*`) nodes into structured simulator talent blueprints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from extractor.bkt import fqn_to_relative_path
from extractor.graph import NodeRecord

_RANK_STAT_LIST_FIELDS = (
    "talStatsList",
    "talModStatsList",
    "talTalentStatsIfTagExists",
)


def _field_value(record: NodeRecord, name: str) -> Any:
    for field in record.resolved_fields:
        if field.get("name") == name:
            return field["value"]
    return None


def _fields_to_dict(nested_fields: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        str(field["name"]): field["value"]
        for field in nested_fields
        if field.get("name") is not None
    }


def _talent_name(record: NodeRecord) -> str | None:
    loc_text = _field_value(record, "locTextRetrieverMap")
    if isinstance(loc_text, dict):
        resolved = loc_text.get("resolved_text")
        if isinstance(resolved, str):
            return resolved
    return None


def _impact_from_key(key: str | None) -> dict[str, str] | None:
    if not key:
        return None
    if key.startswith("abl."):
        return {"type": "abl", "fqn": key}
    if key.startswith("tag."):
        return {"type": "tag", "fqn": key}
    return None


def _parse_stat_change(stat_fields: list[dict[str, Any]]) -> dict[str, Any]:
    fields = _fields_to_dict(stat_fields)
    enum_type = fields.get("talStatInfoStatEnumType")
    if "talStatInfoStatValue" in fields:
        value: Any = fields["talStatInfoStatValue"]
    elif enum_type is not None:
        value = enum_type
    else:
        raise ValueError(
            f"Stat entry missing value for {fields.get('talStatInfoStat')}: {fields}"
        )
    change: dict[str, Any] = {
        "name": fields["talStatInfoStat"],
        "value": value,
        "stackable": fields.get("talStatInfoStackable", False),
        "impact": _impact_from_key(fields.get("talStatInfoKey")),
    }
    if enum_type is not None:
        change["enum_type"] = enum_type
    requires_tag = fields.get("talTalentStatTag")
    if requires_tag:
        change["requires_tag"] = requires_tag
    return change


def _stat_entries_from_list_field(block: dict[str, Any]) -> list[list[dict[str, Any]]]:
    value = block.get("value")
    if not isinstance(value, dict):
        return []
    entries = value.get("list")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, list)]


def _stat_changes_from_rank_block(rank_fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    blocks_by_name = {
        str(block.get("name")): block
        for block in rank_fields
        if block.get("name") is not None
    }
    for field_name in _RANK_STAT_LIST_FIELDS:
        block = blocks_by_name.get(field_name)
        if block is None:
            continue
        for stat_fields in _stat_entries_from_list_field(block):
            changes.append(_parse_stat_change(stat_fields))
    return changes


def _tags_from_record(record: NodeRecord) -> list[str]:
    tag_list = _field_value(record, "talAbilityTagList")
    if isinstance(tag_list, dict) and "list" in tag_list:
        return [str(tag) for tag in tag_list["list"]]
    if isinstance(tag_list, list):
        return [str(tag) for tag in tag_list]
    return []


def _talent_icon(record: NodeRecord) -> str | None:
    val = _field_value(record, "talTalentIcon")
    if not isinstance(val, str):
        return None
    val = val.strip()
    if not val:
        return None
    lower = val.lower()
    if lower.endswith(".png") or lower.endswith(".dds"):
        val = val[: val.rfind(".")]
        if not val:
            return None
    return f"{val}.png"


def _build_talent_payload(record: NodeRecord) -> dict[str, Any]:
    rank_list = _field_value(record, "talRankList")
    stat_changes: list[dict[str, Any]] = []
    if isinstance(rank_list, dict) and rank_list.get("list"):
        first_rank = rank_list["list"][0]
        if isinstance(first_rank, list):
            stat_changes = _stat_changes_from_rank_block(first_rank)

    payload: dict[str, Any] = {
        "fqn": record.entry.fqn,
        "name": _talent_name(record),
        "tags": _tags_from_record(record),
        "stat_changes": stat_changes,
    }
    icon = _talent_icon(record)
    if icon:
        payload["icon"] = icon
    return payload


def build_talents(
    records: dict[str, NodeRecord],
    output_dir: Path,
    icon_stems: set[str] | None = None,
) -> int:
    """Build trimmed talent JSON files from extracted node records."""
    output_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for record in records.values():
        if not record.entry.fqn.startswith("tal."):
            continue
        if record.entry.base_class_name != "talTalent":
            continue
        payload = _build_talent_payload(record)
        if icon_stems is not None and payload.get("icon"):
            stem = payload["icon"]
            if stem.endswith(".png"):
                stem = stem[:-4]
            icon_stems.add(stem)
        dest = output_dir / fqn_to_relative_path(record.entry.fqn)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        count += 1
    return count
