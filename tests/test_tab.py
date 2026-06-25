"""Unit coverage for PageTab without launching a real browser."""

from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

import pytest

from drissionpage_mcp.tab import PageTab


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """Keep PageTab async helper tests fast and deterministic."""

    async def _sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("drissionpage_mcp.tab.asyncio.sleep", _sleep)


class FakeActions:
    def __init__(self) -> None:
        self.clicked = None

    def click(self, point):
        self.clicked = point


class FakeWindow:
    def __init__(self) -> None:
        self.size_args = None

    def size(self, width: int, height: int) -> None:
        self.size_args = (width, height)


class FakeSet:
    def __init__(self) -> None:
        self.window = FakeWindow()


class FakeWait:
    def __init__(self, loaded: bool = True, fail: bool = False) -> None:
        self.loaded = loaded
        self.fail = fail
        self.calls = []

    def ele_loaded(self, selector: str, timeout: int = 10) -> bool:
        if self.fail:
            raise RuntimeError("wait failed")
        self.calls.append(("ele_loaded", selector, timeout))
        return self.loaded


class FakeWaitFallback:
    def __init__(self) -> None:
        self.calls = []

    def eles_loaded(
        self, selector: str, timeout: int = 10, any_one: bool = True
    ) -> bool:
        self.calls.append((selector, timeout, any_one))
        return True


class FakeElement:
    tag = "input"
    html = '<input id="name" value="Ada">'

    def __init__(self) -> None:
        self.text = "Ada"
        self.clicked = False
        self.cleared = False
        self.inputs = []

    def click(self) -> None:
        self.clicked = True

    def clear(self) -> None:
        self.cleared = True

    def input(self, text: str) -> None:
        self.inputs.append(text)
        self.text = text

    def attr(self, attribute: str):
        return {"id": "name", "missing": None}.get(attribute, "attr-value")

    def property(self, property_name: str):
        return {"value": self.text}.get(property_name)


_DEFAULT_ELEMENT = object()


class FakePage:
    def __init__(self, element=_DEFAULT_ELEMENT) -> None:
        self.url = "about:blank"
        self.text = "Whole page text"
        self.html = "<html><body>Whole page text</body></html>"
        self.tab_id = "tab-1"
        self.actions = FakeActions()
        self.wait = FakeWait()
        self.set = FakeSet()
        self.element = FakeElement() if element is _DEFAULT_ELEMENT else element
        self.calls = []
        self.closed = False

    def get(self, url: str):
        self.calls.append(("get", url))
        self.url = url
        return SimpleNamespace(url=url, ok=True)

    def back(self) -> None:
        self.calls.append(("back",))

    def forward(self) -> None:
        self.calls.append(("forward",))

    def refresh(self) -> None:
        self.calls.append(("refresh",))

    def ele(self, selector: str, **_kwargs):
        self.calls.append(("ele", selector))
        return self.element

    def get_screenshot(self, **kwargs):
        self.calls.append(("screenshot", kwargs))
        path = kwargs.get("path")
        if path:
            Path(path).write_bytes(b"path-png")
            return None
        if kwargs.get("as_base64"):
            return b"inline-png"
        return None

    def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(self, browser=None) -> None:
        self.browser = browser


class FakeBrowser:
    def __init__(self) -> None:
        self.closed_tabs = []

    def close_tabs(self, tab_id: str) -> None:
        self.closed_tabs.append(tab_id)


class RaisingUrlPage:
    @property
    def url(self):
        raise RuntimeError("disconnected")


@pytest.mark.asyncio
async def test_navigation_coordinates_and_resize_paths() -> None:
    page = FakePage()
    tab = PageTab(page, FakeContext())

    await tab.navigate("https://example.test")
    await tab.go_back()
    await tab.go_forward()
    await tab.refresh()
    await tab.click(3, 4)
    await tab.resize(800, 600)

    assert tab.url == "https://example.test"
    assert ("get", "https://example.test") in page.calls
    assert ("back",) in page.calls
    assert ("forward",) in page.calls
    assert ("refresh",) in page.calls
    assert page.actions.clicked == (3, 4)
    assert page.set.window.size_args == (800, 600)


@pytest.mark.asyncio
async def test_element_actions_and_readers() -> None:
    element = FakeElement()
    page = FakePage(element)
    tab = PageTab(page, FakeContext())

    await tab.click_element("#name")
    await tab.input_text("#name", "Ada", clear=True)
    await tab.type_text("#name", "Lovelace", clear=False)
    found = await tab.find_element("#name")

    assert element.clicked is True
    assert element.cleared is True
    assert element.inputs == ["Ada", "Lovelace"]
    assert found == {
        "found": True,
        "selector": "#name",
        "text": "Lovelace",
        "tag": "input",
        "html": '<input id="name" value="Ada">',
        "visible": True,
    }
    assert await tab.get_text("#name") == "Lovelace"
    assert await tab.get_text() == "Whole page text"
    assert await tab.get_attribute("#name", "id") == "name"
    assert await tab.get_attribute("#name", "missing") is None
    assert await tab.get_property("#name", "value") == "Lovelace"
    assert await tab.get_html("#name") == '<input id="name" value="Ada">'
    assert await tab.get_html() == "<html><body>Whole page text</body></html>"


@pytest.mark.asyncio
async def test_missing_element_paths_raise() -> None:
    page = FakePage(element=None)
    page.wait = FakeWait(loaded=False)
    tab = PageTab(page, FakeContext())

    with pytest.raises(Exception, match="Element not found"):
        await tab.click_element("#missing")
    with pytest.raises(Exception, match="Element not found"):
        await tab.input_text("#missing", "text")
    with pytest.raises(Exception, match="Element not found"):
        await tab.find_element("#missing")


@pytest.mark.asyncio
async def test_type_text_stops_when_wait_times_out() -> None:
    element = FakeElement()
    page = FakePage(element)
    page.wait = FakeWait(loaded=False)
    tab = PageTab(page, FakeContext())

    with pytest.raises(Exception, match="Element not found"):
        await tab.type_text("#delayed", "should-not-type", timeout=1)

    assert element.inputs == []
    assert ("ele", "#delayed") not in page.calls


@pytest.mark.asyncio
async def test_screenshot_inline_path_and_legacy_fallback(tmp_path) -> None:
    tab = PageTab(FakePage(), FakeContext())

    assert await tab.screenshot() == base64.b64encode(b"inline-png").decode()

    output = tmp_path / "screen.png"
    assert await tab.screenshot(path=str(output), full_page=True) == str(output)
    assert output.read_bytes() == b"path-png"

    class LegacyScreenshotPage(FakePage):
        def get_screenshot(self, **kwargs):
            if kwargs.get("as_base64"):
                raise TypeError("old DrissionPage")
            Path(kwargs["path"]).write_bytes(b"legacy-png")

    legacy_tab = PageTab(LegacyScreenshotPage(), FakeContext())
    assert await legacy_tab.screenshot() == base64.b64encode(b"legacy-png").decode()


@pytest.mark.asyncio
async def test_wait_close_url_and_connection_helpers() -> None:
    page = FakePage()
    browser = FakeBrowser()
    tab = PageTab(page, FakeContext(browser))
    tab._url = "https://cached.test"

    assert await tab.wait_for_element("#ready") is True

    page.wait = FakeWaitFallback()
    assert await tab.wait_for_element("#ready", timeout=2) is True
    assert page.wait.calls == [("#ready", 2, True)]

    page.wait = FakeWait(fail=True)
    assert await tab.wait_for_element("#ready") is False

    page.url = "https://example.test/done"
    assert await tab.wait_for_url("done") is True
    assert await tab.wait_for_url("never", timeout=0) is False

    assert tab.is_connected() is True
    await tab.close()
    assert browser.closed_tabs == ["tab-1"]

    fallback_page = FakePage()
    fallback_page.tab_id = ""
    fallback_tab = PageTab(fallback_page, FakeContext())
    await fallback_tab.close()
    assert fallback_page.closed is True

    disconnected_tab = PageTab(RaisingUrlPage(), FakeContext())
    disconnected_tab._url = "https://cached.test"
    assert disconnected_tab.url == "https://cached.test"
    assert disconnected_tab.is_connected() is False


@pytest.mark.asyncio
async def test_navigation_failure_is_reraised() -> None:
    class FailedNavigationPage(FakePage):
        def get(self, url: str):
            return False

    tab = PageTab(FailedNavigationPage(), FakeContext())

    with pytest.raises(RuntimeError, match="Navigation failed"):
        await tab.navigate("https://bad.test")


@pytest.mark.asyncio
async def test_post_action_stabilization_prefers_doc_loaded() -> None:
    class WaitWithDocLoaded(FakeWait):
        def __init__(self) -> None:
            super().__init__()
            self.doc_loaded_calls = []

        def doc_loaded(self, **kwargs):
            self.doc_loaded_calls.append(kwargs)
            return True

    page = FakePage()
    page.wait = WaitWithDocLoaded()
    tab = PageTab(page, FakeContext())

    await tab.navigate("https://example.test")
    await tab.click(1, 2)

    assert page.wait.doc_loaded_calls[0] == {"timeout": 5.0, "raise_err": False}
    assert page.wait.doc_loaded_calls[1] == {"timeout": 1.0, "raise_err": False}


@pytest.mark.asyncio
async def test_post_action_stabilization_falls_back_to_bounded_sleep(
    monkeypatch,
) -> None:
    sleeps = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("drissionpage_mcp.tab.asyncio.sleep", fake_sleep)
    page = FakePage()
    page.wait = object()
    tab = PageTab(page, FakeContext())

    await tab.go_back()

    assert sleeps == [0.05]
