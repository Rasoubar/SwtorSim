from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from extractor.bkt import fqn_to_relative_path
from extractor.graph import NodeRecord, collect_traversal_refs
from extractor.node import collect_node_refs


def _node_to_json(record: NodeRecord) -> dict[str, Any]:
    return {
        "fqn": record.entry.fqn,
        "id": record.entry.node_id,
        "base_class_id": record.entry.base_class_id,
        "base_class_name": record.entry.base_class_name,
        "fields": record.resolved_fields,
    }


def _collect_edges(records: dict[str, NodeRecord]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for node_id, record in records.items():
        refs = collect_traversal_refs(record.parsed.fields, record.entry.fqn)
        refs |= collect_node_refs(record.resolved_fields)
        for ref_id in refs:
            key = (node_id, ref_id)
            if key in seen:
                continue
            seen.add(key)
            edges.append({"from": node_id, "to": ref_id})
    return edges


def write_node_dump(
    records: dict[str, NodeRecord],
    output_dir: Path,
    roots: list[str],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    index: dict[str, Any] = {
        "roots": roots,
        "nodes": {},
        "edges": _collect_edges(records),
    }

    for node_id, record in records.items():
        rel_path = fqn_to_relative_path(record.entry.fqn)
        dest = output_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        payload = _node_to_json(record)
        dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        index["nodes"][node_id] = {
            "fqn": record.entry.fqn,
            "base_class_id": record.entry.base_class_id,
            "base_class_name": record.entry.base_class_name,
            "path": str(rel_path).replace("\\", "/"),
        }

    index_path = output_dir / "index.json"
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    return index_path
