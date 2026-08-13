"""Element lookup, input, extraction, and upload operations."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any

from ..compat import accepts_parameters
from ..outline import summarize_elements
from ..response_errors import ErrorCode
from ..target import ElementTargetArg
from .targeting import DomTargetResolver

if TYPE_CHECKING:
    from ..tab import PageTab

logger = logging.getLogger(__name__)


class ClickUnsupportedError(RuntimeError):
    """Raised before interaction when the requested native click is unavailable."""

    code = ErrorCode.UNSUPPORTED_OPERATION

    def __init__(self, reason_code: str):
        super().__init__(
            f"Requested click is unsupported by this DrissionPage runtime ({reason_code})."
        )
        self.reason_code = reason_code


class ElementOperations:
    """Own DOM element interactions and extraction for one tab."""

    def __init__(self, tab: PageTab) -> None:
        self._tab = tab
        self._targeting = getattr(tab, "dom_targeting", DomTargetResolver(tab))

    @property
    def _page(self) -> Any:
        return self._tab.page

    async def click(
        self,
        selector: ElementTargetArg,
        timeout: float = 10,
        *,
        button: str = "left",
        click_count: int = 1,
    ) -> None:
        try:
            resolved = await self._targeting.resolve(selector, timeout=timeout)
            element = resolved.element
            await asyncio.to_thread(
                self._click_element,
                element,
                button=button,
                click_count=click_count,
            )
            await self._tab._stabilize(
                "element_click", timeout=1.0, fallback_sleep=0.02
            )
        except Exception as exc:
            logger.error("Failed to click element (%s)", type(exc).__name__)
            raise

    async def input(
        self, selector: ElementTargetArg, text: str, clear: bool = True
    ) -> None:
        try:
            resolved = await self._targeting.resolve(selector, timeout=10)
            await self._input_element(resolved.element, text, clear=clear)
        except Exception as exc:
            logger.error("Failed to input text (%s)", type(exc).__name__)
            raise

    async def type(
        self,
        selector: ElementTargetArg,
        text: str,
        timeout: float = 10,
        clear: bool = True,
    ) -> dict[str, Any]:
        try:
            resolved = await self._targeting.resolve(selector, timeout=timeout)
            await self._input_element(resolved.element, text, clear=clear)
            return resolved.metadata()
        except Exception as exc:
            logger.error("Failed to type text (%s)", type(exc).__name__)
            raise

    async def find(
        self, selector: ElementTargetArg, timeout: float = 10
    ) -> dict[str, Any]:
        try:
            resolved = await self._targeting.resolve(selector, timeout=timeout)
            element = resolved.element
            return {
                "found": True,
                **resolved.metadata(),
                "text": (element.text or "") if hasattr(element, "text") else "",
                "tag": element.tag if hasattr(element, "tag") else "unknown",
                "html": element.html if hasattr(element, "html") else "",
                "visible": True,
            }
        except Exception as exc:
            logger.error("Failed to find element (%s)", type(exc).__name__)
            raise

    async def find_all(
        self,
        selector: ElementTargetArg,
        *,
        limit: int = 20,
        include_html: bool = False,
    ) -> dict[str, Any]:
        try:
            target, elements = await self._targeting.resolve_all(selector)
            summaries, truncated = summarize_elements(
                elements,
                limit=limit,
                include_html=include_html,
            )
            return {
                **target.metadata(),
                "count": len(elements),
                "returned": len(summaries),
                "limit": limit,
                "truncated": truncated,
                "elements": summaries,
            }
        except Exception as exc:
            logger.error("Failed to find elements (%s)", type(exc).__name__)
            raise

    async def text(self, selector: ElementTargetArg = "") -> str:
        try:
            if selector:
                resolved = await self._targeting.resolve(selector, timeout=0)
                element = resolved.element
                return str(element.text) if hasattr(element, "text") else ""
            if hasattr(self._page, "text"):
                return str(self._page.text)
            body = self._page.ele("tag:body", timeout=0)
            return str(body.text) if body else ""
        except Exception as exc:
            logger.error("Failed to get text (%s)", type(exc).__name__)
            raise

    async def attribute(
        self, selector: ElementTargetArg, attribute: str
    ) -> str | None:
        try:
            resolved = await self._targeting.resolve(selector, timeout=0)
            value = resolved.element.attr(attribute)
            return None if value is None else str(value)
        except Exception as exc:
            logger.error("Failed to get attribute (%s)", type(exc).__name__)
            raise

    async def property(self, selector: ElementTargetArg, property_name: str) -> Any:
        try:
            resolved = await self._targeting.resolve(selector, timeout=0)
            return resolved.element.property(property_name)
        except Exception as exc:
            logger.error("Failed to get property (%s)", type(exc).__name__)
            raise

    async def html(self, selector: ElementTargetArg = "") -> str:
        try:
            if selector:
                resolved = await self._targeting.resolve(selector, timeout=0)
                return str(resolved.element.html)
            return str(self._page.html)
        except Exception as exc:
            logger.error("Failed to get HTML (%s)", type(exc).__name__)
            raise

    async def upload(
        self, selector: ElementTargetArg, paths: list[str], timeout: float = 10
    ) -> dict[str, Any]:
        try:
            resolved = await self._targeting.resolve(selector, timeout=timeout)
            resolved.element.input(paths)
            await self._tab._stabilize("upload_file", timeout=1.0, fallback_sleep=0.02)
            return {
                **resolved.metadata(),
                "uploaded": True,
                "file_count": len(paths),
                "filenames": [os.path.basename(path) for path in paths],
            }
        except Exception as exc:
            logger.error("Failed to upload file (%s)", type(exc).__name__)
            raise

    async def state(
        self, selector: ElementTargetArg, *, timeout: float = 3
    ) -> dict[str, Any]:
        resolved = await self._targeting.resolve(selector, timeout=timeout)
        element = resolved.element
        states = element.states
        covered_by = getattr(states, "is_covered", False)
        rect = element.rect
        return {
            **resolved.metadata(),
            "tag": str(getattr(element, "tag", "") or ""),
            "text": str(getattr(element, "text", "") or "")[:500],
            "displayed": bool(getattr(states, "is_displayed", False)),
            "enabled": bool(getattr(states, "is_enabled", False)),
            "alive": bool(getattr(states, "is_alive", False)),
            "clickable": bool(getattr(states, "is_clickable", False)),
            "checked": bool(getattr(states, "is_checked", False)),
            "selected": bool(getattr(states, "is_selected", False)),
            "in_viewport": bool(getattr(states, "is_in_viewport", False)),
            "whole_in_viewport": bool(getattr(states, "is_whole_in_viewport", False)),
            "covered": bool(covered_by),
            "covering_backend_node_id": int(covered_by) if covered_by else None,
            "rect": {
                "location": _point(rect.location),
                "size": _size(rect.size),
                "midpoint": _rect_point(
                    rect, "midpoint", location_attr="location", size_attr="size"
                ),
                "click_point": _rect_point(
                    rect, "click_point", location_attr="location", size_attr="size"
                ),
                "viewport_location": _point(
                    getattr(rect, "viewport_location", None) or rect.location
                ),
                "viewport_midpoint": _rect_point(
                    rect,
                    "viewport_midpoint",
                    location_attr="viewport_location",
                    size_attr="viewport_size",
                ),
                "viewport_click_point": _rect_point(
                    rect,
                    "viewport_click_point",
                    location_attr="viewport_location",
                    size_attr="viewport_size",
                ),
                "coordinate_space": "target_document",
            },
        }

    async def _input_element(self, element: Any, text: str, *, clear: bool) -> None:
        if clear:
            # Avoid DrissionPage's Linux Ctrl+A/Delete clear path; native input follows.
            element.clear(by_js=True)
        element.input(text)
        await self._tab._stabilize("input_text", timeout=1.0, fallback_sleep=0.02)

    @staticmethod
    def _click_element(
        element: Any, *, button: str = "left", click_count: int = 1
    ) -> None:
        clicker = getattr(element, "click", None)
        if button == "left" and click_count == 1:
            if not callable(clicker):
                raise ClickUnsupportedError("CLICK_CALL_UNAVAILABLE")
            clicker()
        elif button == "right" and click_count == 1:
            right = getattr(clicker, "right", None)
            if not callable(right):
                raise ClickUnsupportedError("RIGHT_CLICK_UNAVAILABLE")
            right()
        elif button == "left" and click_count == 2:
            multi = getattr(clicker, "multi", None)
            if not callable(multi) or not accepts_parameters(multi, "times"):
                raise ClickUnsupportedError("MULTI_CLICK_UNAVAILABLE")
            multi(times=2)
        else:
            at = getattr(clicker, "at", None)
            if not callable(at) or not accepts_parameters(at, "button", "count"):
                raise ClickUnsupportedError("BUTTON_COUNT_CLICK_UNAVAILABLE")
            at(button=button, count=click_count)


def _point(value: Any) -> dict[str, float]:
    x, y = value
    return {"x": float(x), "y": float(y)}


def _size(value: Any) -> dict[str, float]:
    width, height = value
    return {"width": float(width), "height": float(height)}


def _midpoint_from_location_size(location: Any, size: Any) -> dict[str, float]:
    x, y = location
    width, height = size
    return {"x": float(x) + float(width) / 2, "y": float(y) + float(height) / 2}


def _rect_point(rect: Any, attr: str, *, location_attr: str, size_attr: str) -> dict[str, float]:
    """Return a rect point, falling back to a location+size midpoint.

    Some DrissionPage element types (notably ``ChromiumFrame`` for
    cross-origin iframes) expose only ``location``/``size`` and omit the
    richer ``midpoint``/``click_point`` attributes normal elements have.
    """
    value = getattr(rect, attr, None)
    if value is not None:
        return _point(value)
    location = getattr(rect, location_attr, None)
    size = getattr(rect, size_attr, None)
    if location is not None and size is not None:
        return _midpoint_from_location_size(location, size)
    return {"x": 0.0, "y": 0.0}
