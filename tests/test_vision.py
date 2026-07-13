"""Contracts for autonomous visual orchestration capabilities."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from drissionpage_mcp.browser.vision import VisionOperations


class FakePointer:
    def __init__(self, fail_index: int | None = None) -> None:
        self.calls: list[tuple[float, float]] = []
        self.fail_index = fail_index

    async def click_at(self, x: float, y: float, **_kwargs):
        index = len(self.calls)
        self.calls.append((x, y))
        if index == self.fail_index:
            raise RuntimeError("target failed")
        return SimpleNamespace(
            to_dict=lambda: {
                "profile": "direct",
                "button": "left",
                "start_x": x,
                "start_y": y,
                "target_x": x,
                "target_y": y,
                "steps": 1,
                "reaction_delay_ms": 0,
                "delay_before_press_ms": 0,
                "hold_duration_ms": 50,
                "planned_duration_ms": 50,
            }
        )

    def random_delay(self, _minimum: int, _maximum: int) -> float:
        return 0


class FakePage:
    def __init__(self, results):
        self.results = list(results)

    def run_js(self, _script: str, **_kwargs):
        return self.results.pop(0)


class FakeTab:
    def __init__(self, results, fail_index: int | None = None) -> None:
        self.page = FakePage(results)
        self.pointer = FakePointer(fail_index)
        self.url = "https://example.test/start"
        self.title = "Fixture"


@pytest.mark.asyncio
async def test_detect_challenges_returns_bounded_signals_and_autonomous_guidance() -> (
    None
):
    tab = FakeTab(
        [
            {
                "signals": [
                    {
                        "source": "iframe",
                        "provider_hint": "turnstile",
                        "matched_signal": "turnstile",
                        "frame_index": 0,
                    }
                ],
                "iframes": [{"index": 0, "src": "https://widget.test"}],
            }
        ]
    )

    result = await VisionOperations(tab).detect_challenges(["turnstile"])

    assert result["detected"] is True
    assert result["challenge_types"] == ["turnstile"]
    assert result["page_state"] == {
        "url": "https://example.test/start",
        "title": "Fixture",
    }
    assert any("page_click_xy_batch" in item for item in result["suggestions"])
    assert any(
        "not recommended or guaranteed" in item for item in result["suggestions"]
    )


@pytest.mark.asyncio
async def test_batch_click_is_fail_fast_by_default_and_records_motion() -> None:
    tab = FakeTab([], fail_index=1)
    result = await VisionOperations(tab).click_batch(
        [
            {"x": 10, "y": 20, "label": "one"},
            {"x": 30, "y": 40, "label": "two"},
            {"x": 50, "y": 60, "label": "three"},
        ],
        profile="direct",
        button="left",
        delay_min_ms=0,
        delay_max_ms=0,
        continue_on_error=False,
        stop_on_url_change=True,
    )

    assert result["clicks_completed"] == 1
    assert result["aborted"] is True
    assert result["abort_index"] == 1
    assert len(result["results"]) == 2
    assert result["results"][0]["motion"]["steps"] == 1
    assert result["results"][1]["error"] == "target failed"


@pytest.mark.asyncio
async def test_wait_challenge_result_classifies_pass_without_returning_token() -> None:
    tab = FakeTab(
        [
            {
                "token_length": 128,
                "success_selector": "",
                "retry_selector": "",
                "challenge_selector": ".fixture",
                "challenge_present": True,
                "challenge_fingerprint": "fixture",
                "observable_signals": True,
            }
        ]
    )

    result = await VisionOperations(tab).wait_challenge_result(
        timeout_s=1,
        poll_interval_s=0.1,
        token_selectors=["#token"],
        success_selectors=[],
        retry_selectors=[],
        challenge_selectors=[".fixture"],
    )

    assert result["status"] == "passed"
    assert result["token_present"] is True
    assert result["token_length"] == 128
    assert "token" not in result


@pytest.mark.asyncio
async def test_batch_click_can_continue_after_failure() -> None:
    tab = FakeTab([], fail_index=1)
    result = await VisionOperations(tab).click_batch(
        [
            {"x": 10, "y": 20, "label": "one"},
            {"x": 30, "y": 40, "label": "two"},
            {"x": 50, "y": 60, "label": "three"},
        ],
        profile="direct",
        button="left",
        delay_min_ms=0,
        delay_max_ms=0,
        continue_on_error=True,
        stop_on_url_change=True,
    )

    assert result["clicks_completed"] == 2
    assert result["aborted"] is False
    assert [item["success"] for item in result["results"]] == [True, False, True]


@pytest.mark.asyncio
async def test_batch_click_stops_when_url_changes_between_targets() -> None:
    tab = FakeTab([])
    original_click = tab.pointer.click_at

    async def navigate_after_first(x: float, y: float, **kwargs):
        motion = await original_click(x, y, **kwargs)
        tab.url = "https://example.test/next"
        return motion

    tab.pointer.click_at = navigate_after_first
    result = await VisionOperations(tab).click_batch(
        [
            {"x": 10, "y": 20, "label": "one"},
            {"x": 30, "y": 40, "label": "two"},
        ],
        profile="direct",
        button="left",
        delay_min_ms=0,
        delay_max_ms=0,
        continue_on_error=True,
        stop_on_url_change=True,
    )

    assert result["clicks_completed"] == 1
    assert result["aborted"] is True
    assert result["abort_index"] == 1
    assert len(tab.pointer.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "status"),
    [
        (
            {
                "token_length": 0,
                "success_selector": "",
                "retry_selector": "#retry",
                "challenge_selector": ".fixture",
                "challenge_present": True,
                "challenge_fingerprint": "same",
                "observable_signals": True,
            },
            "needs_retry",
        ),
        (
            {
                "token_length": 0,
                "success_selector": "",
                "retry_selector": "",
                "challenge_selector": "",
                "challenge_present": False,
                "challenge_fingerprint": "",
                "observable_signals": False,
            },
            "indeterminate",
        ),
    ],
)
async def test_wait_challenge_result_classifies_terminal_signals(
    payload: dict[str, object], status: str
) -> None:
    tab = FakeTab([payload])
    result = await VisionOperations(tab).wait_challenge_result(
        timeout_s=1,
        poll_interval_s=0.1,
        token_selectors=[],
        success_selectors=[],
        retry_selectors=[],
        challenge_selectors=[],
    )
    assert result["status"] == status


@pytest.mark.asyncio
async def test_wait_challenge_result_detects_new_fingerprint() -> None:
    pending = {
        "token_length": 0,
        "success_selector": "",
        "retry_selector": "",
        "challenge_selector": ".fixture",
        "challenge_present": True,
        "challenge_fingerprint": "round-one",
        "observable_signals": True,
    }
    changed = {**pending, "challenge_fingerprint": "round-two"}
    tab = FakeTab([pending, changed])

    result = await VisionOperations(tab).wait_challenge_result(
        timeout_s=1,
        poll_interval_s=0,
        token_selectors=[],
        success_selectors=[],
        retry_selectors=[],
        challenge_selectors=[],
    )

    assert result["status"] == "new_challenge"
    assert result["new_challenge"] is True
    assert result["observations"] == 2


@pytest.mark.asyncio
async def test_wait_challenge_result_times_out_with_pending_signal() -> None:
    pending = {
        "token_length": 0,
        "success_selector": "",
        "retry_selector": "",
        "challenge_selector": ".fixture",
        "challenge_present": True,
        "challenge_fingerprint": "same",
        "observable_signals": True,
    }
    tab = FakeTab([pending])

    result = await VisionOperations(tab).wait_challenge_result(
        timeout_s=0,
        poll_interval_s=0,
        token_selectors=[],
        success_selectors=[],
        retry_selectors=[],
        challenge_selectors=[],
    )

    assert result["status"] == "timeout"
    assert result["passed"] is False


def test_batch_click_input_rejects_invalid_ranges_and_target_limits() -> None:
    from pydantic import ValidationError

    from drissionpage_mcp.tools.vision import BatchClickInput

    with pytest.raises(ValidationError, match="cannot exceed"):
        BatchClickInput.model_validate(
            {
                "targets": [{"x": 1, "y": 2}],
                "inter_click_delay_min_ms": 500,
                "inter_click_delay_max_ms": 200,
            }
        )
    with pytest.raises(ValidationError):
        BatchClickInput.model_validate({"targets": []})
    with pytest.raises(ValidationError):
        BatchClickInput.model_validate(
            {"targets": [{"x": index, "y": index} for index in range(26)]}
        )
