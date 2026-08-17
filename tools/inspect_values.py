import json
from pathlib import Path
from collections import Counter, defaultdict

SCRIPT_DIR = Path(__file__).resolve().parent
CATALOG_PATH = SCRIPT_DIR / "layer1_catalog.json"
DATA_DIR = SCRIPT_DIR.parent / "src" / "extractor" / "data"


def load_catalog():
    if not CATALOG_PATH.exists():
        print(f"Error: Could not find '{CATALOG_PATH.name}'.")
        return None
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_node_values(data, key_path):
    curr = [data]
    for bit in key_path:
        next_level = []
        for item in curr:
            if isinstance(item, dict) and bit in item:
                val = item[bit]
                if isinstance(val, list):
                    next_level.extend(val)
                else:
                    next_level.append(val)
            elif isinstance(item, list):
                for sub in item:
                    if isinstance(sub, dict) and bit in sub:
                        val = sub[bit]
                        if isinstance(val, list):
                            next_level.extend(val)
                        else:
                            next_level.append(val)
        curr = next_level
        if not curr:
            break
    return curr


def flatten_dict_values(obj, prefix=""):
    items = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_prefix = f"{prefix}.{k}" if prefix else str(k)
            items.extend(flatten_dict_values(v, new_prefix))
    elif isinstance(obj, list):
        for elem in obj:
            items.extend(flatten_dict_values(elem, prefix))
    else:
        items.append((prefix, obj))
    return items


def inspect_key_values():
    catalog = load_catalog()
    if not catalog:
        return

    formats = catalog.get("formats", {})

    print("\n--- SELECT A FORMAT TO INSPECT VALUES ---")
    menu_map = {}
    for idx, (fmt_key, fmt_data) in enumerate(formats.items(), 1):
        menu_map[str(idx)] = fmt_key
        print(f" [{idx}] {fmt_key:<20} ({fmt_data['file_count']} files)")

    choice = input("\nSelect format number/name: ").strip()
    target_fmt_key = menu_map.get(choice) or (choice if choice in formats else None)

    if not target_fmt_key:
        print("Invalid selection.")
        return

    fmt_data = formats[target_fmt_key]
    file_list = fmt_data.get("all_files", [])
    sub_paths = fmt_data.get("sub_paths", {})

    if sub_paths:
        print(f"\nSub-variants available for {target_fmt_key}:")
        print(" [0] Entire Top-Level Format (All files)")
        sub_map = {"0": file_list}
        sub_counter = 1

        for path_name, variants in sub_paths.items():
            for v_name, v_data in variants.items():
                sub_map[str(sub_counter)] = v_data.get("all_files", [])
                print(f" [{sub_counter}] Sub-variant: '{path_name} -> {v_name}' ({v_data['file_count']} files)")
                sub_counter += 1

        sub_choice = input("\nSelect target group [default 0]: ").strip() or "0"
        file_list = sub_map.get(sub_choice, file_list)

    key_path_str = input("\nEnter target key path to inspect (e.g. 'stats', 'player.equipment'): ").strip()
    if not key_path_str:
        return

    # Ask the user for the display limit
    limit_input = input(
        "How many unique values to display per key? (e.g., 15, 50, or 'all') [default: 15]: ").strip().lower()

    key_path = [k.strip() for k in key_path_str.split(".") if k.strip()]

    field_value_counts = defaultdict(Counter)
    missing_count = 0
    total_samples = 0

    print(f"\nScanning {len(file_list)} files for values at path '{key_path_str}'...\n")

    for rel_path in file_list:
        full_path = DATA_DIR / rel_path
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            nodes = get_node_values(data, key_path)
            if not nodes:
                missing_count += 1
                continue

            for node in nodes:
                total_samples += 1
                if isinstance(node, (dict, list)):
                    pairs = flatten_dict_values(node)
                    for sub_key, val in pairs:
                        field_value_counts[sub_key][repr(val)] += 1
                else:
                    field_value_counts["(direct value)"][repr(node)] += 1

        except Exception:
            missing_count += 1

    print("=" * 70)
    print(f"  DEEP VALUE ANALYSIS FOR KEY PATH: '{key_path_str}'")
    print(f"  Processed Node Samples : {total_samples}")
    print(f"  Sub-Keys Discovered    : {len(field_value_counts)}")
    if missing_count > 0:
        print(f"  Missing Path In        : {missing_count} files")
    print("=" * 70)

    if not field_value_counts:
        print("No values or keys found at this path.")
        return

    for field_name, counts in field_value_counts.items():
        total_unique = len(counts)
        field_label = f"Sub-Key: .{field_name}" if field_name != "(direct value)" else "Direct Values"
        print(f"\n>>> {field_label} ({total_unique} unique values)")
        print(f"{'FREQUENCY':<12} | {'VALUE'}")
        print("-" * 70)

        # Determine limit based on input
        if limit_input == 'all':
            show_limit = total_unique
        elif limit_input.isdigit():
            show_limit = int(limit_input)
        else:
            show_limit = 15

        for val, count in counts.most_common(show_limit):
            print(f" {count:<11} | {val}")

        if show_limit < total_unique:
            print(f" ... and {total_unique - show_limit} more unique values.")
        print("-" * 70)

    print("=" * 70)


if __name__ == "__main__":
    inspect_key_values()