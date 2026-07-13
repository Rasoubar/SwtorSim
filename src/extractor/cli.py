from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from src.extractor.config import (
    ABILITY_REPLACEMENT_NODE_ID,
    ExtractorConfig,
    ITEM_ABILITY_FQN_PREFIXES,
    ORIGIN_STORIES,
    RELIC_ABILITY_FQN_PREFIX,
    RELIC_SCALES_WITH_ITEM_RATING_SEGMENT,
)
from src.extractor.abilities import build_abilities
from src.extractor.disciplines import build_disciplines
from src.extractor.talents import build_talents
from src.extractor.dump import write_node_dump
from src.extractor.extract import extract_relevant_files
from src.extractor.gear import build_gear_abilities_talents
from src.extractor.relics import build_relics
from src.extractor.gom.gom import GomLookup, parse_gom_js
from src.extractor.gom_cache import ensure_jedipedia_gom_js
from src.extractor.graph import (
    BucketStore,
    discover_apc_base_nodes,
    discover_dis_nodes,
    discover_item_ability_nodes,
    discover_scaled_relic_ability_nodes,
    traverse_combat_graph,
)
from src.extractor.stable_ids import (
    TagResolver,
    ensure_jedipedia_fnv1a64_js,
)
from src.extractor.strings import StringResolver


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract and parse SWTOR combat-relevant GOM nodes to JSON."
    )
    parser.add_argument(
        "--assets",
        type=Path,
        required=True,
        help="Path to SWTOR Assets folder containing .tor archives",
    )
    parser.add_argument(
        "--force-hash-update",
        action="store_true",
        help=(
            "Re-download Jedipedia hash list, gom.js, and fnv1a64.js "
            "even if cached copies exist"
        ),
    )
    parser.add_argument(
        "--pts",
        action="store_true",
        help="Use PTS (_test_) archives instead of live",
    )
    parser.add_argument(
        "--keep-work",
        action="store_true",
        help="Keep intermediate extracted files in data/extract_work",
    )
    return parser


def run_extraction(config: ExtractorConfig) -> Path:
    gom_js_path = ensure_jedipedia_gom_js(
        config.data_dir, force_download=config.force_hash_update
    )
    gom_names = parse_gom_js(gom_js_path)
    fnv1a64_js_path = ensure_jedipedia_fnv1a64_js(
        config.data_dir,
        force_download=config.force_hash_update,
    )
    tag_resolver = TagResolver.from_jedipedia_js(fnv1a64_js_path)

    resources_root = extract_relevant_files(
        config.assets_path,
        config.work_dir,
        config.data_dir,
        force_hash_update=config.force_hash_update,
        pts=config.pts,
    )

    gom = GomLookup.from_resources(resources_root, names=gom_names)
    store = BucketStore(resources_root)
    store.build_index(gom)

    strings = StringResolver(resources_root)
    dis_roots = discover_dis_nodes(store)
    if not dis_roots:
        raise RuntimeError(
            "No discipline root nodes found. Expected dis.* nodes in bucket index."
        )
    item_ability_roots = [
        *discover_item_ability_nodes(store),
        *discover_scaled_relic_ability_nodes(store),
    ]
    base_apc_roots = discover_apc_base_nodes(store, ORIGIN_STORIES)

    records = traverse_combat_graph(
        store,
        gom,
        strings,
        roots=dis_roots,
        additional_roots=[*item_ability_roots, *base_apc_roots],
        additional_node_ids=[ABILITY_REPLACEMENT_NODE_ID],
        tag_resolver=tag_resolver,
    )
    dis_count = sum(1 for r in records.values() if r.entry.fqn.startswith("dis."))
    item_ability_counts = {
        prefix: sum(
            1
            for record in records.values()
            if record.entry.fqn == prefix
            or record.entry.fqn.startswith(f"{prefix}.")
        )
        for prefix in ITEM_ABILITY_FQN_PREFIXES
    }
    scaled_relic_count = sum(
        1
        for record in records.values()
        if record.entry.fqn.startswith(f"{RELIC_ABILITY_FQN_PREFIX}.")
        and f".{RELIC_SCALES_WITH_ITEM_RATING_SEGMENT}" in record.entry.fqn
    )
    index_path = write_node_dump(
        records,
        config.output_dir,
        dis_roots,
        included_fqn_prefixes=ITEM_ABILITY_FQN_PREFIXES,
        flat_node_ids=frozenset({ABILITY_REPLACEMENT_NODE_ID}),
    )

    disciplines_dir = config.data_dir / "disciplines"
    discipline_count = build_disciplines(records, disciplines_dir)

    parsed_dir = config.data_dir / "parsed"
    talent_count = build_talents(records, parsed_dir)
    ability_count = build_abilities(records, parsed_dir)

    gear_path = config.data_dir / "gear_abilities_talents.json"
    gear_count = build_gear_abilities_talents(store, gom, strings, gear_path)

    relics_path = config.data_dir / "relics.json"
    relic_count = build_relics(records, relics_path)

    if not config.keep_work_files and config.work_dir.exists():
        shutil.rmtree(config.work_dir, ignore_errors=True)

    print(f"Wrote {len(records)} nodes to {config.output_dir}")
    print(f"Index: {index_path}")
    print(f"dis.* nodes extracted: {dis_count}")
    print(f"Base APC nodes seeded: {len(base_apc_roots)}")
    print(f"Wrote {discipline_count} discipline files to {disciplines_dir}")
    print(f"Wrote {talent_count} talent files to {parsed_dir / 'tal'}")
    print(f"Wrote {ability_count} ability files to {parsed_dir / 'abl'}")
    print(f"Wrote {gear_count} gear entries to {gear_path}")
    print(f"Wrote {relic_count} relics to {relics_path}")
    print(f"Known tag hashes loaded: {len(tag_resolver.tags_by_hash)}")
    for prefix, count in item_ability_counts.items():
        print(f"{prefix} nodes extracted: {count}")
    print(
        f"{RELIC_ABILITY_FQN_PREFIX}.*.{RELIC_SCALES_WITH_ITEM_RATING_SEGMENT} "
        f"nodes extracted: {scaled_relic_count}"
    )
    return index_path


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = ExtractorConfig(
        assets_path=args.assets,
        force_hash_update=args.force_hash_update,
        pts=args.pts,
        keep_work_files=args.keep_work,
    )

    try:
        run_extraction(config)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
