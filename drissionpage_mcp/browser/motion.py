"""Pure motion planning for viewport pointer operations."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from typing import Literal

MotionPhase = Literal["move", "main", "overshoot", "correction"]
DragAxis = Literal["x", "y"]


@dataclass(frozen=True, slots=True)
class Point:
    """A viewport point in CSS pixels."""

    x: float
    y: float


@dataclass(frozen=True, slots=True)
class MotionConfig:
    """Bounds used to generate one pointer motion plan."""

    steps_min: int = 20
    steps_max: int = 35
    interval_min: float = 0.008
    interval_max: float = 0.025
    jitter_px: float = 0.5
    curve_min_ratio: float = 0.08
    curve_max_ratio: float = 0.22

    def __post_init__(self) -> None:
        _ordered("steps", self.steps_min, self.steps_max)
        _ordered("interval", self.interval_min, self.interval_max)
        _ordered("curve ratio", self.curve_min_ratio, self.curve_max_ratio)
        if self.steps_min < 1:
            raise ValueError("steps_min must be at least 1")
        if self.interval_min < 0:
            raise ValueError("interval_min cannot be negative")
        if self.jitter_px < 0:
            raise ValueError("jitter_px cannot be negative")
        if self.curve_min_ratio < 0:
            raise ValueError("curve_min_ratio cannot be negative")


@dataclass(frozen=True, slots=True)
class DragKinematics:
    """Time-domain and correction bounds for one held-button drag."""

    duration_min: float = 0.30
    duration_max: float = 1.10
    duration_base: float = 0.18
    distance_factor: float = 0.018
    interval_correlation: float = 0.65
    overshoot_min_px: float = 0.0
    overshoot_max_px: float = 2.0
    correction_steps_min: int = 2
    correction_steps_max: int = 5
    micro_pause_probability: float = 0.25
    micro_pause_min: float = 0.035
    micro_pause_max: float = 0.110
    axis: DragAxis | None = None

    def __post_init__(self) -> None:
        _ordered("duration", self.duration_min, self.duration_max)
        _ordered("overshoot", self.overshoot_min_px, self.overshoot_max_px)
        _ordered(
            "correction steps", self.correction_steps_min, self.correction_steps_max
        )
        _ordered("micro pause", self.micro_pause_min, self.micro_pause_max)
        if self.duration_min < 0 or self.duration_base < 0:
            raise ValueError("duration values cannot be negative")
        if self.distance_factor < 0:
            raise ValueError("distance_factor cannot be negative")
        if not 0 <= self.interval_correlation < 1:
            raise ValueError("interval correlation must be in [0, 1)")
        if self.overshoot_min_px < 0:
            raise ValueError("overshoot cannot be negative")
        if self.correction_steps_min < 1:
            raise ValueError("correction_steps_min must be at least 1")
        if not 0 <= self.micro_pause_probability <= 1:
            raise ValueError("micro pause probability must be in [0, 1]")
        if self.micro_pause_min < 0:
            raise ValueError("micro pause cannot be negative")


@dataclass(frozen=True, slots=True)
class MotionStep:
    """One generated move event and its preceding inter-point delay."""

    point: Point
    delay: float
    jitter: Point
    phase: MotionPhase = "move"


@dataclass(frozen=True, slots=True)
class MotionPlan:
    """A complete movement plan from start to target."""

    start: Point
    target: Point
    control_1: Point
    control_2: Point
    steps: tuple[MotionStep, ...]


@dataclass(frozen=True, slots=True)
class MotionPause:
    """A pause inserted after one held movement step."""

    after_step: int
    duration: float


@dataclass(frozen=True, slots=True)
class DragMotionPlan:
    """Segmented held-button drag plan with observable timing metadata."""

    start: Point
    target: Point
    steps: tuple[MotionStep, ...]
    pauses: tuple[MotionPause, ...]
    main_steps: int
    overshoot_steps: int
    correction_steps: int
    overshoot_px: float

    @property
    def movement_duration(self) -> float:
        return sum(step.delay for step in self.steps)

    @property
    def pause_duration(self) -> float:
        return sum(pause.duration for pause in self.pauses)


class MotionPlanner:
    """Generate cubic Bézier paths with eased sampling and bounded jitter."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    def plan(
        self,
        start: Point,
        target: Point,
        config: MotionConfig,
    ) -> MotionPlan:
        return self._plan_with_steps(
            start,
            target,
            config,
            steps=self._step_count(config),
            phase="move",
        )

    def plan_drag(
        self,
        start: Point,
        target: Point,
        config: MotionConfig,
        kinematics: DragKinematics,
    ) -> DragMotionPlan:
        """Plan distance-aware held motion, optional pause, overshoot, and correction."""

        distance = math.hypot(target.x - start.x, target.y - start.y)
        if distance < 1e-9:
            step = MotionStep(target, 0, Point(0, 0), "main")
            return DragMotionPlan(start, target, (step,), (), 1, 0, 0, 0)

        steps = self._step_count(config)
        main = self._plan_with_steps(start, target, config, steps=steps, phase="main")
        if kinematics.axis is not None:
            main = self._constrain_axis(main, kinematics.axis)
        duration = self._drag_duration(distance, steps, config, kinematics)
        delays = self._correlated_delays(
            steps,
            config.interval_min,
            config.interval_max,
            duration,
            kinematics.interval_correlation,
        )
        main_steps = tuple(
            replace(step, delay=delay, phase="main")
            for step, delay in zip(main.steps, delays)
        )

        overshoot_px = self._rng.uniform(
            kinematics.overshoot_min_px, kinematics.overshoot_max_px
        )
        overshoot_steps: tuple[MotionStep, ...] = ()
        correction_steps: tuple[MotionStep, ...] = ()
        if overshoot_px > 1e-9:
            unit_x = (target.x - start.x) / distance
            unit_y = (target.y - start.y) / distance
            overshoot_target = Point(
                max(0.0, target.x + unit_x * overshoot_px),
                max(0.0, target.y + unit_y * overshoot_px),
            )
            overshoot_count = max(2, min(4, round(overshoot_px) + 1))
            correction_count = self._rng.randint(
                kinematics.correction_steps_min,
                kinematics.correction_steps_max,
            )
            overshoot_steps = self._linear_segment(
                target, overshoot_target, overshoot_count, "overshoot"
            )
            correction_steps = self._linear_segment(
                overshoot_target, target, correction_count, "correction"
            )

        pauses: tuple[MotionPause, ...] = ()
        if steps >= 4 and self._rng.random() < kinematics.micro_pause_probability:
            after_step = self._rng.randint(
                max(1, round(steps * 0.45)), max(1, round(steps * 0.80))
            )
            pauses = (
                MotionPause(
                    after_step=after_step,
                    duration=self._rng.uniform(
                        kinematics.micro_pause_min, kinematics.micro_pause_max
                    ),
                ),
            )

        return DragMotionPlan(
            start=start,
            target=target,
            steps=main_steps + overshoot_steps + correction_steps,
            pauses=pauses,
            main_steps=len(main_steps),
            overshoot_steps=len(overshoot_steps),
            correction_steps=len(correction_steps),
            overshoot_px=overshoot_px,
        )

    def _plan_with_steps(
        self,
        start: Point,
        target: Point,
        config: MotionConfig,
        *,
        steps: int,
        phase: MotionPhase,
    ) -> MotionPlan:
        distance = math.hypot(target.x - start.x, target.y - start.y)
        if distance < 1e-9:
            step = MotionStep(
                target,
                self._rng.uniform(config.interval_min, config.interval_max),
                Point(0, 0),
                phase,
            )
            return MotionPlan(start, target, start, target, (step,))

        control_1, control_2 = self._control_points(start, target, distance, config)
        generated: list[MotionStep] = []
        effective_jitter = min(config.jitter_px, distance / 4)

        for index in range(1, steps + 1):
            eased = smoothstep(index / steps)
            curve_point = cubic_bezier(eased, start, control_1, control_2, target)
            if index == steps:
                jitter = Point(0, 0)
                point = target
            else:
                jitter = Point(
                    self._rng.uniform(-effective_jitter, effective_jitter),
                    self._rng.uniform(-effective_jitter, effective_jitter),
                )
                point = Point(
                    max(0.0, curve_point.x + jitter.x),
                    max(0.0, curve_point.y + jitter.y),
                )
            generated.append(
                MotionStep(
                    point=point,
                    delay=self._rng.uniform(config.interval_min, config.interval_max),
                    jitter=jitter,
                    phase=phase,
                )
            )

        return MotionPlan(start, target, control_1, control_2, tuple(generated))

    def _constrain_axis(self, plan: MotionPlan, axis: DragAxis) -> MotionPlan:
        """Keep slider motion close to its primary axis while retaining smooth progress."""

        count = len(plan.steps)
        constrained: list[MotionStep] = []
        for index, step in enumerate(plan.steps, start=1):
            if index == count:
                point = plan.target
            else:
                progress = smoothstep(index / count)
                if axis == "x":
                    point = Point(
                        step.point.x,
                        max(
                            0.0,
                            plan.start.y
                            + (plan.target.y - plan.start.y) * progress
                            + step.jitter.y,
                        ),
                    )
                else:
                    point = Point(
                        max(
                            0.0,
                            plan.start.x
                            + (plan.target.x - plan.start.x) * progress
                            + step.jitter.x,
                        ),
                        step.point.y,
                    )
            constrained.append(replace(step, point=point))
        return replace(plan, steps=tuple(constrained))

    def _linear_segment(
        self,
        start: Point,
        target: Point,
        steps: int,
        phase: MotionPhase,
    ) -> tuple[MotionStep, ...]:
        generated = []
        for index in range(1, steps + 1):
            progress = smoothstep(index / steps)
            generated.append(
                MotionStep(
                    point=Point(
                        start.x + (target.x - start.x) * progress,
                        start.y + (target.y - start.y) * progress,
                    ),
                    delay=self._rng.uniform(0.012, 0.024),
                    jitter=Point(0, 0),
                    phase=phase,
                )
            )
        return tuple(generated)

    def _drag_duration(
        self,
        distance: float,
        steps: int,
        config: MotionConfig,
        kinematics: DragKinematics,
    ) -> float:
        noise = self._rng.uniform(-0.06, 0.09)
        modeled = (
            kinematics.duration_base
            + kinematics.distance_factor * math.sqrt(distance)
            + noise
        )
        feasible_min = steps * config.interval_min
        feasible_max = steps * config.interval_max
        lower = max(kinematics.duration_min, feasible_min)
        upper = min(kinematics.duration_max, feasible_max)
        if lower > upper:
            lower, upper = feasible_min, feasible_max
        return min(upper, max(lower, modeled))

    def _correlated_delays(
        self,
        count: int,
        minimum: float,
        maximum: float,
        total: float,
        correlation: float,
    ) -> tuple[float, ...]:
        if count == 1:
            return (min(maximum, max(minimum, total)),)
        current = self._rng.uniform(minimum, maximum)
        raw: list[float] = []
        for _ in range(count):
            sample = self._rng.uniform(minimum, maximum)
            current = current * correlation + sample * (1 - correlation)
            raw.append(current)
        scale = total / sum(raw)
        scaled = [min(maximum, max(minimum, value * scale)) for value in raw]
        return tuple(scaled)

    def _step_count(self, config: MotionConfig) -> int:
        return self._rng.randint(config.steps_min, config.steps_max)

    def _control_points(
        self,
        start: Point,
        target: Point,
        distance: float,
        config: MotionConfig,
    ) -> tuple[Point, Point]:
        dx = target.x - start.x
        dy = target.y - start.y
        normal_x = -dy / distance
        normal_y = dx / distance
        direction = self._rng.choice((-1.0, 1.0))
        curve = distance * self._rng.uniform(
            config.curve_min_ratio, config.curve_max_ratio
        )
        first_progress = self._rng.uniform(0.25, 0.40)
        second_progress = self._rng.uniform(0.60, 0.80)
        return (
            Point(
                start.x + dx * first_progress + normal_x * curve * direction,
                start.y + dy * first_progress + normal_y * curve * direction,
            ),
            Point(
                start.x + dx * second_progress + normal_x * curve * direction * 0.65,
                start.y + dy * second_progress + normal_y * curve * direction * 0.65,
            ),
        )


def smoothstep(t: float) -> float:
    """Cubic ease-in-out used to sample the geometric path."""

    bounded = min(1.0, max(0.0, t))
    return bounded * bounded * (3.0 - 2.0 * bounded)


def cubic_bezier(t: float, p0: Point, p1: Point, p2: Point, p3: Point) -> Point:
    """Evaluate one point on a cubic Bézier curve."""

    remaining = 1.0 - t
    return Point(
        remaining**3 * p0.x
        + 3 * remaining**2 * t * p1.x
        + 3 * remaining * t**2 * p2.x
        + t**3 * p3.x,
        remaining**3 * p0.y
        + 3 * remaining**2 * t * p1.y
        + 3 * remaining * t**2 * p2.y
        + t**3 * p3.y,
    )


def _ordered(name: str, lower: float, upper: float) -> None:
    if lower > upper:
        raise ValueError(f"{name} minimum cannot exceed maximum")
