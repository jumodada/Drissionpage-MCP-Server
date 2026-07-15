"""Viewport pointer action chains executed through Chromium CDP."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal

from .motion import DragKinematics, MotionConfig, MotionPlan, MotionPlanner, Point

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
    """Observable segmented drag metadata returned to MCP tools."""

    profile: PointerProfile
    button: PointerButton
    start: Point
    target: Point
    approach_steps: int
    drag_steps: int
    main_drag_steps: int
    overshoot_steps: int
    correction_steps: int
    micro_pause_count: int
    overshoot_px: float
    reaction_delay_ms: int
    grip_delay_ms: int
    movement_duration_ms: int
    micro_pause_duration_ms: int
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
            "main_drag_steps": self.main_drag_steps,
            "overshoot_steps": self.overshoot_steps,
            "correction_steps": self.correction_steps,
            "micro_pause_count": self.micro_pause_count,
            "overshoot_px": round(self.overshoot_px, 3),
            "reaction_delay_ms": self.reaction_delay_ms,
            "grip_delay_ms": self.grip_delay_ms,
            "movement_duration_ms": self.movement_duration_ms,
            "micro_pause_duration_ms": self.micro_pause_duration_ms,
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
    delay_before_press_ms: int
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
            "delay_before_press_ms": self.delay_before_press_ms,
            "hold_duration_ms": self.hold_duration_ms,
            "planned_duration_ms": self.planned_duration_ms,
        }


_BUTTON_BITS: dict[PointerButton, int] = {"left": 1, "right": 2, "middle": 4}


@dataclass(frozen=True, slots=True)
class PointerProfileSpec:
    """Internal movement, click timing, and held-drag behavior for one profile."""

    move_config: MotionConfig
    click_reaction: tuple[float, float]
    click_hold: tuple[float, float]
    drag_config: MotionConfig
    drag_kinematics: DragKinematics
    drag_reaction: tuple[float, float]
    drag_grip: tuple[float, float]
    drag_release: tuple[float, float]


_PROFILES: dict[PointerProfile, PointerProfileSpec] = {
    "natural": PointerProfileSpec(
        move_config=MotionConfig(),
        click_reaction=(0.100, 0.300),
        click_hold=(0.050, 0.120),
        drag_config=MotionConfig(
            steps_min=24,
            steps_max=40,
            interval_min=0.008,
            interval_max=0.025,
            jitter_px=0.8,
            curve_min_ratio=0.005,
            curve_max_ratio=0.020,
        ),
        drag_kinematics=DragKinematics(),
        drag_reaction=(0.080, 0.220),
        drag_grip=(0.035, 0.090),
        drag_release=(0.040, 0.110),
    ),
    "precise": PointerProfileSpec(
        move_config=MotionConfig(
            steps_min=18,
            steps_max=28,
            interval_min=0.008,
            interval_max=0.018,
            jitter_px=0.15,
            curve_min_ratio=0.04,
            curve_max_ratio=0.12,
        ),
        click_reaction=(0.080, 0.180),
        click_hold=(0.050, 0.100),
        drag_config=MotionConfig(
            steps_min=30,
            steps_max=48,
            interval_min=0.009,
            interval_max=0.022,
            jitter_px=0.3,
            curve_min_ratio=0.002,
            curve_max_ratio=0.010,
        ),
        drag_kinematics=DragKinematics(
            duration_min=0.40,
            duration_max=1.30,
            duration_base=0.24,
            distance_factor=0.020,
            overshoot_min_px=0,
            overshoot_max_px=0,
            micro_pause_probability=0.10,
        ),
        drag_reaction=(0.100, 0.240),
        drag_grip=(0.045, 0.100),
        drag_release=(0.055, 0.120),
    ),
    "direct": PointerProfileSpec(
        move_config=MotionConfig(
            steps_min=1,
            steps_max=1,
            interval_min=0,
            interval_max=0,
            jitter_px=0,
            curve_min_ratio=0,
            curve_max_ratio=0,
        ),
        click_reaction=(0, 0),
        click_hold=(0.050, 0.050),
        drag_config=MotionConfig(
            steps_min=1,
            steps_max=1,
            interval_min=0,
            interval_max=0,
            jitter_px=0,
            curve_min_ratio=0,
            curve_max_ratio=0,
        ),
        drag_kinematics=DragKinematics(
            duration_min=0,
            duration_max=0,
            duration_base=0,
            distance_factor=0,
            overshoot_min_px=0,
            overshoot_max_px=0,
            micro_pause_probability=0,
        ),
        drag_reaction=(0, 0),
        drag_grip=(0, 0),
        drag_release=(0.050, 0.050),
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
        axis: Literal["x", "y"] | None = None,
        waypoints: tuple[Point, ...] = (),
    ) -> PointerDragResult:
        if any(point.x < 0 or point.y < 0 for point in waypoints):
            raise ValueError("waypoint coordinates cannot be negative")
        _, start, approach = self._plan_move(
            start_x, start_y, start_x=None, start_y=None, profile=profile
        )
        if end_x < 0 or end_y < 0:
            raise ValueError("target coordinates cannot be negative")
        target = Point(float(end_x), float(end_y))
        spec = _PROFILES[profile]
        kinematics = spec.drag_kinematics
        if axis is not None:
            kinematics = replace(kinematics, axis=axis)
        targets = (*waypoints, target)
        segments = []
        segment_start = start
        for index, segment_target in enumerate(targets):
            segment_kinematics = kinematics
            if index < len(targets) - 1:
                segment_kinematics = replace(
                    segment_kinematics,
                    overshoot_min_px=0,
                    overshoot_max_px=0,
                )
            segments.append(
                self._planner.plan_drag(
                    segment_start,
                    segment_target,
                    spec.drag_config,
                    segment_kinematics,
                )
            )
            segment_start = segment_target
        reaction_delay = self._rng.uniform(*spec.drag_reaction)
        grip_delay = self._rng.uniform(*spec.drag_grip)
        release_delay = self._rng.uniform(*spec.drag_release)

        held_actions: list[PointerAction] = []
        for segment in segments:
            pauses = {pause.after_step: pause.duration for pause in segment.pauses}
            for index, step in enumerate(segment.steps, start=1):
                held_actions.append(MoveAction(step.point, step.delay))
                pause = pauses.get(index)
                if pause is not None:
                    held_actions.append(PauseAction(pause))

        sequence = PointerSequence(
            actions=(
                *(MoveAction(step.point, step.delay) for step in approach.steps),
                PauseAction(reaction_delay),
                PressAction(button),
                PauseAction(grip_delay),
                *held_actions,
                PauseAction(release_delay),
                ReleaseAction(button),
            )
        )
        await self.execute(sequence)
        await self._tab._stabilize("pointer_drag", timeout=1.0, fallback_sleep=0.02)
        movement_duration = sum(segment.movement_duration for segment in segments)
        micro_pause_duration = sum(segment.pause_duration for segment in segments)
        planned_duration = sum(step.delay for step in approach.steps)
        planned_duration += reaction_delay + grip_delay + movement_duration
        planned_duration += micro_pause_duration + release_delay
        final_segment = segments[-1]
        return PointerDragResult(
            profile=profile,
            button=button,
            start=start,
            target=target,
            approach_steps=len(approach.steps),
            drag_steps=sum(len(segment.steps) for segment in segments),
            main_drag_steps=sum(segment.main_steps for segment in segments),
            overshoot_steps=sum(segment.overshoot_steps for segment in segments),
            correction_steps=sum(segment.correction_steps for segment in segments),
            micro_pause_count=sum(len(segment.pauses) for segment in segments),
            overshoot_px=final_segment.overshoot_px,
            reaction_delay_ms=round(reaction_delay * 1000),
            grip_delay_ms=round(grip_delay * 1000),
            movement_duration_ms=round(movement_duration * 1000),
            micro_pause_duration_ms=round(micro_pause_duration * 1000),
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
        delay_before_press_ms: int = 0,
    ) -> PointerClickResult:
        start, target, plan = self._plan_move(
            x, y, start_x=start_x, start_y=start_y, profile=profile
        )
        spec = _PROFILES[profile]
        reaction_seconds = self._rng.uniform(*spec.click_reaction)
        configured_delay_seconds = delay_before_press_ms / 1000
        hold_seconds = self._rng.uniform(*spec.click_hold)
        sequence = PointerSequence(
            actions=(
                *(MoveAction(step.point, step.delay) for step in plan.steps),
                PauseAction(reaction_seconds),
                PauseAction(configured_delay_seconds),
                PressAction(button),
                PauseAction(hold_seconds),
                ReleaseAction(button),
            )
        )
        await self.execute(sequence)
        await self._tab._stabilize("pointer_click", timeout=1.0, fallback_sleep=0.02)
        planned_duration = sum(step.delay for step in plan.steps)
        planned_duration += reaction_seconds + configured_delay_seconds + hold_seconds
        return PointerClickResult(
            profile=profile,
            button=button,
            start=start,
            target=target,
            steps=len(plan.steps),
            reaction_delay_ms=round(reaction_seconds * 1000),
            delay_before_press_ms=delay_before_press_ms,
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
        config = _PROFILES[profile].move_config
        if start != current:
            self._dispatch_move(start)
        return start, target, self._planner.plan(start, target, config)

    def random_delay(self, minimum_ms: int, maximum_ms: int) -> float:
        """Return a profile-independent bounded delay in seconds."""
        return self._rng.uniform(minimum_ms, maximum_ms) / 1000

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
