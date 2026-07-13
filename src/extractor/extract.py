from __future__ import annotations

from pathlib import Path

from extractor.hashlist import ensure_jedipedia_hash_list
from extractor.myp_archive import discover_archives, write_filtered_extract


def is_relevant_path(hash_path: str) -> bool:
    normalized = hash_path.replace("\\", "/").lower()
    if "systemgenerated/buckets.info" in normalized:
        return True
    if normalized.endswith("/resources/systemgenerated/client.gom"):
        return True
    if "/systemgenerated/buckets/" in normalized and normalized.endswith(".bkt"):
        return True
    if "/en-us/str/" in normalized and normalized.endswith(".stb"):
        return True
    if normalized.endswith("/resources/gamedata/str/stb.manifest"):
        return True
    return False


def extract_relevant_files(
    assets_path: Path,
    work_dir: Path,
    cache_dir: Path,
    *,
    force_hash_update: bool = False,
    pts: bool = False,
) -> Path:
    hash_dictionary = ensure_jedipedia_hash_list(
        cache_dir, force_download=force_hash_update
    )
    resources_root = work_dir / "resources"
    archives = discover_archives(assets_path, pts=pts)
    if not archives:
        raise FileNotFoundError(f"No .tor archives found under {assets_path}")

    count = write_filtered_extract(
        archives,
        hash_dictionary,
        resources_root,
        path_filter=is_relevant_path,
    )
    if count == 0:
        raise RuntimeError(
            "No relevant files extracted. Check hash list and assets path."
        )
    return resources_root
