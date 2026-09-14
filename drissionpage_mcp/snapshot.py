"""Bounded, redacted page-search results with short-lived cursors."""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from collections import OrderedDict
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .response_json import redact_public_payload, redact_public_text, strict_json_dumps

_PRIVATE_PATH = re.compile(
    r"(?<!\w)(?:/(?:Users|home|private|tmp|var)/[^\s<>]+|[A-Za-z]:\\[^\s<>]+)"
)


class SnapshotCursorError(ValueError):
    code = "SNAPSHOT_CURSOR_INVALID"

    def __init__(self) -> None:
        super().__init__(
            "Invalid or expired snapshot cursor. Repeat the query without a cursor."
        )


@dataclass
class _Snapshot:
    tab_id: str
    binding: str
    expires: float
    payload: dict[str, Any]
    size: int


class SnapshotStore:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        ttl: float = 30,
        max_entries: int = 32,
        max_entries_per_tab: int = 4,
        max_bytes_per_tab: int = 262144,
        max_bytes: int = 2097152,
    ) -> None:
        self._clock, self._ttl = clock, ttl
        self._max_entries, self._per_tab = max_entries, max_entries_per_tab
        self._tab_bytes, self._max_bytes = max_bytes_per_tab, max_bytes
        self._entries: OrderedDict[str, _Snapshot] = OrderedDict()
        self._secret = uuid4().bytes

    @property
    def size_bytes(self) -> int:
        return sum(item.size for item in self._entries.values())

    def clear_tab(self, tab_id: str) -> None:
        for key, item in list(self._entries.items()):
            if item.tab_id == tab_id:
                del self._entries[key]

    def clear(self) -> None:
        self._entries.clear()

    def search(
        self,
        *,
        tab_id: str,
        document_id: str,
        query: str,
        max_elements: int,
        max_text_chars: int,
        capture: dict[str, Any] | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        now = self._clock()
        for key, item in list(self._entries.items()):
            if item.expires <= now:
                del self._entries[key]
        binding = hashlib.sha256(
            strict_json_dumps(
                [tab_id, document_id, query, max_elements, max_text_chars]
            ).encode()
        ).hexdigest()
        offset = 0
        if cursor:
            try:
                identifier, raw_offset, _ = cursor.split(":")
                item = self._entries[identifier]
                offset = int(raw_offset)
                if not hmac.compare_digest(self._cursor(identifier, offset), cursor):
                    raise SnapshotCursorError()
                if item.binding != binding or not 0 < offset < len(
                    item.payload["matches"]
                ):
                    raise SnapshotCursorError()
            except (ValueError, KeyError) as exc:
                raise SnapshotCursorError() from exc
        else:
            if capture is None or capture.get("document_id") != document_id:
                raise SnapshotCursorError()
            payload = _prepare(capture, query, max_text_chars)
            size = len(strict_json_dumps(payload).encode())
            if size > min(self._tab_bytes, self._max_bytes):
                raise ValueError(
                    "Snapshot query exceeds the cache budget; use a narrower query."
                )
            same_tab = [
                key for key, value in self._entries.items() if value.tab_id == tab_id
            ]
            while same_tab and (
                len(same_tab) >= self._per_tab
                or sum(self._entries[key].size for key in same_tab) + size
                > self._tab_bytes
            ):
                del self._entries[same_tab.pop(0)]
            while self._entries and (
                self.size_bytes + size > self._max_bytes
                or len(self._entries) >= self._max_entries
            ):
                self._entries.popitem(last=False)
            identifier = uuid4().hex
            item = _Snapshot(tab_id, binding, now + self._ttl, payload, size)
            self._entries[identifier] = item
        result, selected, remaining = deepcopy(item.payload), [], max_text_chars
        for match in result["matches"][offset : offset + max_elements]:
            if not remaining:
                break
            if len(match["text"]) > remaining:
                match["text"], match["truncated"] = (
                    _snippet(match["text"], query, remaining),
                    True,
                )
            selected.append(match)
            remaining -= len(match["text"])
        next_offset = offset + len(selected)
        has_more = next_offset < result["match_count"]
        result.update(
            observation_id=identifier,
            matches=selected,
            returned=len(selected),
            has_more=has_more,
            next_cursor=self._cursor(identifier, next_offset) if has_more else None,
            limits={
                "max_elements": max_elements,
                "max_text_chars": max_text_chars,
                "ttl_seconds": self._ttl,
            },
        )
        return result

    def _cursor(self, identifier: str, offset: int) -> str:
        prefix = f"{identifier}:{offset}"
        signature = hmac.new(self._secret, prefix.encode(), hashlib.sha256).hexdigest()[
            :24
        ]
        return f"{prefix}:{signature}"


def _snippet(text: str, query: str, limit: int) -> str:
    start = max(0, text.lower().find(query.lower()) - min(60, limit // 3))
    return text[start : start + limit]


def _prepare(
    capture: dict[str, Any], query: str, max_text_chars: int
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for candidate in capture["candidates"]:
        text = _PRIVATE_PATH.sub("<redacted>", redact_public_text(candidate["text"]))
        if query.lower() not in text.lower():
            continue
        snippet = _snippet(text, query, min(500, max_text_chars))
        matches.append(
            {
                "index": len(matches),
                "text": snippet,
                "tag": candidate["tag"],
                "category": candidate["category"],
                "selector": _PRIVATE_PATH.sub(
                    "<redacted>", redact_public_text(candidate["selector"])
                ),
                "truncated": len(snippet) < len(text),
            }
        )
    payload = redact_public_payload(
        {
            "url": capture["url"],
            "title": capture["title"],
            "matches": matches,
            "match_count": len(matches),
            "scan": {
                "nodes": capture["scanned_nodes"],
                "chars": capture["scanned_chars"],
                "truncated": capture["scan_truncated"],
                "max_nodes": 5000,
                "max_chars": 100000,
            },
        }
    )
    assert isinstance(payload, dict)
    return payload
