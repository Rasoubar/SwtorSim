import json
import os
from collections import defaultdict
from pathlib import Path

# Target directory relative to the parent of 'tools'
RELATIVE_PATH = "data/extractor/parsed/abl/sith_inquisitor"


def extract_key_values(obj, target_key="action_type"):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == target_key:
                yield value
            yield from extract_key_values(value, target_key)
    elif isinstance(obj, list):
        for item in obj:
            yield from extract_key_values(item, target_key)


def find_all_action_types(root_directory):
    val_to_files = defaultdict(list)
    error_files = []

    for root, _, files in os.walk(root_directory):
        for file in files:
            if file.lower().endswith(".json"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        for val in extract_key_values(data, "action_type"):
                            clean_val = str(val) if isinstance(val, (dict, list)) else val
                            val_to_files[clean_val].append(file_path)
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    error_files.append((file_path, str(e)))

    return val_to_files, error_files


if __name__ == "__main__":
    # Base is parent of 'tools'
    base_dir = Path(__file__).resolve().parent.parent
    target_path = (base_dir / RELATIVE_PATH).resolve()

    if not target_path.exists() or not target_path.is_dir():
        print(f"Error: Directory not found: {target_path}")
        exit(1)

    print(f"Scanning: {target_path} ...")
    val_to_files, errors = find_all_action_types(str(target_path))

    # Sort values by total occurrences descending
    sorted_values = sorted(val_to_files.keys(), key=lambda k: len(val_to_files[k]), reverse=True)
    total_occurrences = sum(len(files) for files in val_to_files.values())

    print(f"\nTotal 'action_type' occurrences: {total_occurrences}")
    print(f"Unique 'action_type' values: {len(sorted_values)}")
    print("\nAvailable action_types:")
    for i, val in enumerate(sorted_values, 1):
        unique_file_count = len(set(val_to_files[val]))
        total_in_files = len(val_to_files[val])
        print(f"  [{i}] {val!r} ({total_in_files}x across {unique_file_count} file(s))")

    if errors:
        print(f"\nWarning: Skipped {len(errors)} file(s) due to read/parse errors.")

    # Interactive inspection
    while True:
        choice = input("\nEnter number to inspect files, 'all' for everything, or 'q' to quit: ").strip().lower()

        if choice == "q":
            break

        if choice == "all":
            for val in sorted_values:
                unique_files = sorted(set(val_to_files[val]))
                print(f"\nFiles containing {val!r} ({len(unique_files)} file(s)):")
                for f in unique_files:
                    count_in_file = val_to_files[val].count(f)
                    print(f"  - {f} ({count_in_file}x)")
            continue

        if choice.isdigit() and 1 <= int(choice) <= len(sorted_values):
            val = sorted_values[int(choice) - 1]
            unique_files = sorted(set(val_to_files[val]))
            print(f"\nFiles containing {val!r} ({len(unique_files)} file(s)):")
            for f in unique_files:
                count_in_file = val_to_files[val].count(f)
                print(f"  - {f} ({count_in_file}x)")
        else:
            print("Invalid selection.")