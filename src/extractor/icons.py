from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

from extractor.myp_archive import discover_archives, iter_archive_files

GFX_ICONS_MARKER = "/resources/gfx/icons/"
GFX_ARCHIVE_TOKEN = "gfx_assets"


def _normalized_path(path: str) -> str:
    return "/" + path.replace("\\", "/").lower().lstrip("/")


def _is_gfx_icon_path(path: str) -> bool:
    normalized = _normalized_path(path)
    return GFX_ICONS_MARKER in normalized and normalized.endswith(".dds")


def _icon_stem(path: str) -> str:
    return Path(path.replace("\\", "/")).stem


def build_icon_hash_index(hash_dictionary: dict[int, str]) -> dict[str, tuple[int, str]]:
    """Map lowercase icon stem -> (file hash, original archive path)."""
    index: dict[str, tuple[int, str]] = {}
    for file_hash, path in hash_dictionary.items():
        if not _is_gfx_icon_path(path):
            continue
        index[_icon_stem(path).lower()] = (file_hash, path)
    return index


def _order_archives_for_icons(archives: list[Path]) -> list[Path]:
    gfx = [path for path in archives if GFX_ARCHIVE_TOKEN in path.name.lower()]
    rest = [path for path in archives if path not in gfx]
    return gfx + rest


def _dds_to_png(dds_bytes: bytes) -> bytes:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Pillow is required for --extract-icons (pip install Pillow)"
        ) from exc

    try:
        with Image.open(BytesIO(dds_bytes)) as image:
            converted = image.convert("RGBA")
            out = BytesIO()
            converted.save(out, format="PNG")
            return out.getvalue()
    except OSError as exc:
        raise ValueError("unrecognized DDS image") from exc


def _safe_stem(stem: str) -> str | None:
    if not stem or stem in {".", ".."} or "/" in stem or "\\" in stem:
        return None
    return stem


def extract_ability_icons(
    icon_stems: set[str],
    *,
    assets_path: Path,
    output_dir: Path,
    hash_dictionary: dict[int, str],
    pts: bool = False,
    keep_work_dir: Path | None = None,
) -> int:
    """Extract referenced icon DDS files from gfx TOR archives and write PNGs."""
    if not icon_stems:
        return 0

    index = build_icon_hash_index(hash_dictionary)
    wanted: dict[int, str] = {}
    stem_by_lower: dict[str, str] = {}
    for stem in sorted(icon_stems):
        safe = _safe_stem(stem)
        if safe is None:
            print(f"Warning: skipping unsafe icon stem {stem!r}", file=sys.stderr)
            continue
        stem_by_lower[safe.lower()] = safe
        resolved = index.get(safe.lower())
        if resolved is None:
            print(
                f"Warning: no hash list entry for icon {safe!r} "
                f"({GFX_ICONS_MARKER.lstrip('/')}{safe}.dds)",
                file=sys.stderr,
            )
            continue
        file_hash, _path = resolved
        wanted[file_hash] = safe

    if not wanted:
        return 0

    archives = _order_archives_for_icons(discover_archives(assets_path, pts=pts))
    if not archives:
        print(
            f"Warning: no .tor archives found under {assets_path} for icon extraction",
            file=sys.stderr,
        )
        return 0

    remaining = set(wanted)
    found: dict[str, bytes] = {}
    found_paths: dict[str, str] = {}
    for archive in archives:
        if not remaining:
            break
        for hash_path, data in iter_archive_files(
            archive,
            hash_dictionary,
            hash_filter=remaining,
        ):
            stem = stem_by_lower.get(_icon_stem(hash_path).lower())
            if stem is None:
                continue
            found[stem] = data
            found_paths[stem] = hash_path
            file_hash, _path = index[stem.lower()]
            remaining.discard(file_hash)

    for file_hash in remaining:
        stem = wanted[file_hash]
        print(
            f"Warning: icon {stem!r} not found in TOR archives",
            file=sys.stderr,
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for stem, dds_bytes in found.items():
        if keep_work_dir is not None:
            rel = found_paths[stem].lstrip("/").replace("\\", "/")
            if rel.startswith("resources/"):
                rel = rel[len("resources/") :]
            dds_dest = keep_work_dir / "resources" / rel
            dds_dest.parent.mkdir(parents=True, exist_ok=True)
            dds_dest.write_bytes(dds_bytes)
        try:
            png_bytes = _dds_to_png(dds_bytes)
        except (OSError, ValueError, RuntimeError) as exc:
            print(
                f"Warning: failed to convert icon {stem!r}: {exc}",
                file=sys.stderr,
            )
            continue
        dest = output_dir / f"{stem}.png"
        dest.write_bytes(png_bytes)
        written += 1
    return written
