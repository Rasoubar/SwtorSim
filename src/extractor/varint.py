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
    def magnitude(self) -> int:
        return ((self.int_hi & 0xFFFFFFFF) << 32) | (self.int_lo & 0xFFFFFFFF)

    @property
    def value(self) -> int:
        return self.sign * self.magnitude

    @property
    def unsigned_delta(self) -> int:
        if self.sign < 0:
            return (-self.magnitude) & 0xFFFFFFFFFFFFFFFF
        return self.magnitude


def read_swtor_varint(data: bytes | memoryview, pos: int = 0) -> SwtorVarInt:
    """Read SWTOR's custom wire varint."""
    if pos >= len(data):
        raise IndexError("index out of range")

    first = data[pos]
    if first < 0xC0 or first > 0xCF:
        return SwtorVarInt(1, first, 0, 1)

    if first <= 0xC7:
        length = first - 0xBF
        sign = -1
    else:
        length = first - 0xC7
        sign = 1

    end = pos + 1 + length
    if end > len(data):
        raise IndexError("index out of range")
    magnitude = int.from_bytes(data[pos + 1 : end], "big")
    return SwtorVarInt(
        sign=sign,
        int_lo=magnitude & 0xFFFFFFFF,
        int_hi=(magnitude >> 32) & 0xFFFFFFFF,
        consumed=1 + length,
    )


def swtor_varint_uint(data: bytes | memoryview, pos: int = 0) -> tuple[int, int]:
    """Return (wire uint64 value, bytes consumed). Sign is ignored."""
    parsed = read_swtor_varint(data, pos)
    return parsed.magnitude, parsed.consumed


def read_varint(data: bytes | memoryview, pos: int = 0) -> tuple[int, int]:
    """Read a non-negative SWTOR varint used for counts and list indexes."""
    return swtor_varint_uint(data, pos)


def read_signed_varint(data: bytes | memoryview, pos: int = 0) -> tuple[int, int]:
    """Read a signed-magnitude SWTOR scalar integer."""
    parsed = read_swtor_varint(data, pos)
    return parsed.value, parsed.consumed


def read_field_id_delta(data: bytes | memoryview, pos: int = 0) -> tuple[int, int]:
    """Read a field-ID delta, converting negative magnitudes to uint64 deltas."""
    parsed = read_swtor_varint(data, pos)
    return parsed.unsigned_delta, parsed.consumed


def read_u64_varint(data: bytes | memoryview, pos: int = 0) -> tuple[int, int]:
    """Read a signed SWTOR ID/reference varint."""
    parsed = read_swtor_varint(data, pos)
    return parsed.value, parsed.consumed


def read_varint_from_stream(stream: BinaryIO) -> int:
    header = stream.read(1)
    if not header:
        raise EOFError("Unexpected EOF while reading varint")
    first = header[0]
    if first < 0xC0 or first > 0xCF:
        return first
    extra = first - (0xBF if first <= 0xC7 else 0xC7)
    rest = stream.read(extra)
    if len(rest) != extra:
        raise EOFError("Unexpected EOF while reading varint")
    return read_swtor_varint(header + rest, 0).value


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
    from src.extractor.ids import u64_str

    return u64_str((hi << 32) | lo)


def combine_lo_hi(lo: int, hi: int = 0) -> int:
    return (hi << 32) | (lo & 0xFFFFFFFF)


def read_u64_le(data: bytes | memoryview, pos: int) -> tuple[int, int]:
    from src.extractor.ids import read_u64_le as _read

    return _read(data, pos)


def read_f32_le(data: bytes | memoryview, pos: int) -> tuple[float, int]:
    (value,) = struct.unpack_from("<f", data, pos)
    return value, 4
