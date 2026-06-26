"""Context lifecycle coverage without launching a real browser."""

from __future__ import annotations

import pytest

from drissionpage_mcp.context import DrissionPageContext


class FakePage:
    def __init__(self, tab_id: str = "tab") -> None:
        self.tab_id = tab_id
        self.closed = False
        self.url = "about:blank"

    def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self) -> None:
        self.closed_tabs: list[str] = []

    def close_tabs(self, tab_id: str) -> None:
        self.closed_tabs.append(tab_id)


class ManagedTab:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_initialize_is_idempotent_and_exposes_tab_state(monkeypatch) -> None:
    browser = FakeBrowser()
    page = FakePage("initial")
    create_calls = []

    def fake_create_browser():
        create_calls.append("create")
        return browser

    monkeypatch.setattr("drissionpage_mcp.context.create_browser", fake_create_browser)
    monkeypatch.setattr("drissionpage_mcp.context.get_latest_tab", lambda _browser: page)

    context = DrissionPageContext()

    await context.initialize()
    await context.initialize()

    assert create_calls == ["create"]
    assert context.is_active() is True
    assert context.browser is browser
    assert context.current_tab() is context.current_tab_or_die()
    assert len(context.tabs()) == 1
    assert context.tabs() is not context.tabs()


@pytest.mark.asyncio
async def test_initialize_reraises_browser_creation_failure(monkeypatch) -> None:
    def fail_create_browser():
        raise RuntimeError("cannot launch")

    monkeypatch.setattr("drissionpage_mcp.context.create_browser", fail_create_browser)
    context = DrissionPageContext()

    with pytest.raises(RuntimeError, match="cannot launch"):
        await context.initialize()


@pytest.mark.asyncio
async def test_ensure_tab_creates_missing_current_tab_from_existing_browser(
    monkeypatch,
) -> None:
    context = DrissionPageContext()
    context._is_initialized = True
    context._browser = FakeBrowser()
    context._current_tab = None
    new_page = FakePage("new")
    monkeypatch.setattr("drissionpage_mcp.context.new_tab", lambda _browser: new_page)

    tab = await context.ensure_tab()

    assert tab.page is new_page
    assert context.current_tab() is tab
    assert context.tabs() == [tab]


@pytest.mark.asyncio
async def test_ensure_tab_and_new_tab_fail_without_browser() -> None:
    context = DrissionPageContext()
    context._is_initialized = True
    context._browser = None
    context._current_tab = None

    with pytest.raises(RuntimeError, match="Browser context not initialized"):
        await context.ensure_tab()

    with pytest.raises(RuntimeError, match="Browser context not initialized"):
        await context.new_tab()


@pytest.mark.asyncio
async def test_new_tab_tracks_new_page_and_makes_it_current(monkeypatch) -> None:
    context = DrissionPageContext()
    context._is_initialized = True
    context._browser = FakeBrowser()
    new_page = FakePage("new")
    monkeypatch.setattr("drissionpage_mcp.context.new_tab", lambda _browser: new_page)

    tab = await context.new_tab()

    assert tab.page is new_page
    assert context.current_tab() is tab
    assert context.tabs() == [tab]


@pytest.mark.asyncio
async def test_close_tab_noops_without_target_and_promotes_remaining_tab() -> None:
    context = DrissionPageContext()
    await context.close_tab()

    first = ManagedTab()
    second = ManagedTab()
    context._tabs = [first, second]  # type: ignore[list-item]
    context._current_tab = second  # type: ignore[assignment]

    await context.close_tab()

    assert second.closed is True
    assert context.current_tab() is first
    assert context.tabs() == [first]


@pytest.mark.asyncio
async def test_close_browser_clears_state_even_when_quit_fails(monkeypatch) -> None:
    def fail_quit(_browser):
        raise RuntimeError("already disconnected")

    monkeypatch.setattr("drissionpage_mcp.context.quit_browser", fail_quit)
    context = DrissionPageContext()
    context._browser = FakeBrowser()
    context._current_tab = ManagedTab()  # type: ignore[assignment]
    context._tabs = [context._current_tab]
    context._is_initialized = True

    await context.close_browser()

    assert context.browser is None
    assert context.current_tab() is None
    assert context.tabs() == []
    assert context.is_active() is False


@pytest.mark.asyncio
async def test_wait_delegates_to_asyncio_sleep(monkeypatch) -> None:
    sleeps = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("drissionpage_mcp.context.asyncio.sleep", fake_sleep)
    context = DrissionPageContext()

    await context.wait(0.25)

    assert sleeps == [0.25]
