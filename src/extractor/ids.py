from __future__ import annotations

import struct

# JavaScript Number.MAX_SAFE_INTEGER — GOM IDs exceed this; never round-trip
# large IDs through JSON numbers if the consumer is JS.
JS_MAX_SAFE_INTEGER = (1 << 53) - 1


def apply_field_id_delta(prev_id: int, delta_wire: int, first_byte: int) -> int:
    """Accumulate a delta-encoded GOM field ID."""
    mask = (1 << 64) - 1
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
