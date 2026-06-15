from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable, Iterable

import zstandard

MYP_MAGIC = 0x50594D  # "MYP"
MYP_BOM = 0xFD23EC43
HEADER_SIZE = 36
INDEX_ENTRY_SIZE = 34


@dataclass
class TorHeader:
    magic: int
    version: int
    endian: int
    index_offset: int
    capacity: int
    file_count: int


@dataclass
class FileEntry:
    data_offset: int
    compressed_size: int
    decompressed_size: int
    hash: int
    crc: int
    compression_method: int
    version: int

    @property
    def is_compressed(self) -> bool:
        return self.compression_method != 0


def _unpack_exact(data: bytes, fmt: str):
    size = struct.calcsize(fmt)
    if len(data) != size:
        raise struct.error(f"unpack requires a buffer of {size} bytes")
    return struct.unpack(fmt, data)


def _read_unpack(stream: BinaryIO, fmt: str):
    size = struct.calcsize(fmt)
    data = stream.read(size)
    if len(data) != size:
        raise EOFError(f"Unexpected EOF reading {size} bytes for format {fmt!r}")
    return _unpack_exact(data, fmt)


def read_header(stream: BinaryIO) -> TorHeader:
    stream.seek(0)
    header_bytes = stream.read(HEADER_SIZE)
    if len(header_bytes) < 28:
        raise EOFError("Archive file is too small to contain an MYP header")

    magic, version, endian, index_offset, capacity, file_count = _unpack_exact(
        header_bytes[:28], "<iiiqii"
    )
    if magic != MYP_MAGIC:
        raise ValueError(f"Invalid MYP magic: {magic:#x}")
    if version not in (5, 6):
        raise ValueError(f"Unsupported MYP version: {version}")
    if (endian & 0xFFFFFFFF) != MYP_BOM:
        raise ValueError(f"Unexpected MYP byte-order marker: {endian & 0xFFFFFFFF:#x}")
    return TorHeader(magic, version, endian, index_offset, capacity, file_count)


def read_entry(stream: BinaryIO, version: int) -> tuple[FileEntry | None, int]:
    entry_start = stream.tell()
    entry_bytes = stream.read(INDEX_ENTRY_SIZE)
    if len(entry_bytes) < INDEX_ENTRY_SIZE:
        return None, 0

    offset = struct.unpack_from("<Q", entry_bytes, 0)[0]
    next_pos = entry_start + INDEX_ENTRY_SIZE
    if offset == 0:
        return None, next_pos

    header_size = struct.unpack_from("<I", entry_bytes, 8)[0]
    compr_size = struct.unpack_from("<I", entry_bytes, 12)[0]
    uncompr_size = struct.unpack_from("<I", entry_bytes, 16)[0]
    file_hash = struct.unpack_from("<Q", entry_bytes, 20)[0]
    crc = struct.unpack_from("<I", entry_bytes, 28)[0]
    compression_method = struct.unpack_from("<H", entry_bytes, 32)[0]

    entry = FileEntry(
        data_offset=offset + header_size,
        compressed_size=compr_size if compression_method != 0 else uncompr_size,
        decompressed_size=uncompr_size,
        hash=file_hash,
        crc=crc,
        compression_method=compression_method,
        version=version,
    )
    return entry, next_pos


def decompress_payload(payload: bytes, entry: FileEntry) -> bytes:
    if not entry.is_compressed:
        return payload

    if entry.version == 6:
        dctx = zstandard.ZstdDecompressor()
        return dctx.decompress(payload)

    return zlib.decompress(payload)


def _safe_output_path(root: Path, hash_path: str) -> Path | None:
    rel = hash_path.replace("\\", "/").strip("/")
    if not rel or ".." in rel.split("/"):
        return None
    dest = (root / rel).resolve()
    root_resolved = root.resolve()
    if dest != root_resolved and root_resolved not in dest.parents:
        return None
    return dest


def iter_archive_files(
    archive_path: Path,
    hash_dictionary: dict[int, str],
    *,
    path_filter: Callable[[str], bool] | None = None,
) -> Iterable[tuple[str, bytes]]:
    """Yield (hash_path, decompressed_bytes) for entries matching the filter."""
    with archive_path.open("rb") as stream:
        header = read_header(stream)
        next_table_offset = header.index_offset
        file_size = stream.seek(0, 2)

        while next_table_offset != 0 and next_table_offset < file_size:
            stream.seek(next_table_offset)
            table_capacity, = _read_unpack(stream, "<i")
            next_table_offset, = _read_unpack(stream, "<q")

            for _ in range(table_capacity):
                entry, next_pos = read_entry(stream, header.version)
                if next_pos == 0:
                    break
                if entry is None:
                    stream.seek(next_pos)
                    continue

                hash_path = hash_dictionary.get(entry.hash)
                if hash_path and (path_filter is None or path_filter(hash_path)):
                    stream.seek(entry.data_offset)
                    payload = stream.read(entry.compressed_size)
                    if len(payload) != entry.compressed_size:
                        stream.seek(next_pos)
                        continue
                    try:
                        data = decompress_payload(payload, entry)
                    except (zstandard.ZstdError, zlib.error):
                        stream.seek(next_pos)
                        continue
                    if len(data) == entry.decompressed_size:
                        yield hash_path, data

                stream.seek(next_pos)

            if next_table_offset == 0:
                break
            stream.seek(next_table_offset)


def discover_archives(assets_path: Path, *, pts: bool = False) -> list[Path]:
    archives = sorted(assets_path.glob("*.tor"))
    if pts:
        archives = [p for p in archives if "_test_" in p.name.lower()]
    else:
        archives = [p for p in archives if "_test_" not in p.name.lower()]
    return archives


def write_filtered_extract(
    archives: Iterable[Path],
    hash_dictionary: dict[int, str],
    resources_root: Path,
    path_filter: Callable[[str], bool],
) -> int:
    resources_root.mkdir(parents=True, exist_ok=True)
    written = 0
    for archive in archives:
        for hash_path, data in iter_archive_files(
            archive, hash_dictionary, path_filter=path_filter
        ):
            rel = hash_path.lstrip("/").replace("\\", "/")
            if rel.startswith("resources/"):
                rel = rel[len("resources/") :]
            dest = _safe_output_path(resources_root, rel)
            if dest is None:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            written += 1
    return written
