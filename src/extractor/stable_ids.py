from __future__ import annotations

import re
import urllib.request
from pathlib import Path
from typing import Any

from src.extractor.config import FNV1A64_JS_URL
from src.extractor.hashlist import hash_list_is_stale

FNV1A64_JS_FILENAME = "fnv1a64.js"
FNV1A64_OFFSET_BASIS = 0xCBF29CE484222325
FNV1A64_PRIME = 0x100000001B3
U64_MASK = 0xFFFFFFFFFFFFFFFF

TAG_STRING_PATTERN = re.compile(
    r"^\s*'(?P<name>tag\.[^'\\]*)'\s*,?(?:\s*//.*)?$",
    re.IGNORECASE | re.MULTILINE,
)


def fnv1a64(text: str) -> int:
    """Match Jedipedia's uppercase, UTF-16-code-unit FNV-1a implementation."""
    value = FNV1A64_OFFSET_BASIS
    utf16 = text.upper().encode("utf-16-le", errors="surrogatepass")
    for pos in range(0, len(utf16), 2):
        code_unit = int.from_bytes(utf16[pos : pos + 2], "little")
        value ^= code_unit
        value = (value * FNV1A64_PRIME) & U64_MASK
    return value


def parse_tag_hashes(path: Path) -> dict[str, str]:
    """Build decimal uint64 hash -> lowercase tag name from Jedipedia's helper."""
    text = path.read_text(encoding="utf-8", errors="replace")
    tags = (match.group("name") for match in TAG_STRING_PATTERN.finditer(text))
    return {str(fnv1a64(tag)): tag.lower() for tag in tags}


def ensure_jedipedia_fnv1a64_js(
    cache_dir: Path,
    *,
    force_download: bool = False,
    url: str = FNV1A64_JS_URL,
) -> Path:
    """Download and cache Jedipedia's stable-ID helper and known strings."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    js_path = cache_dir / FNV1A64_JS_FILENAME

    should_download = (
        force_download or not js_path.exists() or hash_list_is_stale(js_path, url)
    )
    if should_download:
        with urllib.request.urlopen(url, timeout=120) as response:
            js_path.write_bytes(response.read())

    return js_path


class TagResolver:
    def __init__(self, tags_by_hash: dict[str, str]):
        self.tags_by_hash = tags_by_hash

    @classmethod
    def from_jedipedia_js(cls, path: Path) -> TagResolver:
        return cls(parse_tag_hashes(path))

    @staticmethod
    def _unsigned_decimal(value: Any) -> str | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return str(value & U64_MASK)
        if not isinstance(value, str) or not re.fullmatch(r"-?\d+", value):
            return None
        return str(int(value) & U64_MASK)

    def resolve(self, value: Any) -> Any:
        unsigned = self._unsigned_decimal(value)
        if unsigned is None:
            return value
        return self.tags_by_hash.get(unsigned, value)
