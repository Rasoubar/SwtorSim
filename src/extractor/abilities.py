from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from extractor.bkt import fqn_to_relative_path
from extractor.graph import NodeRecord


def _field_value(record: NodeRecord, name: str) -> Any:
    for field in record.resolved_fields:
        if field.get("name") == name:
            return field["value"]
    return None


def _ability_name(record: NodeRecord) -> str | None:
    loc_text = _field_value(record, "locTextRetrieverMap")
    if isinstance(loc_text, dict):
        resolved = loc_text.get("resolved_text")
        if isinstance(resolved, str):
            return resolved
    return None


def _cooldown(record: NodeRecord) -> float | None:
    value = _field_value(record, "ablCooldownTime")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _effect_ids(record: NodeRecord) -> list[str]:
    effect_ids = _field_value(record, "ablEffectIDs")
    if isinstance(effect_ids, dict) and isinstance(effect_ids.get("list"), list):
        return [str(fqn) for fqn in effect_ids["list"]]
    return []


def _build_ability_payload(record: NodeRecord) -> dict[str, Any]:
    return {
        "fqn": record.entry.fqn,
        "name": _ability_name(record),
        "cooldown": _cooldown(record),
    }


def build_abilities(
    records: dict[str, NodeRecord],
    output_dir: Path,
) -> int:
    """Build trimmed root-ability JSON files from extracted node records."""
    output_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for record in records.values():
        if not record.entry.fqn.startswith("abl."):
            continue
        if record.entry.base_class_name != "ablAbility":
            continue
        payload = _build_ability_payload(record)
        dest = output_dir / fqn_to_relative_path(record.entry.fqn)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        count += 1
    return count
