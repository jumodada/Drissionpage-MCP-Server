"""Deterministic contracts for natural pointer motion and CDP execution."""

from __future__ import annotations

import math
import random
from types import SimpleNamespace

import pytest

from drissionpage_mcp.browser.motion import (
    MotionConfig,
    MotionPlanner,
    Point,
    smoothstep,
)
from drissionpage_mcp.browser.pointer import PointerButton, PointerOperations


def test_smoothstep_accelerates_then_decelerates() -> None:
    samples = [smoothstep(index / 10) for index in range(11)]

    assert samples[0] == 0
    assert samples[-1] == 1
    assert samples == sorted(samples)
    increments = [right - left for left, right in zip(samples, samples[1:])]
    assert increments[0] < increments[4]
    assert increments[-1] < increments[4]


def test_natural_bezier_plan_has_bounded_steps_delays_and_jitter() -> None:
    config = MotionConfig(
        steps_min=20,
        steps_max=35,
        interval_min=0.008,
        interval_max=0.025,
        jitter_px=0.5,
        curve_min_ratio=0.08,
        curve_max_ratio=0.22,
    )
    plan = MotionPlanner(random.Random(17)).plan(
        Point(100, 100), Point(442, 369), config
    )

    assert 20 <= len(plan.steps) <= 35
    assert plan.steps[-1].point == Point(442, 369)
    assert plan.steps[-1].jitter == Point(0, 0)
    assert all(0.008 <= step.delay <= 0.025 for step in plan.steps)
    assert all(abs(step.jitter.x) <= 0.5 for step in plan.steps)
    assert all(abs(step.jitter.y) <= 0.5 for step in plan.steps)

    # A genuine curve must leave the straight line between start and target.
    dx, dy = 342, 269
    distance = math.hypot(dx, dy)
    deviations = [
        abs(dy * (step.point.x - 100) - dx * (step.point.y - 100)) / distance
        for step in plan.steps[:-1]
    ]
    assert max(deviations) > 5


def test_short_and_zero_distance_plans_remain_exact() -> None:
    config = MotionConfig(steps_min=20, steps_max=35, jitter_px=0.5)
    planner = MotionPlanner(random.Random(3))

    zero = planner.plan(Point(10, 10), Point(10, 10), config)
    short = planner.plan(Point(10, 10), Point(10.2, 10.1), config)

    assert zero.steps[-1].point == Point(10, 10)
    assert short.steps[-1].point == Point(10.2, 10.1)
    assert len(zero.steps) == 1
    assert 20 <= len(short.steps) <= 35
    assert all(step.point.x >= 0 and step.point.y >= 0 for step in short.steps)


class FakePage:
    def __init__(self) -> None:
        self.actions = SimpleNamespace(curr_x=100.0, curr_y=100.0, modifier=0)
        self.events: list[tuple[str, dict[str, object]]] = []

    def run_cdp(self, method: str, **params: object) -> dict[str, object]:
        self.events.append((method, params))
        return {}


class FakeTab:
    def __init__(self) -> None:
        self.page = FakePage()
        self.url = "https://example.test/"
        self.stabilized: list[str] = []

    async def _stabilize(self, action: str, **_kwargs: object) -> None:
        self.stabilized.append(action)


@pytest.mark.asyncio
async def test_pointer_move_dispatches_only_natural_motion() -> None:
    tab = FakeTab()
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    pointer = PointerOperations(tab, rng=random.Random(7), sleep=fake_sleep)
    result = await pointer.move_to(442, 369, profile="natural")

    event_types = [params["type"] for _, params in tab.page.events]
    assert event_types == ["mouseMoved"] * result.steps
    assert 20 <= result.steps <= 35
    assert result.profile == "natural"
    assert result.target == Point(442, 369)
    assert result.planned_duration_ms == round(sum(sleeps) * 1000)
    assert tab.page.actions.curr_x == 442
    assert tab.page.actions.curr_y == 369
    assert tab.stabilized == ["pointer_move"]


@pytest.mark.asyncio
async def test_pointer_click_dispatches_move_reaction_press_hold_release() -> None:
    tab = FakeTab()
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    pointer = PointerOperations(tab, rng=random.Random(7), sleep=fake_sleep)
    result = await pointer.click_at(442, 369, profile="natural")

    event_types = [params["type"] for _, params in tab.page.events]
    assert event_types[: result.steps] == ["mouseMoved"] * result.steps
    assert event_types[-2:] == ["mousePressed", "mouseReleased"]
    assert tab.page.events[-2][1]["buttons"] == 1
    assert tab.page.events[-1][1]["buttons"] == 0
    assert 20 <= result.steps <= 35
    assert 100 <= result.reaction_delay_ms <= 300
    assert 50 <= result.hold_duration_ms <= 120
    assert all(event[1]["buttons"] == 0 for event in tab.page.events[: result.steps])
    assert tab.page.events[result.steps - 1][1]["x"] == 442
    assert tab.page.events[result.steps - 1][1]["y"] == 369
    assert tab.page.actions.curr_x == 442
    assert tab.page.actions.curr_y == 369
    assert tab.stabilized == ["pointer_click"]
    assert len(sleeps) == result.steps + 2


@pytest.mark.asyncio
async def test_pointer_releases_button_when_hold_is_interrupted() -> None:
    tab = FakeTab()

    async def interrupted_sleep(_seconds: float) -> None:
        if any(params.get("type") == "mousePressed" for _, params in tab.page.events):
            raise RuntimeError("cancelled during hold")

    pointer = PointerOperations(tab, rng=random.Random(11), sleep=interrupted_sleep)

    with pytest.raises(RuntimeError, match="cancelled during hold"):
        await pointer.click_at(120, 130, profile="direct")

    assert [params["type"] for _, params in tab.page.events][-2:] == [
        "mousePressed",
        "mouseReleased",
    ]


def test_natural_motion_config_matches_public_contract() -> None:
    motion = MotionConfig()

    assert (motion.steps_min, motion.steps_max) == (20, 35)
    assert (motion.interval_min, motion.interval_max) == (0.008, 0.025)
    assert motion.jitter_px == 0.5

    from drissionpage_mcp.tools.common import ClickCoordinatesInput

    profile_description = ClickCoordinatesInput.model_json_schema()["properties"][
        "profile"
    ]["description"]
    assert "20–35 cubic Bézier steps" in profile_description
    assert "100–300ms reaction delay" in profile_description
    assert "50–120ms button hold" in profile_description


@pytest.mark.parametrize(
    "payload",
    [
        {"x": 10, "y": 20, "start_x": 1},
        {"x": 10, "y": 20, "start_y": 1},
        {"x": -0.1, "y": 20},
        {"x": 10, "y": -0.1},
    ],
)
def test_coordinate_click_rejects_invalid_inputs(payload: dict[str, object]) -> None:
    from pydantic import ValidationError

    from drissionpage_mcp.tools.common import ClickCoordinatesInput

    with pytest.raises(ValidationError):
        ClickCoordinatesInput.model_validate(payload)


@pytest.mark.asyncio
async def test_reaction_delay_starts_only_after_exact_target_arrival() -> None:
    tab = FakeTab()
    sleep_observations: list[tuple[float, list[str]]] = []

    async def observe_sleep(seconds: float) -> None:
        sleep_observations.append(
            (seconds, [params["type"] for _, params in tab.page.events])
        )

    pointer = PointerOperations(tab, rng=random.Random(19), sleep=observe_sleep)
    result = await pointer.click_at(
        442,
        369,
        start_x=100,
        start_y=100,
        profile="natural",
    )

    reaction_seconds, events_at_reaction = sleep_observations[result.steps]
    assert events_at_reaction == ["mouseMoved"] * result.steps
    assert tab.page.events[result.steps - 1][1]["x"] == 442
    assert tab.page.events[result.steps - 1][1]["y"] == 369
    assert round(reaction_seconds * 1000) == result.reaction_delay_ms


@pytest.mark.asyncio
async def test_direct_profile_is_one_move_without_reaction_and_fixed_hold() -> None:
    tab = FakeTab()
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    pointer = PointerOperations(tab, rng=random.Random(23), sleep=fake_sleep)
    result = await pointer.click_at(150, 160, profile="direct")

    assert [params["type"] for _, params in tab.page.events] == [
        "mouseMoved",
        "mousePressed",
        "mouseReleased",
    ]
    assert result.steps == 1
    assert result.reaction_delay_ms == 0
    assert result.hold_duration_ms == 50
    assert sleeps == [0.05]


@pytest.mark.asyncio
@pytest.mark.parametrize(("button", "bit"), [("right", 2), ("middle", 4)])
async def test_pointer_button_events_expose_cdp_pressed_state(
    button: PointerButton, bit: int
) -> None:
    tab = FakeTab()

    async def fake_sleep(_seconds: float) -> None:
        return None

    pointer = PointerOperations(tab, rng=random.Random(29), sleep=fake_sleep)
    await pointer.click_at(150, 160, profile="direct", button=button)

    assert tab.page.events[-2][1]["buttons"] == bit
    assert tab.page.events[-1][1]["buttons"] == 0


@pytest.mark.asyncio
async def test_pointer_drag_moves_to_start_then_drags_with_pressed_button() -> None:
    tab = FakeTab()
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    pointer = PointerOperations(tab, rng=random.Random(31), sleep=fake_sleep)
    result = await pointer.drag_to(180, 190, 420, 360, profile="natural")

    events = [params for _, params in tab.page.events]
    types = [params["type"] for params in events]
    press_index = types.index("mousePressed")
    release_index = types.index("mouseReleased")
    assert types[:press_index] == ["mouseMoved"] * result.approach_steps
    assert types[press_index + 1 : release_index] == ["mouseMoved"] * result.drag_steps
    assert all(params["buttons"] == 0 for params in events[:press_index])
    assert events[press_index]["buttons"] == 1
    assert all(
        params["buttons"] == 1 for params in events[press_index + 1 : release_index]
    )
    assert events[release_index]["buttons"] == 0
    assert events[press_index]["x"] == 180
    assert events[press_index]["y"] == 190
    assert events[release_index]["x"] == 420
    assert events[release_index]["y"] == 360
    assert result.start == Point(180, 190)
    assert result.target == Point(420, 360)
    assert tab.stabilized == ["pointer_drag"]
    assert result.planned_duration_ms == round(sum(sleeps) * 1000)


@pytest.mark.asyncio
async def test_pointer_drag_releases_button_when_drag_motion_is_interrupted() -> None:
    tab = FakeTab()

    async def interrupted_sleep(_seconds: float) -> None:
        if any(params.get("type") == "mousePressed" for _, params in tab.page.events):
            raise RuntimeError("cancelled during drag")

    pointer = PointerOperations(tab, rng=random.Random(37), sleep=interrupted_sleep)

    with pytest.raises(RuntimeError, match="cancelled during drag"):
        await pointer.drag_to(180, 190, 420, 360, profile="natural")

    assert [params["type"] for _, params in tab.page.events][-2:] == [
        "mousePressed",
        "mouseReleased",
    ]
    assert tab.page.events[-1][1]["buttons"] == 0


@pytest.mark.asyncio
async def test_click_delay_before_press_runs_after_reaction_and_before_press() -> None:
    tab = FakeTab()
    observations: list[tuple[float, list[str]]] = []

    async def observe_sleep(seconds: float) -> None:
        observations.append(
            (seconds, [params["type"] for _, params in tab.page.events])
        )

    pointer = PointerOperations(tab, rng=random.Random(41), sleep=observe_sleep)
    result = await pointer.click_at(
        150,
        160,
        profile="direct",
        delay_before_press_ms=500,
    )

    assert result.delay_before_press_ms == 500
    assert observations[0][0] == 0.5
    assert observations[0][1] == ["mouseMoved"]
    assert [params["type"] for _, params in tab.page.events] == [
        "mouseMoved",
        "mousePressed",
        "mouseReleased",
    ]
