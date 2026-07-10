"""Page observation, console capture, and JavaScript evaluation operations."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ..observation import (
    bounded_json_value,
    build_observe_script,
    result_type,
    safe_int,
)
from ..outline import build_page_snapshot_script
from ._scripts import run_structured_script

if TYPE_CHECKING:
    from ..tab import PageTab

logger = logging.getLogger(__name__)


class ObservationOperations:
    """Own bounded page observation and diagnostic data collection."""

    def __init__(self, tab: "PageTab") -> None:
        self._tab = tab
        self._console_log_cache: list[dict[str, Any]] = []

    @property
    def _page(self) -> Any:
        return self._tab.page

    async def snapshot(
        self,
        *,
        include_html: bool = False,
        max_elements: int = 50,
        max_text_chars: int = 4000,
    ) -> dict[str, Any]:
        try:
            script = build_page_snapshot_script(
                include_html=include_html,
                max_elements=max_elements,
                max_text_chars=max_text_chars,
            )
            snapshot = run_structured_script(
                self._page, script, "page snapshot script returned no structured data"
            )
            snapshot.setdefault("url", self._tab.url)
            return snapshot
        except Exception as exc:
            logger.error("Failed to build page snapshot: %s", exc)
            raise

    async def observe(
        self, *, max_texts: int = 20, max_text_chars: int = 160
    ) -> dict[str, Any]:
        try:
            result = run_structured_script(
                self._page,
                build_observe_script(
                    max_texts=max_texts, max_text_chars=max_text_chars
                ),
                "page observe script returned no structured data",
            )
            result.setdefault("url", self._tab.url)
            result.setdefault("title", self._tab.title)
            result.setdefault("ready_state", "")
            result.setdefault("counts", {})
            result.setdefault("text_samples", [])
            result.setdefault("active_element", None)
            result.setdefault("console", self._console_summary(limit=5))
            result.setdefault(
                "limits", {"max_texts": max_texts, "max_text_chars": max_text_chars}
            )
            return result
        except Exception as exc:
            logger.error("Failed to observe page: %s", exc)
            raise

    def ensure_console_capture(self) -> bool:
        console = self._console_surface()
        if console is None:
            return False
        try:
            if bool(getattr(console, "listening", False)):
                return True
            start = getattr(console, "start", None)
            if callable(start):
                start()
            return bool(getattr(console, "listening", False))
        except Exception:
            logger.debug("Could not start DrissionPage console capture", exc_info=True)
            return False

    async def console_logs(
        self, *, level: str = "all", since: int = -1, limit: int = 20
    ) -> dict[str, Any]:
        console = self._console_surface()
        if console is None:
            return _empty_console_logs(available=False)

        self.ensure_console_capture()
        messages = self._normalized_console_messages()
        level_filter = _normalize_console_level(level)
        filtered = [item for item in messages if int(item["index"]) > int(since)]
        if level_filter != "all":
            filtered = [item for item in filtered if item["level"] == level_filter]

        max_items = max(1, min(int(limit), 100))
        logs = filtered[-max_items:] if int(since) < 0 else filtered[:max_items]
        return {
            "available": True,
            "listening": bool(getattr(console, "listening", False)),
            "count": len(logs),
            "total": len(messages),
            "next_cursor": _next_console_cursor(messages),
            "logs": logs,
        }

    async def evaluate(
        self, script: str, *, args: list[Any] | None = None, max_chars: int = 4000
    ) -> dict[str, Any]:
        try:
            args_json = json.dumps(args or [], ensure_ascii=False, default=str)
            wrapped = (
                "(() => {\n"
                f"  const __mcpArgs = {args_json};\n"
                "  const __mcpFn = function(...args) {\n"
                f"{script}\n"
                "  };\n"
                "  return __mcpFn(...__mcpArgs);\n"
                "})()"
            )
            value = self._page.run_js(wrapped, as_expr=True)
            bounded, truncated, original_chars = bounded_json_value(
                value, max_chars=max_chars
            )
            return {
                "result": bounded,
                "result_type": result_type(value),
                "truncated": truncated,
                "original_json_chars": original_chars,
                "max_chars": max_chars,
            }
        except Exception as exc:
            logger.error("Failed to evaluate script: %s", exc)
            raise

    def _console_surface(self) -> Any | None:
        try:
            return getattr(self._page, "console", None)
        except Exception:
            logger.debug("Could not access DrissionPage console surface", exc_info=True)
            return None

    def _normalized_console_messages(self) -> list[dict[str, Any]]:
        console = self._console_surface()
        if console is None:
            return []
        try:
            raw_messages = getattr(console, "messages", []) or []
        except Exception:
            logger.debug("Could not read DrissionPage console messages", exc_info=True)
            return []
        try:
            iterable = list(raw_messages)
        except TypeError:
            return list(self._console_log_cache)
        return self._merge_console_messages(iterable)

    def _merge_console_messages(self, raw_messages: list[Any]) -> list[dict[str, Any]]:
        if not raw_messages:
            return list(self._console_log_cache)
        raw_from_zero = [
            _normalize_console_message(message, index)
            for index, message in enumerate(raw_messages)
        ]
        if _console_prefix_matches(self._console_log_cache, raw_from_zero):
            self._console_log_cache = raw_from_zero
            return list(self._console_log_cache)

        seen = {_console_signature(item) for item in self._console_log_cache}
        for message in raw_messages:
            normalized = _normalize_console_message(
                message, len(self._console_log_cache)
            )
            signature = _console_signature(normalized)
            if signature not in seen:
                self._console_log_cache.append(normalized)
                seen.add(signature)
        return list(self._console_log_cache)

    def _console_summary(self, *, limit: int = 5) -> dict[str, Any]:
        console = self._console_surface()
        if console is None:
            return {
                "available": False,
                "listening": False,
                "count": 0,
                "total": 0,
                "next_cursor": -1,
                "error_count": 0,
                "warning_count": 0,
                "recent": [],
            }
        self.ensure_console_capture()
        messages = self._normalized_console_messages()
        recent = messages[-max(1, int(limit)) :]
        return {
            "available": True,
            "listening": bool(getattr(console, "listening", False)),
            "count": len(recent),
            "total": len(messages),
            "next_cursor": _next_console_cursor(messages),
            "error_count": sum(1 for item in messages if item["level"] == "error"),
            "warning_count": sum(1 for item in messages if item["level"] == "warning"),
            "recent": recent,
        }


def _empty_console_logs(*, available: bool) -> dict[str, Any]:
    return {
        "available": available,
        "listening": False,
        "count": 0,
        "total": 0,
        "next_cursor": -1,
        "logs": [],
    }


def _next_console_cursor(messages: list[dict[str, Any]]) -> int:
    return (
        -1
        if not messages
        else max(safe_int(item.get("index"), -1) for item in messages)
    )


def _console_prefix_matches(
    cached: list[dict[str, Any]], current: list[dict[str, Any]]
) -> bool:
    return len(current) >= len(cached) and all(
        _console_signature(cached[index]) == _console_signature(current[index])
        for index in range(len(cached))
    )


def _console_signature(message: dict[str, Any]) -> tuple[str, str, str, int, int, str]:
    return (
        str(message.get("level") or ""),
        str(message.get("text") or ""),
        str(message.get("url") or ""),
        safe_int(message.get("line"), 0),
        safe_int(message.get("column"), 0),
        str(message.get("source") or ""),
    )


def _normalize_console_message(message: Any, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "level": _normalize_console_level(_message_field(message, "level", "log")),
        "text": _message_text(message),
        "url": str(_message_field(message, "url", "") or ""),
        "line": safe_int(_message_field(message, "line", 0), 0),
        "column": safe_int(_message_field(message, "column", 0), 0),
        "source": str(_message_field(message, "source", "") or ""),
    }


def _message_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    value = _message_field(message, "text", "")
    if value in ("", None):
        value = _message_field(message, "message", "")
    return str(value or "")


def _message_field(message: Any, field: str, default: Any) -> Any:
    if isinstance(message, Mapping):
        return message.get(field, default)
    try:
        return getattr(message, field)
    except Exception:
        return default


def _normalize_console_level(level: Any) -> str:
    value = str(level or "log").lower()
    if value == "warn":
        return "warning"
    return value if value in {"all", "error", "warning", "info", "log"} else "log"
