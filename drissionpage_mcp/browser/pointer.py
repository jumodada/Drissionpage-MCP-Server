"""Deterministic viewport pointer actions executed through Chromium CDP."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from .motion import Point, PointerPath, PointerProfile, plan_pointer_path

if TYPE_CHECKING:
    from ..tab import PageTab

PointerButton = Literal["left", "right", "middle"]
Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class MoveAction:
    point: Point
    delay: float = 0.0


@dataclass(frozen=True, slots=True)
class PauseAction:
    duration: float


@dataclass(frozen=True, slots=True)
class PressAction:
    button: PointerButton


@dataclass(frozen=True, slots=True)
class ReleaseAction:
    button: PointerButton


PointerAction = MoveAction | PauseAction | PressAction | ReleaseAction


@dataclass(frozen=True, slots=True)
class PointerSequence:
    """Immutable ordered pointer action chain."""

    actions: tuple[PointerAction, ...]


@dataclass(frozen=True, slots=True)
class PointerMoveResult:
    profile: PointerProfile
    start: Point
    target: Point
    steps: int = 1
    planned_duration_ms: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "start_x": self.start.x,
            "start_y": self.start.y,
            "target_x": self.target.x,
            "target_y": self.target.y,
            "steps": self.steps,
            "planned_duration_ms": self.planned_duration_ms,
        }


@dataclass(frozen=True, slots=True)
class PointerDragResult:
    profile: PointerProfile
    button: PointerButton
    start: Point
    target: Point
    drag_steps: int
    waypoint_count: int
    approach_steps: int = 1
    planned_duration_ms: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "button": self.button,
            "start_x": self.start.x,
            "start_y": self.start.y,
            "target_x": self.target.x,
            "target_y": self.target.y,
            "approach_steps": self.approach_steps,
            "drag_steps": self.drag_steps,
            "waypoint_count": self.waypoint_count,
            "planned_duration_ms": self.planned_duration_ms,
        }


@dataclass(frozen=True, slots=True)
class PointerClickResult:
    profile: PointerProfile
    button: PointerButton
    start: Point
    target: Point
    delay_before_press_ms: int
    steps: int = 1
    planned_duration_ms: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "button": self.button,
            "start_x": self.start.x,
            "start_y": self.start.y,
            "target_x": self.target.x,
            "target_y": self.target.y,
            "steps": self.steps,
            "delay_before_press_ms": self.delay_before_press_ms,
            "planned_duration_ms": self.planned_duration_ms,
        }


_BUTTON_BITS: dict[PointerButton, int] = {"left": 1, "right": 2, "middle": 4}


class PointerOperations:
    """Execute bounded pointer profiles and guarantee held-button cleanup."""

    def __init__(self, tab: "PageTab", *, sleep: Sleep | None = None) -> None:
        self._tab = tab
        self._sleep = sleep or asyncio.sleep

    async def move_to(
        self, x: float, y: float, *, profile: PointerProfile = "direct"
    ) -> PointerMoveResult:
        start = self._current_point()
        target = self._point(x, y, label="target")
        path = plan_pointer_path(start, target, profile)
        await self.execute(PointerSequence(self._path_actions(path)))
        await self._tab._stabilize("pointer_move", timeout=1.0, fallback_sleep=0.02)
        return PointerMoveResult(
            profile=profile,
            start=start,
            target=target,
            steps=len(path.points),
            planned_duration_ms=path.planned_duration_ms,
        )

    async def click_at(
        self,
        x: float,
        y: float,
        *,
        profile: PointerProfile = "direct",
        button: PointerButton = "left",
        delay_before_press_ms: int = 0,
    ) -> PointerClickResult:
        if not 0 <= delay_before_press_ms <= 10000:
            raise ValueError("delay_before_press_ms must be between 0 and 10000")
        start = self._current_point()
        target = self._point(x, y, label="target")
        path = plan_pointer_path(start, target, profile)
        actions: list[PointerAction] = list(self._path_actions(path))
        if delay_before_press_ms:
            actions.append(PauseAction(delay_before_press_ms / 1000))
        actions.extend((PressAction(button), ReleaseAction(button)))
        await self.execute(PointerSequence(tuple(actions)))
        await self._tab._stabilize("pointer_click", timeout=1.0, fallback_sleep=0.02)
        return PointerClickResult(
            profile=profile,
            button=button,
            start=start,
            target=target,
            delay_before_press_ms=delay_before_press_ms,
            steps=len(path.points),
            planned_duration_ms=(
                path.planned_duration_ms + delay_before_press_ms
            ),
        )

    async def drag_to(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        *,
        profile: PointerProfile = "direct",
        button: PointerButton = "left",
        axis: Literal["x", "y"] | None = None,
        waypoints: tuple[Point, ...] = (),
    ) -> PointerDragResult:
        start = self._point(start_x, start_y, label="start")
        target = self._point(end_x, end_y, label="target")
        if any(point.x < 0 or point.y < 0 for point in waypoints):
            raise ValueError("waypoint coordinates cannot be negative")
        approach = plan_pointer_path(self._current_point(), start, profile)
        segments: list[PointerPath] = []
        segment_start = start
        for segment_target in (*waypoints, target):
            segments.append(
                plan_pointer_path(
                    segment_start,
                    segment_target,
                    profile,
                    axis=axis,
                )
            )
            segment_start = segment_target
        actions: list[PointerAction] = [*self._path_actions(approach), PressAction(button)]
        for segment in segments:
            actions.extend(self._path_actions(segment))
        actions.extend((ReleaseAction(button),))
        await self.execute(PointerSequence(tuple(actions)))
        await self._tab._stabilize("pointer_drag", timeout=1.0, fallback_sleep=0.02)
        return PointerDragResult(
            profile=profile,
            button=button,
            start=start,
            target=target,
            approach_steps=len(approach.points),
            drag_steps=sum(len(segment.points) for segment in segments),
            waypoint_count=len(waypoints),
            planned_duration_ms=(
                approach.planned_duration_ms
                + sum(segment.planned_duration_ms for segment in segments)
            ),
        )

    async def execute(self, sequence: PointerSequence) -> None:
        pressed: PointerButton | None = None
        try:
            for action in sequence.actions:
                if isinstance(action, MoveAction):
                    if action.delay:
                        await self._sleep(action.delay)
                    self._dispatch_move(action.point, pressed)
                elif isinstance(action, PauseAction):
                    if action.duration:
                        await self._sleep(action.duration)
                elif isinstance(action, PressAction):
                    self._dispatch_button("mousePressed", action.button)
                    pressed = action.button
                else:
                    self._dispatch_button("mouseReleased", action.button)
                    pressed = None
        finally:
            if pressed is not None:
                self._dispatch_button("mouseReleased", pressed)

    @property
    def _page(self):
        return self._tab.page

    def _current_point(self) -> Point:
        actions = self._page.actions
        return Point(float(actions.curr_x), float(actions.curr_y))

    @staticmethod
    def _point(x: float, y: float, *, label: str) -> Point:
        if x < 0 or y < 0:
            raise ValueError(f"{label} coordinates cannot be negative")
        return Point(float(x), float(y))

    @staticmethod
    def _path_actions(path: PointerPath) -> tuple[MoveAction, ...]:
        return tuple(
            MoveAction(point, delay) for point, delay in zip(path.points, path.delays)
        )

    def _dispatch_move(
        self, point: Point, pressed: PointerButton | None = None
    ) -> None:
        actions = self._page.actions
        self._page.run_cdp(
            "Input.dispatchMouseEvent",
            type="mouseMoved",
            button=pressed or "none",
            buttons=_BUTTON_BITS[pressed] if pressed is not None else 0,
            x=point.x,
            y=point.y,
            modifiers=int(getattr(actions, "modifier", 0)),
        )
        actions.curr_x = point.x
        actions.curr_y = point.y

    def _dispatch_button(self, event_type: str, button: PointerButton) -> None:
        actions = self._page.actions
        self._page.run_cdp(
            "Input.dispatchMouseEvent",
            type=event_type,
            button=button,
            buttons=_BUTTON_BITS[button] if event_type == "mousePressed" else 0,
            clickCount=1,
            x=float(actions.curr_x),
            y=float(actions.curr_y),
            modifiers=int(getattr(actions, "modifier", 0)),
        )


__all__ = [
    "MoveAction",
    "PauseAction",
    "PointerButton",
    "PointerClickResult",
    "PointerDragResult",
    "PointerMoveResult",
    "PointerOperations",
    "PointerProfile",
    "PointerSequence",
    "PressAction",
    "ReleaseAction",
]
