from __future__ import annotations

import urllib.request
from pathlib import Path

from extractor.config import GOM_JS_URL
from extractor.hashlist import hash_list_is_stale

GOM_JS_FILENAME = "gom.js"


def ensure_jedipedia_gom_js(
    cache_dir: Path,
    *,
    force_download: bool = False,
    url: str = GOM_JS_URL,
) -> Path:
    """Download and cache Jedipedia's gom.js name map."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    js_path = cache_dir / GOM_JS_FILENAME

    should_download = (
        force_download or not js_path.exists() or hash_list_is_stale(js_path, url)
    )
    if should_download:
        with urllib.request.urlopen(url, timeout=120) as response:
            js_path.write_bytes(response.read())

    return js_path
