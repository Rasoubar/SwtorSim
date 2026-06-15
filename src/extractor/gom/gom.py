from __future__ import annotations

import json
import re
from pathlib import Path

from extractor.config import DATA_DIR
from extractor.gom.client_gom import ClientGomData, enum_ref_for_field, load_client_gom

GOM_JS_FILENAME = "gom.js"


def parse_gom_js(path: Path) -> dict[str, dict[str, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    result = {"classes": {}, "fields": {}, "enums": {}}
    patterns = {
        "classes": re.compile(r"GOM\.classes\['(\d+)'\]\s*=\s*'([^']*)'"),
        "fields": re.compile(r"GOM\.fields\['(\d+)'\]\s*=\s*'([^']*)'"),
        "enums": re.compile(r"GOM\.enums\['(\d+)'\]\s*=\s*'([^']*)'"),
    }
    for key, pattern in patterns.items():
        for match in pattern.finditer(text):
            result[key][match.group(1)] = match.group(2)
    return result


def load_gom_names(path: Path | None = None) -> dict[str, dict[str, str]]:
    if path is None:
        path = DATA_DIR / GOM_JS_FILENAME
    if path.suffix == ".js":
        return parse_gom_js(path)
    return json.loads(path.read_text(encoding="utf-8"))


class GomLookup:
    def __init__(
        self,
        names: dict[str, dict[str, str]] | None = None,
        client_gom: ClientGomData | None = None,
    ):
        names = names or load_gom_names()
        self.classes = names.get("classes", {})
        self.fields = names.get("fields", {})
        self.enums = names.get("enums", {})
        self._client_gom = client_gom

    @classmethod
    def from_resources(
        cls,
        resources_root: Path | None = None,
        *,
        names: dict[str, dict[str, str]] | None = None,
    ) -> GomLookup:
        lookup = cls(names=names)
        if resources_root is None:
            return lookup
        client_gom_path = resources_root / "systemgenerated" / "client.gom"
        if client_gom_path.exists():
            lookup._client_gom = load_client_gom(client_gom_path)
        return lookup

    def class_name(self, class_id: int | str) -> str:
        return self.classes.get(str(class_id), str(class_id))

    def field_name(self, field_id: int | str) -> str:
        return self.fields.get(str(field_id), str(field_id))

    def enum_name(self, enum_id: int | str) -> str:
        return self.enums.get(str(enum_id), str(enum_id))

    def enum_member(self, enum_type_id: str | None, index: int) -> str:
        if enum_type_id and self._client_gom is not None:
            members = self._client_gom.enum_members.get(str(enum_type_id))
            if members and 1 <= index <= len(members):
                return members[index - 1]
        if enum_type_id:
            type_name = self.enum_name(enum_type_id)
            if type_name != str(enum_type_id):
                return f"{type_name}[{index}]"
        return str(index)

    def field_enum_ref(self, field_id: str) -> str | None:
        if self._client_gom is None:
            return None
        field_type = self._client_gom.field_types.get(str(field_id))
        return enum_ref_for_field(field_type)

    def lookup_list_enum_refs(self, field_id: str) -> tuple[str | None, str | None]:
        if self._client_gom is None:
            return None, None
        field_type = self._client_gom.field_types.get(str(field_id))
        if field_type is None or field_type.dom_type != 8:  # DOM_LOOKUP_LIST
            return None, None
        key_ref = enum_ref_for_field(field_type.index) if field_type.index else None
        val_ref = enum_ref_for_field(field_type.element) if field_type.element else None
        return key_ref, val_ref
