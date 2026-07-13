from __future__ import annotations

import json
from pathlib import Path

from extractor.config import (
    RELIC_ABILITY_FQN_PREFIX,
    RELIC_SCALES_WITH_ITEM_RATING_SEGMENT,
)
from extractor.graph import NodeRecord


def build_relics(
    records: dict[str, NodeRecord],
    output_path: Path,
) -> int:
    """Write a sorted list of root relic ability FQNs to JSON."""
    marker = f".{RELIC_SCALES_WITH_ITEM_RATING_SEGMENT}"
    relics = sorted(
        record.entry.fqn
        for record in records.values()
        if record.entry.fqn.startswith(f"{RELIC_ABILITY_FQN_PREFIX}.")
        and marker in record.entry.fqn
        and record.entry.base_class_name == "ablAbility"
        and "/" not in record.entry.fqn
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(relics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return len(relics)
