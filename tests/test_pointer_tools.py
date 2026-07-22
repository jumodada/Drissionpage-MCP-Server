"""Unit success and branch coverage for public pointer tools."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from drissionpage_mcp.browser.motion import Point
from drissionpage_mcp.browser.targeting import ResolvedTarget
from drissionpage_mcp.tools import pointer


class MotionResult:
    def __init__(self, *, drag: bool = False) -> None:
        self.drag = drag

    def to_dict(self) -> dict[str, object]:
        if not self.drag:
            return {
                "profile": "direct",
                "start_x": 0,
                "start_y": 0,
                "target_x": 10,
                "target_y": 20,
                "steps": 1,
                "planned_duration_ms": 0,
            }
        return {
            "profile": "direct",
            "button": "left",
            "start_x": 10,
            "start_y": 20,
            "target_x": 100,
            "target_y": 20,
            "approach_steps": 1,
            "drag_steps": 1,
            "waypoint_count": 0,
            "planned_duration_ms": 0,
        }


class FakePointer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    async def move_to(self, *args: object, **kwargs: object) -> MotionResult:
        self.calls.append(("move", args, kwargs))
        return MotionResult()

    async def drag_to(self, *args: object, **kwargs: object) -> MotionResult:
        self.calls.append(("drag", args, kwargs))
        return MotionResult(drag=True)

    async def click_at(self, *args: object, **kwargs: object) -> MotionResult:
        self.calls.append(("click", args, kwargs))
        result = MotionResult()
        result.to_dict = lambda: {
            "profile": "direct",
            "button": "left",
            "start_x": 0,
            "start_y": 0,
            "target_x": 10,
            "target_y": 20,
            "steps": 1,
            "delay_before_press_ms": 0,
            "planned_duration_ms": 0,
        }
        return result


class FakeTargeting:
    def __init__(self, resolved: dict[str, ResolvedTarget]) -> None:
        self.resolved = resolved
        self.calls = []

    def resolve_many(self, targets):
        self.calls.append(targets)
        return {name: self.resolved[name] for name in targets}


class FakeContext:
    def __init__(self, targeting: FakeTargeting) -> None:
        self.tab = SimpleNamespace(
            url="https://example.test/",
            pointer=FakePointer(),
            targeting=targeting,
        )

    def current_tab_or_die(self):
        return self.tab


def _resolved(name: str, left: float, top: float, width: float, height: float):
    return ResolvedTarget(
        selector=f"#{name}",
        locator=f"css:#{name}",
        selector_strategy="css",
        selector_normalized=True,
        frame_selector=None,
        shadow_hosts=(),
        anchor="center",
        offset_x=0,
        offset_y=0,
        point=Point(left + width / 2, top + height / 2),
        left=left,
        top=top,
        right=left + width,
        bottom=top + height,
        width=width,
        height=height,
    )


@pytest.mark.asyncio
async def test_coordinate_pointer_tools_delegate_to_pointer_capability() -> None:
    ctx = FakeContext(FakeTargeting({}))

    move = await pointer.pointer_move.execute(
        ctx, pointer.PointerCoordinatesInput(x=10, y=20)
    )
    drag = await pointer.pointer_drag.execute(
        ctx, pointer.PointerDragInput(start_x=10, start_y=20, end_x=100, end_y=20)
    )
    click = await pointer.click_coordinates.execute(
        ctx, pointer.ClickCoordinatesInput(x=10, y=20)
    )

    assert move.structured_content()["data"]["motion"]["steps"] == 1
    assert drag.structured_content()["data"]["motion"]["drag_steps"] == 1
    assert click.structured_content()["data"]["motion"]["delay_before_press_ms"] == 0
    assert [call[0] for call in ctx.tab.pointer.calls] == ["move", "drag", "click"]

    for _, _, kwargs in ctx.tab.pointer.calls:
        assert kwargs["profile"] == "direct"


def test_pointer_profiles_are_bounded_to_direct_and_natural() -> None:
    natural = pointer.ClickCoordinatesInput(x=10, y=20, profile="natural")

    assert natural.profile == "natural"
    with pytest.raises(ValidationError):
        pointer.ClickCoordinatesInput.model_validate(
            {"x": 10, "y": 20, "profile": "human_like"}
        )


def test_pointer_drag_waypoints_are_bounded_and_strict() -> None:
    valid = pointer.PointerDragInput.model_validate(
        {
            "start_x": 10,
            "start_y": 20,
            "end_x": 100,
            "end_y": 120,
            "waypoints": [{"x": 40, "y": 20}, {"x": 40, "y": 80}],
        }
    )

    assert [(point.x, point.y) for point in valid.waypoints] == [(40, 20), (40, 80)]

    invalid_payloads = [
        {
            "start_x": 10,
            "start_y": 20,
            "end_x": 100,
            "end_y": 120,
            "waypoints": [{"x": -1, "y": 20}],
        },
        {
            "start_x": 10,
            "start_y": 20,
            "end_x": 100,
            "end_y": 120,
            "waypoints": [{"x": index, "y": 20} for index in range(7)],
        },
        {
            "start_x": 10,
            "start_y": 20,
            "end_x": 100,
            "end_y": 120,
            "waypoints": [{"x": 40, "y": 20, "pause_ms": 50}],
        },
    ]
    for payload in invalid_payloads:
        with pytest.raises(ValidationError):
            pointer.PointerDragInput.model_validate(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["element", "offset", "track_ratio"])
async def test_element_drag_supports_all_destination_modes(kind: str) -> None:
    resolved = {
        "source": _resolved("source", 10, 10, 20, 20),
        "target": _resolved("target", 100, 20, 30, 30),
        "track": _resolved("track", 20, 10, 200, 20),
    }
    ctx = FakeContext(FakeTargeting(resolved))
    if kind == "element":
        destination = {"kind": "element", "target": {"selector": "#target"}}
    elif kind == "offset":
        destination = {"kind": "offset", "x": 50, "y": -5}
    else:
        destination = {
            "kind": "track_ratio",
            "track": {"selector": "#track"},
            "ratio": 0.5,
            "axis": "x",
        }
    args = pointer.PointerDragElementInput.model_validate(
        {"source": {"selector": "#source"}, "destination": destination}
    )

    outcome = await pointer.pointer_drag_element.execute(ctx, args)

    data = outcome.structured_content()["data"]
    assert data["destination"]["kind"] == kind
    call = ctx.tab.pointer.calls[-1]
    assert call[0] == "drag"
    if kind == "track_ratio":
        assert data["destination"]["track"]["selector"] == "#track"
        assert data["destination"]["axis"] == "x"
        assert call[2]["axis"] == "x"
    elif kind == "element":
        assert data["destination"]["target"]["selector"] == "#target"
    else:
        assert data["destination"]["offset_x"] == 50


@pytest.mark.asyncio
async def test_element_drag_rejects_negative_resolved_destination() -> None:
    ctx = FakeContext(FakeTargeting({"source": _resolved("source", 0, 0, 10, 10)}))
    args = pointer.PointerDragElementInput.model_validate(
        {
            "source": {"selector": "#source"},
            "destination": {"kind": "offset", "x": -20, "y": 0},
        }
    )

    outcome = await pointer.pointer_drag_element.execute(ctx, args)
    assert outcome.structured_content()["ok"] is False
    assert "cannot be negative" in outcome.structured_content()["message"]
