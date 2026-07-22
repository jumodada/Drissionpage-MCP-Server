"""Bounded deterministic motion planning for viewport pointer capabilities."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

PointerProfile = Literal["direct", "natural"]


@dataclass(frozen=True, slots=True)
class Point:
    """One viewport coordinate in CSS pixels."""

    x: float
    y: float


@dataclass(frozen=True, slots=True)
class PointerPath:
    """One immutable pointer path with bounded per-point delays."""

    points: tuple[Point, ...]
    delays: tuple[float, ...]

    @property
    def planned_duration_ms(self) -> int:
        return round(sum(self.delays) * 1000)


def plan_pointer_path(
    start: Point,
    target: Point,
    profile: PointerProfile,
    *,
    axis: Literal["x", "y"] | None = None,
) -> PointerPath:
    """Return a direct move or a reproducible 24-step eased Bezier path."""

    if min(start.x, start.y, target.x, target.y) < 0:
        raise ValueError("pointer coordinates cannot be negative")
    if profile == "direct" or start == target:
        return PointerPath((target,), (0.0,))
    if profile != "natural":
        raise ValueError(f"unsupported pointer profile: {profile}")

    dx = target.x - start.x
    dy = target.y - start.y
    distance = math.hypot(dx, dy)
    curve = 0.0 if axis is not None else min(distance * 0.12, 80.0)
    perpendicular_x = -dy / distance
    perpendicular_y = dx / distance
    control_1 = Point(
        max(0.0, start.x + dx / 3 + perpendicular_x * curve),
        max(0.0, start.y + dy / 3 + perpendicular_y * curve),
    )
    control_2 = Point(
        max(0.0, start.x + 2 * dx / 3 + perpendicular_x * curve),
        max(0.0, start.y + 2 * dy / 3 + perpendicular_y * curve),
    )
    steps = 24
    points = tuple(
        _cubic_bezier(start, control_1, control_2, target, _smoothstep(i / steps))
        for i in range(1, steps)
    ) + (target,)
    delays = tuple(
        0.008 + 0.006 * abs(2 * (index / steps) - 1)
        for index in range(1, steps + 1)
    )
    return PointerPath(points, delays)


def _smoothstep(value: float) -> float:
    return value * value * (3 - 2 * value)


def _cubic_bezier(
    start: Point,
    control_1: Point,
    control_2: Point,
    target: Point,
    position: float,
) -> Point:
    inverse = 1 - position
    return Point(
        inverse**3 * start.x
        + 3 * inverse**2 * position * control_1.x
        + 3 * inverse * position**2 * control_2.x
        + position**3 * target.x,
        inverse**3 * start.y
        + 3 * inverse**2 * position * control_1.y
        + 3 * inverse * position**2 * control_2.y
        + position**3 * target.y,
    )


__all__ = ["Point", "PointerPath", "PointerProfile", "plan_pointer_path"]
