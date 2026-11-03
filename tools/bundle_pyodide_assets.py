"""Bundle SwtorSim runtime assets into a compact zip archive for Pyodide WebAssembly release.

Excludes large extraction artifacts (raw extracted GOM JSONs, hashes.bin, fnv1a64.js)
and packages only what the simulation engine and web UI need at runtime.
"""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

SWTORSIM_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = SWTORSIM_ROOT / "dist"
OUTPUT_ZIP = DIST_DIR / "swtorsim_assets.zip"

EXCLUDE_PATTERNS = {
    "__pycache__",
    ".pytest_cache",
    ".idea",
    ".venv",
    ".git",
    "extracted",  # data/extractor/extracted (~400MB)
    "hashes.bin",  # GOM string table cache (137MB)
    "fnv1a64.js",
    "gom.js",
}

INCLUDE_DIRS = [
    ("src/swtorsim", "src/swtorsim"),
    ("data/Choices", "data/Choices"),
    ("data/Choices", "data/choices"),
    ("data/builds", "data/builds"),
    ("data/rotations", "data/rotations"),
    ("data/run_config", "data/run_config"),
    ("data/extractor/parsed", "data/extractor/parsed"),
    ("data/extractor/disciplines", "data/extractor/disciplines"),
    ("data/extractor/pts/parsed", "data/extractor/pts/parsed"),
    ("data/extractor/pts/disciplines", "data/extractor/pts/disciplines"),
]

INCLUDE_FILES = [
    ("data/__init__.py", "data/__init__.py"),
    ("data/DebuffModule.json", "data/DebuffModule.json"),
    ("data/rotation_builder.py", "data/rotation_builder.py"),
    ("data/extractor/combat_curves.json", "data/extractor/combat_curves.json"),
    ("data/extractor/adrenals.json", "data/extractor/adrenals.json"),
    ("data/extractor/gear_abilities_talents.json", "data/extractor/gear_abilities_talents.json"),
    ("data/extractor/relics.json", "data/extractor/relics.json"),
    ("data/extractor/pts/combat_curves.json", "data/extractor/pts/combat_curves.json"),
    ("data/extractor/pts/adrenals.json", "data/extractor/pts/adrenals.json"),
    ("data/extractor/pts/gear_abilities_talents.json", "data/extractor/pts/gear_abilities_talents.json"),
    ("data/extractor/pts/relics.json", "data/extractor/pts/relics.json"),
]


def should_exclude(path: Path) -> bool:
    for part in path.parts:
        if part in EXCLUDE_PATTERNS:
            return True
        if part.endswith(".pyc") or part.endswith(".pyo"):
            return True
    return False


def build_asset_bundle(output_path: Path = OUTPUT_ZIP) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total_files = 0
    raw_bytes = 0

    print(f"[INFO] Building Pyodide asset bundle: {output_path}")
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # 1. Directories
        for src_rel, arc_rel in INCLUDE_DIRS:
            src_path = SWTORSIM_ROOT / src_rel
            if not src_path.is_dir():
                print(f"[WARN] Optional directory not found: {src_rel}")
                continue
            for item in sorted(src_path.rglob("*")):
                if not item.is_file() or should_exclude(item):
                    continue
                rel_to_base = item.relative_to(src_path)
                archive_name = (Path(arc_rel) / rel_to_base).as_posix()
                zf.write(item, archive_name)
                total_files += 1
                raw_bytes += item.stat().st_size

        # 2. Individual Files
        for src_rel, arc_rel in INCLUDE_FILES:
            src_file = SWTORSIM_ROOT / src_rel
            if not src_file.is_file():
                continue
            zf.write(src_file, arc_rel)
            total_files += 1
            raw_bytes += src_file.stat().st_size

    zip_bytes = output_path.stat().st_size
    print(f"[OK] Asset bundle created: {total_files} files packaged.")
    print(f"     Uncompressed size: {raw_bytes / (1024 * 1024):.2f} MB")
    print(f"     Compressed size:   {zip_bytes / (1024 * 1024):.2f} MB")
    return output_path


if __name__ == "__main__":
    build_asset_bundle()
