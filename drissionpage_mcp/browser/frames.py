"""Frame and shadow-root operations for a browser tab."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from DrissionPage.errors import ElementNotFoundError

from ..frame_payload import _frame_snapshot_payload, _frame_summary, _safe_string_attr
from ..outline import summarize_elements
from ..selector import SelectorPlan, normalize_selector

if TYPE_CHECKING:
    from ..tab import PageTab

logger = logging.getLogger(__name__)


class FrameOperations:
    """Own iframe and open shadow-root lookup behavior."""

    def __init__(self, tab: "PageTab") -> None:
        self._tab = tab

    @property
    def _page(self) -> Any:
        return self._tab.page

    async def list_frames(self, *, limit: int = 20) -> dict[str, Any]:
        try:
            frames = self._frames()
            summaries = [
                _frame_summary(frame, index)
                for index, frame in enumerate(frames[: max(0, limit)])
            ]
            return {
                "count": len(frames),
                "returned": len(summaries),
                "limit": limit,
                "frames": summaries,
            }
        except Exception as exc:
            logger.error("Failed to list frames: %s", exc)
            raise

    async def snapshot(
        self,
        *,
        frame_selector: str = "",
        frame_index: int = 0,
        include_html: bool = False,
        max_elements: int = 50,
        max_text_chars: int = 4000,
        timeout: int = 3,
    ) -> dict[str, Any]:
        try:
            frame, index = self._resolve(
                frame_selector=frame_selector,
                frame_index=frame_index,
                timeout=timeout,
            )
            result = _frame_snapshot_payload(
                frame,
                include_html=include_html,
                max_elements=max_elements,
                max_text_chars=max_text_chars,
            )
            return {"frame": _frame_summary(frame, index, frame_selector), **result}
        except Exception as exc:
            logger.error("Failed to capture frame snapshot: %s", exc)
            raise

    async def find(
        self,
        *,
        selector: str,
        frame_selector: str = "",
        frame_index: int = 0,
        timeout: int = 3,
    ) -> dict[str, Any]:
        try:
            frame, index = self._resolve(
                frame_selector=frame_selector,
                frame_index=frame_index,
                timeout=timeout,
            )
            plan = normalize_selector(selector)
            element = frame.ele(plan.locator, timeout=timeout)
            if not element:
                raise ElementNotFoundError(f"Element not found: {selector}")
            return {
                "frame": _frame_summary(frame, index, frame_selector),
                "element": _element_info(element, plan),
            }
        except Exception as exc:
            logger.error("Failed to find frame element %s: %s", selector, exc)
            raise

    async def shadow_find(
        self,
        *,
        host_selector: str,
        selector: str,
        timeout: int = 3,
    ) -> dict[str, Any]:
        try:
            host_plan, root = await self._shadow_root(host_selector, timeout=timeout)
            target_plan = normalize_selector(selector)
            element = root.ele(target_plan.locator, timeout=timeout)
            if not element:
                raise ElementNotFoundError(f"Element not found: {selector}")
            return {
                "host": host_plan.metadata(),
                "element": _element_info(element, target_plan),
            }
        except Exception as exc:
            logger.error("Failed to find shadow element %s: %s", selector, exc)
            raise

    async def shadow_find_all(
        self,
        *,
        host_selector: str,
        selector: str,
        limit: int = 20,
        include_html: bool = False,
    ) -> dict[str, Any]:
        try:
            host_plan, root = await self._shadow_root(host_selector, timeout=3)
            target_plan = normalize_selector(selector)
            elements = list(root.eles(target_plan.locator, timeout=0) or [])
            summaries, truncated = summarize_elements(
                elements,
                limit=limit,
                include_html=include_html,
            )
            return {
                "host": host_plan.metadata(),
                "target": target_plan.metadata(),
                "count": len(elements),
                "returned": len(summaries),
                "limit": limit,
                "truncated": truncated,
                "elements": summaries,
            }
        except Exception as exc:
            logger.error("Failed to find shadow elements %s: %s", selector, exc)
            raise

    def _frames(self) -> list[Any]:
        get_frames = getattr(self._page, "get_frames", None)
        if not callable(get_frames):
            return []
        try:
            raw_frames = list(get_frames(timeout=0) or [])
        except TypeError:
            raw_frames = list(get_frames() or [])
        frames: list[Any] = []
        for raw in raw_frames:
            frame = self._coerce(raw)
            if frame is not None:
                frames.append(frame)
        return frames

    def _coerce(self, frame_like: Any) -> Any | None:
        if hasattr(frame_like, "frame_ele") or (
            hasattr(frame_like, "ele") and hasattr(frame_like, "run_js")
        ):
            return frame_like
        get_frame = getattr(self._page, "get_frame", None)
        if not callable(get_frame):
            return None
        try:
            return get_frame(frame_like, timeout=0)
        except Exception:
            logger.debug("Could not resolve frame object", exc_info=True)
            return None

    def _resolve(
        self,
        *,
        frame_selector: str = "",
        frame_index: int = 0,
        timeout: int = 3,
    ) -> tuple[Any, int]:
        if frame_selector:
            plan = normalize_selector(frame_selector)
            get_frame = getattr(self._page, "get_frame", None)
            if not callable(get_frame):
                raise ElementNotFoundError("Frames are not supported by this page")
            frame = get_frame(plan.locator, timeout=timeout)
            if not frame:
                raise ElementNotFoundError(f"Frame not found: {frame_selector}")
            frames = self._frames()
            index = next(
                (idx for idx, candidate in enumerate(frames) if candidate is frame),
                max(0, frame_index),
            )
            return frame, index

        frames = self._frames()
        if frame_index < 0 or frame_index >= len(frames):
            raise ElementNotFoundError(f"Frame index not found: {frame_index}")
        return frames[frame_index], frame_index

    async def _shadow_root(
        self, host_selector: str, *, timeout: int = 3
    ) -> tuple[SelectorPlan, Any]:
        host_plan = normalize_selector(host_selector)
        host = await self._tab._element_by_plan(host_plan, timeout=timeout)
        root = getattr(host, "shadow_root", None)
        if not root:
            raise ElementNotFoundError(f"Shadow root not found: {host_selector}")
        return host_plan, root


def _element_info(element: Any, plan: SelectorPlan) -> dict[str, Any]:
    return {
        "found": True,
        **plan.metadata(),
        "text": _safe_string_attr(element, "text"),
        "tag": _safe_string_attr(element, "tag") or "unknown",
        "html": _safe_string_attr(element, "html"),
        "visible": True,
    }
