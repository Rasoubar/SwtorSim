import json
from pathlib import Path
from collections import defaultdict

SCRIPT_DIR = Path(__file__).resolve().parent
CATALOG_PATH = SCRIPT_DIR / "layer1_catalog.json"
DATA_DIR = SCRIPT_DIR.parent / "src" / "extractor" / "data"


def load_catalog():
    if not CATALOG_PATH.exists():
        print(f"Error: Could not find '{CATALOG_PATH.name}'.")
        print("Please run 'python tools/inspect_layer1.py' first to build the catalog.")
        return None
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_catalog(catalog):
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)
    print(f"\n[Saved changes to '{CATALOG_PATH.name}']")


def get_node_by_path(data, key_path):
    curr = data
    for bit in key_path:
        if isinstance(curr, dict) and bit in curr:
            curr = curr[bit]
        elif isinstance(curr, list):
            if bit.isdigit() and int(bit) < len(curr):
                curr = curr[int(bit)]
            elif len(curr) > 0 and isinstance(curr[0], dict) and bit in curr[0]:
                curr = curr[0][bit]
            elif len(curr) > 0:
                curr = curr[0]
            else:
                return None
        else:
            return None
    return curr


def get_sub_schema_signature(data):
    if isinstance(data, dict):
        return ("object", tuple(sorted(data.keys())))
    elif isinstance(data, list):
        if not data:
            return ("array", "empty")
        first_elem = data[0]
        if isinstance(first_elem, dict):
            return ("array_of_objects", tuple(sorted(first_elem.keys())))
        return ("array_of_primitives", type(first_elem).__name__)
    else:
        return ("primitive", type(data).__name__)


def inspect_and_save_sub_path(catalog, target_node, scope_name="Format"):
    """
    Scans child paths inside `target_node` (can be top format or nested sub-variant).
    """
    print(f"\n--- NESTED PATH SCHEMA SCANNER ({scope_name}) ---")
    path_str = input("Enter key path to inspect (e.g. 'stats', 'stat_changes.details'): ").strip()

    if not path_str:
        return

    path_keys = [k.strip() for k in path_str.split(".") if k.strip()]
    sub_formats = defaultdict(list)
    missing_count = 0
    file_scope = target_node.get("all_files", [])

    print(f"Scanning {len(file_scope)} files at path '{path_str}'...")

    for rel_path in file_scope:
        full_path = DATA_DIR / rel_path
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            node = get_node_by_path(data, path_keys)
            if node is None:
                missing_count += 1
                continue

            sig = get_sub_schema_signature(node)
            sub_formats[sig].append(rel_path)
        except Exception:
            missing_count += 1

    print("\n" + "=" * 65)
    print(f"  NESTED RESULTS FOR PATH: '{path_str}'")
    print(f"  Found {len(sub_formats)} distinct sub-format variant(s).")
    if missing_count > 0:
        print(f"  ({missing_count} files did not contain this path or were empty)")
    print("=" * 65)

    if not sub_formats:
        return

    variant_menu = {}
    for idx, (sig, file_list) in enumerate(sub_formats.items(), 1):
        struct_type, details = sig
        var_key = f"sub_variant_{idx:02d}"
        variant_menu[str(idx)] = {
            "key": var_key,
            "signature": sig,
            "files": file_list
        }
        print(f" [{idx}] Sub-Variant #{idx} ({len(file_list)} files)")
        print(f"     Type     : {struct_type}")
        if struct_type in ("object", "array_of_objects"):
            print(f"     Sub-keys : {list(details)}")
        else:
            print(f"     Details  : {details}")
        print(f"     Sample   : {file_list[0]}")
        print("-" * 45)

    print("\nActions for these sub-formats:")
    print(" [S] Save all detected sub-formats (and their file lists) to catalog")
    print(" [B] Back without saving")

    action = input("\nSelect action: ").strip().lower()

    if action == 's':
        if "sub_paths" not in target_node:
            target_node["sub_paths"] = {}

        path_entry = {}
        for var_id, var_info in variant_menu.items():
            sig_type, sig_details = var_info["signature"]

            print(f"\nNaming Sub-Variant #{var_id} (Sample: {Path(var_info['files'][0]).name}):")
            custom_name = input(f"Enter name for variant [default: '{var_info['key']}']: ").strip()
            final_name = custom_name if custom_name else var_info["key"]

            path_entry[final_name] = {
                "type": sig_type,
                "keys" if sig_type in ("object", "array_of_objects") else "details": (
                    list(sig_details) if isinstance(sig_details, tuple) else sig_details
                ),
                "file_count": len(var_info["files"]),
                "sample_file": var_info["files"][0],
                "all_files": var_info["files"],
                "sub_paths": {}  # Prepared for recursive nesting
            }

        target_node["sub_paths"][path_str] = path_entry
        save_catalog(catalog)
        print(f"Successfully saved sub-path '{path_str}' analysis to {scope_name}!")


def view_and_inspect_sub_variants(catalog, node_data, scope_name):
    """Browses sub-variants and lets you drill down recursively inside one."""
    saved_sub = node_data.get("sub_paths", {})
    if not saved_sub:
        print("\nNo sub-paths have been analyzed and saved for this scope yet.")
        return

    variant_lookup = {}
    counter = 1

    print(f"\n--- SAVED SUB-VARIANTS ({scope_name}) ---")
    for path_name, variants in saved_sub.items():
        print(f" Path: '{path_name}'")
        if isinstance(variants, dict):
            for var_name, var_data in variants.items():
                if isinstance(var_data, dict):
                    variant_lookup[str(counter)] = (path_name, var_name, var_data)
                    count = var_data.get("file_count", len(var_data.get("all_files", [])))
                    sub_count = len(var_data.get("sub_paths", {}))
                    sub_info = f" | {sub_count} nested sub-path(s)" if sub_count else ""
                    print(f"  [{counter}] Variant: {var_name:<20} ({count} files{sub_info})")
                    counter += 1

    if not variant_lookup:
        print("No selectable sub-variants found.")
        return

    choice = input("\nSelect a sub-variant number to open/drill down (or press Enter to back): ").strip()
    if choice not in variant_lookup:
        return

    path_name, var_name, selected_var_data = variant_lookup[choice]
    sub_variant_drilldown_menu(catalog, selected_var_data, f"{path_name} -> {var_name}")


def sub_variant_drilldown_menu(catalog, var_data, var_label):
    """Sub-menu targeting a specific sub-variant object recursively."""
    while True:
        print("\n" + "=" * 60)
        print(f"  INSPECTING SUB-VARIANT: {var_label}")
        print("=" * 60)
        print(f"File Count  : {var_data.get('file_count', len(var_data.get('all_files', [])))}")
        print(f"Type        : {var_data.get('type')}")
        keys_or_details = var_data.get('keys') or var_data.get('details')
        print(f"Structure   : {keys_or_details}")
        print(f"Sample File : {var_data.get('sample_file')}")

        saved_sub = var_data.get("sub_paths", {})
        if saved_sub:
            print(f"\nNested Sub-Path Analyses ({len(saved_sub)}):")
            for p_name, variants in saved_sub.items():
                var_summary = ", ".join([f"{v_name} ({v_data['file_count']} files)" for v_name, v_data in variants.items()])
                print(f"  • Path '{p_name}': {var_summary}")

        print("-" * 60)
        print(" [P] Inspect & Save Sub-Path Inside This Sub-Variant")
        print(" [V] View / Drill into Nested Sub-Variants")
        print(" [F] View ALL File Paths in this sub-variant")
        print(" [B] Back")

        sub_choice = input("\nSelect an action: ").strip().lower()

        if sub_choice == 'p':
            inspect_and_save_sub_path(catalog, var_data, scope_name=var_label)
            input("\nPress Enter to return...")
        elif sub_choice == 'v':
            view_and_inspect_sub_variants(catalog, var_data, scope_name=var_label)
        elif sub_choice == 'f':
            show_format_files(var_data)
            input("\nPress Enter to return...")
        elif sub_choice == 'b':
            break


def display_format_details(format_key, fmt_data):
    print("\n" + "=" * 60)
    print(f"  INSPECTING FORMAT: {format_key}")
    print("=" * 60)
    print(f"File Count  : {fmt_data['file_count']}")
    print(f"Type        : {fmt_data['type']}")

    keys_or_details = fmt_data.get('keys') or fmt_data.get('details')
    print(f"Structure   : {keys_or_details}")
    print(f"Sample File : {fmt_data['sample_file']}")

    saved_sub = fmt_data.get("sub_paths", {})
    if saved_sub:
        print(f"\nSaved Sub-Path Analyses ({len(saved_sub)}):")
        for p_name, variants in saved_sub.items():
            var_summary = ", ".join([f"{v_name} ({v_data['file_count']} files)" for v_name, v_data in variants.items()])
            print(f"  • Path '{p_name}': {var_summary}")

    print("-" * 60)

    sample_full_path = DATA_DIR / fmt_data["sample_file"]
    try:
        with open(sample_full_path, "r", encoding="utf-8") as f:
            sample_data = json.load(f)

        print("LAYER-1 PREVIEW (Key -> Value Type):")
        if isinstance(sample_data, dict):
            for k, v in sample_data.items():
                print(f"  • {k:<20} -> ({type(v).__name__})")
        elif isinstance(sample_data, list):
            print(f"  • List containing {len(sample_data)} top-level items.")
        else:
            print(f"  • Primitive Value: {sample_data}")

    except Exception as e:
        print(f"Could not load sample file: {e}")

    print("=" * 60)


def show_format_files(fmt_data):
    all_files = fmt_data.get("all_files", [])
    total = len(all_files)

    print(f"\n--- ALL FILES IN THIS SCOPE ({total} total) ---")
    limit_input = input("How many files to show? [default: 10]: ").strip().lower()
    limit = int(limit_input) if limit_input.isdigit() else total if limit_input == 'all' else 10

    for idx, path_str in enumerate(all_files[:limit], 1):
        print(f"  {idx:3d}. {path_str}")
    if limit < total:
        print(f"  ... and {total - limit} more files.")
    print("-" * 60)


def search_file_location(catalog):
    query = input("\nEnter file name or keyword: ").strip().lower()
    if not query:
        return

    matches = []
    formats = catalog.get("formats", {})

    def recursive_search(sub_paths_dict, parent_chain):
        for path_name, variants in sub_paths_dict.items():
            for var_name, var_data in variants.items():
                chain = f"{parent_chain} -> {path_name}:{var_name}"
                for rel_path in var_data.get("all_files", []):
                    if query in rel_path.lower():
                        matches.append({"sub": chain, "path": rel_path})
                if "sub_paths" in var_data:
                    recursive_search(var_data["sub_paths"], chain)

    for fmt_key, fmt_data in formats.items():
        for rel_path in fmt_data.get("all_files", []):
            if query in rel_path.lower():
                matches.append({"sub": f"Format [{fmt_key}]", "path": rel_path})

        if "sub_paths" in fmt_data:
            recursive_search(fmt_data["sub_paths"], f"Format [{fmt_key}]")

    print(f"\nFound {len(matches)} match(es):")
    for m in matches[:20]:
        print(f"  • {m['path']}  --> Location: {m['sub']}")


def rename_format(catalog, menu_map):
    formats = catalog.get("formats", {})
    choice = input("\nEnter format number or current name to rename: ").strip()
    target_key = menu_map.get(choice) or (choice if choice in formats else None)

    if not target_key:
        print("Invalid selection.\n")
        return

    new_name = input(f"Enter new custom name for '{target_key}': ").strip()
    if not new_name or new_name in formats:
        print("Invalid or duplicate name.\n")
        return

    updated_formats = {}
    for k, v in formats.items():
        updated_formats[new_name if k == target_key else k] = v

    catalog["formats"] = updated_formats
    save_catalog(catalog)
    print(f"Renamed format '{target_key}' to '{new_name}'.")


def inspect_format_menu(catalog, format_key):
    while True:
        fmt_data = catalog.get("formats", {}).get(format_key)
        if not fmt_data:
            print(f"Error: Format '{format_key}' not found.")
            break

        display_format_details(format_key, fmt_data)
        print(" [P] Inspect & Save Sub-Path Schemas")
        print(" [V] View / Drill into Saved Sub-Variants")
        print(" [F] View ALL File Paths in this top-level format")
        print(" [B] Back to main menu")

        sub_choice = input("\nSelect an action: ").strip().lower()

        if sub_choice == 'p':
            inspect_and_save_sub_path(catalog, fmt_data, scope_name=format_key)
            input("\nPress Enter to return to format options...")
        elif sub_choice == 'v':
            view_and_inspect_sub_variants(catalog, fmt_data, scope_name=format_key)
        elif sub_choice == 'f':
            show_format_files(fmt_data)
            input("\nPress Enter to return to format options...")
        elif sub_choice == 'b':
            break


def interactive_inspector():
    catalog = load_catalog()
    if not catalog:
        return

    while True:
        formats = catalog.get("formats", {})
        if not formats:
            print("No formats found in catalog.")
            return

        menu_map = {}
        print("\n--- AVAILABLE FORMATS ---")
        for num, (fmt_key, fmt_data) in enumerate(formats.items(), 1):
            menu_map[str(num)] = fmt_key
            sample_name = Path(fmt_data['sample_file']).name
            sub_count = len(fmt_data.get("sub_paths", {}))
            sub_info = f" | {sub_count} sub-path(s) saved" if sub_count else ""
            print(f" [{num}] {fmt_key:<20} ({fmt_data['file_count']} files{sub_info}) -> e.g., {sample_name}")

        print(" [S] Search for a file by name")
        print(" [R] Rename a Format")
        print(" [Q] Quit")

        choice = input("\nSelect an option: ").strip().lower()

        if choice == 'q':
            print("Exiting inspector.")
            break
        elif choice == 's':
            search_file_location(catalog)
            input("\nPress Enter to continue...")
        elif choice == 'r':
            rename_format(catalog, menu_map)
        else:
            selected_key = menu_map.get(choice) or (choice if choice in formats else None)
            if selected_key:
                inspect_format_menu(catalog, selected_key)


if __name__ == "__main__":
    interactive_inspector()