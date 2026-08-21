"""Regression coverage for ElementOperations against frame-like elements.

Cross-origin ``<iframe>`` elements resolve to DrissionPage's ``ChromiumFrame``
type, which exposes a much smaller surface than a normal element: no
``.text``, and a ``FrameStates``/``FrameRect`` pair missing most of the
state/geometry attributes a regular element has (``is_covered``,
``is_checked``, ``midpoint``, ``click_point``, ...). ``element_find`` and
``element_state_get`` must degrade gracefully instead of raising
``AttributeError`` when handed one of these.
"""

from __future__ import annotations

import pytest

from drissionpage_mcp.browser.elements import ElementOperations


class _FrameStates:
    """Mirrors DrissionPage's ``FrameStates``: a minimal state surface."""

    is_alive = True
    is_displayed = True
    is_loading = False
    has_alert = False


class _FrameRect:
    """Mirrors DrissionPage's ``FrameRect``: no midpoint/click_point."""

    location = (8.0, 87.875)
    size = (300.0, 65.0)
    viewport_location = (8.0, 87.875)
    viewport_size = (300.0, 65.0)


class _OuterFrameStates:
    is_alive = True
    is_displayed = True
    is_enabled = True
    is_clickable = True
    is_checked = False
    is_selected = False
    is_in_viewport = True
    is_whole_in_viewport = True
    is_covered = False


class _OuterFrameRect:
    location = (8.0, 87.875)
    size = (304.0, 69.0)
    midpoint = (160.0, 122.375)
    click_point = (160.0, 90.875)
    viewport_location = (8.0, 87.875)
    viewport_midpoint = (160.0, 122.375)
    viewport_click_point = (160.0, 90.875)


class _OuterFrameElement:
    states = _OuterFrameStates()
    rect = _OuterFrameRect()

    def run_js(self, _script: str):
        return {
            "display": "inline",
            "visibility": "visible",
            "opacity": 1.0,
            "pointer_events": "auto",
            "transform": "none",
            "transform_style": "flat",
            "perspective": "none",
            "ancestor_3d": False,
        }


class _ChromiumFrameLike:
    """Stand-in for a cross-origin iframe's ``ChromiumFrame`` object."""

    tag = "iframe"
    states = _FrameStates()
    rect = _FrameRect()
    frame_ele = _OuterFrameElement()

    def attr(self, _name: str) -> None:
        return None


class _ElementTab:
    def __init__(self, element: object) -> None:
        self.element = element

    async def _element_by_plan(self, _plan: object, *, timeout: int) -> object:
        return self.element

    async def _stabilize(self, *args: object, **kwargs: object) -> None:
        return None


@pytest.mark.asyncio
async def test_element_find_on_frame_like_element_does_not_raise() -> None:
    tab = _ElementTab(_ChromiumFrameLike())

    result = await ElementOperations(tab).find("iframe")  # type: ignore[arg-type]

    assert result["found"] is True
    assert result["tag"] == "iframe"
    assert result["text"] == ""


@pytest.mark.asyncio
async def test_element_get_text_on_frame_like_element_returns_empty_string() -> None:
    tab = _ElementTab(_ChromiumFrameLike())

    result = await ElementOperations(tab).text("iframe")  # type: ignore[arg-type]

    assert result == ""


@pytest.mark.asyncio
async def test_element_state_get_on_frame_like_element_falls_back_cleanly() -> None:
    tab = _ElementTab(_ChromiumFrameLike())

    result = await ElementOperations(tab).state("iframe")  # type: ignore[arg-type]

    assert result["displayed"] is True
    assert result["alive"] is True
    assert result["checked"] is False
    assert result["clickable"] is True
    assert result["in_viewport"] is True
    assert result["whole_in_viewport"] is True
    assert result["covered"] is False
    assert result["covering_backend_node_id"] is None

    rect = result["rect"]
    assert rect["location"] == {"x": 8.0, "y": 87.875}
    # Geometry must describe the outer iframe element, not the inner document.
    assert rect["size"] == {"width": 304.0, "height": 69.0}
    assert rect["midpoint"] == {"x": 160.0, "y": 122.375}
    assert rect["click_point"] == {"x": 160.0, "y": 90.875}
    assert rect["viewport_midpoint"] == {"x": 160.0, "y": 122.375}
    assert rect["viewport_click_point"] == {"x": 160.0, "y": 90.875}
    assert rect["viewport_coordinate_space"] == "top_level_viewport"
    assert result["presentation"]["coordinate_actionability"] == "ready"


@pytest.mark.asyncio
async def test_element_find_and_state_still_work_for_normal_elements() -> None:
    class _NormalStates:
        is_alive = True
        is_displayed = True
        is_enabled = True
        is_clickable = True
        is_checked = True
        is_selected = False
        is_in_viewport = True
        is_whole_in_viewport = True
        is_covered = False

    class _Point:
        def __init__(self, x: float, y: float) -> None:
            self._value = (x, y)

        def __iter__(self):
            return iter(self._value)

    class _NormalRect:
        location = (10.0, 20.0)
        size = (100.0, 40.0)
        midpoint = (60.0, 40.0)
        click_point = (60.0, 40.0)
        viewport_location = (10.0, 20.0)
        viewport_midpoint = (60.0, 40.0)
        viewport_click_point = (60.0, 40.0)

    class _NormalElement:
        tag = "button"
        text = "Submit"
        html = "<button>Submit</button>"
        states = _NormalStates()
        rect = _NormalRect()

        def attr(self, _name: str) -> None:
            return None

    tab = _ElementTab(_NormalElement())

    found = await ElementOperations(tab).find("button")  # type: ignore[arg-type]
    assert found["text"] == "Submit"
    assert found["tag"] == "button"

    state = await ElementOperations(tab).state("button")  # type: ignore[arg-type]
    assert state["checked"] is True
    assert state["rect"]["midpoint"] == {"x": 60.0, "y": 40.0}
    assert state["rect"]["click_point"] == {"x": 60.0, "y": 40.0}
