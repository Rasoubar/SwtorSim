from __future__ import annotations

import struct
from dataclasses import dataclass

from src.extractor.ids import u64_str


@dataclass
class StbEntry:
    string_id: str
    text: str


class StringTable:
    def __init__(self, data: bytes):
        self._by_id: dict[str, str] = {}
        self._parse(data)

    def _parse(self, data: bytes) -> None:
        if len(data) < 7:
            return
        num_strings = struct.unpack_from("<I", data, 3)[0]
        pos = 7
        entries: list[tuple[str, int, int]] = []
        for _ in range(num_strings):
            if pos + 24 > len(data):
                break
            string_id = u64_str(struct.unpack_from("<Q", data, pos)[0])
            pos += 8
            pos += 2  # bitflag
            pos += 4  # version float
            length = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            offset = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            pos += 4  # len2
            entries.append((string_id, offset, length))

        for string_id, offset, length in entries:
            if offset + length <= len(data):
                text = data[offset : offset + length].decode("utf-8", errors="replace")
                self._by_id[string_id] = text

    def get(self, string_id: str | int) -> str | None:
        return self._by_id.get(str(string_id))

    def __contains__(self, string_id: str | int) -> bool:
        return str(string_id) in self._by_id

    def __len__(self) -> int:
        return len(self._by_id)
