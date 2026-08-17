import json
from pathlib import Path
from collections import defaultdict

SCRIPT_DIR = Path(__file__).resolve().parent
CATALOG_PATH = SCRIPT_DIR / "layer1_catalog.json"
DATA_DIR = SCRIPT_DIR.parent / "src" / "extractor" / "data"


def load_catalog():
    if not CATALOG_PATH.exists():
        print(f"Error: Could not find '{CATALOG_PATH.name}'.")
        return None
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_file_to_format_map(catalog):
    file_map = {}
    for fmt_key, fmt_data in catalog.get("formats", {}).items():
        for rel_path in fmt_data.get("all_files", []):
            file_map[rel_path] = fmt_key
    return file_map


def find_matches_in_node(data, target, search_keys, search_vals, exact_match, current_path=""):
    """
    Recursively searches a JSON node for matching keys and/or values.
    Returns a list of tuples: (match_type, path, matched_content)
    """
    results = []
    target_str = target.lower()

    if isinstance(data, dict):
        for k, v in data.items():
            new_path = f"{current_path}.{k}" if current_path else k
            k_str = str(k).lower()

            # 1. Search Keys
            if search_keys:
                is_key_match = (k_str == target_str) if exact_match else (target_str in k_str)
                if is_key_match:
                    results.append(("KEY", new_path, str(k)))

            # Recurse into dict values
            results.extend(find_matches_in_node(v, target, search_keys, search_vals, exact_match, new_path))

    elif isinstance(data, list):
        for idx, item in enumerate(data):
            array_path = f"{current_path}[{idx}]"
            results.extend(find_matches_in_node(item, target, search_keys, search_vals, exact_match, array_path))

    else:
        # 2. Search Leaf Values (primitives: str, int, bool, float)
        if search_vals:
            v_str = str(data).lower()
            is_val_match = (v_str == target_str) if exact_match else (target_str in v_str)
            if is_val_match:
                results.append(("VALUE", current_path, repr(data)))

    return results


def search_keys_and_values():
    catalog = load_catalog()
    file_to_fmt = build_file_to_format_map(catalog) if catalog else {}

    target = input("\nEnter search term (key or value): ").strip()
    if not target:
        print("Search target cannot be empty.")
        return

    print("\nWhat do you want to search?")
    print(" [1] Keys AND Values (Both)")
    print(" [2] Keys Only")
    print(" [3] Values Only")
    scope_choice = input("Select scope [default: 1]: ").strip() or "1"

    search_keys = scope_choice in ("1", "2")
    search_vals = scope_choice in ("1", "3")

    match_type = input("Exact match only? (y/n) [default: n]: ").strip().lower()
    exact_match = (match_type == 'y')

    print(f"\nScanning all JSON files for '{target}'...")

    files = list(DATA_DIR.rglob("*.json"))
    files = [f for f in files if "extracted" not in f.parts]

    matches_by_file = {}
    matches_by_format = defaultdict(int)
    total_occurrences = 0

    for file_path in files:
        rel_path = str(file_path.relative_to(DATA_DIR))
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            found = find_matches_in_node(data, target, search_keys, search_vals, exact_match)
            if found:
                matches_by_file[rel_path] = found
                total_occurrences += len(found)

                fmt = file_to_fmt.get(rel_path, "Uncataloged")
                matches_by_format[fmt] += 1

        except Exception:
            continue

    # Summary Output
    print("=" * 70)
    print(f"  SEARCH RESULTS FOR: '{target}'")
    print(f"  Matching Files       : {len(matches_by_file)} / {len(files)}")
    print(f"  Total Occurrences    : {total_occurrences}")
    print("=" * 70)

    if not matches_by_file:
        print("No matches found in any file.")
        return

    print("\n--- OCCURRENCES BY FORMAT GROUP ---")
    for fmt_name, count in matches_by_format.items():
        print(f"  • Format [{fmt_name:<20}] : present in {count} file(s)")

    print("\n" + "=" * 70)
    limit_input = input("How many matching files to preview? (e.g., 10, 50, or 'all') [default: 10]: ").strip().lower()
    limit = int(limit_input) if limit_input.isdigit() else len(matches_by_file) if limit_input == 'all' else 10

    print(f"\nDetailed locations in first {min(limit, len(matches_by_file))} file(s):")
    print("-" * 70)

    for idx, (rel_path, occurrences) in enumerate(list(matches_by_file.items())[:limit], 1):
        fmt = file_to_fmt.get(rel_path, "Uncataloged")
        print(f" [{idx}] File   : {rel_path}")
        print(f"      Format : {fmt}")
        print(f"      Matches: {len(occurrences)}")

        for match_kind, match_path, match_content in occurrences[:5]:
            if match_kind == "KEY":
                print(f"        ↳ [KEY MATCH]   Path: '{match_path}'")
            else:
                print(f"        ↳ [VALUE MATCH] Path: '{match_path}' -> Value: {match_content}")

        if len(occurrences) > 5:
            print(f"        ↳ ... and {len(occurrences) - 5} more matches in this file.")
        print("-" * 70)

    if limit < len(matches_by_file):
        print(f"\n... and {len(matches_by_file) - limit} more matching files.")


if __name__ == "__main__":
    search_keys_and_values()