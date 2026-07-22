"""Context lifecycle coverage without launching a real browser."""

from __future__ import annotations

import pytest

from drissionpage_mcp.context import DrissionPageContext


class FakePage:
    def __init__(self, tab_id: str = "tab") -> None:
        self.tab_id = tab_id
        self.closed = False
        self.url = "about:blank"
        self.title = f"Title {tab_id}"

    def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self) -> None:
        self.closed_tabs: list[str] = []
        self.pages: dict[str, FakePage] = {}
        self.active_tab_id = ""

    def close_tabs(self, tab_id: str) -> None:
        self.closed_tabs.append(tab_id)
        self.pages.pop(tab_id, None)
        if self.active_tab_id == tab_id:
            self.active_tab_id = next(iter(self.pages), "")

    @property
    def latest_tab(self) -> FakePage | None:
        if self.active_tab_id:
            return self.pages[self.active_tab_id]
        return next(iter(self.pages.values()), None)

    @property
    def tab_ids(self) -> list[str]:
        return list(self.pages)

    def get_tab(self, tab_id: str | None = None) -> FakePage | None:
        if tab_id is None:
            return self.latest_tab
        return self.pages[tab_id]

    def get_tabs(self) -> list[FakePage]:
        return list(self.pages.values())

    def activate_tab(self, id_or_tab) -> None:
        self.active_tab_id = getattr(id_or_tab, "tab_id", id_or_tab)


class BrokenCloseBrowser(FakeBrowser):
    def close_tabs(self, tab_id: str) -> None:
        raise RuntimeError(f"cannot close {tab_id}")


class ManagedTab:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FailedManagedTab:
    async def close(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_initialize_is_idempotent_and_exposes_tab_state(monkeypatch) -> None:
    browser = FakeBrowser()
    page = FakePage("initial")
    create_calls = []

    def fake_create_browser():
        create_calls.append("create")
        return browser

    monkeypatch.setattr("drissionpage_mcp.context.create_browser", fake_create_browser)
    monkeypatch.setattr(
        "drissionpage_mcp.context.get_latest_tab", lambda _browser: page
    )

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
async def test_sync_tabs_discovers_external_browser_tabs_and_switches() -> None:
    browser = FakeBrowser()
    browser.pages = {
        "a": FakePage("a"),
        "b": FakePage("b"),
    }
    browser.pages["a"].url = "https://example.test/a"
    browser.pages["b"].url = "https://example.test/b"
    browser.active_tab_id = "a"
    context = DrissionPageContext()
    context._browser = browser
    context._is_initialized = True

    tabs = await context.sync_tabs()

    assert [tab.native_tab_id for tab in tabs] == ["a", "b"]
    assert [tab.mcp_tab_id for tab in tabs] == ["t0", "t1"]
    assert context.current_tab().native_tab_id == "a"

    switched = await context.switch_tab("t1")

    assert switched.native_tab_id == "b"
    assert context.current_tab() is switched
    assert browser.active_tab_id == "b"


@pytest.mark.asyncio
async def test_close_tab_by_id_removes_tab_and_promotes_remaining() -> None:
    browser = FakeBrowser()
    browser.pages = {
        "a": FakePage("a"),
        "b": FakePage("b"),
    }
    browser.active_tab_id = "b"
    context = DrissionPageContext()
    context._browser = browser
    context._is_initialized = True
    await context.sync_tabs()

    await context.close_tab_by_id("t1")

    assert browser.closed_tabs == ["b"]
    assert [tab.native_tab_id for tab in context.tabs()] == ["a"]
    assert context.current_tab().native_tab_id == "a"


@pytest.mark.asyncio
async def test_close_tab_by_id_keeps_state_when_browser_close_fails() -> None:
    browser = BrokenCloseBrowser()
    browser.pages = {
        "a": FakePage("a"),
        "b": FakePage("b"),
    }
    browser.active_tab_id = "b"
    context = DrissionPageContext()
    context._browser = browser
    context._is_initialized = True
    await context.sync_tabs()

    with pytest.raises(RuntimeError, match="Failed to close tab"):
        await context.close_tab_by_id("t1")

    assert [tab.native_tab_id for tab in context.tabs()] == ["a", "b"]
    assert context.current_tab().native_tab_id == "b"


def test_context_does_not_retain_action_history() -> None:
    context = DrissionPageContext()
    assert not hasattr(context, "record_action")
    assert not hasattr(context, "action_history")


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
