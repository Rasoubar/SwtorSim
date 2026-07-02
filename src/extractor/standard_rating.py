from __future__ import annotations

from typing import Any

from extractor.config import STANDARD_RATING_INFO_NODE_ID
from extractor.graph import BucketStore, resolve_fields
from extractor.gom.gom import GomLookup
from extractor.strings import StringResolver


def _float_list_field(resolved_fields: list[dict[str, Any]], name: str) -> list[float] | None:
    for field in resolved_fields:
        if field.get("name") != name:
            continue
        value = field.get("value")
        if not isinstance(value, dict):
            continue
        raw_list = value.get("list")
        if not isinstance(raw_list, list):
            continue
        return [float(item) for item in raw_list]
    return None


def load_standard_rating_table(
    store: BucketStore,
    gom: GomLookup,
    strings: StringResolver,
) -> list[float]:
    """Load the item-rating -> standard-rating lookup from cbtStandardRatingInfo."""
    parsed = store.parse_node(STANDARD_RATING_INFO_NODE_ID, gom)
    resolved = resolve_fields(parsed.fields, store, strings, gom)
    table = _float_list_field(resolved, "cbtStandardRatingInfo")
    if not table:
        raise RuntimeError(
            f"Failed to load cbtStandardRatingInfo from node {STANDARD_RATING_INFO_NODE_ID}"
        )
    return table


def standard_rating_for_item_rating(table: list[float], item_rating: int) -> float:
    if item_rating < 1:
        raise ValueError(f"item_rating must be >= 1, got {item_rating}")
    index = item_rating - 1
    if index >= len(table):
        raise ValueError(
            f"item_rating {item_rating} exceeds standard rating table size {len(table)}"
        )
    return table[index]
