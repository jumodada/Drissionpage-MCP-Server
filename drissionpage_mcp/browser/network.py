"""Network listener operations for a browser tab."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ..network_payload import _network_packet_payload
from ..response_errors import ErrorCode

if TYPE_CHECKING:
    from ..tab import PageTab

logger = logging.getLogger(__name__)


class NetworkUnsupportedError(RuntimeError):
    """Raised when DrissionPage does not expose a usable network listener."""

    code = ErrorCode.UNSUPPORTED_OPERATION


class NetworkOperations:
    """Own DrissionPage listener state and bounded packet serialization."""

    def __init__(self, tab: "PageTab") -> None:
        self._tab = tab
        self._started_at = ""
        self._filters: dict[str, Any] = {}

    @property
    def _page(self) -> Any:
        return self._tab.page

    async def start(
        self,
        *,
        targets: list[str] | None = None,
        is_regex: bool = False,
        method: str = "",
        resource_type: str = "",
        clear: bool = True,
    ) -> dict[str, Any]:
        listener = self._listener()
        if clear and bool(getattr(listener, "listening", False)):
            self._safe_stop(listener)
        elif clear and callable(getattr(listener, "clear", None)):
            listener.clear()

        target_arg: Any = None
        if targets:
            target_arg = targets[0] if len(targets) == 1 else list(targets)

        kwargs: dict[str, Any] = {
            "targets": target_arg,
            "is_regex": is_regex if target_arg is not None else None,
            "method": method or None,
            "res_type": resource_type or None,
        }
        try:
            listener.start(**kwargs)
        except TypeError:
            listener.start(target_arg, is_regex if target_arg is not None else None)

        self._started_at = datetime.now(timezone.utc).isoformat()
        self._filters = {
            "targets": list(targets or []),
            "is_regex": bool(is_regex),
            "method": method,
            "resource_type": resource_type,
        }
        return {
            "listening": bool(getattr(listener, "listening", False)),
            "filters": dict(self._filters),
            "started_at": self._started_at,
            "tab_id": self._tab.mcp_tab_id,
            "cleared": bool(clear),
        }

    async def wait(
        self,
        *,
        timeout: float = 5.0,
        limit: int = 10,
        include_headers: bool = False,
        include_body: bool = False,
        max_body_chars: int = 2000,
    ) -> dict[str, Any]:
        listener = self._listener()
        if not bool(getattr(listener, "listening", False)):
            raise NetworkUnsupportedError("Network listener is not listening.")

        raw_packets = await asyncio.to_thread(
            listener.wait,
            count=limit,
            timeout=timeout,
            fit_count=False,
            raise_err=False,
        )
        timed_out = raw_packets is False
        if raw_packets is False or raw_packets is None:
            packets: list[Any] = []
        elif isinstance(raw_packets, list):
            packets = raw_packets
            timed_out = len(packets) < limit
        else:
            packets = [raw_packets]
            timed_out = limit > 1

        normalized = [
            _network_packet_payload(
                packet,
                index=index,
                include_headers=include_headers,
                include_body=include_body,
                max_body_chars=max_body_chars,
            )
            for index, packet in enumerate(packets[:limit])
        ]
        return {
            "listening": bool(getattr(listener, "listening", False)),
            "timed_out": bool(timed_out),
            "count": len(normalized),
            "limit": limit,
            "packets": normalized,
        }

    async def stop(self, *, clear: bool = True) -> dict[str, Any]:
        listener = self._listener()
        was_listening = bool(getattr(listener, "listening", False))
        if was_listening:
            self._safe_stop(listener, clear=clear)
        elif clear and callable(getattr(listener, "clear", None)):
            listener.clear()
        return {
            "listening": bool(getattr(listener, "listening", False)),
            "was_listening": was_listening,
            "cleared": bool(clear),
        }

    def _listener(self) -> Any:
        listener = getattr(self._page, "listen", None)
        if listener is None:
            raise NetworkUnsupportedError(
                "Network listener is unavailable on this browser tab."
            )
        required = ("start", "wait", "stop")
        missing = [
            name for name in required if not callable(getattr(listener, name, None))
        ]
        if missing:
            raise NetworkUnsupportedError(
                "Network listener is unsupported; missing: " + ", ".join(missing)
            )
        return listener

    @staticmethod
    def _safe_stop(listener: Any, *, clear: bool = True) -> None:
        try:
            if clear:
                listener.stop()
            else:
                pause = getattr(listener, "pause", None)
                if callable(pause):
                    pause(clear=False)
                else:
                    listener.stop()
        except AttributeError:
            logger.debug(
                "Network listener stop hit a partial driver state", exc_info=True
            )
        except Exception:
            logger.debug("Network listener stop failed", exc_info=True)
            raise
