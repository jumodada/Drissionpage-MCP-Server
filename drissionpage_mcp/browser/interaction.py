"""Page and element interaction operations for a browser tab."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..selector import normalize_selector

if TYPE_CHECKING:
    from ..tab import PageTab

logger = logging.getLogger(__name__)


class InteractionOperations:
    """Own scrolling, hover, keyboard, selection, and check behavior."""

    def __init__(self, tab: "PageTab") -> None:
        self._tab = tab

    @property
    def _page(self) -> Any:
        return self._tab.page

    async def click_coordinates(self, x: int, y: int) -> None:
        """Click at viewport coordinates."""

        try:
            self._page.actions.click((x, y))
            await self._tab._stabilize(
                "coordinate_click", timeout=1.0, fallback_sleep=0.02
            )
        except Exception as exc:
            logger.error("Failed to click at (%s, %s): %s", x, y, exc)
            raise

    async def scroll_page(
        self,
        *,
        direction: str = "down",
        pixels: int = 300,
        x: int = 0,
        y: int = 0,
    ) -> dict[str, Any]:
        try:
            scroll = getattr(self._page, "scroll", None)
            if scroll is None:
                raise RuntimeError(
                    "Current page does not expose DrissionPage scroll API."
                )
            actions = {
                "down": lambda: scroll.down(pixels),
                "up": lambda: scroll.up(pixels),
                "left": lambda: scroll.left(pixels),
                "right": lambda: scroll.right(pixels),
                "top": scroll.to_top,
                "bottom": scroll.to_bottom,
                "half": scroll.to_half,
                "position": lambda: scroll.to_location(x, y),
            }
            action = actions.get(direction)
            if action is None:
                raise ValueError(f"Unsupported scroll direction: {direction}")
            action()
            await self._tab._stabilize("page_scroll", timeout=0.5, fallback_sleep=0.02)
            return {
                "direction": direction,
                "pixels": pixels,
                "x": x,
                "y": y,
                "url": self._tab.url,
            }
        except Exception as exc:
            logger.error("Failed to scroll page: %s", exc)
            raise

    async def scroll_element_into_view(
        self, selector: str, *, center: bool = True, timeout: int = 10
    ) -> dict[str, Any]:
        try:
            plan = normalize_selector(selector)
            element = await self._tab._element_by_plan(plan, timeout=timeout)
            element.scroll.to_see(center=center)
            await self._tab._stabilize(
                "element_scroll_into_view", timeout=0.5, fallback_sleep=0.02
            )
            return {**plan.metadata(), "center": center, "url": self._tab.url}
        except Exception as exc:
            logger.error("Failed to scroll element into view %s: %s", selector, exc)
            raise

    async def hover_element(
        self,
        selector: str,
        *,
        timeout: int = 10,
        offset_x: int | None = None,
        offset_y: int | None = None,
    ) -> dict[str, Any]:
        try:
            plan = normalize_selector(selector)
            element = await self._tab._element_by_plan(plan, timeout=timeout)
            element.hover(offset_x=offset_x, offset_y=offset_y)
            await self._tab._stabilize(
                "element_hover", timeout=0.5, fallback_sleep=0.02
            )
            return {
                **plan.metadata(),
                "url": self._tab.url,
                "offset_x": offset_x,
                "offset_y": offset_y,
            }
        except Exception as exc:
            logger.error("Failed to hover element %s: %s", selector, exc)
            raise

    async def keyboard_press(self, keys: str, *, interval: float = 0) -> dict[str, Any]:
        try:
            self._page.actions.type(keys, interval=interval)
            await self._tab._stabilize(
                "keyboard_press", timeout=0.5, fallback_sleep=0.02
            )
            return {"keys": keys, "interval": interval, "url": self._tab.url}
        except Exception as exc:
            logger.error("Failed to press keyboard keys: %s", exc)
            raise

    async def select_element(
        self,
        selector: str,
        *,
        value: str,
        by: str = "value",
        timeout: int = 10,
    ) -> dict[str, Any]:
        try:
            plan = normalize_selector(selector)
            element = await self._tab._element_by_plan(plan, timeout=timeout)
            select = element.select
            actions = {
                "value": lambda: select.by_value(value, timeout=timeout),
                "text": lambda: select.by_text(value, timeout=timeout),
                "index": lambda: select.by_index(int(value), timeout=timeout),
            }
            action = actions.get(by)
            if action is None:
                raise ValueError(f"Unsupported select mode: {by}")
            action()
            await self._tab._stabilize(
                "element_select", timeout=0.5, fallback_sleep=0.02
            )
            return {**plan.metadata(), "selected": True, "by": by, "value": value}
        except Exception as exc:
            logger.error("Failed to select option for %s: %s", selector, exc)
            raise

    async def check_element(
        self,
        selector: str,
        *,
        checked: bool = True,
        by_js: bool = False,
        timeout: int = 10,
    ) -> dict[str, Any]:
        try:
            plan = normalize_selector(selector)
            element = await self._tab._element_by_plan(plan, timeout=timeout)
            element.check(uncheck=not checked, by_js=by_js)
            await self._tab._stabilize(
                "element_check", timeout=0.5, fallback_sleep=0.02
            )
            return {**plan.metadata(), "checked": checked, "by_js": by_js}
        except Exception as exc:
            logger.error("Failed to check element %s: %s", selector, exc)
            raise
