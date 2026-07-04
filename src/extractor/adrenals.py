from __future__ import annotations

import json
from pathlib import Path

from extractor.config import ADRENAL_ABILITY_FQNS
from extractor.graph import BucketStore, discover_adrenal_ability_nodes


def build_adrenals(
    store: BucketStore,
    output_path: Path,
) -> int:
    """Write a sorted list of configured adrenal ability FQNs found in game data."""
    adrenals = discover_adrenal_ability_nodes(store)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(adrenals, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return len(adrenals)
