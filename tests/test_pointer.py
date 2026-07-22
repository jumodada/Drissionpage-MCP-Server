"""Deterministic direct and natural pointer execution contracts."""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from drissionpage_mcp.browser.motion import Point, plan_pointer_path
from drissionpage_mcp.browser.pointer import PointerOperations


class FakePage:
    def __init__(self, *, fail_on_event: int | None = None) -> None:
        self.actions = SimpleNamespace(curr_x=100.0, curr_y=100.0, modifier=0)
        self.events: list[tuple[str, dict[str, object]]] = []
        self.fail_on_event = fail_on_event

    def run_cdp(self, method: str, **params: object) -> dict[str, object]:
        self.events.append((method, params))
        if self.fail_on_event == len(self.events):
            raise RuntimeError("injected CDP failure")
        return {}


class FakeTab:
    def __init__(self, *, fail_on_event: int | None = None) -> None:
        self.page = FakePage(fail_on_event=fail_on_event)
        self.url = "https://example.test/"
        self.stabilized: list[str] = []

    async def _stabilize(self, action: str, **_kwargs: object) -> None:
        self.stabilized.append(action)


def _event_params(tab: FakeTab) -> list[dict[str, object]]:
    return [params for _, params in tab.page.events]


@pytest.mark.asyncio
async def test_pointer_move_is_one_exact_deterministic_cdp_event() -> None:
    first = FakeTab()
    second = FakeTab()

    first_result = await PointerOperations(first).move_to(442, 369)
    second_result = await PointerOperations(second).move_to(442, 369)

    assert first.page.events == second.page.events
    assert first_result == second_result
    assert [event["type"] for event in _event_params(first)] == ["mouseMoved"]
    assert _event_params(first)[0]["x"] == 442
    assert _event_params(first)[0]["y"] == 369
    assert first_result.to_dict() == {
        "profile": "direct",
        "start_x": 100.0,
        "start_y": 100.0,
        "target_x": 442.0,
        "target_y": 369.0,
        "steps": 1,
        "planned_duration_ms": 0,
    }
    assert first.stabilized == ["pointer_move"]


def test_natural_path_is_bounded_curved_reproducible_and_exact() -> None:
    first = plan_pointer_path(Point(100, 100), Point(442, 369), "natural")
    second = plan_pointer_path(Point(100, 100), Point(442, 369), "natural")

    assert first == second
    assert len(first.points) == 24
    assert first.points[-1] == Point(442, 369)
    assert len(first.delays) == 24
    assert min(first.delays) == pytest.approx(0.008)
    assert max(first.delays) == pytest.approx(0.014)
    assert max(first.delays) - min(first.delays) >= 0.004

    dx, dy = 342, 269
    distance = math.hypot(dx, dy)
    deviations = [
        abs(dy * (point.x - 100) - dx * (point.y - 100)) / distance
        for point in first.points[:-1]
    ]
    assert max(deviations) > 1


@pytest.mark.asyncio
async def test_natural_pointer_move_dispatches_bounded_reproducible_path() -> None:
    first = FakeTab()
    second = FakeTab()
    first_sleeps: list[float] = []
    second_sleeps: list[float] = []

    async def first_sleep(seconds: float) -> None:
        first_sleeps.append(seconds)

    async def second_sleep(seconds: float) -> None:
        second_sleeps.append(seconds)

    first_result = await PointerOperations(first, sleep=first_sleep).move_to(
        442, 369, profile="natural"
    )
    second_result = await PointerOperations(second, sleep=second_sleep).move_to(
        442, 369, profile="natural"
    )

    assert first.page.events == second.page.events
    assert first_result == second_result
    assert first_sleeps == second_sleeps == list(
        plan_pointer_path(Point(100, 100), Point(442, 369), "natural").delays
    )
    assert first_result.profile == "natural"
    assert first_result.steps == 24
    assert first_result.planned_duration_ms == 264
    assert (_event_params(first)[-1]["x"], _event_params(first)[-1]["y"]) == (
        442,
        369,
    )


@pytest.mark.asyncio
async def test_coordinate_click_is_move_optional_delay_press_release() -> None:
    tab = FakeTab()
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    result = await PointerOperations(tab, sleep=fake_sleep).click_at(
        50,
        75,
        button="right",
        delay_before_press_ms=250,
    )

    events = _event_params(tab)
    assert [event["type"] for event in events] == [
        "mouseMoved",
        "mousePressed",
        "mouseReleased",
    ]
    assert [event["button"] for event in events] == ["none", "right", "right"]
    assert [event["buttons"] for event in events] == [0, 2, 0]
    assert sleeps == [0.25]
    assert result.to_dict() == {
        "profile": "direct",
        "button": "right",
        "start_x": 100.0,
        "start_y": 100.0,
        "target_x": 50.0,
        "target_y": 75.0,
        "steps": 1,
        "delay_before_press_ms": 250,
        "planned_duration_ms": 250,
    }
    assert tab.stabilized == ["pointer_click"]


@pytest.mark.asyncio
async def test_natural_click_moves_along_path_then_presses_and_releases() -> None:
    tab = FakeTab()
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    result = await PointerOperations(tab, sleep=fake_sleep).click_at(
        442,
        369,
        profile="natural",
        delay_before_press_ms=20,
    )

    events = _event_params(tab)
    assert [event["type"] for event in events] == ["mouseMoved"] * 24 + [
        "mousePressed",
        "mouseReleased",
    ]
    assert result.profile == "natural"
    assert result.steps == 24
    assert result.planned_duration_ms == 284
    path = plan_pointer_path(Point(100, 100), Point(442, 369), "natural")
    assert sleeps == [*path.delays, 0.02]


@pytest.mark.asyncio
async def test_drag_preserves_waypoint_order_and_held_button_state() -> None:
    tab = FakeTab()
    result = await PointerOperations(tab).drag_to(
        10,
        20,
        90,
        100,
        button="left",
        waypoints=(Point(30, 20), Point(30, 80)),
    )

    events = _event_params(tab)
    assert [event["type"] for event in events] == [
        "mouseMoved",
        "mousePressed",
        "mouseMoved",
        "mouseMoved",
        "mouseMoved",
        "mouseReleased",
    ]
    assert [(event["x"], event["y"]) for event in events] == [
        (10.0, 20.0),
        (10.0, 20.0),
        (30, 20),
        (30, 80),
        (90.0, 100.0),
        (90.0, 100.0),
    ]
    assert [event["buttons"] for event in events] == [0, 1, 1, 1, 1, 0]
    assert result.to_dict() == {
        "profile": "direct",
        "button": "left",
        "start_x": 10.0,
        "start_y": 20.0,
        "target_x": 90.0,
        "target_y": 100.0,
        "approach_steps": 1,
        "drag_steps": 3,
        "waypoint_count": 2,
        "planned_duration_ms": 0,
    }
    assert tab.stabilized == ["pointer_drag"]


@pytest.mark.asyncio
async def test_natural_drag_keeps_one_button_hold_across_bounded_segments() -> None:
    tab = FakeTab()

    async def fake_sleep(_seconds: float) -> None:
        return None

    result = await PointerOperations(tab, sleep=fake_sleep).drag_to(
        10,
        20,
        90,
        100,
        profile="natural",
        waypoints=(Point(30, 20),),
    )

    events = _event_params(tab)
    event_types = [event["type"] for event in events]
    assert event_types.count("mousePressed") == 1
    assert event_types.count("mouseReleased") == 1
    assert result.profile == "natural"
    assert result.approach_steps == 24
    assert result.drag_steps == 48
    assert result.waypoint_count == 1
    assert result.planned_duration_ms == 792
    assert (events[-1]["x"], events[-1]["y"]) == (90, 100)
    press_index = event_types.index("mousePressed")
    release_index = event_types.index("mouseReleased")
    assert all(event["buttons"] == 1 for event in events[press_index:release_index])


@pytest.mark.asyncio
async def test_drag_releases_button_after_held_move_failure() -> None:
    tab = FakeTab(fail_on_event=3)

    with pytest.raises(RuntimeError, match="injected CDP failure"):
        await PointerOperations(tab).drag_to(10, 20, 90, 100)

    assert [event["type"] for event in _event_params(tab)] == [
        "mouseMoved",
        "mousePressed",
        "mouseMoved",
        "mouseReleased",
    ]
    assert _event_params(tab)[-1]["buttons"] == 0
    assert tab.stabilized == []


@pytest.mark.asyncio
async def test_pointer_coordinates_reject_negative_values() -> None:
    pointer = PointerOperations(FakeTab())

    with pytest.raises(ValueError, match="target coordinates"):
        await pointer.move_to(-1, 0)
    with pytest.raises(ValueError, match="start coordinates"):
        await pointer.drag_to(-1, 0, 10, 10)
    with pytest.raises(ValueError, match="waypoint coordinates"):
        await pointer.drag_to(0, 0, 10, 10, waypoints=(Point(-1, 2),))
