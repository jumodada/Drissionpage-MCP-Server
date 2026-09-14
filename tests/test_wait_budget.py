"""Deadline regressions for browser wait operations."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from drissionpage_mcp.browser.waits import WaitOperations, WaitTimeoutError
from drissionpage_mcp.tools.wait import WaitUntilInput, wait_until


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakePage:
    def __init__(self, *, ready_state: str = "loading") -> None:
        self.ready_state = ready_state

    def run_js(self, script: str, **_kwargs: object) -> object:
        if "document.readyState" in script:
            return self.ready_state
        return {
            "exists": True,
            "visible": True,
            "disabled": False,
            "tag": "div",
            "text": "ready",
            "signature": "div|ready|True|False",
        }


class FakeTab:
    def __init__(self, page: FakePage | None = None) -> None:
        self.page = page or FakePage()
        self.current_url = "https://example.test/loading?token=secret"
        self.dom_targeting = SimpleNamespace()
        self.elements = SimpleNamespace()

    @property
    def url(self) -> str:
        return self.current_url


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr("drissionpage_mcp.browser.waits.time.monotonic", fake.monotonic)
    monkeypatch.setattr("drissionpage_mcp.browser.waits.asyncio.sleep", fake.sleep)
    return fake


@pytest.mark.asyncio
async def test_stable_window_cannot_outlive_deadline(clock: FakeClock) -> None:
    waits = WaitOperations(FakeTab())

    with pytest.raises(WaitTimeoutError) as captured:
        await waits.until(
            condition="stable",
            selector="#ready",
            timeout=0.01,
            interval=1,
            stable_ms=100,
        )

    assert clock.sleeps == pytest.approx([0.01])
    assert captured.value.details == {
        "condition": "stable",
        "elapsed_ms": 10,
        "last_state": {
            "exists": True,
            "visible": True,
            "disabled": False,
            "tag": "div",
            "text": "ready",
            "signature": "div|ready|True|False",
        },
    }


@pytest.mark.asyncio
async def test_timeout_zero_samples_once_without_waiting(clock: FakeClock) -> None:
    waits = WaitOperations(FakeTab())
    samples = 0

    async def sample(**_kwargs: object) -> tuple[bool, dict[str, object]]:
        nonlocal samples
        samples += 1
        return False, {"exists": False}

    waits._condition_matches = sample  # type: ignore[method-assign]

    with pytest.raises(WaitTimeoutError):
        await waits.until(condition="present", selector="#later", timeout=0)

    assert samples == 1
    assert clock.sleeps == []


@pytest.mark.asyncio
async def test_timeout_zero_does_not_accept_positive_stable_window(
    clock: FakeClock,
) -> None:
    waits = WaitOperations(FakeTab())

    with pytest.raises(WaitTimeoutError):
        await waits.until(condition="stable", selector="#ready", timeout=0, stable_ms=1)

    assert clock.sleeps == []


@pytest.mark.asyncio
async def test_poll_sleep_is_limited_to_remaining_budget(clock: FakeClock) -> None:
    waits = WaitOperations(FakeTab())

    with pytest.raises(WaitTimeoutError):
        await waits.until(
            condition="url_contains",
            value="done",
            timeout=0.05,
            interval=1,
        )

    assert clock.sleeps == pytest.approx([0.05])


@pytest.mark.asyncio
async def test_match_observed_after_deadline_is_not_accepted(clock: FakeClock) -> None:
    waits = WaitOperations(FakeTab())

    async def slow_match(**_kwargs: object) -> tuple[bool, dict[str, object]]:
        clock.now += 0.02
        return True, {"exists": True}

    waits._condition_matches = slow_match  # type: ignore[method-assign]

    with pytest.raises(WaitTimeoutError) as captured:
        await waits.until(condition="present", selector="#ready", timeout=0.01)

    assert captured.value.details["elapsed_ms"] == 19


@pytest.mark.asyncio
async def test_wait_for_url_uses_monotonic_bounded_budget(clock: FakeClock) -> None:
    tab = FakeTab()
    waits = WaitOperations(tab)

    assert await waits.url("done", timeout=0.05) is False
    assert clock.sleeps == pytest.approx([0.05])

    clock.sleeps.clear()
    tab.current_url = "https://example.test/done"
    assert await waits.url("done", timeout=0) is True
    assert clock.sleeps == []


@pytest.mark.asyncio
async def test_wait_for_url_rejects_match_read_after_deadline(clock: FakeClock) -> None:
    class SlowUrlTab(FakeTab):
        @property
        def url(self) -> str:
            clock.now += 0.02
            return "https://example.test/done"

    assert await WaitOperations(SlowUrlTab()).url("done", timeout=0.01) is False


@pytest.mark.asyncio
async def test_wait_cancellation_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    waits = WaitOperations(FakeTab())

    async def cancel(_seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr("drissionpage_mcp.browser.waits.asyncio.sleep", cancel)

    with pytest.raises(asyncio.CancelledError):
        await waits.until(
            condition="url_contains", value="done", timeout=1, interval=0.01
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("current", "expected", "matches"),
    [
        ("loading", "interactive", False),
        ("interactive", "interactive", True),
        ("complete", "interactive", True),
        ("interactive", "complete", False),
        ("complete", "complete", True),
    ],
)
async def test_ready_state_waits_for_requested_document_stage(
    current: str,
    expected: str,
    matches: bool,
) -> None:
    waits = WaitOperations(FakeTab(FakePage(ready_state=current)))

    if matches:
        result = await waits.until(condition="ready_state", value=expected, timeout=0)
        assert result["state"] == {"ready_state": current}
    else:
        with pytest.raises(WaitTimeoutError):
            await waits.until(condition="ready_state", value=expected, timeout=0)


def test_ready_state_is_part_of_public_wait_input() -> None:
    args = WaitUntilInput(condition="ready_state", value="complete")

    assert args.condition == "ready_state"


@pytest.mark.asyncio
async def test_wait_until_error_exposes_bounded_redacted_diagnostics() -> None:
    tab = FakeTab()
    tab.waits = WaitOperations(tab)  # type: ignore[attr-defined]
    context = SimpleNamespace(current_tab_or_die=lambda: tab)

    outcome = await wait_until.execute(
        context,
        WaitUntilInput(condition="url_contains", value="done", timeout=0),
    )

    payload = outcome.structured_content()
    assert payload["error"]["details"]["elapsed_ms"] >= 0
    assert payload["error"]["details"]["last_state"] == {
        "url": "https://example.test/loading?token=%3Credacted%3E"
    }
    assert "secret" not in str(payload)
    assert all("secret" not in item.text for item in outcome.content())


@pytest.mark.asyncio
async def test_stable_window_restarts_when_intermediate_sample_changes(clock):
    waits = WaitOperations(FakeTab())
    samples = 0

    async def sample(selector):
        nonlocal samples
        samples += 1
        # Same initial/final state must not hide movement during the window.
        return {
            "exists": True,
            "signature": "moving" if 100.025 < clock.now < 100.075 else "fixed",
        }

    waits._selector_state = sample
    with pytest.raises(WaitTimeoutError):
        await waits.until(
            condition="stable",
            selector="#ready",
            timeout=0.12,
            stable_ms=100,
            interval=0.01,
        )
    assert samples >= 3
