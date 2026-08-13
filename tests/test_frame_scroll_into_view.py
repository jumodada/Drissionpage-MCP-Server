"""Regression coverage for scrolling frame-like elements into view.

Cross-origin ``<iframe>`` elements resolve to DrissionPage's ``ChromiumFrame``
type, whose ``.scroll`` is a ``FrameScroller`` with an incompatible
``to_see(loc_or_ele, center=...)`` signature compared to a normal element's
``ElementScroller.to_see(center=...)``. ``element_scroll_into_view`` must fall
back to scrolling the page to the frame's own location instead of raising.
"""

from __future__ import annotations

import pytest

from drissionpage_mcp.browser.interaction import InteractionOperations
from drissionpage_mcp.browser.targeting import DomTargetResolver


class _FrameRect:
    location = (8.0, 900.0)


class _FrameScroller:
    """Mirrors DrissionPage's ``FrameScroller``: requires ``loc_or_ele``."""

    def to_see(self, loc_or_ele=None, *, center: bool = True) -> None:
        if loc_or_ele is None:
            raise TypeError(
                "FrameScroller.to_see() missing 1 required positional "
                "argument: 'loc_or_ele'"
            )


class _ChromiumFrameLike:
    tag = "iframe"
    rect = _FrameRect()
    scroll = _FrameScroller()


class _PageScroll:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def to_location(self, x: int, y: int) -> None:
        self.calls.append((x, y))


class _Page:
    def __init__(self) -> None:
        self.scroll = _PageScroll()


class _ElementTab:
    def __init__(self, element: object) -> None:
        self.element = element
        self.page = _Page()
        self.dom_targeting = DomTargetResolver(self)
        self.url = "https://example.test/"

    async def _element_by_plan(self, _plan: object, *, timeout: int) -> object:
        return self.element

    async def _stabilize(self, *args: object, **kwargs: object) -> None:
        return None


@pytest.mark.asyncio
async def test_scroll_element_into_view_falls_back_for_frame_like_elements() -> None:
    tab = _ElementTab(_ChromiumFrameLike())

    result = await InteractionOperations(tab).scroll_element_into_view("iframe")  # type: ignore[arg-type]

    assert result["center"] is True
    assert tab.page.scroll.calls == [(8, 900)]


@pytest.mark.asyncio
async def test_scroll_element_into_view_uses_native_to_see_for_normal_elements() -> None:
    calls: list[bool] = []

    class _NormalScroller:
        def to_see(self, *, center: bool = True) -> None:
            calls.append(center)

    class _NormalElement:
        tag = "button"
        scroll = _NormalScroller()

    tab = _ElementTab(_NormalElement())

    await InteractionOperations(tab).scroll_element_into_view("button", center=False)  # type: ignore[arg-type]

    assert calls == [False]
    assert tab.page.scroll.calls == []
