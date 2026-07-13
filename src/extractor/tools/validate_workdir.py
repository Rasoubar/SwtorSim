from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from extractor.config import DATA_DIR, WORK_DIR
from extractor.gom.gom import GomLookup, parse_gom_js
from extractor.gom_cache import ensure_jedipedia_gom_js
from extractor.graph import BucketStore, discover_apc_roots, traverse_combat_graph
from extractor.strings import StringResolver


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate extracted work dir without re-reading .tor archives."
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=WORK_DIR / "resources",
    )
    parser.add_argument("--sample-fqn", type=str, default=None)
    args = parser.parse_args()

    gom_js_path = ensure_jedipedia_gom_js(DATA_DIR)
    gom_names = parse_gom_js(gom_js_path)
    gom = GomLookup(names=gom_names)
    store = BucketStore(args.work_dir)
    store.build_index(gom)
    roots = discover_apc_roots(store)
    print(f"Indexed {len(store.index)} nodes, {len(roots)} APC roots")

    if args.sample_fqn:
        node_id = store.fqn_to_id.get(args.sample_fqn)
        if not node_id:
            print(f"FQN not found: {args.sample_fqn}")
            return 1
        parsed = store.parse_node(node_id, gom)
        print(f"{args.sample_fqn}: {len(parsed.fields)} fields")
        return 0

    strings = StringResolver(args.work_dir)
    records = traverse_combat_graph(store, gom, strings)
    print(f"Combat closure: {len(records)} nodes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
