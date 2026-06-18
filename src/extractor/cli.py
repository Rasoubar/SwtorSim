from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from extractor.config import (
    ExtractorConfig,
    ITEM_ABILITY_FQN_PREFIXES,
    ORIGIN_STORIES,
)
from extractor.dump import write_node_dump
from extractor.extract import extract_relevant_files
from extractor.gom.gom import GomLookup, parse_gom_js
from extractor.gom_cache import ensure_jedipedia_gom_js
from extractor.graph import (
    BucketStore,
    discover_apc_roots,
    discover_item_ability_nodes,
    traverse_combat_graph,
)
from extractor.strings import StringResolver


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
        help="Re-download Jedipedia hash list and gom.js even if cached copies exist",
    )
    parser.add_argument(
        "--origin-story",
        action="append",
        dest="origin_stories",
        choices=list(ORIGIN_STORIES),
        help="Limit to specific origin story (repeatable)",
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
    roots = discover_apc_roots(store, config.origin_stories)
    if not roots:
        raise RuntimeError(
            "No APC root nodes found. Expected apc.<origin_story>.<class> nodes."
        )
    item_ability_roots = discover_item_ability_nodes(store)

    records = traverse_combat_graph(
        store,
        gom,
        strings,
        roots=roots,
        additional_roots=item_ability_roots,
        origin_stories=config.origin_stories,
    )
    apc_count = sum(1 for r in records.values() if r.entry.fqn.startswith("apc."))
    item_ability_counts = {
        prefix: sum(
            1
            for record in records.values()
            if record.entry.fqn == prefix
            or record.entry.fqn.startswith(f"{prefix}.")
        )
        for prefix in ITEM_ABILITY_FQN_PREFIXES
    }
    index_path = write_node_dump(
        records,
        config.output_dir,
        roots,
        included_fqn_prefixes=ITEM_ABILITY_FQN_PREFIXES,
    )

    if not config.keep_work_files and config.work_dir.exists():
        shutil.rmtree(config.work_dir, ignore_errors=True)

    print(f"Wrote {len(records)} nodes to {config.output_dir}")
    print(f"Index: {index_path}")
    print(f"APC nodes extracted: {apc_count}")
    for prefix, count in item_ability_counts.items():
        print(f"{prefix} nodes extracted: {count}")
    return index_path


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    origin_stories = tuple(args.origin_stories) if args.origin_stories else ORIGIN_STORIES
    config = ExtractorConfig(
        assets_path=args.assets,
        origin_stories=origin_stories,
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
