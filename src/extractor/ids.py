from __future__ import annotations

import struct

# JavaScript Number.MAX_SAFE_INTEGER — GOM IDs exceed this; never round-trip
# large IDs through JSON numbers if the consumer is JS.
JS_MAX_SAFE_INTEGER = (1 << 53) - 1


def bswap32(value: int) -> int:
    """Reverse the four bytes of a uint32."""
    return int.from_bytes((value & 0xFFFFFFFF).to_bytes(4, "little")[::-1], "little")


def canonical_u64(wire: int) -> int:
    """Convert a wire-encoded SWTOR uint64 to its canonical unsigned value.

    Multi-byte varints (prefix 0xC4-0xCF) store each 32-bit half with its bytes
    reversed relative to a normal little-endian uint64. Node IDs (0xE000…), GOM
    field IDs (0x4000…), and other database keys all use this encoding.
    """
    wire &= (1 << 64) - 1
    lo = wire & 0xFFFFFFFF
    hi = wire >> 32
    return bswap32(lo) | (bswap32(hi) << 32)


def is_wire_u64_varint(first_byte: int) -> bool:
    """True when a varint prefix carries a wire-encoded 64-bit key."""
    return first_byte >= 0xC4


def apply_field_id_delta(prev_id: int, delta_wire: int, first_byte: int) -> int:
    """Accumulate a delta-encoded GOM field ID."""
    mask = (1 << 64) - 1
    if is_wire_u64_varint(first_byte) and prev_id == 0:
        return canonical_u64(delta_wire)
    return (prev_id + delta_wire) & mask


def u64_str(value: int) -> str:
    """Canonical string form for a 64-bit game ID or hash."""
    if value < 0:
        value &= (1 << 64) - 1
    return str(value)


def read_u64_le(data: bytes | memoryview, pos: int) -> tuple[int, int]:
    (value,) = struct.unpack_from("<Q", data, pos)
    return value, 8


def read_i64_le(data: bytes | memoryview, pos: int) -> tuple[int, int]:
    (value,) = struct.unpack_from("<q", data, pos)
    return value, 8
