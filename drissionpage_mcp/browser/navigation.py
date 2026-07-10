"""Navigation operations for a browser tab."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..tab import PageTab

logger = logging.getLogger(__name__)


class NavigationOperations:
    """Own page navigation and history behavior."""

    def __init__(self, tab: "PageTab") -> None:
        self._tab = tab

    @property
    def _page(self) -> Any:
        return self._tab.page

    async def navigate(self, url: str) -> None:
        try:
            result = self._page.get(url)
            if result is False or (hasattr(result, "ok") and result.ok is False):
                raise RuntimeError(f"Navigation failed: {result}")
            self._tab._url = getattr(result, "url", None) or self._page.url or url
            await self._tab._stabilize("navigation", timeout=5.0, fallback_sleep=0.05)
            logger.info("Navigated to: %s", url)
        except Exception as exc:
            logger.error("Failed to navigate to %s: %s", url, exc)
            raise

    async def back(self) -> None:
        try:
            self._page.back()
            await self._tab._stabilize("go_back", timeout=5.0, fallback_sleep=0.05)
        except Exception as exc:
            logger.error("Failed to go back: %s", exc)
            raise

    async def forward(self) -> None:
        try:
            self._page.forward()
            await self._tab._stabilize("go_forward", timeout=5.0, fallback_sleep=0.05)
        except Exception as exc:
            logger.error("Failed to go forward: %s", exc)
            raise

    async def refresh(self) -> None:
        try:
            self._page.refresh()
            await self._tab._stabilize("refresh", timeout=5.0, fallback_sleep=0.05)
        except Exception as exc:
            logger.error("Failed to refresh page: %s", exc)
            raise
