import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

import modifiers
from modifiers import Modifier, load_stat_map


def find_project_root() -> Path:
    """Finds the SwtorSim root folder regardless of where the script is executed from."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "data").exists():
            return parent
    return current


PROJECT_ROOT = find_project_root()
CSV_PATH = PROJECT_ROOT / "data" / "modifier_id_mapping.csv"

SCAN_TARGETS = [
    PROJECT_ROOT / "data" / "extractor" / "parsed" / "abl" / "sith_inquisitor",
    PROJECT_ROOT / "data" / "extractor" / "parsed" / "tal" / "sith_inquisitor",
]


def initialize_stat_map(csv_path: Path) -> None:
    """Explicitly populates STAT_ID_MAP in modifiers module from the project CSV."""
    if not csv_path.is_file():
        print(f"ERROR: Mapping file not found at {csv_path}")
        return

    load_stat_map(csv_path)
    print(
        f"Loaded {len(modifiers.STAT_ID_MAP)} stat mappings from: {csv_path.relative_to(PROJECT_ROOT)}"
    )


class SithInquisitorModifierTester:

    def __init__(self, target_dirs: List[Path]):
        self.target_dirs = target_dirs
        self.total_files = 0
        self.created_by_type: Dict[str, List[Tuple[Path, str, Modifier]]] = (
            defaultdict(list)
        )
        self.source_counts = Counter()
        self.unmapped_stats = set()
        self.errors = []
        self.stat_distribution = Counter()
        self.scoped_count = 0
        self.global_count = 0

    def run(self) -> None:
        json_files: List[Path] = []
        for target in self.target_dirs:
            if not target.exists():
                print(f"Directory not found (skipping): {target}")
                continue
            matched = list(target.rglob("*.json"))
            print(f"Found {len(matched)} JSON files in: {target}")
            json_files.extend(matched)

        self.total_files = len(json_files)
        print(f"\nTotal files queued for scanning: {self.total_files}")

        for file_path in json_files:
            self._scan_file(file_path)

        self._print_objects_by_type()
        self._print_report()

    def _scan_file(self, file_path: Path) -> None:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self.errors.append((str(file_path), "JSON Load Error", str(e)))
            return

        if not isinstance(data, dict):
            return

        # 1. Talent-level stat changes (supports both 'name' and 'stat' keys)
        stat_changes = data.get("stat_changes")
        if isinstance(stat_changes, list):
            for idx, change in enumerate(stat_changes):
                self._test_node(
                    file_path=file_path,
                    node_desc=f"stat_changes[{idx}]",
                    source_type="stat_change",
                    payload=change,
                    factory=Modifier.from_stat_change,
                )

        # 2. Branch actions inside effects
        effects = data.get("effects")
        if isinstance(effects, list):
            for e_idx, effect in enumerate(effects):
                if not isinstance(effect, dict):
                    continue
                for b_idx, branch in enumerate(effect.get("branches", [])):
                    if not isinstance(branch, dict):
                        continue
                    for a_idx, action in enumerate(branch.get("actions", [])):
                        if not isinstance(action, dict):
                            continue
                        action_type = action.get("action_type")

                        if action_type == "modify_stat":
                            self._test_node(
                                file_path=file_path,
                                node_desc=f"effect[{e_idx}].branch[{b_idx}].action[{a_idx}]",
                                source_type="modify_stat",
                                payload=action,
                                factory=Modifier.from_modify_stat,
                            )
                        elif action_type == "modify_meta_stat":
                            self._test_node(
                                file_path=file_path,
                                node_desc=f"effect[{e_idx}].branch[{b_idx}].action[{a_idx}]",
                                source_type="modify_meta_stat",
                                payload=action,
                                factory=Modifier.from_modify_meta_stat,
                            )

    def _test_node(
        self,
        file_path: Path,
        node_desc: str,
        source_type: str,
        payload: Dict[str, Any],
        factory,
    ) -> None:
        try:
            mod = factory(payload)

            assert isinstance(
                mod.stat, str
            ), f"Stat must be str, got {type(mod.stat)}"
            assert isinstance(
                mod.value, float
            ), f"Value must be float, got {type(mod.value)}"
            assert isinstance(
                mod.targets, frozenset
            ), f"Targets must be frozenset, got {type(mod.targets)}"

            if mod.stat.isdigit():
                self.unmapped_stats.add(int(mod.stat))

            self.created_by_type[source_type].append(
                (file_path, node_desc, mod)
            )
            self.source_counts[source_type] += 1
            self.stat_distribution[mod.stat] += 1

            if mod.targets:
                self.scoped_count += 1
            else:
                self.global_count += 1

        except Exception as e:
            self.errors.append(
                (
                    f"{file_path.name} :: {node_desc}",
                    source_type,
                    f"{e}\nPayload: {payload}",
                )
            )

    def _print_objects_by_type(self) -> None:
        total_objects = sum(
            len(items) for items in self.created_by_type.values()
        )
        print("\n" + "=" * 90)
        print(f"GENERATED MODIFIER OBJECTS BY TYPE ({total_objects} total)")
        print("=" * 90)

        for mod_type, items in sorted(self.created_by_type.items()):
            print(f"\n{'#' * 90}")
            print(f"MODIFIER TYPE: {mod_type.upper()} ({len(items)} instances)")
            print(f"{'#' * 90}")
            for file_path, node_desc, mod in items:
                print(f"[{file_path.name} :: {node_desc}]")
                print(f"  {mod}")

    def _print_report(self) -> None:
        total_mods = sum(len(items) for items in self.created_by_type.values())
        print("\n" + "=" * 60)
        print("SITH INQUISITOR MODIFIER TEST REPORT")
        print("=" * 60)
        print(f"Files Processed:       {self.total_files}")
        print(f"Total Modifiers Built: {total_mods}")
        print(f"Global Modifiers:      {self.global_count}")
        print(f"Scoped Modifiers:      {self.scoped_count}")
        print(f"Total Parse Errors:    {len(self.errors)}")
        print("-" * 60)

        print("Action Types Parsed:")
        for source, count in self.source_counts.items():
            print(f"  - {source:18}: {count}")

        if self.unmapped_stats:
            print("\n" + "!" * 60)
            print(
                f"WARNING: {len(self.unmapped_stats)} UNMAPPED STAT IDs ENCOUNTERED"
            )
            print(f"IDs: {sorted(self.unmapped_stats)}")
            print("!" * 60)

        if self.errors:
            print("\n" + "!" * 60)
            print(f"FAILURES ({len(self.errors)}):")
            for loc, src, err in self.errors[:15]:
                print(f"Location: {loc}\nType: {src}\nDetail: {err}\n" + "-" * 40)
            if len(self.errors) > 15:
                print(f"... and {len(self.errors) - 15} more.")
            print("!" * 60)
        else:
            print("\nALL INQUISITOR FILES PARSED SUCCESSFULLY WITH ZERO ERRORS.")


if __name__ == "__main__":
    initialize_stat_map(CSV_PATH)
    tester = SithInquisitorModifierTester(SCAN_TARGETS)
    tester.run()