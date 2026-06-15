from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import BinaryIO


@dataclass(frozen=True)
class SwtorVarInt:
    sign: int
    int_lo: int
    int_hi: int
    consumed: int

    @property
    def value(self) -> int:
        return ((self.int_hi & 0xFFFFFFFF) << 32) | (self.int_lo & 0xFFFFFFFF)


def read_swtor_varint(data: bytes | memoryview, pos: int = 0) -> SwtorVarInt:
    """Read SWTOR's custom wire varint."""
    if pos >= len(data):
        raise IndexError("index out of range")

    first = data[pos]

    if first == 0xC0:
        return SwtorVarInt(-1, data[pos + 1], 0, 2)
    if first == 0xC1:
        (int_lo,) = struct.unpack_from(">H", data, pos + 1)
        return SwtorVarInt(-1, int_lo, 0, 3)
    if first == 0xC2:
        int_lo = (data[pos + 1] << 8) | data[pos + 2]
        int_lo = (int_lo << 8) | data[pos + 3]
        return SwtorVarInt(-1, int_lo, 0, 4)
    if first == 0xC3:
        (int_lo,) = struct.unpack_from(">I", data, pos + 1)
        return SwtorVarInt(-1, int_lo, 0, 5)
    if first == 0xC4:
        int_hi = data[pos + 1]
        (int_lo,) = struct.unpack_from("<I", data, pos + 2)
        return SwtorVarInt(-1, int_lo, int_hi, 6)
    if first == 0xC5:
        (int_hi,) = struct.unpack_from("<H", data, pos + 1)
        (int_lo,) = struct.unpack_from("<I", data, pos + 3)
        return SwtorVarInt(-1, int_lo, int_hi, 7)
    if first == 0xC6:
        int_hi = (data[pos + 1] << 16) | (data[pos + 2] << 8) | data[pos + 3]
        (int_lo,) = struct.unpack_from("<I", data, pos + 4)
        return SwtorVarInt(-1, int_lo, int_hi, 8)
    if first == 0xC7:
        (int_hi,) = struct.unpack_from("<I", data, pos + 1)
        (int_lo,) = struct.unpack_from("<I", data, pos + 5)
        return SwtorVarInt(-1, int_lo, int_hi, 9)

    if first == 0xC8:
        return SwtorVarInt(1, data[pos + 1], 0, 2)
    if first == 0xC9:
        (int_lo,) = struct.unpack_from(">H", data, pos + 1)
        return SwtorVarInt(1, int_lo, 0, 3)
    if first == 0xCA:
        int_lo = (data[pos + 1] << 16) | (data[pos + 2] << 8) | data[pos + 3]
        return SwtorVarInt(1, int_lo, 0, 4)
    if first == 0xCB:
        (int_lo,) = struct.unpack_from(">I", data, pos + 1)
        return SwtorVarInt(1, int_lo, 0, 5)
    if first == 0xCC:
        int_hi = data[pos + 1]
        (int_lo,) = struct.unpack_from("<I", data, pos + 2)
        return SwtorVarInt(1, int_lo, int_hi, 6)
    if first == 0xCD:
        (int_hi,) = struct.unpack_from("<H", data, pos + 1)
        (int_lo,) = struct.unpack_from("<I", data, pos + 3)
        return SwtorVarInt(1, int_lo, int_hi, 7)
    if first == 0xCE:
        int_hi = (data[pos + 1] << 16) | (data[pos + 2] << 8) | data[pos + 3]
        (int_lo,) = struct.unpack_from("<I", data, pos + 4)
        return SwtorVarInt(1, int_lo, int_hi, 8)
    if first == 0xCF:
        (int_hi,) = struct.unpack_from("<I", data, pos + 1)
        (int_lo,) = struct.unpack_from("<I", data, pos + 5)
        return SwtorVarInt(1, int_lo, int_hi, 9)

    return SwtorVarInt(1, first, 0, 1)


def swtor_varint_uint(data: bytes | memoryview, pos: int = 0) -> tuple[int, int]:
    """Return (wire uint64 value, bytes consumed). Sign is ignored."""
    parsed = read_swtor_varint(data, pos)
    return parsed.value, parsed.consumed


def read_varint(data: bytes | memoryview, pos: int = 0) -> tuple[int, int]:
    """Read a SWTOR varint and return the raw wire integer."""
    return swtor_varint_uint(data, pos)


def read_u64_varint(data: bytes | memoryview, pos: int = 0) -> tuple[int, int]:
    """Read a varint and decode wire-encoded 64-bit database keys (prefix >= 0xC4)."""
    from extractor.ids import canonical_u64, is_wire_u64_varint

    parsed = read_swtor_varint(data, pos)
    value = parsed.value
    if is_wire_u64_varint(data[pos]):
        value = canonical_u64(value)
    return value, parsed.consumed


def read_varint_from_stream(stream: BinaryIO) -> int:
    header = stream.read(1)
    if not header:
        raise EOFError("Unexpected EOF while reading varint")
    first = header[0]
    if first <= 0xCF and first != 0xC0:
        extra = {0xC1: 1, 0xC2: 2, 0xC3: 3, 0xC4: 4, 0xC5: 5, 0xC6: 6, 0xC7: 7,
                 0xC8: 0, 0xC9: 1, 0xCA: 2, 0xCB: 3, 0xCC: 4, 0xCD: 5, 0xCE: 6, 0xCF: 7}.get(first, 0)
        if extra:
            rest = stream.read(extra)
            if len(rest) != extra:
                raise EOFError("Unexpected EOF while reading varint")
            chunk = header + rest
            if first >= 0xC8:
                return read_swtor_varint(chunk, 0).value
            return read_swtor_varint(chunk, 0).value
    return first


def read_cstring(data: bytes | memoryview, pos: int) -> str:
    end = pos
    length = len(data)
    while end < length and data[end] != 0:
        end += 1
    return bytes(data[pos:end]).decode("utf-8", errors="replace")


def read_length_prefixed_string(data: bytes | memoryview, pos: int) -> tuple[str, int]:
    length, len_bytes = swtor_varint_uint(data, pos)
    start = pos + len_bytes
    end = start + length
    raw = bytes(data[start:end])
    if raw.endswith(b"\x00"):
        raw = raw[:-1]
    return raw.decode("utf-8", errors="replace"), len_bytes + length


def uint64_to_str(lo: int, hi: int = 0) -> str:
    from extractor.ids import u64_str

    return u64_str((hi << 32) | lo)


def combine_lo_hi(lo: int, hi: int = 0) -> int:
    return (hi << 32) | (lo & 0xFFFFFFFF)


def read_u64_le(data: bytes | memoryview, pos: int) -> tuple[int, int]:
    from extractor.ids import read_u64_le as _read

    return _read(data, pos)


def read_f32_le(data: bytes | memoryview, pos: int) -> tuple[float, int]:
    (value,) = struct.unpack_from("<f", data, pos)
    return value, 4
