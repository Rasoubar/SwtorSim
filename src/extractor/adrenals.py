from __future__ import annotations

import json
from pathlib import Path

from extractor.config import ADRENAL_ABILITY_FQNS
from extractor.graph import NodeRecord


def build_adrenals(
    records: dict[str, NodeRecord],
    output_path: Path,
) -> int:
    """Write a sorted list of root adrenal ability FQNs to JSON."""
    adrenal_fqns = frozenset(ADRENAL_ABILITY_FQNS)
    adrenals = sorted(
        record.entry.fqn
        for record in records.values()
        if record.entry.fqn in adrenal_fqns
        and record.entry.base_class_name == "ablAbility"
        and "/" not in record.entry.fqn
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(adrenals, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return len(adrenals)
