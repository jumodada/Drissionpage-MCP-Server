"""Pure unit coverage for tool success paths without launching DrissionPage."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from DrissionPage.errors import ElementNotFoundError

from drissionpage_mcp.response import ToolResponse
from drissionpage_mcp.tools import common, debug, element, forms, navigate, tabs, wait

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)
PNG_1X1_B64 = base64.b64encode(PNG_1X1).decode()


class FakeTab:
    """Small async PageTab stand-in for tool handler tests."""

    def __init__(self) -> None:
        self.url = "https://example.test/current"
        self.title = "Fake Tab"
        self.mcp_tab_id = "t0"
        self.native_tab_id = "native-0"
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.wait_element_result = True
        self.wait_url_result = True
        self.observe_count = 0

    def summary(self, *, active: bool = False) -> dict[str, Any]:
        return {
            "id": self.mcp_tab_id,
            "native_id": self.native_tab_id,
            "url": self.url,
            "title": self.title,
            "active": active,
            "connected": True,
        }

    async def resize(self, width: int, height: int) -> None:
        self._record("resize", width, height)

    async def screenshot(self, path: str | None = None, full_page: bool = False) -> str:
        self._record("screenshot", path, full_page=full_page)
        if path is not None:
            Path(path).write_bytes(PNG_1X1)
            return path
        return PNG_1X1_B64

    async def page_snapshot(
        self,
        *,
        include_html: bool = False,
        max_elements: int = 50,
        max_text_chars: int = 4000,
    ) -> dict[str, Any]:
        self._record(
            "page_snapshot",
            include_html=include_html,
            max_elements=max_elements,
            max_text_chars=max_text_chars,
        )
        return {
            "url": self.url,
            "title": "Fake Catalog",
            "text_excerpt": "Alpha Beta",
            "headings": [
                {
                    "index": 0,
                    "tag": "h1",
                    "text": "Fake Catalog",
                    "selector": "#title",
                    "attributes": {"id": "title"},
                }
            ],
            "links": [],
            "buttons": [],
            "inputs": [],
            "forms": [],
            "counts": {"headings": 1},
            "truncated": {
                "text": False,
                "elements": False,
                "returned_elements": 1,
            },
            "limits": {
                "max_elements": max_elements,
                "max_text_chars": max_text_chars,
            },
        }

    async def observe(
        self,
        *,
        max_texts: int = 20,
        max_text_chars: int = 160,
    ) -> dict[str, Any]:
        self._record(
            "observe",
            max_texts=max_texts,
            max_text_chars=max_text_chars,
        )
        phase = self.observe_count
        self.observe_count += 1
        return {
            "url": self.url,
            "title": self.title,
            "ready_state": "complete",
            "counts": {"buttons": 1 + phase, "inputs": 1},
            "text_samples": ["before"] if phase % 2 == 0 else ["after"],
            "active_element": None,
            "console": {
                "available": True,
                "listening": True,
                "count": phase + 1,
                "total": phase + 1,
                "next_cursor": phase,
                "error_count": 1 if phase else 0,
                "warning_count": 0,
                "recent": [
                    {
                        "index": phase,
                        "level": "error" if phase else "log",
                        "text": "after error" if phase else "before log",
                        "url": self.url,
                        "line": 1,
                        "column": 1,
                        "source": "console-api",
                    }
                ],
            },
            "limits": {
                "max_texts": max_texts,
                "max_text_chars": max_text_chars,
            },
        }

    async def console_logs(
        self,
        *,
        level: str = "all",
        since: int = -1,
        limit: int = 20,
    ) -> dict[str, Any]:
        self._record("console_logs", level=level, since=since, limit=limit)
        logs = [
            {
                "index": 0,
                "level": "log",
                "text": "before log",
                "url": self.url,
                "line": 1,
                "column": 1,
                "source": "console-api",
            },
            {
                "index": 1,
                "level": "error",
                "text": "after error",
                "url": self.url,
                "line": 2,
                "column": 1,
                "source": "console-api",
            },
        ]
        filtered = [item for item in logs if item["index"] > since]
        if level != "all":
            filtered = [item for item in filtered if item["level"] == level]
        return {
            "available": True,
            "listening": True,
            "count": len(filtered[:limit]),
            "total": len(logs),
            "next_cursor": logs[-1]["index"],
            "logs": filtered[:limit],
        }

    async def evaluate_script(
        self,
        script: str,
        *,
        args: list[Any] | None = None,
        max_chars: int = 4000,
    ) -> dict[str, Any]:
        self._record("evaluate_script", script, args=args or [], max_chars=max_chars)
        return {
            "result": {"script": script, "args": args or []},
            "result_type": "object",
            "truncated": False,
            "original_json_chars": 42,
            "max_chars": max_chars,
        }

    async def inspect_forms(
        self,
        *,
        selector: str = "",
        include_values: bool = False,
        max_forms: int = 10,
        max_fields_per_form: int = 50,
    ) -> dict[str, Any]:
        self._record(
            "inspect_forms",
            selector=selector,
            include_values=include_values,
            max_forms=max_forms,
            max_fields_per_form=max_fields_per_form,
        )
        return {
            "selector": selector,
            "include_values": include_values,
            "count": 1,
            "returned": 1,
            "limits": {
                "max_forms": max_forms,
                "max_fields_per_form": max_fields_per_form,
            },
            "truncated": {"forms": False, "fields": False},
            "forms": [
                {
                    "index": 0,
                    "selector": "#fixture-form",
                    "id": "fixture-form",
                    "name": "",
                    "method": "get",
                    "action": "/form",
                    "text": "Name Submit",
                    "fields": [
                        {
                            "index": 0,
                            "tag": "input",
                            "type": "text",
                            "name": "name",
                            "label": "Name",
                            "selector": "#name",
                            "placeholder": "",
                            "required": False,
                            "disabled": False,
                            "readonly": False,
                            "checked": False,
                            "value": "Ada" if include_values else None,
                            "attributes": {"id": "name", "name": "name"},
                            "options": [],
                        }
                    ],
                }
            ],
        }

    async def click(self, x: int, y: int) -> None:
        self._record("click", x, y)

    async def navigate(self, url: str) -> None:
        self._record("navigate", url)
        self.url = url

    async def go_back(self) -> None:
        self._record("go_back")

    async def go_forward(self) -> None:
        self._record("go_forward")

    async def refresh(self) -> None:
        self._record("refresh")

    async def wait_for_element(self, selector: str, timeout: int = 10) -> bool:
        self._record("wait_for_element", selector, timeout=timeout)
        return self.wait_element_result

    async def wait_for_url(self, pattern: str, timeout: int = 10) -> bool:
        self._record("wait_for_url", pattern, timeout=timeout)
        return self.wait_url_result

    async def wait_until(
        self,
        *,
        condition: str,
        selector: str = "",
        value: str = "",
        timeout: float = 10,
        interval: float = 0.1,
        stable_ms: int = 300,
    ) -> dict[str, Any]:
        self._record(
            "wait_until",
            condition=condition,
            selector=selector,
            value=value,
            timeout=timeout,
            interval=interval,
            stable_ms=stable_ms,
        )
        return {
            "condition": condition,
            "selector": selector,
            "value": value,
            "matched": True,
            "timeout": timeout,
            "elapsed_ms": 15,
            "state": {"selector": selector, "visible": True},
        }

    async def find_element(self, selector: str, timeout: int = 10) -> dict[str, Any]:
        self._record("find_element", selector, timeout=timeout)
        return {
            "found": True,
            "selector": selector,
            "locator": "css:#name",
            "selector_strategy": "css",
            "selector_normalized": True,
            "text": "Ada",
            "tag": "input",
            "html": "<input id='name'>",
            "visible": True,
        }

    async def find_elements(
        self,
        selector: str,
        *,
        limit: int = 20,
        include_html: bool = False,
    ) -> dict[str, Any]:
        self._record(
            "find_elements",
            selector,
            limit=limit,
            include_html=include_html,
        )
        elements = [
            {
                "index": 0,
                "tag": "article",
                "text": "Alpha",
                "selector": "#alpha",
                "attributes": {"id": "alpha", "class": "product-card"},
            },
            {
                "index": 1,
                "tag": "article",
                "text": "Beta",
                "selector": "#beta",
                "attributes": {"id": "beta", "class": "product-card"},
            },
        ][:limit]
        if include_html:
            for item in elements:
                item["html"] = f"<article>{item['text']}</article>"
        return {
            "selector": selector,
            "locator": "css:.product-card",
            "selector_strategy": "css",
            "selector_normalized": True,
            "count": 2,
            "returned": len(elements),
            "limit": limit,
            "truncated": limit < 2,
            "elements": elements,
        }

    async def click_element(self, selector: str, timeout: int = 10) -> None:
        self._record("click_element", selector, timeout=timeout)

    async def type_text(
        self,
        selector: str,
        text: str,
        timeout: int = 10,
        clear: bool = True,
    ) -> None:
        self._record("type_text", selector, text, timeout=timeout, clear=clear)

    async def get_text(self, selector: str = "") -> str:
        self._record("get_text", selector)
        return "page text" if selector == "" else "element text"

    async def get_attribute(self, selector: str, attribute: str) -> str | None:
        self._record("get_attribute", selector, attribute)
        return None if attribute == "missing" else "attr-value"

    async def get_property(self, selector: str, property_name: str) -> str | None:
        self._record("get_property", selector, property_name)
        return None if property_name == "missing" else "prop-value"

    async def get_html(self, selector: str = "") -> str:
        self._record("get_html", selector)
        return "<html></html>" if selector == "" else "<input>"

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))


class FakeContext:
    def __init__(self) -> None:
        self.tab = FakeTab()
        self.created_tab = FakeTab()
        self.created_tab.mcp_tab_id = "t1"
        self.created_tab.native_tab_id = "native-1"
        self.created_tab.url = "https://example.test/new"
        self.closed = False
        self.waited: list[float] = []
        self.tab_infos = [
            {
                "id": "t0",
                "native_id": "native-0",
                "url": "https://example.test/current",
                "title": "Current",
                "active": True,
                "connected": True,
            },
            {
                "id": "t1",
                "native_id": "native-1",
                "url": "https://example.test/new",
                "title": "New",
                "active": False,
                "connected": True,
            },
        ]

    def current_tab_or_die(self) -> FakeTab:
        return self.tab

    async def ensure_tab(self) -> FakeTab:
        return self.tab

    async def new_tab(self) -> FakeTab:
        return self.created_tab

    async def sync_tabs(self):
        return [self.tab, self.created_tab]

    def tab_summaries(self):
        return self.tab_infos

    async def switch_tab(self, tab_id: str):
        self.tab_infos[0]["active"] = False
        self.tab_infos[1]["active"] = True
        self.tab = self.created_tab
        return self.created_tab

    async def close_tab_by_id(self, tab_id: str):
        self.tab_infos = [info for info in self.tab_infos if info["id"] != tab_id]

    async def close_browser(self) -> None:
        self.closed = True

    async def wait(self, seconds: float) -> None:
        self.waited.append(seconds)


async def _execute(tool, ctx: FakeContext, args) -> ToolResponse:
    response = ToolResponse()
    await tool.handler(ctx, args, response)
    return response


def _message(response: ToolResponse) -> str:
    return response.get_structured_content()["message"]


@pytest.mark.asyncio
async def test_common_tools_success_paths(monkeypatch, tmp_path) -> None:
    ctx = FakeContext()

    resize_response = await _execute(
        common.resize, ctx, common.ResizeInput(width=640, height=480)
    )
    assert resize_response.get_structured_content()["data"] == {
        "width": 640,
        "height": 480,
    }
    assert "640x480" in _message(resize_response)
    assert ctx.tab.calls[-1] == ("resize", (640, 480), {})

    inline_response = await _execute(
        common.screenshot, ctx, common.ScreenshotInput(full_page=True)
    )
    inline_payload = inline_response.get_structured_content()
    assert inline_payload["data"]["screenshot"]["inline"] is True
    assert inline_payload["data"]["screenshot"]["full_page"] is True

    screenshot_path = tmp_path / "screen.png"
    monkeypatch.setenv("DP_MCP_SCREENSHOT_ROOT", str(tmp_path))
    path_response = await _execute(
        common.screenshot_save,
        ctx,
        common.ScreenshotSaveInput(path=str(screenshot_path), full_page=False),
    )
    path_payload = path_response.get_structured_content()
    assert path_payload["data"]["screenshot"]["path"] == str(screenshot_path)
    assert path_payload["data"]["screenshot"]["inline"] is False

    snapshot_response = await _execute(
        common.page_snapshot,
        ctx,
        common.PageSnapshotInput(
            include_html=True,
            max_elements=5,
            max_text_chars=100,
        ),
    )
    snapshot_payload = snapshot_response.get_structured_content()
    assert snapshot_payload["data"]["title"] == "Fake Catalog"
    assert snapshot_payload["data"]["limits"] == {
        "max_elements": 5,
        "max_text_chars": 100,
    }
    assert ctx.tab.calls[-1] == (
        "page_snapshot",
        (),
        {"include_html": True, "max_elements": 5, "max_text_chars": 100},
    )

    observe_response = await _execute(
        common.page_observe,
        ctx,
        common.PageObserveInput(max_texts=3, max_text_chars=80),
    )
    observe_payload = observe_response.get_structured_content()
    assert observe_payload["data"]["url"] == "https://example.test/current"
    assert observe_payload["data"]["limits"] == {
        "max_texts": 3,
        "max_text_chars": 80,
    }

    evaluate_response = await _execute(
        common.page_evaluate,
        ctx,
        common.PageEvaluateInput(
            script="return {total: args[0] + args[1]};",
            args=[2, 3],
            max_chars=1000,
        ),
    )
    evaluate_payload = evaluate_response.get_structured_content()
    assert evaluate_payload["data"]["result_type"] == "object"
    assert evaluate_payload["data"]["max_chars"] == 1000
    assert ctx.tab.calls[-1] == (
        "evaluate_script",
        ("return {total: args[0] + args[1]};",),
        {"args": [2, 3], "max_chars": 1000},
    )

    console_response = await _execute(
        debug.page_console_logs,
        ctx,
        debug.ConsoleLogsInput(level="error", since=0, limit=10),
    )
    console_payload = console_response.get_structured_content()
    assert console_payload["data"]["count"] == 1
    assert console_payload["data"]["logs"][0]["text"] == "after error"
    assert ctx.tab.calls[-1] == (
        "console_logs",
        (),
        {"level": "error", "since": 0, "limit": 10},
    )

    click_response = await _execute(
        common.click_coordinates,
        ctx,
        common.ClickCoordinatesInput(x=7, y=9),
    )
    assert click_response.get_structured_content()["data"] == {
        "x": 7,
        "y": 9,
        "element": "",
        "url": "https://example.test/current",
    }
    assert "(7, 9)" in _message(click_response)
    assert click_response.should_include_snapshot() is True

    close_response = await _execute(common.close, ctx, common.EmptyInput())
    assert close_response.get_structured_content()["data"] == {"closed": True}
    assert ctx.closed is True
    assert "closed browser" in _message(close_response)

    url_response = await _execute(common.get_url, ctx, common.EmptyInput())
    assert url_response.get_structured_content()["data"] == {
        "url": "https://example.test/current"
    }
    assert "https://example.test/current" in _message(url_response)


@pytest.mark.asyncio
async def test_form_tools_success_paths() -> None:
    ctx = FakeContext()

    response = await _execute(
        forms.form_inspect,
        ctx,
        forms.FormInspectInput(
            selector="#fixture-form",
            include_values=True,
            max_forms=2,
            max_fields_per_form=3,
        ),
    )

    payload = response.get_structured_content()
    assert payload["message"] == "Inspected 1 of 1 forms"
    assert payload["data"]["forms"][0]["selector"] == "#fixture-form"
    assert payload["data"]["forms"][0]["fields"][0]["selector"] == "#name"
    assert payload["data"]["forms"][0]["fields"][0]["value"] == "Ada"
    assert ctx.tab.calls[-1] == (
        "inspect_forms",
        (),
        {
            "selector": "#fixture-form",
            "include_values": True,
            "max_forms": 2,
            "max_fields_per_form": 3,
        },
    )


@pytest.mark.asyncio
async def test_navigation_tools_success_paths() -> None:
    ctx = FakeContext()

    nav_response = await _execute(
        navigate.navigate,
        ctx,
        navigate.NavigateInput(url="https://example.test/next"),
    )
    assert nav_response.get_structured_content()["data"] == {
        "url": "https://example.test/next",
        "final_url": "https://example.test/next",
        "new_tab": False,
        "tab_id": "t0",
    }
    assert "Successfully navigated" in _message(nav_response)
    assert nav_response.should_include_snapshot() is True
    assert ctx.tab.url == "https://example.test/next"

    observed_ctx = FakeContext()
    observed_nav_response = await _execute(
        navigate.navigate,
        observed_ctx,
        navigate.NavigateInput(url="https://example.test/observed", observe=True),
    )
    observed_nav_data = observed_nav_response.get_structured_content()["data"]
    assert observed_nav_data["final_url"] == "https://example.test/observed"
    assert observed_nav_data["changes"]["url_changed"] is True
    assert observed_nav_data["changes"]["appeared_texts"] == ["after"]
    assert observed_nav_data["changes"]["console_errors_added"] == 1
    assert observed_nav_data["changes"]["new_console_messages"][0]["text"] == "after error"

    new_tab_response = await _execute(
        navigate.navigate,
        ctx,
        navigate.NavigateInput(url="https://example.test/new", new_tab=True),
    )
    new_tab_payload = new_tab_response.get_structured_content()
    assert new_tab_payload["data"]["url"] == "https://example.test/new"
    assert new_tab_payload["data"]["final_url"] == "https://example.test/new"
    assert new_tab_payload["data"]["new_tab"] is True

    for tool, expected_call, expected_message in [
        (navigate.go_back, "go_back", "went back"),
        (navigate.go_forward, "go_forward", "went forward"),
        (navigate.refresh, "refresh", "refreshed page"),
    ]:
        response = await _execute(tool, ctx, navigate.EmptyInput())
        assert response.get_structured_content()["data"] == {
            "url": "https://example.test/next"
        }
        assert expected_message in _message(response)
        assert response.should_include_snapshot() is True
        assert ctx.tab.calls[-1][0] == expected_call


@pytest.mark.asyncio
async def test_wait_tools_success_and_timeout_paths() -> None:
    ctx = FakeContext()

    element_response = await _execute(
        wait.wait_for_element,
        ctx,
        wait.WaitElementInput(selector="#ready", timeout=2),
    )
    assert element_response.get_structured_content()["data"] == {
        "selector": "#ready",
        "locator": "css:#ready",
        "selector_strategy": "css",
        "selector_normalized": True,
        "found": True,
        "timeout": 2,
    }
    assert "appeared within 2 seconds" in _message(element_response)

    url_response = await _execute(
        wait.wait_for_url,
        ctx,
        wait.WaitUrlInput(url_pattern="ready", timeout=3),
    )
    assert url_response.get_structured_content()["data"] == {
        "url_pattern": "ready",
        "matched": True,
        "url": "https://example.test/current",
        "timeout": 3,
    }
    assert "URL matched" in _message(url_response)

    time_response = await _execute(
        wait.wait_time, ctx, wait.WaitTimeInput(seconds=0.25)
    )
    assert time_response.get_structured_content()["data"] == {"waited_seconds": 0.25}
    assert ctx.waited == [0.25]
    assert "Waited for 0.25 seconds" in _message(time_response)

    until_response = await _execute(
        wait.wait_until,
        ctx,
        wait.WaitUntilInput(
            condition="clickable",
            selector="#ready",
            timeout=2,
            interval=0.2,
            stable_ms=50,
        ),
    )
    until_payload = until_response.get_structured_content()
    assert until_payload["data"] == {
        "condition": "clickable",
        "selector": "#ready",
        "value": "",
        "matched": True,
        "timeout": 2.0,
        "elapsed_ms": 15,
        "state": {"selector": "#ready", "visible": True},
    }

    ctx.tab.wait_element_result = False
    timeout_response = await _execute(
        wait.wait_for_element,
        ctx,
        wait.WaitElementInput(selector="#missing", timeout=1),
    )
    assert timeout_response.is_error() is True
    assert "did not appear" in timeout_response.get_structured_content()["message"]

    ctx.tab.wait_url_result = False
    url_timeout_response = await _execute(
        wait.wait_for_url,
        ctx,
        wait.WaitUrlInput(url_pattern="never", timeout=1),
    )
    assert url_timeout_response.is_error() is True
    assert (
        "URL did not match" in url_timeout_response.get_structured_content()["message"]
    )


def test_element_find_default_timeout_is_llm_friendly() -> None:
    args = element.FindElementInput(selector="h1")

    assert args.timeout == 3


def test_get_property_input_uses_property_field_only() -> None:
    args = element.GetPropertyInput.model_validate(
        {"selector": "#name", "property": "value"}
    )

    assert args.property == "value"

    with pytest.raises(Exception, match="property"):
        element.GetPropertyInput.model_validate(
            {"selector": "#name", "property_name": "value"}
        )


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (common.PageSnapshotInput, {"maxElements": 10}),
        (common.PageObserveInput, {"maxTexts": 10}),
        (common.PageEvaluateInput, {"script": "return 1", "maxChars": 100}),
        (common.ScreenshotInput, {"fullPage": True}),
        (common.ScreenshotInput, {"path": "/tmp/screen.png"}),
        (common.ResizeInput, {"width": 800, "height": 600, "extra": True}),
        (navigate.NavigateInput, {"url": "https://example.test", "background": True}),
        (element.FindElementInput, {"selector": "h1", "timeout_ms": 1}),
        (element.FindAllElementsInput, {"selector": "li", "max_items": 10}),
        (
            element.TypeTextInput,
            {"selector": "#name", "text": "Ada", "clear_first": False},
        ),
        (
            element.GetPropertyInput,
            {"selector": "#name", "property": "value", "property_name": "value"},
        ),
        (wait.WaitTimeInput, {"seconds": 1, "milliseconds": 500}),
        (wait.WaitUntilInput, {"condition": "visible", "timeout_ms": 1}),
    ],
)
def test_tool_inputs_reject_unknown_fields(model, payload) -> None:
    """LLM/client field typos should fail instead of being silently ignored."""

    with pytest.raises(Exception, match="Extra inputs"):
        model.model_validate(payload)


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (element.FindElementInput, {"selector": "h1", "timeout": 121}),
        (element.ClickElementInput, {"selector": "button", "timeout": 121}),
        (
            element.TypeTextInput,
            {"selector": "#name", "text": "Ada", "timeout": 121},
        ),
        (wait.WaitElementInput, {"selector": "#ready", "timeout": 121}),
        (wait.WaitUrlInput, {"url_pattern": "ready", "timeout": 121}),
        (wait.WaitTimeInput, {"seconds": 121}),
    ],
)
def test_wait_inputs_reject_excessive_timeouts(model, payload) -> None:
    """Client-controlled waits should stay bounded."""

    with pytest.raises(Exception):
        model.model_validate(payload)


@pytest.mark.asyncio
async def test_tab_tools_success_paths() -> None:
    ctx = FakeContext()

    list_response = await _execute(tabs.tab_list, ctx, tabs.EmptyInput())
    list_payload = list_response.get_structured_content()
    assert list_payload["data"]["count"] == 2
    assert list_payload["data"]["active_tab_id"] == "t0"
    assert list_payload["data"]["tabs"][1]["url"] == "https://example.test/new"

    switch_response = await _execute(
        tabs.tab_switch, ctx, tabs.TabIdInput(tab_id="t1")
    )
    switch_payload = switch_response.get_structured_content()
    assert switch_payload["data"]["tab"]["id"] == "t1"
    assert switch_payload["data"]["tab"]["active"] is True

    close_response = await _execute(tabs.tab_close, ctx, tabs.TabIdInput(tab_id="t1"))
    close_payload = close_response.get_structured_content()
    assert close_payload["data"]["closed"] is True
    assert close_payload["data"]["tab_id"] == "t1"


@pytest.mark.asyncio
async def test_element_tools_success_paths() -> None:
    ctx = FakeContext()
    selector_metadata = {
        "selector": "#name",
        "locator": "css:#name",
        "selector_strategy": "css",
        "selector_normalized": True,
    }

    found_response = await _execute(
        element.find_element,
        ctx,
        element.FindElementInput(selector="#name", timeout=1),
    )
    assert found_response.get_structured_content()["data"] == {
        "element": {
            "found": True,
            **selector_metadata,
            "text": "Ada",
            "tag": "input",
            "html": "<input id='name'>",
            "visible": True,
        }
    }
    assert found_response.get_structured_content()["message"] == "Found element: #name"

    found_all_response = await _execute(
        element.find_all_elements,
        ctx,
        element.FindAllElementsInput(
            selector=".product-card",
            limit=1,
            include_html=True,
        ),
    )
    found_all_payload = found_all_response.get_structured_content()
    found_all_data = dict(found_all_payload["data"])
    found_all_meta = found_all_data.pop("meta")
    assert found_all_meta["approx_tokens"] > 0
    assert found_all_meta["json_chars"] > 0
    assert found_all_meta["truncated"] is True
    assert found_all_data == {
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
                "text": "Alpha",
                "selector": "#alpha",
                "attributes": {"id": "alpha", "class": "product-card"},
                "html": "<article>Alpha</article>",
            }
        ],
    }

    click_response = await _execute(
        element.click_element,
        ctx,
        element.ClickElementInput(selector="#name", timeout=1),
    )
    assert click_response.get_structured_content()["data"] == {
        **selector_metadata,
        "url": "https://example.test/current",
    }
    assert "Successfully clicked element" in _message(click_response)
    assert click_response.should_include_snapshot() is True

    observed_click = await _execute(
        element.click_element,
        ctx,
        element.ClickElementInput(selector="#name", timeout=1, observe=True),
    )
    observed_click_data = observed_click.get_structured_content()["data"]
    assert observed_click_data["changes"]["appeared_texts"] == ["after"]

    type_response = await _execute(
        element.type_text,
        ctx,
        element.TypeTextInput(selector="#name", text="Ada", clear=False),
    )
    assert type_response.get_structured_content()["data"] == {
        **selector_metadata,
        "typed": True,
        "cleared": False,
    }
    assert "Ada" not in str(type_response.get_structured_content()["data"])
    assert "Successfully typed" in _message(type_response)
    assert type_response.should_include_snapshot() is True

    observed_type = await _execute(
        element.type_text,
        ctx,
        element.TypeTextInput(
            selector="#name",
            text="Ada",
            clear=False,
            observe=True,
        ),
    )
    observed_type_data = observed_type.get_structured_content()["data"]
    assert observed_type_data["changes"]["counts_delta"]["buttons"] == 1

    text_response = await _execute(
        element.get_text, ctx, element.GetTextInput(selector="#name")
    )
    assert text_response.get_structured_content()["data"] == {
        "text": "element text",
        **selector_metadata,
    }
    page_text_response = await _execute(element.get_text, ctx, element.GetTextInput())
    assert page_text_response.get_structured_content()["data"] == {
        "text": "page text",
        "selector": "",
        "locator": "",
        "selector_strategy": "page",
        "selector_normalized": False,
    }

    attr_response = await _execute(
        element.get_attribute,
        ctx,
        element.GetAttributeInput(selector="#name", attribute="id"),
    )
    assert attr_response.get_structured_content()["data"] == {
        **selector_metadata,
        "attribute": "id",
        "value": "attr-value",
    }

    missing_attr_response = await _execute(
        element.get_attribute,
        ctx,
        element.GetAttributeInput(selector="#name", attribute="missing"),
    )
    assert missing_attr_response.get_structured_content()["data"]["value"] is None

    prop_response = await _execute(
        element.get_property,
        ctx,
        element.GetPropertyInput(selector="#name", property="value"),
    )
    assert prop_response.get_structured_content()["data"] == {
        **selector_metadata,
        "property": "value",
        "value": "prop-value",
    }
    missing_prop_response = await _execute(
        element.get_property,
        ctx,
        element.GetPropertyInput(selector="#name", property="missing"),
    )
    assert missing_prop_response.get_structured_content()["data"]["value"] is None

    html_response = await _execute(
        element.get_html, ctx, element.GetHtmlInput(selector="#name")
    )
    assert html_response.get_structured_content()["data"] == {
        "html": "<input>",
        **selector_metadata,
    }
    page_html_response = await _execute(element.get_html, ctx, element.GetHtmlInput())
    assert page_html_response.get_structured_content()["data"] == {
        "html": "<html></html>",
        "selector": "",
        "locator": "",
        "selector_strategy": "page",
        "selector_normalized": False,
    }


class MissingElementTypeTab(FakeTab):
    async def type_text(
        self,
        selector: str,
        text: str,
        timeout: int = 10,
        clear: bool = True,
    ) -> None:
        self._record("type_text", selector, text, timeout=timeout, clear=clear)
        raise ElementNotFoundError(f"Element not found: {selector}")


@pytest.mark.asyncio
async def test_element_type_reports_structured_not_found_error() -> None:
    ctx = FakeContext()
    ctx.tab = MissingElementTypeTab()

    response = await _execute(
        element.type_text,
        ctx,
        element.TypeTextInput(selector="#missing", text="Ada", timeout=1),
    )

    payload = response.get_structured_content()
    assert response.is_error() is True
    assert payload["error"]["code"] == "ELEMENT_NOT_FOUND"
    assert "#missing" in payload["message"]
