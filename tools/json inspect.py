import json
from pathlib import Path
from collections import defaultdict

# Path setup
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "src" / "extractor" / "data"
OUTPUT_CATALOG = SCRIPT_DIR / "layer1_catalog.json"


def get_first_layer_structure(data):
    if isinstance(data, dict):
        return ("object", tuple(sorted(data.keys())))
    elif isinstance(data, list):
        return ("array", f"list_of_{len(data)}_items")
    else:
        return ("primitive", type(data).__name__)


def scan_and_save():
    layer_1_groups = defaultdict(list)
    corrupt_files = []
    skipped_count = 0

    files = list(DATA_DIR.rglob("*.json"))
    print(f"Found {len(files)} total files in '{DATA_DIR.name}'. Filtering...")

    for file_path in files:
        # Check if "extracted" is anywhere in the folder path or file name
        if "extracted" in file_path.parts or file_path.name == "extracted":
            skipped_count += 1
            continue

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            sig = get_first_layer_structure(data)
            layer_1_groups[sig].append(str(file_path.relative_to(DATA_DIR)))
        except Exception as e:
            corrupt_files.append((str(file_path.relative_to(DATA_DIR)), str(e)))

    print(f"Skipped {skipped_count} files/folders matching 'extracted'.")
    print(f"Processing {len(files) - skipped_count} valid files...\n")

    # Build structured catalog
    catalog = {
        "summary": {
            "total_scanned_files": len(files) - skipped_count,
            "skipped_extracted_files": skipped_count,
            "distinct_formats": len(layer_1_groups),
            "corrupt_files_count": len(corrupt_files)
        },
        "formats": {}
    }

    for idx, (sig, file_list) in enumerate(layer_1_groups.items(), 1):
        struct_type, details = sig
        format_key = f"format_{idx:02d}"  # format_01, format_02, etc.

        catalog["formats"][format_key] = {
            "type": struct_type,
            "keys" if struct_type == "object" else "details": list(details) if isinstance(details, tuple) else details,
            "file_count": len(file_list),
            "sample_file": file_list[0],
            "all_files": file_list
        }

    # Overwrite catalog file with filtered data
    with open(OUTPUT_CATALOG, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)

    print(f"Success! Catalog saved to: {OUTPUT_CATALOG.name}")
    print(f"Found {len(layer_1_groups)} distinct format(s).")


if __name__ == "__main__":
    scan_and_save()