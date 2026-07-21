"""Element lookup, input, extraction, and upload operations."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from DrissionPage.errors import ElementNotFoundError

from ..compat import accepts_parameters
from ..outline import summarize_elements
from ..response_errors import ErrorCode
from ..selector import normalize_selector

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

    def __init__(self, tab: "PageTab") -> None:
        self._tab = tab

    @property
    def _page(self) -> Any:
        return self._tab.page

    async def click(
        self,
        selector: str,
        timeout: int = 10,
        *,
        button: str = "left",
        click_count: int = 1,
    ) -> None:
        try:
            plan = normalize_selector(selector)
            element = await self._tab._element_by_plan(plan, timeout=timeout)
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
            await self._tab._stabilize(
                "element_click", timeout=1.0, fallback_sleep=0.02
            )
        except Exception as exc:
            logger.error("Failed to click element %s: %s", selector, exc)
            raise

    async def input(self, selector: str, text: str, clear: bool = True) -> None:
        try:
            plan = normalize_selector(selector)
            element = self._page.ele(plan.locator)
            if not element:
                raise ElementNotFoundError(f"Element not found: {selector}")
            if clear:
                element.clear()
            element.input(text)
            await self._tab._stabilize("input_text", timeout=1.0, fallback_sleep=0.02)
        except Exception as exc:
            logger.error("Failed to input text to %s: %s", selector, exc)
            raise

    async def type(
        self, selector: str, text: str, timeout: int = 10, clear: bool = True
    ) -> None:
        try:
            plan = normalize_selector(selector)
            await self._tab._element_by_plan(plan, timeout=timeout)
            await self.input(plan.locator, text, clear)
        except Exception as exc:
            logger.error("Failed to type text to %s: %s", selector, exc)
            raise

    async def find(self, selector: str, timeout: int = 10) -> dict[str, Any]:
        try:
            plan = normalize_selector(selector)
            element = await self._tab._element_by_plan(plan, timeout=timeout)
            return {
                "found": True,
                **plan.metadata(),
                "text": element.text or "",
                "tag": element.tag if hasattr(element, "tag") else "unknown",
                "html": element.html if hasattr(element, "html") else "",
                "visible": True,
            }
        except Exception as exc:
            logger.error("Failed to find element %s: %s", selector, exc)
            raise

    async def find_all(
        self,
        selector: str,
        *,
        limit: int = 20,
        include_html: bool = False,
    ) -> dict[str, Any]:
        try:
            plan = normalize_selector(selector)
            elements = list(self._page.eles(plan.locator, timeout=0) or [])
            summaries, truncated = summarize_elements(
                elements,
                limit=limit,
                include_html=include_html,
            )
            return {
                **plan.metadata(),
                "count": len(elements),
                "returned": len(summaries),
                "limit": limit,
                "truncated": truncated,
                "elements": summaries,
            }
        except Exception as exc:
            logger.error("Failed to find elements %s: %s", selector, exc)
            raise

    async def text(self, selector: str = "") -> str:
        try:
            if selector:
                plan = normalize_selector(selector)
                element = self._page.ele(plan.locator)
                if not element:
                    raise ElementNotFoundError(f"Element not found: {selector}")
                return str(element.text)
            if hasattr(self._page, "text"):
                return str(self._page.text)
            body = self._page.ele("tag:body", timeout=0)
            return str(body.text) if body else ""
        except Exception as exc:
            logger.error("Failed to get text from %s: %s", selector or "page", exc)
            raise

    async def attribute(self, selector: str, attribute: str) -> str | None:
        try:
            plan = normalize_selector(selector)
            element = self._page.ele(plan.locator)
            if not element:
                raise ElementNotFoundError(f"Element not found: {selector}")
            value = element.attr(attribute)
            return None if value is None else str(value)
        except Exception as exc:
            logger.error(
                "Failed to get attribute %s from %s: %s", attribute, selector, exc
            )
            raise

    async def property(self, selector: str, property_name: str) -> Any:
        try:
            plan = normalize_selector(selector)
            element = self._page.ele(plan.locator)
            if not element:
                raise ElementNotFoundError(f"Element not found: {selector}")
            return element.property(property_name)
        except Exception as exc:
            logger.error(
                "Failed to get property %s from %s: %s",
                property_name,
                selector,
                exc,
            )
            raise

    async def html(self, selector: str = "") -> str:
        try:
            if selector:
                plan = normalize_selector(selector)
                element = self._page.ele(plan.locator)
                if not element:
                    raise ElementNotFoundError(f"Element not found: {selector}")
                return str(element.html)
            return str(self._page.html)
        except Exception as exc:
            logger.error("Failed to get HTML from %s: %s", selector or "page", exc)
            raise

    async def upload(
        self, selector: str, paths: list[str], timeout: int = 10
    ) -> dict[str, Any]:
        try:
            plan = normalize_selector(selector)
            element = await self._tab._element_by_plan(plan, timeout=timeout)
            element.input(paths)
            await self._tab._stabilize("upload_file", timeout=1.0, fallback_sleep=0.02)
            return {
                **plan.metadata(),
                "uploaded": True,
                "file_count": len(paths),
                "filenames": [os.path.basename(path) for path in paths],
            }
        except Exception as exc:
            logger.error("Failed to upload file into %s: %s", selector, exc)
            raise
