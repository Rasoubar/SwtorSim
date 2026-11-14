"""Standalone SWTOR icon extractor.

Scans parsed blueprint JSONs (abilities, talents, effects) for referenced icon specs,
resolves their FNV-1a hashes against data/extractor/hashes.bin, extracts the DDS textures
directly from SWTOR's gfx assets archive (swtor_main_gfx_assets_1.tor), and converts them
to PNGs.

Usage:
    python tools/extract_icons.py [--assets <path_to_assets>] [--output <out_dir>] [--copy-to-web]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

SWTORSIM_ROOT = Path(__file__).resolve().parents[1]
if str(SWTORSIM_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(SWTORSIM_ROOT / "src"))

from extractor.hashlist import load_hash_dictionary
from extractor.icons import extract_ability_icons

DEFAULT_ASSET_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Steam\steamapps\common\Star Wars - The Old Republic\Assets"),
    Path(r"C:\Program Files (x86)\Electronic Arts\BioWare\Star Wars - The Old Republic\Assets"),
    Path(r"D:\Steam\steamapps\common\Star Wars - The Old Republic\Assets"),
    Path(r"D:\SteamLibrary\steamapps\common\Star Wars - The Old Republic\Assets"),
    Path(r"E:\Steam\steamapps\common\Star Wars - The Old Republic\Assets"),
    Path(r"E:\SteamLibrary\steamapps\common\Star Wars - The Old Republic\Assets"),
    Path(r"C:\Games\Star Wars - The Old Republic\Assets"),
]


def detect_assets_path() -> Path | None:
    for candidate in DEFAULT_ASSET_CANDIDATES:
        if candidate.is_dir() and any(candidate.glob("*gfx*.tor")):
            return candidate
    return None


def collect_referenced_icon_stems(parsed_dirs: list[Path]) -> set[str]:
    stems: set[str] = set()

    def _add_spec(spec: Any) -> None:
        if not isinstance(spec, str):
            return
        clean = spec.strip()
        if not clean:
            return
        lower = clean.lower()
        if lower.endswith(".png") or lower.endswith(".dds"):
            clean = clean[: clean.rfind(".")]
        if clean:
            stems.add(clean)

    for pdir in parsed_dirs:
        if not pdir.is_dir():
            continue
        for json_path in pdir.rglob("*.json"):
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception:
                continue

            if isinstance(data, dict):
                _add_spec(data.get("icon"))
                # Effects in abilities
                for eff in data.get("effects") or []:
                    if isinstance(eff, dict):
                        _add_spec(eff.get("icon"))
                # Packages/disciplines if any
                _add_spec(data.get("ui_icon"))
                _add_spec(data.get("icon_spec"))

    return stems


def run_icon_extraction(
    assets_path: Path,
    output_dir: Path,
    parsed_dirs: list[Path] | None = None,
    hashes_bin: Path | None = None,
    pts: bool = False,
    copy_to_web: bool = False,
) -> int:
    if parsed_dirs is None:
        parsed_dirs = [
            SWTORSIM_ROOT / "data" / "extractor" / "live" / "parsed",
            SWTORSIM_ROOT / "data" / "extractor" / "live" / "disciplines",
        ]
    if hashes_bin is None:
        hashes_bin = SWTORSIM_ROOT / "data" / "extractor" / "hashes.bin"

    if not hashes_bin.is_file():
        print(f"[FAIL] Hash dictionary not found at {hashes_bin}")
        return 0

    print(f"[INFO] Scanning parsed blueprints for referenced icons...")
    icon_stems = collect_referenced_icon_stems(parsed_dirs)
    print(f"[INFO] Found {len(icon_stems)} unique referenced icon stems.")

    print(f"[INFO] Loading hash dictionary from {hashes_bin.name}...")
    hash_dictionary = load_hash_dictionary(hashes_bin)
    print(f"[INFO] Loaded {len(hash_dictionary)} hash entries.")

    print(f"[INFO] Extracting icons from assets at {assets_path} -> {output_dir}...")
    output_dir.mkdir(parents=True, exist_ok=True)
    count = extract_ability_icons(
        icon_stems,
        assets_path=assets_path,
        output_dir=output_dir,
        hash_dictionary=hash_dictionary,
        pts=pts,
    )
    print(f"[OK] Successfully extracted and converted {count} PNG icons to {output_dir}")

    if copy_to_web:
        web_icons_dir = SWTORSIM_ROOT / "tools" / "web" / "icons"
        web_icons_dir.mkdir(parents=True, exist_ok=True)
        copied = 0
        for png_file in output_dir.glob("*.png"):
            dest = web_icons_dir / png_file.name
            dest.write_bytes(png_file.read_bytes())
            copied += 1
        print(f"[OK] Mirrored {copied} PNG icons to {web_icons_dir}")

    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract referenced SWTOR icons from game archives to PNG.")
    parser.add_argument(
        "--assets",
        type=Path,
        default=None,
        help="Path to SWTOR Assets/ directory (auto-detected if omitted)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=SWTORSIM_ROOT / "data" / "extractor" / "live" / "icons",
        help="Output directory for PNG icons (default: data/extractor/live/icons)",
    )
    parser.add_argument(
        "--pts",
        action="store_true",
        help="Use PTS archives instead of live",
    )
    parser.add_argument(
        "--copy-to-web",
        action="store_true",
        help="Also copy extracted PNGs to tools/web/icons for local web serving and distribution",
    )

    args = parser.parse_args()

    assets = args.assets
    if assets is None:
        assets = detect_assets_path()
        if assets is None:
            print("[FAIL] Could not auto-detect SWTOR Assets directory.")
            print("       Please provide --assets <path-to-SWTOR/Assets>")
            sys.exit(1)
        print(f"[INFO] Auto-detected SWTOR Assets at: {assets}")
    elif not assets.is_dir():
        print(f"[FAIL] Assets directory not found at: {assets}")
        sys.exit(1)

    written = run_icon_extraction(
        assets_path=assets,
        output_dir=args.output,
        pts=args.pts,
        copy_to_web=args.copy_to_web,
    )
    if written > 0:
        print("[OK] Icon extraction completed successfully.")
    else:
        print("[WARN] No icons were extracted.")


if __name__ == "__main__":
    main()
