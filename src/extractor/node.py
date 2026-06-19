from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from extractor.ids import apply_field_id_delta, u64_str
from extractor.varint import (
    read_field_id_delta,
    read_f32_le,
    read_length_prefixed_string,
    read_signed_varint,
    read_u64_varint,
    read_varint,
)

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

DOM_TYPE_NAMES = {
    DOM_ID: "ID",
    DOM_INTEGER: "Integer",
    DOM_BOOLEAN: "Boolean",
    DOM_FLOAT: "Float",
    DOM_ENUM: "Enum",
    DOM_STRING: "String",
    DOM_LIST: "List",
    DOM_LOOKUP_LIST: "LookupList",
    DOM_CLASS: "Class",
    DOM_SCRIPT_REF: "ScriptRef",
    DOM_NODE_REF: "NodeRef",
    DOM_VECTOR3: "Vector3",
    DOM_TIME_INTERVAL: "TimeInterval",
    DOM_DATE: "Date",
}


@dataclass
class ParsedField:
    id: str
    name: str
    dom_type: int
    dom_type_name: str
    value: Any


@dataclass
class ParsedNode:
    fields: list[ParsedField] = field(default_factory=list)
    stream_style: int = 1


def _id_to_str(value: int) -> str:
    return u64_str(value)


def read_field_value(
    data: bytes | memoryview,
    pos: int,
    dom_type: int,
    field_id: str = "0",
) -> tuple[Any, int]:
    if dom_type in (DOM_ID, DOM_SCRIPT_REF, DOM_NODE_REF):
        value, consumed = read_u64_varint(data, pos)
        if dom_type == DOM_NODE_REF:
            return {"ref_id": _id_to_str(value)}, consumed
        if dom_type == DOM_SCRIPT_REF:
            return {"script_ref_id": _id_to_str(value)}, consumed
        return _id_to_str(value), consumed

    if dom_type in (DOM_INTEGER, DOM_TIME_INTERVAL, DOM_DATE):
        value, consumed = read_signed_varint(data, pos)
        return _id_to_str(value), consumed

    if dom_type == DOM_BOOLEAN:
        return bool(data[pos]), 1

    if dom_type == DOM_FLOAT:
        value, consumed = read_f32_le(data, pos)
        return value, consumed

    if dom_type == DOM_ENUM:
        value, consumed = read_varint(data, pos)
        return {"index": value}, consumed

    if dom_type == DOM_STRING:
        return read_length_prefixed_string(data, pos)

    if dom_type == DOM_VECTOR3:
        x, _ = read_f32_le(data, pos)
        y, _ = read_f32_le(data, pos + 4)
        z, _ = read_f32_le(data, pos + 8)
        return [x, y, z], 12

    if dom_type == DOM_LIST:
        start = pos
        element_type = data[pos]
        pos += 1
        count1, c1 = read_varint(data, pos)
        pos += c1
        count2, c2 = read_varint(data, pos)
        pos += c2
        elements: list[Any] = []
        for _ in range(count1):
            _, ic = read_varint(data, pos)
            pos += ic
            elem, ec = read_field_value(data, pos, element_type)
            pos += ec
            elements.append(elem)
        return {
            "element_type": element_type,
            "element_type_name": DOM_TYPE_NAMES.get(element_type, str(element_type)),
            "list": elements,
        }, pos - start

    if dom_type == DOM_LOOKUP_LIST:
        start = pos
        key_type = data[pos]
        value_type = data[pos + 1]
        pos += 2
        count1, c1 = read_varint(data, pos)
        pos += c1
        count2, c2 = read_varint(data, pos)
        pos += c2
        entries: list[dict[str, Any]] = []
        for _ in range(count1):
            if pos < len(data) and data[pos] == 0xD2:
                pos += 1
            key, kc = read_field_value(data, pos, key_type)
            pos += kc
            val, vc = read_field_value(data, pos, value_type)
            pos += vc
            entries.append({"key": key, "value": val})
        return {
            "key_type": key_type,
            "value_type": value_type,
            "list": entries,
        }, pos - start

    if dom_type == DOM_CLASS:
        start = pos
        pos += 1  # const7
        num_fields, nf = read_varint(data, pos)
        pos += nf
        prev_id = 0
        children: list[dict[str, Any]] = []
        for _ in range(num_fields):
            first_byte = data[pos]
            delta, dc = read_field_id_delta(data, pos)
            pos += dc
            prev_id = apply_field_id_delta(prev_id, delta, first_byte)
            child_type = data[pos]
            pos += 1
            child_val, cc = read_field_value(data, pos, child_type, _id_to_str(prev_id))
            pos += cc
            children.append(
                {
                    "id": _id_to_str(prev_id),
                    "type": child_type,
                    "type_name": DOM_TYPE_NAMES.get(child_type, str(child_type)),
                    "value": child_val,
                }
            )
        return children, pos - start

    return None, 0


def parse_node_fields(
    data: bytes,
    stream_style: int = 1,
    field_name_lookup: dict[str, str] | None = None,
) -> ParsedNode:
    field_name_lookup = field_name_lookup or {}
    pos = 0
    if 1 <= stream_style <= 6:
        _, consumed = read_varint(data, pos)
        pos += consumed

    num_fields, consumed = read_varint(data, pos)
    pos += consumed

    fields: list[ParsedField] = []
    prev_id = 0
    for _ in range(num_fields):
        first_byte = data[pos]
        delta, dc = read_field_id_delta(data, pos)
        pos += dc
        prev_id = apply_field_id_delta(prev_id, delta, first_byte)
        dom_type = data[pos]
        pos += 1
        field_id = _id_to_str(prev_id)
        value, vc = read_field_value(data, pos, dom_type, field_id)
        pos += vc
        fields.append(
            ParsedField(
                id=field_id,
                name=field_name_lookup.get(field_id, field_id),
                dom_type=dom_type,
                dom_type_name=DOM_TYPE_NAMES.get(dom_type, str(dom_type)),
                value=value,
            )
        )

    return ParsedNode(fields=fields, stream_style=stream_style)


def _looks_like_node_id(value: str) -> bool:
    return value.isdigit() and len(value) >= 17 and value.startswith("1614")


def collect_node_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        if "ref_id" in value:
            refs.add(str(value["ref_id"]))
        for child in value.values():
            refs |= collect_node_refs(child)
    elif isinstance(value, list):
        for item in value:
            refs |= collect_node_refs(item)
    elif isinstance(value, str) and _looks_like_node_id(value):
        refs.add(value)
    return refs


def fields_to_dict(fields: list[ParsedField]) -> list[dict[str, Any]]:
    return [
        {
            "id": f.id,
            "name": f.name,
            "type": f.dom_type,
            "type_name": f.dom_type_name,
            "value": f.value,
        }
        for f in fields
    ]
