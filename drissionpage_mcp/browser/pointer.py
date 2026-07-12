"""Viewport pointer action chains executed through Chromium CDP."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from .motion import MotionConfig, MotionPlan, MotionPlanner, Point

if TYPE_CHECKING:
    from ..tab import PageTab

PointerButton = Literal["left", "right", "middle"]
PointerProfile = Literal["natural", "precise", "direct"]
Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class MoveAction:
    point: Point
    delay: float


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
    """Observable movement metadata returned to MCP tools."""

    profile: PointerProfile
    start: Point
    target: Point
    steps: int
    planned_duration_ms: int

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
    """Observable drag metadata returned to the MCP tool."""

    profile: PointerProfile
    button: PointerButton
    start: Point
    target: Point
    approach_steps: int
    drag_steps: int
    press_delay_ms: int
    release_delay_ms: int
    planned_duration_ms: int

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
            "press_delay_ms": self.press_delay_ms,
            "release_delay_ms": self.release_delay_ms,
            "planned_duration_ms": self.planned_duration_ms,
        }


@dataclass(frozen=True, slots=True)
class PointerClickResult:
    """Observable click metadata returned to the MCP tool."""

    profile: PointerProfile
    button: PointerButton
    start: Point
    target: Point
    steps: int
    reaction_delay_ms: int
    hold_duration_ms: int
    planned_duration_ms: int

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "button": self.button,
            "start_x": self.start.x,
            "start_y": self.start.y,
            "target_x": self.target.x,
            "target_y": self.target.y,
            "steps": self.steps,
            "reaction_delay_ms": self.reaction_delay_ms,
            "hold_duration_ms": self.hold_duration_ms,
            "planned_duration_ms": self.planned_duration_ms,
        }


_BUTTON_BITS: dict[PointerButton, int] = {"left": 1, "right": 2, "middle": 4}


_PROFILES: dict[
    PointerProfile, tuple[MotionConfig, tuple[float, float], tuple[float, float]]
] = {
    "natural": (
        MotionConfig(),
        (0.100, 0.300),
        (0.050, 0.120),
    ),
    "precise": (
        MotionConfig(
            steps_min=18,
            steps_max=28,
            interval_min=0.008,
            interval_max=0.018,
            jitter_px=0.15,
            curve_min_ratio=0.04,
            curve_max_ratio=0.12,
        ),
        (0.080, 0.180),
        (0.050, 0.100),
    ),
    "direct": (
        MotionConfig(
            steps_min=1,
            steps_max=1,
            interval_min=0,
            interval_max=0,
            jitter_px=0,
            curve_min_ratio=0,
            curve_max_ratio=0,
        ),
        (0, 0),
        (0.050, 0.050),
    ),
}


class PointerOperations:
    """Own cursor state, natural movement planning, and button event execution."""

    def __init__(
        self,
        tab: "PageTab",
        *,
        rng: random.Random | None = None,
        sleep: Sleep | None = None,
    ) -> None:
        self._tab = tab
        self._rng = rng or random.Random()
        self._sleep = sleep or asyncio.sleep
        self._planner = MotionPlanner(self._rng)

    async def move_to(
        self,
        x: float,
        y: float,
        *,
        start_x: float | None = None,
        start_y: float | None = None,
        profile: PointerProfile = "natural",
    ) -> PointerMoveResult:
        start, target, plan = self._plan_move(
            x, y, start_x=start_x, start_y=start_y, profile=profile
        )
        await self.execute(
            PointerSequence(
                actions=tuple(MoveAction(step.point, step.delay) for step in plan.steps)
            )
        )
        await self._tab._stabilize("pointer_move", timeout=1.0, fallback_sleep=0.02)
        return PointerMoveResult(
            profile=profile,
            start=start,
            target=target,
            steps=len(plan.steps),
            planned_duration_ms=round(sum(step.delay for step in plan.steps) * 1000),
        )

    async def drag_to(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        *,
        profile: PointerProfile = "natural",
        button: PointerButton = "left",
    ) -> PointerDragResult:
        current, start, approach = self._plan_move(
            start_x, start_y, start_x=None, start_y=None, profile=profile
        )
        if end_x < 0 or end_y < 0:
            raise ValueError("target coordinates cannot be negative")
        target = Point(float(end_x), float(end_y))
        config, reaction, hold = _PROFILES[profile]
        drag = self._planner.plan(start, target, config)
        press_delay = self._rng.uniform(*reaction)
        release_delay = self._rng.uniform(*hold)
        sequence = PointerSequence(
            actions=(
                *(MoveAction(step.point, step.delay) for step in approach.steps),
                PauseAction(press_delay),
                PressAction(button),
                *(MoveAction(step.point, step.delay) for step in drag.steps),
                PauseAction(release_delay),
                ReleaseAction(button),
            )
        )
        await self.execute(sequence)
        await self._tab._stabilize("pointer_drag", timeout=1.0, fallback_sleep=0.02)
        planned_duration = sum(step.delay for step in approach.steps)
        planned_duration += sum(step.delay for step in drag.steps)
        planned_duration += press_delay + release_delay
        return PointerDragResult(
            profile=profile,
            button=button,
            start=start,
            target=target,
            approach_steps=len(approach.steps),
            drag_steps=len(drag.steps),
            press_delay_ms=round(press_delay * 1000),
            release_delay_ms=round(release_delay * 1000),
            planned_duration_ms=round(planned_duration * 1000),
        )

    async def click_at(
        self,
        x: float,
        y: float,
        *,
        start_x: float | None = None,
        start_y: float | None = None,
        profile: PointerProfile = "natural",
        button: PointerButton = "left",
    ) -> PointerClickResult:
        start, target, plan = self._plan_move(
            x, y, start_x=start_x, start_y=start_y, profile=profile
        )
        _, reaction, hold = _PROFILES[profile]
        reaction_seconds = self._rng.uniform(*reaction)
        hold_seconds = self._rng.uniform(*hold)
        sequence = PointerSequence(
            actions=(
                *(MoveAction(step.point, step.delay) for step in plan.steps),
                PauseAction(reaction_seconds),
                PressAction(button),
                PauseAction(hold_seconds),
                ReleaseAction(button),
            )
        )
        await self.execute(sequence)
        await self._tab._stabilize("pointer_click", timeout=1.0, fallback_sleep=0.02)
        planned_duration = sum(step.delay for step in plan.steps)
        planned_duration += reaction_seconds + hold_seconds
        return PointerClickResult(
            profile=profile,
            button=button,
            start=start,
            target=target,
            steps=len(plan.steps),
            reaction_delay_ms=round(reaction_seconds * 1000),
            hold_duration_ms=round(hold_seconds * 1000),
            planned_duration_ms=round(planned_duration * 1000),
        )

    def _plan_move(
        self,
        x: float,
        y: float,
        *,
        start_x: float | None,
        start_y: float | None,
        profile: PointerProfile,
    ) -> tuple[Point, Point, MotionPlan]:
        if (start_x is None) != (start_y is None):
            raise ValueError("start_x and start_y must be provided together")
        if x < 0 or y < 0:
            raise ValueError("target coordinates cannot be negative")

        actions = self._page.actions
        current = Point(float(actions.curr_x), float(actions.curr_y))
        start = (
            Point(float(start_x), float(start_y))
            if start_x is not None and start_y is not None
            else current
        )
        target = Point(float(x), float(y))
        config, _, _ = _PROFILES[profile]
        if start != current:
            self._dispatch_move(start)
        return start, target, self._planner.plan(start, target, config)

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
