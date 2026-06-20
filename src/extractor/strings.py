from __future__ import annotations

from pathlib import Path
from typing import Any

from extractor.config import LOC_ENGLISH_KEY, LOC_STR_BUCKET_FIELD, LOC_STR_ID_FIELD
from extractor.stb import StringTable


def convert_loc_retriever(value: Any) -> dict[str, tuple[str, str]]:
    """Map language id -> (stb_bucket, string_id)."""
    if not isinstance(value, dict) or "list" not in value:
        return {}
    out: dict[str, tuple[str, str]] = {}
    for entry in value.get("list", []):
        if not isinstance(entry, dict):
            continue
        lang_key = str(entry.get("key", ""))
        fields = entry.get("value", [])
        if not isinstance(fields, list):
            continue
        str_id = ""
        bucket = ""
        for field in fields:
            if not isinstance(field, dict):
                continue
            fid = str(field.get("id", ""))
            fval = field.get("value")
            if fid == LOC_STR_ID_FIELD:
                if isinstance(fval, dict) and "ref_id" in fval:
                    str_id = str(fval["ref_id"])
                else:
                    str_id = str(fval)
            elif fid == LOC_STR_BUCKET_FIELD:
                bucket = str(fval)
        if lang_key and bucket and str_id:
            out[lang_key] = (bucket, str_id)
    return out


class StringResolver:
    _STB_BUCKET_ALIASES = {
        "str.itm": "itm",
    }

    def __init__(self, resources_root: Path):
        self.resources_root = resources_root
        self._tables: dict[str, StringTable] = {}
        self._stb_root = resources_root / "en-us" / "str"
        if not self._stb_root.exists():
            self._stb_root = resources_root / "resources" / "en-us" / "str"

    def load_bucket(self, bucket_name: str) -> StringTable | None:
        bucket_name = self._STB_BUCKET_ALIASES.get(bucket_name, bucket_name)
        if bucket_name in self._tables:
            return self._tables[bucket_name]
        stb_path = self._stb_root / f"{bucket_name}.stb"
        if not stb_path.exists():
            stb_path = self._stb_root / bucket_name.replace(".", "/")
            if not stb_path.suffix:
                stb_path = stb_path.with_suffix(".stb")
        if not stb_path.exists():
            return None
        table = StringTable(stb_path.read_bytes())
        self._tables[bucket_name] = table
        return table

    def resolve(self, bucket_name: str, string_id: str) -> str | None:
        table = self.load_bucket(bucket_name)
        if table is None:
            return None
        return table.get(string_id)

    def resolve_loc_retriever(self, value: Any, lang_key: str = LOC_ENGLISH_KEY) -> str | None:
        mapping = convert_loc_retriever(value)
        if lang_key not in mapping:
            if mapping:
                lang_key = next(iter(mapping))
            else:
                return None
        bucket, string_id = mapping[lang_key]
        return self.resolve(bucket, string_id)


# Field IDs known to carry loc retriever lookup lists on abilities/talents.
LOC_RETRIEVER_FIELD_IDS = frozenset(
    {
        "4611686102842470023",  # common loc retriever on abl/tal
    }
)
