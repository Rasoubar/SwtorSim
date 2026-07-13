from __future__ import annotations

import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from extractor.ids import read_u64_le, u64_str
from extractor.varint import read_cstring, read_length_prefixed_string, read_varint

PBUK_MAGIC = 0x4B554250
DBLB_MAGIC = 0x424C4244
MAGIC_ZSTD = 0xB528
MAGIC_ZLIB = 0x9C78


@dataclass
class BucketNodeEntry:
    fqn: str
    node_id: int
    base_class_id: int
    data_offset: int
    data_length: int
    node_content_length: int
    content_offset: int
    stream_style: int
    bitset: int
    bucket_path: str = ""


def parse_bucket_names_from_info(data: bytes) -> list[str]:
    if len(data) < 9 or data[8] != 0xC9:
        return []
    pos = 9
    if pos + 2 > len(data):
        return []
    num_entries = struct.unpack_from(">H", data, pos)[0]
    pos += 2
    names: list[str] = []
    for _ in range(num_entries):
        name, consumed = read_length_prefixed_string(data, pos)
        if consumed == 0:
            break
        if name:
            names.append(name)
        pos += consumed
    return names


def list_node_entries(bucket_data: bytes, bucket_path: str = "") -> list[BucketNodeEntry]:
    if len(bucket_data) < 8:
        return []
    if struct.unpack_from("<I", bucket_data, 0)[0] != PBUK_MAGIC:
        return []

    ver_major = struct.unpack_from("<H", bucket_data, 4)[0]
    ver_minor = struct.unpack_from("<H", bucket_data, 6)[0]
    if ver_major != 2 or ver_minor not in (4, 5):
        return []

    result: list[BucketNodeEntry] = []
    pos = 8
    end_bound = len(bucket_data) - 12

    while pos < end_bound:
        if pos + 4 > len(bucket_data):
            break
        dblb_length = struct.unpack_from("<I", bucket_data, pos)[0]
        pos += 4
        if dblb_length == 0:
            break

        dblb_start = pos
        if pos + 8 > len(bucket_data):
            break
        if struct.unpack_from("<I", bucket_data, pos)[0] != DBLB_MAGIC:
            break
        pos += 4
        dblb_version = struct.unpack_from("<I", bucket_data, pos)[0]
        pos += 4
        if dblb_version not in (1, 2):
            break

        while dblb_start + dblb_length - pos >= 4:
            start_offset = pos
            entry_length = struct.unpack_from("<I", bucket_data, pos)[0]
            pos += 4
            if entry_length == 0:
                break

            if dblb_version == 1:
                if pos + 12 > len(bucket_data):
                    return result
                bitset = struct.unpack_from("<H", bucket_data, pos)[0]
                pos += 2
                data_offset_rel = struct.unpack_from("<H", bucket_data, pos)[0]
                pos += 2
                node_id, _ = read_u64_le(bucket_data, pos)
                pos += 8
            else:
                if pos + 16 > len(bucket_data):
                    return result
                pos += 4
                node_id, _ = read_u64_le(bucket_data, pos)
                pos += 8
                bitset = struct.unpack_from("<H", bucket_data, pos)[0]
                pos += 2
                data_offset_rel = struct.unpack_from("<H", bucket_data, pos)[0]
                pos += 2

            name_offset_rel = struct.unpack_from("<H", bucket_data, pos)[0]
            pos += 2
            pos += 2  # description offset

            if dblb_version == 1:
                pos += 4

            base_class_id, _ = read_u64_le(bucket_data, pos)
            pos += 8

            if dblb_version == 2:
                pos += 4

            pos += 2  # num glommed
            pos += 2  # glommed offset
            node_content_length = struct.unpack_from("<I", bucket_data, pos)[0]
            pos += 4
            uncompr_offset = struct.unpack_from("<H", bucket_data, pos)[0]
            pos += 2
            pos += 2  # pbuk minor echo
            stream_style = bucket_data[pos]
            pos += 1
            pos += 1  # node type

            name_pos = start_offset + name_offset_rel
            fqn = read_cstring(bucket_data, name_pos) if name_pos < len(bucket_data) else ""
            data_abs = start_offset + data_offset_rel
            data_len = int(entry_length) - data_offset_rel
            content_offset = uncompr_offset - data_offset_rel if uncompr_offset >= data_offset_rel else 0

            if data_len > 0 and fqn:
                result.append(
                    BucketNodeEntry(
                        fqn=fqn,
                        node_id=node_id,
                        base_class_id=base_class_id,
                        data_offset=data_abs,
                        data_length=data_len,
                        node_content_length=node_content_length,
                        content_offset=content_offset,
                        stream_style=stream_style,
                        bitset=bitset,
                        bucket_path=bucket_path,
                    )
                )

            rel = start_offset - dblb_start + entry_length
            pos = dblb_start + ((rel + 7) & ~7)

        pos = dblb_start + dblb_length

    return result


def normalize_node_payload(raw: bytes, content_offset: int, bitset: int) -> bytes:
    if not raw:
        return raw

    if bitset == 14:
        decompressed = raw
    elif len(raw) >= 2:
        magic = raw[0] | (raw[1] << 8)
        if magic == MAGIC_ZSTD:
            import zstandard

            dctx = zstandard.ZstdDecompressor()
            decompressed = dctx.decompress(raw)
        elif magic == MAGIC_ZLIB or raw[0] == 0x78:
            try:
                decompressed = zlib.decompress(raw)
            except zlib.error:
                if len(raw) > 6:
                    try:
                        decompressed = zlib.decompress(raw[2:-4], -zlib.MAX_WBITS)
                    except zlib.error:
                        decompressed = raw
                else:
                    decompressed = raw
        else:
            decompressed = raw
    else:
        decompressed = raw

    if 0 < content_offset < len(decompressed):
        return decompressed[content_offset:]
    return decompressed


def extract_node_payload(bucket_data: bytes, entry: BucketNodeEntry) -> bytes:
    raw = bucket_data[entry.data_offset : entry.data_offset + entry.data_length]
    return normalize_node_payload(raw, entry.content_offset, entry.bitset)


def fqn_to_relative_path(fqn: str, suffix: str = ".json") -> Path:
    parts = [p for p in fqn.split(".") if p]
    if not parts:
        return Path("_" + suffix)
    invalid = re.compile(r'[<>:"/\\|?*]')
    safe = [invalid.sub("_", part) for part in parts]
    return Path(*safe[:-1]) / f"{safe[-1]}{suffix}"
