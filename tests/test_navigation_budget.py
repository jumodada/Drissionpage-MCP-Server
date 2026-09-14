"""Navigation budget, cancellation, and evidence regression tests."""

from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from drissionpage_mcp.browser.navigation import NavigationOperations
from drissionpage_mcp.tab import PageTab
from drissionpage_mcp.tools.navigate import NavigateInput, navigate


class _Observation:
    def __init__(self) -> None:
        self.clears = 0

    def clear_snapshots(self) -> None:
        self.clears += 1


class _Tab:
    def __init__(self, page: object) -> None:
        self.page = page
        self._url = ""
        self.observation = _Observation()
        self.stabilize_timeouts: list[float] = []

    @property
    def url(self) -> str:
        return str(getattr(self.page, "url", "") or self._url)

    async def _stabilize(
        self,
        _action: str,
        *,
        timeout: float,
        fallback_sleep: float,
        strict_timeout: bool = False,
    ) -> bool:
        del fallback_sleep
        self.stabilize_timeouts.append(timeout)
        return True


class _Page:
    def __init__(self) -> None:
        self.url = "https://example.test/final"
        self.states = SimpleNamespace(ready_state="complete")
        self.get_calls: list[tuple[str, dict[str, object]]] = []
        self.history_calls: list[str] = []

    def get(self, url: str, **kwargs: object) -> bool:
        self.get_calls.append((url, kwargs))
        return True

    def back(self) -> None:
        self.history_calls.append("back")

    def forward(self) -> None:
        self.history_calls.append("forward")

    def refresh(self) -> None:
        self.history_calls.append("refresh")


@pytest.mark.asyncio
async def test_default_navigation_preserves_native_call_and_returns_evidence() -> None:
    page = _Page()
    tab = _Tab(page)

    evidence = await NavigationOperations(tab).navigate("https://example.test/start")

    assert page.get_calls == [("https://example.test/start", {})]
    assert evidence["final_url"] == "https://example.test/final"
    assert evidence["ready_state"] == "complete"
    assert evidence["settled"] is True
    assert evidence["navigation_ms"] >= 0
    assert evidence["settle_ms"] >= 0
    assert evidence["total_ms"] >= evidence["navigation_ms"]
    assert tab.observation.clears == 1


@pytest.mark.asyncio
async def test_navigation_passes_remaining_native_budget_without_retry() -> None:
    page = _Page()
    tab = _Tab(page)

    await NavigationOperations(tab).navigate("https://example.test/start", timeout=0.5)

    _, kwargs = page.get_calls[0]
    assert kwargs["retry"] == 0
    assert 0 < float(kwargs["timeout"]) <= 0.5
    assert 0 <= tab.stabilize_timeouts[0] <= 0.5


@pytest.mark.asyncio
async def test_native_navigation_does_not_block_other_async_work() -> None:
    started = threading.Event()
    release = threading.Event()

    class BlockingPage(_Page):
        def get(self, url: str, **kwargs: object) -> bool:
            self.get_calls.append((url, kwargs))
            started.set()
            assert release.wait(1)
            return True

    operation = NavigationOperations(_Tab(BlockingPage()))
    task = asyncio.create_task(operation.navigate("https://example.test"))
    assert await asyncio.to_thread(started.wait, 0.2)

    progressed = False

    async def heartbeat() -> None:
        nonlocal progressed
        await asyncio.sleep(0)
        progressed = True

    await heartbeat()
    assert progressed is True
    release.set()
    await task


@pytest.mark.asyncio
async def test_cancellation_waits_for_native_worker_to_drain() -> None:
    started = threading.Event()
    release = threading.Event()

    class BlockingPage(_Page):
        def get(self, url: str, **kwargs: object) -> bool:
            started.set()
            assert release.wait(1)
            return True

    task = asyncio.create_task(
        NavigationOperations(_Tab(BlockingPage())).navigate("https://example.test")
    )
    assert await asyncio.to_thread(started.wait, 0.2)
    task.cancel()
    await asyncio.sleep(0.01)
    assert task.done() is False

    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_navigation_timeout_is_reported_after_native_worker_drains() -> None:
    class SlowPage(_Page):
        def get(self, url: str, **kwargs: object) -> bool:
            threading.Event().wait(0.03)
            return True

    with pytest.raises(TimeoutError, match="budget"):
        await NavigationOperations(_Tab(SlowPage())).navigate(
            "https://example.test", timeout=0.01
        )


@pytest.mark.asyncio
async def test_all_navigation_actions_invalidate_snapshot_cursors() -> None:
    page = _Page()
    tab = _Tab(page)
    navigation = NavigationOperations(tab)

    await navigation.navigate("https://example.test")
    await navigation.back()
    await navigation.forward()
    await navigation.refresh()

    assert tab.observation.clears == 4


@pytest.mark.asyncio
async def test_new_tab_result_is_built_inside_its_action_lifetime() -> None:
    class LockedTab:
        def __init__(self) -> None:
            self.inside_action = False
            self.navigation = SimpleNamespace(
                navigate=AsyncMock(
                    return_value={
                        "final_url": "https://example.test/final",
                        "ready_state": "complete",
                        "settled": True,
                        "navigation_ms": 1,
                        "settle_ms": 2,
                        "total_ms": 3,
                    }
                )
            )
            self.mcp_tab_id = "t-new"

        @asynccontextmanager
        async def action(self):
            self.inside_action = True
            try:
                yield self
            finally:
                self.inside_action = False

        @property
        def url(self) -> str:
            if not self.inside_action:
                raise RuntimeError("URL read outside action lifetime")
            return "https://example.test/final"

    tab = LockedTab()
    context = SimpleNamespace(
        new_tab=AsyncMock(return_value=tab),
        current_tab=lambda: tab,
    )

    outcome = await navigate.execute(
        context, NavigateInput(url="https://example.test/start", new_tab=True)
    )

    assert outcome.is_error is False
    assert outcome.structured_content()["data"]["final_url"] == (
        "https://example.test/final"
    )


def test_timeout_input_is_optional_and_bounded() -> None:
    assert NavigateInput(url="https://example.test").timeout is None
    assert NavigateInput(url="https://example.test", timeout=1.5).timeout == 1.5

    with pytest.raises(ValueError):
        NavigateInput(url="https://example.test", timeout=0)


@pytest.mark.asyncio
@pytest.mark.parametrize("settled", [False, None])
async def test_ready_state_does_not_fabricate_stabilization_success(settled):
    page = _Page()
    if settled is not None:
        page.wait = SimpleNamespace(doc_loaded=lambda **kwargs: settled)
    tab = PageTab(page, SimpleNamespace())
    result = await tab.navigation.navigate("https://example.test", timeout=1)
    assert result["ready_state"] == "complete"
    assert result["settled"] is settled


@pytest.mark.asyncio
async def test_stabilization_cancellation_keeps_tab_locked_until_native_drain():
    started = threading.Event()
    release = threading.Event()
    progressed = asyncio.Event()

    def doc_loaded(**kwargs):
        started.set()
        assert release.wait(2)
        return True

    page = _Page()
    page.wait = SimpleNamespace(doc_loaded=doc_loaded)
    tab = PageTab(page, SimpleNamespace())

    async def navigate_locked():
        async with tab.action():
            await tab.navigation.navigate("https://example.test")

    async def next_action():
        async with tab.action():
            progressed.set()

    task = asyncio.create_task(navigate_locked())
    try:
        assert await asyncio.to_thread(started.wait, 1)
        task.cancel()
        following = asyncio.create_task(next_action())
        await asyncio.sleep(0.01)
        assert not task.done()
        assert not progressed.is_set()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    await following
    assert progressed.is_set()


@pytest.mark.asyncio
async def test_explicit_budget_never_calls_unbounded_stabilization():
    calls = []

    def doc_loaded(**kwargs):
        calls.append(kwargs)
        if kwargs:
            raise TypeError("unsupported keyword")
        raise AssertionError("unbounded call")

    page = _Page()
    page.wait = SimpleNamespace(doc_loaded=doc_loaded)
    result = await PageTab(page, SimpleNamespace()).navigation.navigate(
        "https://example.test", timeout=1
    )
    assert result["settled"] is None
    assert len(calls) == 2
    assert all(0 < call["timeout"] <= 1 for call in calls)
