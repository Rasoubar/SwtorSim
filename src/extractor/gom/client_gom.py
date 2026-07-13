from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from extractor.ids import read_u64_le, u64_str
from extractor.varint import read_swtor_varint

DBLB_MAGIC = 0x424C4244

DOM_NONE = 0
DOM_ID = 1
DOM_INTEGER = 2
DOM_BOOLEAN = 3
DOM_FLOAT = 4
DOM_ENUM = 5
DOM_STRING = 6
DOM_LIST = 7
DOM_LOOKUP_LIST = 8
DOM_CLASS = 9
DOM_SCRIPT_REF = 14
DOM_NODE_REF = 15
DOM_VECTOR3 = 18
DOM_TIME_INTERVAL = 20
DOM_DATE = 21
DOM_TUPLE = 24


@dataclass
class DomType:
    dom_type: int
    ref: str | None = None
    index: DomType | None = None
    element: DomType | None = None
    elements: list[DomType] = field(default_factory=list)


@dataclass
class ClientGomData:
    enum_members: dict[str, list[str]]
    field_types: dict[str, DomType]


def _read_cstring(data: bytes | memoryview, offset: int) -> tuple[str, int]:
    end = data.find(b"\x00", offset)
    if end < 0:
        end = len(data)
    return bytes(data[offset:end]).decode("utf-8", errors="replace"), end + 1


def _read_type(data: bytes | memoryview, offset: int) -> tuple[DomType, int]:
    start = offset
    dom_type = data[offset]
    pos = offset + 1

    if dom_type == DOM_ENUM:
        ref, consumed = read_u64_le(data, pos)
        return DomType(dom_type=dom_type, ref=u64_str(ref)), 1 + consumed

    if dom_type == DOM_LIST:
        element, consumed = _read_type(data, pos)
        return DomType(dom_type=dom_type, element=element), 1 + consumed

    if dom_type == DOM_LOOKUP_LIST:
        index_type, index_consumed = _read_type(data, pos)
        element_type, element_consumed = _read_type(data, pos + index_consumed)
        return (
            DomType(
                dom_type=dom_type,
                index=index_type,
                element=element_type,
            ),
            1 + index_consumed + element_consumed,
        )

    if dom_type in (DOM_CLASS, DOM_NODE_REF, DOM_SCRIPT_REF):
        ref, consumed = read_u64_le(data, pos)
        return DomType(dom_type=dom_type, ref=u64_str(ref)), 1 + consumed

    if dom_type == DOM_TUPLE:
        parsed = read_swtor_varint(data, pos)
        pos += parsed.consumed
        elements: list[DomType] = []
        for _ in range(parsed.int_lo):
            element, consumed = _read_type(data, pos)
            pos += consumed
            elements.append(element)
        return DomType(dom_type=dom_type, elements=elements), pos - start

    return DomType(dom_type=dom_type), 1


def parse_client_gom(data: bytes) -> ClientGomData:
    if len(data) < 8:
        raise ValueError("client.gom too small")
    magic = struct.unpack_from("<I", data, 0)[0]
    if magic != DBLB_MAGIC:
        raise ValueError(f"Expected DBLB magic, got {magic:#x}")

    dblb_version = struct.unpack_from("<I", data, 4)[0]
    if dblb_version not in (1, 2):
        raise ValueError(f"Unsupported client.gom DBLB version {dblb_version}")

    enum_members: dict[str, list[str]] = {}
    field_types: dict[str, DomType] = {}
    pos = 8

    while pos < len(data):
        start_offset = pos
        entry_length = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        if entry_length == 0:
            break

        if dblb_version == 2:
            pos += 4  # name_hash
            entry_id, id_size = read_u64_le(data, pos)
            pos += id_size
            type_bitflag = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            entry_type = (type_bitflag >> 3) & 0b111
            pos += 2  # compr_data_offset
            pos += 2  # name_offset
            pos += 2  # desc_offset
        else:
            type_bitflag = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            entry_type = (type_bitflag >> 3) & 7
            pos += 2  # compr_data_offset
            entry_id, id_size = read_u64_le(data, pos)
            pos += id_size
            pos += 2  # name_offset
            pos += 2  # desc_offset

        entry_id_str = u64_str(entry_id)

        if entry_type == 2:
            num_values = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            offsets_offset = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            values: list[str] = []
            values_pos = start_offset + offsets_offset
            for _ in range(num_values):
                string_offset = struct.unpack_from("<H", data, values_pos)[0]
                values_pos += 2
                value, _ = _read_cstring(data, start_offset + string_offset)
                values.append(value)
            enum_members[entry_id_str] = values
        elif entry_type == 3:
            pos += 2  # unknown_bitset
            type_length = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            type_offset = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            field_type, type_consumed = _read_type(data, start_offset + type_offset)
            if type_consumed != type_length:
                pass  # tolerate minor mismatches in older patches
            field_types[entry_id_str] = field_type

        pos = (start_offset + entry_length + 7) & ~7

    return ClientGomData(enum_members=enum_members, field_types=field_types)


def load_client_gom(path: Path) -> ClientGomData:
    return parse_client_gom(path.read_bytes())


def enum_ref_for_field(field_type: DomType | None) -> str | None:
    if field_type is None:
        return None
    if field_type.dom_type == DOM_ENUM:
        return field_type.ref
    if field_type.dom_type == DOM_LOOKUP_LIST and field_type.index is not None:
        return enum_ref_for_field(field_type.index)
    if field_type.dom_type == DOM_LIST and field_type.element is not None:
        return enum_ref_for_field(field_type.element)
    return None
