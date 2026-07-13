from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.extractor.config import ITEM_FQN_PREFIXES
from src.extractor.graph import BucketStore, discover_fqn_prefix_nodes, resolve_fields
from src.extractor.gom.gom import GomLookup
from src.extractor.node import ParsedField
from src.extractor.strings import StringResolver

ITM_EQUIP_ABILITY_FIELD = "itmEquipAbility"
ILVL_SEGMENT = re.compile(r"^ilvl_\d+$")


def _field_value(fields: list[dict[str, Any]], name: str) -> Any:
    for field in fields:
        if field.get("name") == name:
            return field["value"]
    return None


def _item_name(strings: StringResolver, fields: list[ParsedField]) -> str | None:
    for field in fields:
        if field.name == "locTextRetrieverMap":
            return strings.resolve_loc_retriever(field.value)
    return None


def _ability_fqn_from_item_fqn(item_fqn: str) -> str:
    parts = [part for part in item_fqn.split(".") if not ILVL_SEGMENT.match(part)]
    return "abl." + ".".join(parts)


def _equip_ability_fqn(fields: list[dict[str, Any]], item_fqn: str) -> str | None:
    value = _field_value(fields, ITM_EQUIP_ABILITY_FIELD)
    if isinstance(value, str) and (
        value.startswith("abl.") or value.startswith("tal.")
    ):
        return value
    return _ability_fqn_from_item_fqn(item_fqn)


def build_gear_abilities_talents(
    store: BucketStore,
    gom: GomLookup,
    strings: StringResolver,
    output_path: Path,
) -> int:
    """Build a flat item-name -> ability/talent FQN lookup for gear implants."""
    lookup: dict[str, str] = {}
    seen_abilities: set[str] = set()

    for fqn in discover_fqn_prefix_nodes(store, ITEM_FQN_PREFIXES):
        node_id = store.fqn_to_id.get(fqn)
        if node_id is None:
            continue
        index_entry = store.index[node_id]
        if index_entry.base_class_name != "itmItem":
            continue

        parsed = store.parse_node(node_id, gom)
        resolved = resolve_fields(parsed.fields, store, strings, gom)

        ability_fqn = _equip_ability_fqn(resolved, fqn)
        if ability_fqn is None or ability_fqn in seen_abilities:
            continue

        name = _item_name(strings, parsed.fields)
        if not name:
            continue

        seen_abilities.add(ability_fqn)
        lookup[name] = ability_fqn

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dict(sorted(lookup.items())), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return len(lookup)
