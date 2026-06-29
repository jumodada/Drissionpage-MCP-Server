"""Pure unit coverage for tool success paths without launching DrissionPage."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from DrissionPage.errors import ElementNotFoundError

from drissionpage_mcp.response import ToolResponse
from drissionpage_mcp.tools import common, element, navigate, wait

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)
PNG_1X1_B64 = base64.b64encode(PNG_1X1).decode()


class FakeTab:
    """Small async PageTab stand-in for tool handler tests."""

    def __init__(self) -> None:
        self.url = "https://example.test/current"
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.wait_element_result = True
        self.wait_url_result = True

    async def resize(self, width: int, height: int) -> None:
        self._record("resize", width, height)

    async def screenshot(self, path: str | None = None, full_page: bool = False) -> str:
        self._record("screenshot", path, full_page=full_page)
        if path is not None:
            Path(path).write_bytes(PNG_1X1)
            return path
        return PNG_1X1_B64

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
        self.closed = False
        self.waited: list[float] = []

    def current_tab_or_die(self) -> FakeTab:
        return self.tab

    async def ensure_tab(self) -> FakeTab:
        return self.tab

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
async def test_common_tools_success_paths(tmp_path) -> None:
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
    path_response = await _execute(
        common.screenshot,
        ctx,
        common.ScreenshotInput(path=str(screenshot_path), full_page=False),
    )
    path_payload = path_response.get_structured_content()
    assert path_payload["data"]["screenshot"]["path"] == str(screenshot_path)
    assert path_payload["data"]["screenshot"]["inline"] is False

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
    }
    assert "Successfully navigated" in _message(nav_response)
    assert nav_response.should_include_snapshot() is True
    assert ctx.tab.url == "https://example.test/next"

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
        (common.ScreenshotInput, {"fullPage": True}),
        (common.ResizeInput, {"width": 800, "height": 600, "extra": True}),
        (navigate.NavigateInput, {"url": "https://example.test", "new_tab": True}),
        (element.FindElementInput, {"selector": "h1", "timeout_ms": 1}),
        (
            element.TypeTextInput,
            {"selector": "#name", "text": "Ada", "clear_first": False},
        ),
        (
            element.GetPropertyInput,
            {"selector": "#name", "property": "value", "property_name": "value"},
        ),
        (wait.WaitTimeInput, {"seconds": 1, "milliseconds": 500}),
    ],
)
def test_tool_inputs_reject_unknown_fields(model, payload) -> None:
    """LLM/client field typos should fail instead of being silently ignored."""

    with pytest.raises(Exception, match="Extra inputs"):
        model.model_validate(payload)


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
