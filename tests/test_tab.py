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


class FakeConsole:
    def __init__(self, *, messages=None, listening: bool = False, start_raises=False) -> None:
        self.messages = list(messages or [])
        self.listening = listening
        self.start_raises = start_raises
        self.started = False

    def start(self) -> None:
        if self.start_raises:
            raise RuntimeError("console unavailable")
        self.started = True
        self.listening = True


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
    def __init__(
        self,
        *,
        tag: str = "input",
        text: str = "Ada",
        html: str = '<input id="name" value="Ada">',
        attrs: dict[str, str | None] | None = None,
    ) -> None:
        self.tag = tag
        self.html = html
        self.text = text
        self.attrs = {"id": "name", "missing": None}
        if attrs:
            self.attrs.update(attrs)
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
        if attribute in self.attrs:
            return self.attrs[attribute]
        if attribute in {
            "class",
            "name",
            "type",
            "href",
            "value",
            "placeholder",
            "role",
            "aria-label",
            "data-testid",
        }:
            return None
        return "attr-value"

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
        self.console = FakeConsole()
        self.element = FakeElement() if element is _DEFAULT_ELEMENT else element
        self.elements = [self.element] if self.element is not None else []
        self.calls = []
        self.closed = False
        self.snapshot = {
            "url": self.url,
            "title": "Fake Page",
            "text_excerpt": "Whole page text",
            "headings": [],
            "links": [],
            "buttons": [],
            "inputs": [],
            "forms": [],
            "counts": {},
            "truncated": {
                "text": False,
                "elements": False,
                "returned_elements": 0,
            },
            "limits": {"max_elements": 50, "max_text_chars": 4000},
        }

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

    def eles(self, selector: str, **kwargs):
        self.calls.append(("eles", selector, kwargs))
        return self.elements

    def run_js(self, script: str, **kwargs):
        self.calls.append(("run_js", script[:40], kwargs))
        return self.snapshot

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


class AttrConsoleMessage:
    def __init__(
        self,
        *,
        level: str = "log",
        text: str = "attr log",
        url: str = "https://example.test",
        line: int = 5,
        column: int = 2,
        source: str = "console-api",
    ) -> None:
        self.level = level
        self.text = text
        self.url = url
        self.line = line
        self.column = column
        self.source = source


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


class RaisingIdentityPage(FakePage):
    @property
    def tab_id(self):
        raise RuntimeError("tab detached")

    @tab_id.setter
    def tab_id(self, _value):
        pass

    @property
    def title(self):
        raise RuntimeError("title detached")

    @title.setter
    def title(self, _value):
        pass


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
        "locator": "css:#name",
        "selector_strategy": "css",
        "selector_normalized": True,
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
async def test_page_snapshot_and_find_elements_return_bounded_summaries() -> None:
    page = FakePage()
    page.snapshot = {
        "url": "https://example.test/catalog",
        "title": "Catalog",
        "text_excerpt": "Products",
        "headings": [
            {
                "index": 0,
                "tag": "h1",
                "text": "Products",
                "selector": "#title",
                "attributes": {"id": "title"},
            }
        ],
        "links": [],
        "buttons": [],
        "inputs": [],
        "forms": [],
        "counts": {"headings": 1},
        "truncated": {"text": False, "elements": False, "returned_elements": 1},
        "limits": {"max_elements": 5, "max_text_chars": 100},
    }
    page.elements = [
        FakeElement(
            tag="article",
            text="Alpha card",
            html="<article id='alpha'>Alpha card</article>",
            attrs={"id": "alpha", "class": "product-card"},
        ),
        FakeElement(
            tag="article",
            text="Beta card",
            html="<article id='beta'>Beta card</article>",
            attrs={"id": "beta", "class": "product-card"},
        ),
    ]
    tab = PageTab(page, FakeContext())

    snapshot = await tab.page_snapshot(
        include_html=True,
        max_elements=5,
        max_text_chars=100,
    )
    found = await tab.find_elements(".product-card", limit=1, include_html=True)

    assert snapshot["title"] == "Catalog"
    assert ("run_js",) == (page.calls[-2][0],)
    assert found == {
        "selector": ".product-card",
        "locator": "css:.product-card",
        "selector_strategy": "css",
        "selector_normalized": True,
        "count": 2,
        "returned": 1,
        "limit": 1,
        "truncated": True,
        "elements": [
            {
                "index": 0,
                "tag": "article",
                "text": "Alpha card",
                "selector": "#alpha",
                "attributes": {"id": "alpha", "class": "product-card"},
                "html": "<article id='alpha'>Alpha card</article>",
            }
        ],
    }


@pytest.mark.asyncio
async def test_observe_evaluate_and_wait_until_return_observable_state() -> None:
    class ObservablePage(FakePage):
        def run_js(self, script: str, **kwargs):
            self.calls.append(("run_js", script[:40], kwargs))
            if "__mcpFn" in script:
                return "abcdef"
            if "text_samples" in script:
                return {
                    "url": self.url,
                    "title": "Observable",
                    "ready_state": "complete",
                    "counts": {"buttons": 1, "inputs": 1},
                    "text_samples": ["Ready", "Save"],
                    "active_element": None,
                }
            if "const strategy" in script:
                return {
                    "exists": True,
                    "visible": True,
                    "disabled": False,
                    "tag": "button",
                    "text": "Save",
                    "signature": "button|save|enabled",
                }
            return super().run_js(script, **kwargs)

    page = ObservablePage()
    page.url = "https://example.test/ready"
    page.text = "Page is Ready"
    tab = PageTab(page, FakeContext())

    observation = await tab.observe(max_texts=2, max_text_chars=50)
    evaluated = await tab.evaluate_script(
        "return args[0];",
        args=["abcdef"],
        max_chars=4,
    )
    url_wait = await tab.wait_until(
        condition="url_contains",
        value="ready",
        timeout=0,
    )
    text_wait = await tab.wait_until(
        condition="text_contains",
        value="Ready",
        timeout=0,
    )
    clickable_wait = await tab.wait_until(
        condition="clickable",
        selector="#save",
        timeout=0,
    )
    stable_wait = await tab.wait_until(
        condition="stable",
        selector="#save",
        timeout=0,
        stable_ms=10,
    )

    assert observation["text_samples"] == ["Ready", "Save"]
    assert observation["active_element"] is None
    assert observation["limits"] == {"max_texts": 2, "max_text_chars": 50}
    assert evaluated == {
        "result": "abcd",
        "result_type": "string",
        "truncated": True,
        "original_json_chars": 8,
        "max_chars": 4,
    }
    assert url_wait["matched"] is True
    assert text_wait["state"]["text"] == "Page is Ready"
    assert clickable_wait["state"]["tag"] == "button"
    assert stable_wait["matched"] is True


@pytest.mark.asyncio
async def test_console_logs_are_normalized_filterable_and_cursor_based() -> None:
    page = FakePage()
    page.console = FakeConsole(
        messages=[
            AttrConsoleMessage(level="log", text="load log"),
            {
                "level": "warning",
                "text": "slow request",
                "url": "https://example.test/console",
                "line": "9",
                "column": "4",
                "source": "console-api",
            },
            AttrConsoleMessage(level="error", text="action failed", line=12),
        ]
    )
    tab = PageTab(page, FakeContext())

    all_logs = await tab.console_logs(level="all", since=-1, limit=2)
    error_logs = await tab.console_logs(level="error", since=-1, limit=20)
    cursor_logs = await tab.console_logs(level="all", since=1, limit=20)

    assert page.console.started is True
    assert all_logs["available"] is True
    assert all_logs["listening"] is True
    assert all_logs["count"] == 2
    assert all_logs["total"] == 3
    assert all_logs["next_cursor"] == 2
    assert [item["index"] for item in all_logs["logs"]] == [1, 2]
    assert all_logs["logs"][0] == {
        "index": 1,
        "level": "warning",
        "text": "slow request",
        "url": "https://example.test/console",
        "line": 9,
        "column": 4,
        "source": "console-api",
    }
    assert [item["text"] for item in error_logs["logs"]] == ["action failed"]
    assert [item["index"] for item in cursor_logs["logs"]] == [2]


@pytest.mark.asyncio
async def test_console_logs_report_capability_when_unavailable() -> None:
    page = FakePage()
    page.console = None
    unavailable = await PageTab(page, FakeContext()).console_logs()

    page.console = FakeConsole(start_raises=True)
    start_failed = await PageTab(page, FakeContext()).console_logs()

    assert unavailable == {
        "available": False,
        "listening": False,
        "count": 0,
        "total": 0,
        "next_cursor": -1,
        "logs": [],
    }
    assert start_failed["available"] is True
    assert start_failed["listening"] is False
    assert start_failed["logs"] == []


@pytest.mark.asyncio
async def test_observe_includes_bounded_console_summary() -> None:
    class ObservablePage(FakePage):
        def run_js(self, script: str, **kwargs):
            self.calls.append(("run_js", script[:40], kwargs))
            return {
                "url": self.url,
                "title": "Observable",
                "ready_state": "complete",
                "counts": {"buttons": 1},
                "text_samples": ["Ready"],
                "active_element": None,
            }

    page = ObservablePage()
    page.console = FakeConsole(
        messages=[
            AttrConsoleMessage(level="warning", text="first warning"),
            AttrConsoleMessage(level="error", text="first error"),
            AttrConsoleMessage(level="log", text="plain log"),
        ]
    )
    tab = PageTab(page, FakeContext())

    observation = await tab.observe()

    assert observation["console"]["available"] is True
    assert observation["console"]["error_count"] == 1
    assert observation["console"]["warning_count"] == 1
    assert observation["console"]["next_cursor"] == 2
    assert [item["text"] for item in observation["console"]["recent"]] == [
        "first warning",
        "first error",
        "plain log",
    ]


@pytest.mark.asyncio
async def test_observable_helpers_raise_on_invalid_page_results() -> None:
    class InvalidScriptPage(FakePage):
        def __init__(self, mode: str) -> None:
            super().__init__()
            self.mode = mode

        def run_js(self, script: str, **kwargs):
            self.calls.append(("run_js", script[:40], kwargs))
            if self.mode == "raise":
                raise RuntimeError("script failed")
            return "not structured"

    with pytest.raises(RuntimeError, match="page snapshot script returned"):
        await PageTab(InvalidScriptPage("invalid"), FakeContext()).page_snapshot()

    with pytest.raises(RuntimeError, match="form inspect script returned"):
        await PageTab(InvalidScriptPage("invalid"), FakeContext()).inspect_forms()

    with pytest.raises(RuntimeError, match="page observe script returned"):
        await PageTab(InvalidScriptPage("invalid"), FakeContext()).observe()

    with pytest.raises(RuntimeError, match="script failed"):
        await PageTab(InvalidScriptPage("raise"), FakeContext()).evaluate_script(
            "return 1;"
        )


@pytest.mark.asyncio
async def test_wait_until_conditions_cover_fallback_and_timeout_edges() -> None:
    page = FakePage(FakeElement(tag="button", text="Save"))
    tab = PageTab(page, FakeContext())

    present = await tab.wait_until(condition="present", selector="tag:button", timeout=0)
    visible = await tab.wait_until(condition="visible", selector="tag:button", timeout=0)
    hidden = await PageTab(FakePage(element=None), FakeContext()).wait_until(
        condition="hidden",
        selector="tag:missing",
        timeout=0,
    )
    detached = await PageTab(FakePage(element=None), FakeContext()).wait_until(
        condition="detached",
        selector="tag:missing",
        timeout=0,
    )

    assert present["state"]["exists"] is True
    assert visible["state"]["visible"] is True
    assert hidden["matched"] is True
    assert detached["matched"] is True

    class SelectorJsFailPage(FakePage):
        def run_js(self, script: str, **kwargs):
            self.calls.append(("run_js", script[:40], kwargs))
            raise RuntimeError("selector js failed")

    fallback_visible = await PageTab(
        SelectorJsFailPage(FakeElement(tag="button", text="Save")),
        FakeContext(),
    ).wait_until(condition="visible", selector="#save", timeout=0)
    assert fallback_visible["state"]["visible"] is True

    with pytest.raises(TimeoutError):
        await PageTab(
            FakePage(FakeElement(tag="button", attrs={"disabled": ""})),
            FakeContext(),
        ).wait_until(condition="clickable", selector="tag:button", timeout=0)

    class EleRaisingPage(FakePage):
        def ele(self, selector: str, **_kwargs):
            self.calls.append(("ele", selector))
            raise RuntimeError("element lookup failed")

    with pytest.raises(TimeoutError):
        await PageTab(EleRaisingPage(), FakeContext()).wait_until(
            condition="text_contains",
            selector="#missing",
            value="never",
            timeout=0,
        )

    with pytest.raises(ValueError, match="selector is required"):
        await tab.wait_until(condition="visible", timeout=0)

    with pytest.raises(TimeoutError, match="was not met"):
        await PageTab(FakePage(element=None), FakeContext()).wait_until(
            condition="visible",
            selector="tag:missing",
            timeout=0,
        )

    class TextAndHtmlRaisingPage(FakePage):
        @property
        def text(self):
            raise RuntimeError("text detached")

        @text.setter
        def text(self, _value):
            pass

        @property
        def html(self):
            raise RuntimeError("html detached")

        @html.setter
        def html(self, _value):
            pass

    with pytest.raises(TimeoutError):
        await PageTab(TextAndHtmlRaisingPage(), FakeContext()).wait_until(
            condition="text_contains",
            value="never",
            timeout=0,
        )


def test_tab_identity_summary_handles_detached_properties() -> None:
    tab = PageTab(RaisingIdentityPage(), FakeContext(), mcp_tab_id="t0")

    assert tab.native_tab_id == ""
    assert tab.title == ""
    assert tab.summary(active=True)["native_id"] == ""


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
async def test_element_wait_success_but_lookup_missing_paths_raise() -> None:
    """wait success must not hide a second failed element lookup."""

    page = FakePage(element=None)
    page.wait = FakeWait(loaded=True)
    tab = PageTab(page, FakeContext())

    for call in (
        tab.click_element("#missing"),
        tab.find_element("#missing"),
        tab.get_text("#missing"),
        tab.get_attribute("#missing", "id"),
        tab.get_property("#missing", "value"),
        tab.get_html("#missing"),
    ):
        with pytest.raises(Exception, match="Element not found"):
            await call


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
async def test_page_text_falls_back_to_body_when_text_property_is_absent() -> None:
    page = FakePage()
    del page.text
    tab = PageTab(page, FakeContext())

    assert await tab.get_text() == "Ada"
    assert ("ele", "tag:body") in page.calls

    empty_page = FakePage(element=None)
    del empty_page.text
    empty_tab = PageTab(empty_page, FakeContext())

    assert await empty_tab.get_text() == ""


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
async def test_screenshot_cleans_temp_file_best_effort_and_reraises_failures(
    monkeypatch,
) -> None:
    class LegacyScreenshotPage(FakePage):
        def get_screenshot(self, **kwargs):
            if kwargs.get("as_base64"):
                raise TypeError("old DrissionPage")
            Path(kwargs["path"]).write_bytes(b"legacy-png")

    removed_paths = []

    def fail_remove(path: str) -> None:
        removed_paths.append(path)
        raise OSError("already gone")

    monkeypatch.setattr("drissionpage_mcp.tab.os.remove", fail_remove)
    tab = PageTab(LegacyScreenshotPage(), FakeContext())

    assert await tab.screenshot() == base64.b64encode(b"legacy-png").decode()
    assert removed_paths

    class BrokenScreenshotPage(FakePage):
        def get_screenshot(self, **_kwargs):
            raise RuntimeError("screenshot failed")

    broken_tab = PageTab(BrokenScreenshotPage(), FakeContext())
    with pytest.raises(RuntimeError, match="screenshot failed"):
        await broken_tab.screenshot()


@pytest.mark.asyncio
async def test_wait_close_url_and_connection_helpers() -> None:
    page = FakePage()
    browser = FakeBrowser()
    tab = PageTab(page, FakeContext(browser))
    tab._url = "https://cached.test"

    assert await tab.wait_for_element("#ready") is True

    page.wait = FakeWaitFallback()
    assert await tab.wait_for_element("#ready", timeout=2) is True
    assert page.wait.calls == [("css:#ready", 2, True)]

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
async def test_wait_for_url_polls_and_handles_polling_errors(monkeypatch) -> None:
    page = FakePage()
    page.url = "https://example.test/loading"
    tab = PageTab(page, FakeContext())
    sleeps = []

    async def finish_after_first_poll(seconds: float) -> None:
        sleeps.append(seconds)
        page.url = "https://example.test/done"

    monkeypatch.setattr("drissionpage_mcp.tab.asyncio.sleep", finish_after_first_poll)

    assert await tab.wait_for_url("done", timeout=1) is True
    assert sleeps == [0.5]

    async def fail_sleep(_seconds: float) -> None:
        raise RuntimeError("clock failed")

    page.url = "https://example.test/loading"
    monkeypatch.setattr("drissionpage_mcp.tab.asyncio.sleep", fail_sleep)

    assert await tab.wait_for_url("done", timeout=1) is False


@pytest.mark.asyncio
async def test_navigation_failure_is_reraised() -> None:
    class FailedNavigationPage(FakePage):
        def get(self, url: str):
            return False

    tab = PageTab(FailedNavigationPage(), FakeContext())

    with pytest.raises(RuntimeError, match="Navigation failed"):
        await tab.navigate("https://bad.test")


@pytest.mark.asyncio
async def test_page_action_failures_are_reraised() -> None:
    class BrokenActions(FakeActions):
        def click(self, point):
            raise RuntimeError(f"cannot click {point}")

    class BrokenWindow(FakeWindow):
        def size(self, width: int, height: int) -> None:
            raise RuntimeError(f"cannot resize {width}x{height}")

    class BrokenSet(FakeSet):
        def __init__(self) -> None:
            self.window = BrokenWindow()

    class BrokenPage(FakePage):
        def __init__(self, broken_action: str) -> None:
            super().__init__()
            self.broken_action = broken_action
            self.actions = BrokenActions()
            self.set = BrokenSet()

        def back(self) -> None:
            if self.broken_action == "back":
                raise RuntimeError("back failed")
            super().back()

        def forward(self) -> None:
            if self.broken_action == "forward":
                raise RuntimeError("forward failed")
            super().forward()

        def refresh(self) -> None:
            if self.broken_action == "refresh":
                raise RuntimeError("refresh failed")
            super().refresh()

    for action, call in (
        ("back", lambda tab: tab.go_back()),
        ("forward", lambda tab: tab.go_forward()),
        ("refresh", lambda tab: tab.refresh()),
        ("click", lambda tab: tab.click(1, 2)),
        ("resize", lambda tab: tab.resize(800, 600)),
    ):
        tab = PageTab(BrokenPage(action), FakeContext())
        with pytest.raises(RuntimeError):
            await call(tab)


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
async def test_post_action_stabilization_tries_compatible_doc_loaded_signatures() -> None:
    class WaitWithStrictDocLoaded(FakeWait):
        def __init__(self) -> None:
            super().__init__()
            self.doc_loaded_calls = []

        def doc_loaded(self, **kwargs):
            self.doc_loaded_calls.append(kwargs)
            if "raise_err" in kwargs or "timeout" in kwargs:
                raise TypeError("unsupported keyword")
            return True

    page = FakePage()
    page.wait = WaitWithStrictDocLoaded()
    tab = PageTab(page, FakeContext())

    await tab.refresh()

    assert page.wait.doc_loaded_calls == [
        {"timeout": 5.0, "raise_err": False},
        {"timeout": 5.0},
        {},
    ]


@pytest.mark.asyncio
async def test_post_action_stabilization_falls_back_when_doc_loaded_fails(
    monkeypatch,
) -> None:
    class WaitWithFailingDocLoaded(FakeWait):
        def doc_loaded(self, **_kwargs):
            raise RuntimeError("load waiter disconnected")

    sleeps = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("drissionpage_mcp.tab.asyncio.sleep", fake_sleep)
    page = FakePage()
    page.wait = WaitWithFailingDocLoaded()
    tab = PageTab(page, FakeContext())

    await tab.click(1, 2)

    assert sleeps == [0.02]


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


@pytest.mark.asyncio
async def test_close_reports_browser_close_errors_without_raising() -> None:
    class BrokenBrowser(FakeBrowser):
        def close_tabs(self, tab_id: str) -> None:
            raise RuntimeError(f"cannot close {tab_id}")

    tab = PageTab(FakePage(), FakeContext(BrokenBrowser()))

    assert await tab.close() is False
