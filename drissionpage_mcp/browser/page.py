"""Page media and browser-window operations."""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..tab import PageTab

logger = logging.getLogger(__name__)


class PageOperations:
    """Own screenshots and browser-window state changes."""

    def __init__(self, tab: "PageTab") -> None:
        self._tab = tab

    @property
    def _page(self) -> Any:
        return self._tab.page

    async def screenshot(self, path: str | None = None, full_page: bool = False) -> str:
        try:
            if path:
                self._page.get_screenshot(path=path, full_page=full_page)
                return path
            screenshot_data = self._page.get_screenshot(
                as_base64=True, full_page=full_page
            )
            if isinstance(screenshot_data, bytes):
                return base64.b64encode(screenshot_data).decode()
            if isinstance(screenshot_data, str):
                return screenshot_data
            raise TypeError(
                "DrissionPage get_screenshot(as_base64=True) returned "
                f"unsupported type: {type(screenshot_data).__name__}"
            )
        except Exception as exc:
            logger.error("Failed to take screenshot: %s", exc)
            raise

    async def resize(self, width: int, height: int) -> None:
        try:
            self._page.set.window.size(width, height)
        except Exception as exc:
            logger.error("Failed to resize window to %sx%s: %s", width, height, exc)
            raise
