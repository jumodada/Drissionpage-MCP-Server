"""Browser integration tests using the deterministic local HTTP fixture."""

from __future__ import annotations

import base64
from typing import Any, Dict, List, Tuple
from urllib.request import urlopen

import pytest

from drissionpage_mcp.response import ToolResponse
from drissionpage_mcp.server import DrissionPageMCPServer
from tests.fixtures.http_fixture import local_http_fixture

_BROWSER_UNAVAILABLE_MARKERS = (
    "browser",
    "chrome",
    "chromium",
    "cannot find",
    "connection refused",
    "failed to initialize",
    "executable",
)


def test_local_http_fixture_serves_required_routes() -> None:
    """serves all deterministic fixture routes without external network access."""

    with local_http_fixture() as base_url:
        assert _read(base_url + "/")[0] == 200
        assert "DrissionMCP Fixture" in _read(base_url + "/")[1]
        assert "fixture-form" in _read(base_url + "/form")[1]
        assert "dynamic-root" in _read(base_url + "/dynamic")[1]
        assert _read(base_url + "/redirect")[0] == 200
        assert _read(base_url + "/status/404")[0] == 404
        assert _read(base_url + "/status/500")[0] == 500
        assert "Iframe Content" in _read(base_url + "/iframe")[1]


@pytest.mark.asyncio
async def test_mcp_browser_tools_can_read_local_fixture_page() -> None:
    """navigates to a local fixture page and reads page text through MCP tools."""

    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            navigate = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/"}
            )
            _skip_if_browser_unavailable(navigate)
            assert "Successfully navigated" in navigate

            text = await _execute_tool_text(
                server, "element_get_text", {"selector": "#app"}
            )
            _skip_if_browser_unavailable(text)
            assert "DrissionMCP Fixture" in text

            frame = await _execute_tool_text(
                server,
                "element_get_attribute",
                {"selector": "#fixture-frame", "attribute": "src"},
            )
            _skip_if_browser_unavailable(frame)
            assert "/iframe" in frame

            form_nav = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/form"}
            )
            _skip_if_browser_unavailable(form_nav)
            assert "Successfully navigated" in form_nav

            typed = await _execute_tool_text(
                server,
                "element_type",
                {"selector": "#name", "text": "Ada", "clear": True},
            )
            _skip_if_browser_unavailable(typed)
            assert "Successfully typed" in typed

            value = await _execute_tool_text(
                server,
                "element_get_property",
                {"selector": "#name", "property_name": "value"},
            )
            _skip_if_browser_unavailable(value)
            assert "Ada" in value

            screenshot, screenshot_payload = await _execute_tool(
                server, "page_screenshot", {}
            )
            text_content = "\n".join(
                item.text for item in screenshot if item.type == "text"
            )
            _skip_if_browser_unavailable(text_content)
            images = [item for item in screenshot if item.type == "image"]
            assert images
            assert base64.b64decode(images[0].data).startswith(b"\x89PNG")
            metadata = screenshot_payload["data"]["screenshot"]
            assert metadata["mime_type"] == "image/png"
            assert metadata["inline"] is True
            assert metadata["encoding"] == "base64"
            assert metadata["full_page"] is False
            assert metadata["bytes"] > 0
            assert metadata["width"] > 0
            assert metadata["height"] > 0

            closed = await _execute_tool_text(server, "page_close", {})
            assert "Successfully closed browser" in closed
    finally:
        await server.cleanup()


@pytest.mark.asyncio
async def test_mcp_browser_tools_normalize_llm_friendly_selectors() -> None:
    """treats bare selectors as CSS and preserves explicit DrissionPage locators."""

    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            navigate = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/selectors"}
            )
            _skip_if_browser_unavailable(navigate)
            assert "Successfully navigated" in navigate

            _content, h1_payload = await _execute_tool(
                server, "element_find", {"selector": "h1", "timeout": 2}
            )
            assert h1_payload["ok"] is True
            h1 = h1_payload["data"]["element"]
            assert h1["tag"] == "h1"
            assert h1["locator"] == "css:h1"
            assert h1["selector_strategy"] == "css"
            assert h1["selector_normalized"] is True

            _content, input_payload = await _execute_tool(
                server,
                "element_find",
                {"selector": "input[name='custname']", "timeout": 2},
            )
            assert input_payload["ok"] is True
            input_element = input_payload["data"]["element"]
            assert input_element["tag"] == "input"
            assert input_element["locator"] == "css:input[name='custname']"

            _content, explicit_payload = await _execute_tool(
                server, "element_find", {"selector": "tag:h1", "timeout": 2}
            )
            assert explicit_payload["ok"] is True
            explicit = explicit_payload["data"]["element"]
            assert explicit["tag"] == "h1"
            assert explicit["locator"] == "tag:h1"
            assert explicit["selector_normalized"] is False
    finally:
        await server.cleanup()


async def _execute_tool_text(
    server: DrissionPageMCPServer, name: str, arguments: Dict[str, Any]
) -> str:
    content = await _execute_tool_content(server, name, arguments)
    return "\n".join(item.text for item in content if item.type == "text")


async def _execute_tool_content(
    server: DrissionPageMCPServer, name: str, arguments: Dict[str, Any]
) -> List[Any]:
    content, _payload = await _execute_tool(server, name, arguments)
    return content


async def _execute_tool(
    server: DrissionPageMCPServer, name: str, arguments: Dict[str, Any]
) -> Tuple[List[Any], Dict[str, Any]]:
    tool = server.tools[name]
    if server.context is None:
        from drissionpage_mcp.context import DrissionPageContext

        server.context = DrissionPageContext()
    response = ToolResponse()
    validated = tool.input_schema.model_validate(arguments)
    await tool.execute(server.context, validated, response)
    return list(response.get_content()), response.get_structured_content()


def _read(url: str) -> Tuple[int, str]:
    try:
        response = urlopen(url, timeout=5)  # noqa: S310 - local fixture URL only
        return response.status, response.read().decode("utf-8")
    except Exception as exc:
        status = getattr(getattr(exc, "fp", None), "status", None) or getattr(
            exc, "code", None
        )
        body = ""
        if getattr(exc, "fp", None) is not None:
            body = exc.fp.read().decode("utf-8")
        if status is not None:
            return int(status), body
        raise


def _skip_if_browser_unavailable(text: str) -> None:
    lowered = text.lower()
    if "### Error" in text and any(
        marker in lowered for marker in _BROWSER_UNAVAILABLE_MARKERS
    ):
        pytest.skip(
            "Chrome/Chromium browser unavailable for DrissionPage integration: {0}".format(
                text[:300]
            )
        )
