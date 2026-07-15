"""Viewport pointer movement, drag, and coordinate click tools."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..browser.motion import Point
from ..browser.targeting import ElementTarget
from ..tool_outputs import (
    PageClickXYData,
    PagePointerDragData,
    PagePointerDragElementData,
    PagePointerMoveData,
)
from .base import ToolInput, ToolOutcome, ToolType, define_tool

if TYPE_CHECKING:
    from ..context import DrissionPageContext


class PointerCoordinatesInput(ToolInput):
    """Shared input schema for vision-directed viewport pointer movement."""

    x: float = Field(..., ge=0, description="Viewport X coordinate in CSS pixels")
    y: float = Field(..., ge=0, description="Viewport Y coordinate in CSS pixels")
    start_x: float | None = Field(
        default=None, ge=0, description="Optional known pointer start X coordinate"
    )
    start_y: float | None = Field(
        default=None, ge=0, description="Optional known pointer start Y coordinate"
    )
    element: str = Field(
        "", description="Human-readable element or interaction description"
    )
    profile: Literal["natural", "precise", "direct"] = Field(
        default="natural",
        description=(
            "Pointer movement profile; natural uses 20–35 cubic Bézier steps, "
            "8–25ms intervals, ±0.5px jitter, 100–300ms reaction delay, and "
            "50–120ms button hold; precise lowers jitter; direct is one-step."
        ),
    )

    @model_validator(mode="after")
    def _paired_start(self) -> "PointerCoordinatesInput":
        if (self.start_x is None) != (self.start_y is None):
            raise ValueError("start_x and start_y must be provided together")
        return self


class PointerWaypointInput(BaseModel):
    """One viewport point visited while the mouse button remains pressed."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(..., ge=0, description="Viewport X coordinate in CSS pixels")
    y: float = Field(..., ge=0, description="Viewport Y coordinate in CSS pixels")


class PointerDragInput(ToolInput):
    """Input schema for one failure-safe viewport drag action."""

    start_x: float = Field(..., ge=0, description="Viewport drag start X in CSS pixels")
    start_y: float = Field(..., ge=0, description="Viewport drag start Y in CSS pixels")
    end_x: float = Field(..., ge=0, description="Viewport drag end X in CSS pixels")
    end_y: float = Field(..., ge=0, description="Viewport drag end Y in CSS pixels")
    waypoints: list[PointerWaypointInput] = Field(
        default_factory=list,
        max_length=6,
        description=(
            "Optional ordered viewport points visited while the button remains pressed"
        ),
    )
    element: str = Field(
        "", description="Human-readable draggable element or interaction description"
    )
    profile: Literal["natural", "precise", "direct"] = Field(
        default="natural",
        description=(
            "Held-drag profile. natural uses distance-aware timing, acceleration and "
            "deceleration, correlated intervals, bounded jitter, optional micro-pause, "
            "and exact-target correction."
        ),
    )
    button: Literal["left", "right", "middle"] = Field(
        default="left", description="Mouse button held during the drag"
    )


class ElementTargetInput(BaseModel):
    """Selector path resolved immediately before a pointer action."""

    model_config = ConfigDict(extra="forbid")

    selector: str = Field(
        ..., min_length=1, max_length=2000, description="CSS or XPath selector"
    )
    frame_selector: str | None = Field(
        default=None,
        min_length=1,
        max_length=2000,
        description="Optional same-origin iframe CSS or XPath selector",
    )
    shadow_hosts: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Ordered CSS selectors for nested open shadow hosts; Shadow DOM target selectors must also be CSS",
    )
    anchor: Literal["center", "left", "right", "top", "bottom"] = "center"
    offset_x: float = Field(default=0, ge=-10000, le=10000)
    offset_y: float = Field(default=0, ge=-10000, le=10000)

    def to_target(self) -> ElementTarget:
        return ElementTarget.from_selectors(
            self.selector,
            frame_selector=self.frame_selector,
            shadow_hosts=tuple(self.shadow_hosts),
            anchor=self.anchor,
            offset_x=self.offset_x,
            offset_y=self.offset_y,
        )


class ElementDestinationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["element"]
    target: ElementTargetInput


class OffsetDestinationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["offset"]
    x: float = Field(..., ge=-10000, le=10000)
    y: float = Field(..., ge=-10000, le=10000)


class TrackRatioDestinationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["track_ratio"]
    track: ElementTargetInput
    ratio: float = Field(..., ge=0, le=1)
    axis: Literal["x", "y"] = "x"


PointerElementDestination = Annotated[
    ElementDestinationInput | OffsetDestinationInput | TrackRatioDestinationInput,
    Field(discriminator="kind"),
]


class PointerDragElementInput(ToolInput):
    """Resolve an element and structured destination immediately before dragging."""

    source: ElementTargetInput
    destination: PointerElementDestination
    profile: Literal["natural", "precise", "direct"] = "natural"
    button: Literal["left", "right", "middle"] = "left"


class ClickCoordinatesInput(PointerCoordinatesInput):
    """Input schema for a vision-directed viewport click."""

    button: Literal["left", "right", "middle"] = Field(
        default="left", description="Mouse button to press and release"
    )
    delay_before_press_ms: int = Field(
        default=0,
        ge=0,
        le=10000,
        description=(
            "Optional additional delay after natural arrival and before mousePressed. "
            "This is timing control, not target-stability detection; moving targets "
            "require a fresh screenshot or selector-first action."
        ),
    )


@define_tool(
    name="page_pointer_move",
    title="Move Pointer to Coordinates",
    description=(
        "Move the viewport pointer along the selected Bézier/eased profile without "
        "clicking, for visual hover, reveal, canvas, and inspection workflows."
    ),
    input_schema=PointerCoordinatesInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=PagePointerMoveData,
    failure_message=lambda args, exc: (
        lambda e: f"Failed to move pointer to ({args.x}, {args.y}): {e}"
    )(exc),
)
async def pointer_move(
    context: "DrissionPageContext", args: PointerCoordinatesInput
) -> "ToolOutcome":
    """Move the pointer to viewport coordinates without pressing a button."""
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    result = await tab.pointer.move_to(
        args.x,
        args.y,
        start_x=args.start_x,
        start_y=args.start_y,
        profile=args.profile,
    )
    outcome.add_code("page.run_cdp(<pointer move sequence>)")
    outcome.add_result(
        f"Successfully moved pointer to coordinates ({args.x:g}, {args.y:g})",
        x=args.x,
        y=args.y,
        element=args.element,
        url=tab.url,
        motion=result.to_dict(),
    )
    outcome.set_include_snapshot(True)
    return outcome


@define_tool(
    name="page_pointer_drag",
    title="Drag Pointer Between Coordinates",
    description=(
        "Perform one failure-safe viewport drag through optional ordered waypoints "
        "with distance-aware timing, acceleration/deceleration, correlated intervals, "
        "bounded jitter, optional micro-pauses and exact final correction. Always "
        "releases the button."
    ),
    input_schema=PointerDragInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=PagePointerDragData,
    failure_message=lambda args, exc: (
        lambda e: f"Failed to drag from ({args.start_x}, {args.start_y}) to "
        f"({args.end_x}, {args.end_y}): {e}"
    )(exc),
)
async def pointer_drag(
    context: "DrissionPageContext", args: PointerDragInput
) -> "ToolOutcome":
    """Drag between viewport coordinates without exposing persistent button state."""
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    result = await tab.pointer.drag_to(
        args.start_x,
        args.start_y,
        args.end_x,
        args.end_y,
        profile=args.profile,
        button=args.button,
        waypoints=tuple(Point(point.x, point.y) for point in args.waypoints),
    )
    outcome.add_code("page.run_cdp(<pointer move/press/held-move/release sequence>)")
    outcome.add_result(
        "Successfully completed pointer drag",
        start_x=args.start_x,
        start_y=args.start_y,
        end_x=args.end_x,
        end_y=args.end_y,
        element=args.element,
        url=tab.url,
        motion=result.to_dict(),
    )
    outcome.set_include_snapshot(True)
    return outcome


@define_tool(
    name="page_pointer_drag_element",
    title="Drag Element to Structured Destination",
    description=(
        "Resolve a source element and element, offset, or track-ratio destination "
        "immediately before one failure-safe drag. Supports CSS/XPath in the top "
        "document or one same-origin iframe, plus CSS paths through nested open "
        "Shadow DOM hosts; use coordinate drag for visual-only targets."
    ),
    input_schema=PointerDragElementInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=PagePointerDragElementData,
    failure_message=lambda args, exc: f"Failed to resolve and drag element: {exc}",
)
async def pointer_drag_element(
    context: "DrissionPageContext", args: PointerDragElementInput
) -> "ToolOutcome":
    """Resolve selector geometry atomically and execute one held-button drag."""
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    targets = {"source": args.source.to_target()}
    if isinstance(args.destination, ElementDestinationInput):
        targets["target"] = args.destination.target.to_target()
    elif isinstance(args.destination, TrackRatioDestinationInput):
        targets["track"] = args.destination.track.to_target()
    resolved = tab.targeting.resolve_many(targets)
    source = resolved["source"]
    axis = None
    destination_data: dict[str, object]
    if isinstance(args.destination, ElementDestinationInput):
        target = resolved["target"]
        end_x, end_y = target.point.x, target.point.y
        destination_data = {
            "kind": "element",
            "x": end_x,
            "y": end_y,
            "target": target.to_dict(),
        }
    elif isinstance(args.destination, OffsetDestinationInput):
        end_x = source.point.x + args.destination.x
        end_y = source.point.y + args.destination.y
        destination_data = {
            "kind": "offset",
            "x": end_x,
            "y": end_y,
            "offset_x": args.destination.x,
            "offset_y": args.destination.y,
        }
    else:
        track = resolved["track"]
        axis = args.destination.axis
        if axis == "x":
            travel = max(0.0, track.width - source.width)
            end_x = track.left + source.width / 2 + travel * args.destination.ratio
            end_y = track.top + track.height / 2
        else:
            travel = max(0.0, track.height - source.height)
            end_x = track.left + track.width / 2
            end_y = track.top + source.height / 2 + travel * args.destination.ratio
        destination_data = {
            "kind": "track_ratio",
            "x": end_x,
            "y": end_y,
            "track": track.to_dict(),
            "ratio": args.destination.ratio,
            "axis": axis,
        }
    if end_x < 0 or end_y < 0:
        raise ValueError("resolved drag destination cannot be negative")
    motion = await tab.pointer.drag_to(
        source.point.x,
        source.point.y,
        end_x,
        end_y,
        profile=args.profile,
        button=args.button,
        axis=axis,
    )
    outcome.add_code("resolve selector geometry; page.run_cdp(<held drag sequence>)")
    outcome.add_result(
        "Successfully resolved and dragged element",
        source=source.to_dict(),
        destination=destination_data,
        url=tab.url,
        motion=motion.to_dict(),
    )
    outcome.set_include_snapshot(True)
    return outcome


@define_tool(
    name="page_click_xy",
    title="Click Coordinates",
    description=(
        "Move the viewport pointer to coordinates and click. The natural profile uses "
        "a cubic Bézier path, smoothstep easing, bounded jitter, reaction delay, and "
        "realistic button hold time."
    ),
    input_schema=ClickCoordinatesInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=PageClickXYData,
    failure_message=lambda args, exc: (
        lambda e: f"Failed to click at ({args.x}, {args.y}): {e}"
    )(exc),
)
async def click_coordinates(
    context: "DrissionPageContext", args: ClickCoordinatesInput
) -> "ToolOutcome":
    """Click at coordinates."""
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    result = await tab.pointer.click_at(
        args.x,
        args.y,
        start_x=args.start_x,
        start_y=args.start_y,
        profile=args.profile,
        button=args.button,
        delay_before_press_ms=args.delay_before_press_ms,
    )
    outcome.add_code("page.run_cdp(<pointer move/press/release sequence>)")
    outcome.add_result(
        f"Successfully clicked at coordinates ({args.x:g}, {args.y:g})",
        x=args.x,
        y=args.y,
        element=args.element,
        url=tab.url,
        motion=result.to_dict(),
    )
    outcome.set_include_snapshot(True)
    return outcome
