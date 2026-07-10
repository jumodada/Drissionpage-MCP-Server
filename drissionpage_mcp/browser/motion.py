"""Pure motion planning for viewport pointer operations."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


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
class MotionStep:
    """One generated move event and its preceding inter-point delay."""

    point: Point
    delay: float
    jitter: Point


@dataclass(frozen=True, slots=True)
class MotionPlan:
    """A complete movement plan from start to target."""

    start: Point
    target: Point
    control_1: Point
    control_2: Point
    steps: tuple[MotionStep, ...]


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
        distance = math.hypot(target.x - start.x, target.y - start.y)
        if distance < 1e-9:
            step = MotionStep(
                target,
                self._rng.uniform(config.interval_min, config.interval_max),
                Point(0, 0),
            )
            return MotionPlan(start, target, start, target, (step,))

        steps = self._step_count(config)
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
                )
            )

        return MotionPlan(
            start=start,
            target=target,
            control_1=control_1,
            control_2=control_2,
            steps=tuple(generated),
        )

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
