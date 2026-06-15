from __future__ import annotations

import email.utils
import struct
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from extractor.config import JEDIHASH_URL

HASH_FILENAME_TXT = "hashes_filename.txt"
HASH_FILENAME_BIN = "hashes.bin"


def parse_hash_line(line: str) -> tuple[int, str] | None:
    parts = line.strip().split("#")
    if len(parts) != 4:
        return None
    ph = int(parts[0], 16)
    sh = int(parts[1], 16)
    path = parts[2]
    hash64 = (ph << 32) | sh
    return hash64, path


def load_hash_dictionary_txt(path: Path) -> dict[int, str]:
    result: dict[int, str] = {}
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parsed = parse_hash_line(line)
            if parsed:
                hash64, file_path = parsed
                result[hash64] = file_path
    return result


def load_hash_dictionary_bin(path: Path) -> dict[int, str]:
    result: dict[int, str] = {}
    data = path.read_bytes()
    pos = 0
    length = len(data)
    while pos < length:
        if pos + 8 > length:
            break
        hash64 = struct.unpack_from("<Q", data, pos)[0]
        pos += 8
        if pos + 4 > length:
            break
        str_len = struct.unpack_from("<i", data, pos)[0]
        pos += 4
        raw = data[pos : pos + str_len]
        pos += str_len
        file_path = raw.decode("utf-8").rstrip("\x00")
        result[hash64] = file_path
    return result


def load_hash_dictionary(path: Path) -> dict[int, str]:
    if path.suffix.lower() == ".bin":
        return load_hash_dictionary_bin(path)
    return load_hash_dictionary_txt(path)


def binarize_hash_list_txt(txt_path: Path, bin_path: Path) -> None:
    with txt_path.open("r", encoding="utf-8", errors="replace") as handle, bin_path.open(
        "wb"
    ) as out:
        for line in handle:
            parsed = parse_hash_line(line)
            if not parsed:
                continue
            hash64, file_path = parsed
            out.write(struct.pack("<Q", hash64))
            encoded = (file_path + "\x00").encode("utf-8")
            out.write(struct.pack("<i", len(encoded)))
            out.write(encoded)


def download_hash_list(url: str = JEDIHASH_URL, dest: Path | None = None) -> Path:
    dest = dest or Path(HASH_FILENAME_TXT)
    with urllib.request.urlopen(url, timeout=120) as response:
        dest.write_bytes(response.read())
    return dest


def get_remote_modified_time(url: str = JEDIHASH_URL) -> datetime | None:
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            last_modified = response.headers.get("Last-Modified")
    except (urllib.error.URLError, TimeoutError):
        return None
    if not last_modified:
        return None
    parsed = email.utils.parsedate_to_datetime(last_modified)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _local_modified_utc(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def hash_list_is_stale(bin_path: Path, url: str = JEDIHASH_URL) -> bool:
    if not bin_path.exists():
        return True
    remote_mod = get_remote_modified_time(url)
    if remote_mod is None:
        return False
    return _local_modified_utc(bin_path) < remote_mod


def ensure_jedipedia_hash_list(
    cache_dir: Path,
    *,
    force_download: bool = False,
    url: str = JEDIHASH_URL,
) -> dict[int, str]:
    """Download and cache the Jedipedia hash list."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    txt_path = cache_dir / HASH_FILENAME_TXT
    bin_path = cache_dir / HASH_FILENAME_BIN

    if txt_path.exists() and not bin_path.exists():
        binarize_hash_list_txt(txt_path, bin_path)
        txt_path.unlink(missing_ok=True)

    should_download = force_download or not bin_path.exists() or hash_list_is_stale(bin_path, url)
    if should_download:
        download_hash_list(url, txt_path)
        binarize_hash_list_txt(txt_path, bin_path)
        txt_path.unlink(missing_ok=True)

    return load_hash_dictionary(bin_path)
