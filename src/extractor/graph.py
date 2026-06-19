from __future__ import annotations

import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from extractor.bkt import (
    BucketNodeEntry,
    extract_node_payload,
    list_node_entries,
    parse_bucket_names_from_info,
)
from extractor.config import (
    COMBAT_REF_FIELD_IDS,
    COMBAT_FQN_PREFIXES,
    ITEM_ABILITY_FQN_PREFIXES,
    ORIGIN_STORIES,
)
from extractor.gom.gom import GomLookup
from extractor.ids import u64_str
from extractor.node import (
    DOM_ENUM,
    ParsedField,
    ParsedNode,
    collect_node_refs,
    fields_to_dict,
    parse_node_fields,
)
from extractor.stable_ids import TagResolver
from extractor.strings import LOC_RETRIEVER_FIELD_IDS, StringResolver


@dataclass
class NodeIndexEntry:
    node_id: str
    fqn: str
    base_class_id: str
    base_class_name: str
    bucket_path: str
    stream_style: int
    bitset: int
    content_offset: int


@dataclass
class NodeRecord:
    entry: NodeIndexEntry
    parsed: ParsedNode
    raw_fields: list[dict[str, Any]] = field(default_factory=list)
    resolved_fields: list[dict[str, Any]] = field(default_factory=list)


class BucketStore:
    def __init__(self, resources_root: Path):
        self.resources_root = resources_root
        self._bucket_cache: dict[str, bytes] = {}
        self._entries_by_id: dict[str, BucketNodeEntry] = {}
        self.index: dict[str, NodeIndexEntry] = {}
        self.fqn_to_id: dict[str, str] = {}

    def _locate_buckets_info(self) -> Path | None:
        candidates = [
            self.resources_root / "systemgenerated" / "buckets.info",
            self.resources_root / "resources" / "systemgenerated" / "buckets.info",
        ]
        for path in candidates:
            if path.exists():
                return path
        return None

    def _buckets_dir(self, info_path: Path) -> Path:
        return info_path.parent / "buckets"

    def _load_bucket(self, bucket_path: Path) -> bytes:
        key = str(bucket_path)
        if key not in self._bucket_cache:
            self._bucket_cache[key] = bucket_path.read_bytes()
        return self._bucket_cache[key]

    def build_index(self, gom: GomLookup) -> None:
        info_path = self._locate_buckets_info()
        if info_path is None:
            raise FileNotFoundError("buckets.info not found in extracted resources")

        bucket_names = parse_bucket_names_from_info(info_path.read_bytes())
        buckets_dir = self._buckets_dir(info_path)

        for name in bucket_names:
            bucket_path = buckets_dir / name
            if not bucket_path.exists():
                continue
            data = self._load_bucket(bucket_path)
            for entry in list_node_entries(data, bucket_path=str(bucket_path)):
                node_id = u64_str(entry.node_id)
                self._entries_by_id[node_id] = entry
                index_entry = NodeIndexEntry(
                    node_id=node_id,
                    fqn=entry.fqn,
                    base_class_id=u64_str(entry.base_class_id),
                    base_class_name=gom.class_name(entry.base_class_id),
                    bucket_path=str(bucket_path),
                    stream_style=entry.stream_style,
                    bitset=entry.bitset,
                    content_offset=entry.content_offset,
                )
                self.index[node_id] = index_entry
                self.fqn_to_id[entry.fqn] = node_id

    def get_payload(self, node_id: str) -> bytes:
        entry = self._entries_by_id[node_id]
        data = self._load_bucket(Path(entry.bucket_path))
        return extract_node_payload(data, entry)

    def parse_node(self, node_id: str, gom: GomLookup) -> ParsedNode:
        index_entry = self.index[node_id]
        payload = self.get_payload(node_id)
        field_lookup = gom.fields
        return parse_node_fields(payload, index_entry.stream_style, field_lookup)


def discover_apc_roots(
    store: BucketStore,
    origin_stories: tuple[str, ...] = ORIGIN_STORIES,
) -> list[str]:
    """Entry-point APC per origin story: apc.<origin_story>.base."""
    stories = set(origin_stories)
    roots: list[str] = []
    for fqn in store.fqn_to_id:
        parts = fqn.split(".")
        if (
            len(parts) == 3
            and parts[0] == "apc"
            and parts[1] in stories
            and parts[2] == "base"
        ):
            roots.append(fqn)
    return sorted(roots)


def discover_player_apc_nodes(
    store: BucketStore,
    origin_stories: tuple[str, ...] = ORIGIN_STORIES,
) -> list[str]:
    """All player APC nodes under each origin story: apc.<origin_story>.*."""
    stories = set(origin_stories)
    nodes: list[str] = []
    for fqn in store.fqn_to_id:
        parts = fqn.split(".")
        if len(parts) >= 3 and parts[0] == "apc" and parts[1] in stories:
            nodes.append(fqn)
    return sorted(nodes)


def discover_fqn_prefix_nodes(
    store: BucketStore,
    prefixes: tuple[str, ...],
) -> list[str]:
    """All nodes at or below any dot-delimited FQN prefix."""
    nodes: list[str] = []
    for fqn in store.fqn_to_id:
        if any(fqn == prefix or fqn.startswith(f"{prefix}.") for prefix in prefixes):
            nodes.append(fqn)
    return sorted(nodes)


def discover_item_ability_nodes(
    store: BucketStore,
    prefixes: tuple[str, ...] = ITEM_ABILITY_FQN_PREFIXES,
) -> list[str]:
    """Item ability/effect nodes that are not necessarily referenced by player APCs."""
    return discover_fqn_prefix_nodes(store, prefixes)


def _is_combat_fqn(fqn: str) -> bool:
    return any(fqn.startswith(prefix) for prefix in COMBAT_FQN_PREFIXES)


def _resolve_enum_value(
    gom: GomLookup,
    index: int,
    *,
    enum_type_id: str | None = None,
    field_id: str = "",
) -> str:
    resolved_type = enum_type_id or gom.field_enum_ref(field_id)
    return gom.enum_member(resolved_type, index)


def _resolve_value(
    value: Any,
    store: BucketStore,
    strings: StringResolver,
    gom: GomLookup,
    tag_resolver: TagResolver | None = None,
    field_id: str = "",
    enum_type_id: str | None = None,
) -> Any:
    if isinstance(value, dict) and "ref_id" in value:
        ref_id = value["ref_id"]
        target = store.index.get(ref_id)
        return {
            "ref_id": ref_id,
            "fqn": target.fqn if target else None,
            "base_class": target.base_class_name if target else None,
        }

    if field_id in LOC_RETRIEVER_FIELD_IDS and isinstance(value, dict):
        text = strings.resolve_loc_retriever(value)
        if text is not None:
            return {"loc_retriever": value, "resolved_text": text}

    if isinstance(value, dict) and "key_type" in value and "list" in value:
        key_type = value["key_type"]
        value_type = value["value_type"]
        key_enum_ref, val_enum_ref = gom.lookup_list_enum_refs(field_id)
        entries: list[dict[str, Any]] = []
        for entry in value["list"]:
            key = entry["key"]
            val = entry["value"]
            if key_type == DOM_ENUM and isinstance(key, dict) and "index" in key:
                resolved_key: Any = _resolve_enum_value(
                    gom,
                    int(key["index"]),
                    enum_type_id=key_enum_ref or enum_type_id,
                    field_id=field_id,
                )
            else:
                resolved_key = _resolve_value(
                    key,
                    store,
                    strings,
                    gom,
                    tag_resolver,
                    field_id,
                    enum_type_id=key_enum_ref,
                )
            if value_type == DOM_ENUM and isinstance(val, dict) and "index" in val:
                resolved_val: Any = _resolve_enum_value(
                    gom,
                    int(val["index"]),
                    enum_type_id=val_enum_ref,
                    field_id=field_id,
                )
            else:
                resolved_val = _resolve_value(
                    val,
                    store,
                    strings,
                    gom,
                    tag_resolver,
                    field_id,
                    enum_type_id=val_enum_ref,
                )
            entries.append({"key": resolved_key, "value": resolved_val})
        return entries

    if isinstance(value, dict) and "index" in value and len(value) == 1:
        return _resolve_enum_value(
            gom,
            int(value["index"]),
            enum_type_id=enum_type_id,
            field_id=field_id,
        )

    if isinstance(value, dict):
        return {
            k: _resolve_value(
                v,
                store,
                strings,
                gom,
                tag_resolver,
                field_id,
                enum_type_id=enum_type_id,
            )
            for k, v in value.items()
        }

    if isinstance(value, list):
        resolved: list[Any] = []
        for item in value:
            if isinstance(item, dict) and "id" in item and "value" in item:
                child_id = str(item["id"])
                resolved.append(
                    {
                        "id": child_id,
                        "name": gom.field_name(child_id),
                        "type": item.get("type"),
                        "type_name": item.get("type_name"),
                        "value": _resolve_value(
                            item["value"],
                            store,
                            strings,
                            gom,
                            tag_resolver,
                            child_id,
                        ),
                    }
                )
            else:
                resolved.append(
                    _resolve_value(
                        item,
                        store,
                        strings,
                        gom,
                        tag_resolver,
                        field_id,
                        enum_type_id=enum_type_id,
                    )
                )
        return resolved

    if tag_resolver is not None:
        return tag_resolver.resolve(value)

    return value


def resolve_fields(
    fields: list[ParsedField],
    store: BucketStore,
    strings: StringResolver,
    gom: GomLookup,
    tag_resolver: TagResolver | None = None,
) -> list[dict[str, Any]]:
    resolved = []
    for field in fields:
        resolved.append(
            {
                "id": field.id,
                "name": gom.field_name(field.id),
                "type": field.dom_type,
                "type_name": field.dom_type_name,
                "value": _resolve_value(
                    field.value,
                    store,
                    strings,
                    gom,
                    tag_resolver,
                    field.id,
                ),
            }
        )
    return resolved


def collect_traversal_refs(fields: list[ParsedField], fqn: str = "") -> set[str]:
    refs: set[str] = set()
    for field in fields:
        if field.id in COMBAT_REF_FIELD_IDS:
            refs |= collect_node_refs(field.value)
    if _is_combat_fqn(fqn):
        refs |= collect_node_refs(fields_to_dict(fields))
    return refs


def traverse_combat_graph(
    store: BucketStore,
    gom: GomLookup,
    strings: StringResolver,
    roots: list[str] | None = None,
    additional_roots: list[str] | None = None,
    origin_stories: tuple[str, ...] = ORIGIN_STORIES,
    tag_resolver: TagResolver | None = None,
) -> dict[str, NodeRecord]:
    if roots is None:
        roots_fqns = discover_apc_roots(store, origin_stories)
    else:
        roots_fqns = roots

    seed_fqns = discover_player_apc_nodes(store, origin_stories)
    if additional_roots:
        seed_fqns.extend(additional_roots)

    queue: deque[str] = deque()
    for fqn in seed_fqns:
        node_id = store.fqn_to_id.get(fqn)
        if node_id:
            queue.append(node_id)

    root_ids = {
        store.fqn_to_id[fqn]
        for fqn in [*roots_fqns, *(additional_roots or [])]
        if fqn in store.fqn_to_id
    }
    visited: dict[str, NodeRecord] = {}
    skipped: set[str] = set()
    while queue:
        node_id = queue.popleft()
        if node_id in visited or node_id in skipped:
            continue
        if node_id not in store.index:
            continue

        index_entry = store.index[node_id]
        if not _is_combat_fqn(index_entry.fqn) and node_id not in root_ids:
            continue

        try:
            parsed = store.parse_node(node_id, gom)
        except Exception as exc:
            skipped.add(node_id)
            print(
                f"Warning: skipping unparseable node {index_entry.fqn}: {exc}",
                file=sys.stderr,
            )
            continue

        raw_fields = fields_to_dict(parsed.fields)
        resolved = resolve_fields(
            parsed.fields,
            store,
            strings,
            gom,
            tag_resolver,
        )
        visited[node_id] = NodeRecord(
            entry=index_entry,
            parsed=parsed,
            raw_fields=raw_fields,
            resolved_fields=resolved,
        )

        for ref_id in collect_traversal_refs(parsed.fields, index_entry.fqn):
            if (
                ref_id not in visited
                and ref_id not in skipped
                and ref_id in store.index
            ):
                target_fqn = store.index[ref_id].fqn
                if _is_combat_fqn(target_fqn):
                    queue.append(ref_id)

    return visited
