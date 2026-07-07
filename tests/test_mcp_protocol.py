"""MCP protocol smoke coverage without external network access."""

from __future__ import annotations

import json
import re
from typing import Any, Dict

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolRequest, CallToolRequestParams, ListToolsRequest

import drissionpage_mcp
from drissionpage_mcp.server import DrissionPageMCPServer


@pytest.mark.asyncio
async def test_list_tools_handler_returns_current_mcp_tools_with_annotations() -> None:
    """lists all current tools through the MCP Server request handler."""

    server = DrissionPageMCPServer()
    handler = server.server.request_handlers[ListToolsRequest]

    result = await handler(ListToolsRequest(method="tools/list"))

    tools = result.root.tools
    assert len(tools) == 52
    assert "element_input_text" not in {tool.name for tool in tools}
    assert "wait_sleep" not in {tool.name for tool in tools}
    assert {tool.name for tool in tools} >= {
        "page_navigate",
        "page_screenshot_save",
        "page_observe",
        "page_console_logs",
        "page_evaluate",
        "page_snapshot",
        "tab_list",
        "tab_switch",
        "tab_close",
        "element_find_all",
        "form_inspect",
        "element_get_text",
        "wait_until",
        "wait_time",
        "element_upload_file",
        "page_scroll",
        "element_hover",
        "element_select",
        "frame_list",
        "frame_snapshot",
        "shadow_find",
        "browser_cookies_get",
        "storage_get",
        "browser_open_and_snapshot",
        "browser_extract_links",
        "form_fill_preview",
        "network_listen_start",
        "network_listen_wait",
        "network_listen_stop",
    }
    for tool in tools:
        assert tool.description
        assert tool.inputSchema["type"] == "object"
        assert tool.annotations is not None
        assert tool.annotations.title == tool.title
        assert tool.annotations.openWorldHint is True
        assert isinstance(tool.annotations.readOnlyHint, bool)
        assert isinstance(tool.annotations.destructiveHint, bool)
        assert isinstance(tool.annotations.idempotentHint, bool)


@pytest.mark.asyncio
async def test_call_tool_handler_returns_validation_error_for_missing_required_arguments() -> (
    None
):
    """returns a text error when MCP call arguments fail schema validation."""

    server = DrissionPageMCPServer()
    handler = server.server.request_handlers[CallToolRequest]

    result = await handler(_call_tool_request("page_navigate", {}))

    assert result.root.isError is True
    assert result.root.content[0].type == "text"
    assert result.root.content[0].text.startswith("### JSON_RESULT")
    assert result.root.structuredContent["ok"] is False
    assert result.root.structuredContent["error"]["code"] == "MCP_ARGUMENT_INVALID"
    assert "Input validation error" in result.root.structuredContent["message"]
    assert "url" in result.root.structuredContent["message"]


@pytest.mark.asyncio
async def test_call_tool_handler_rejects_unknown_arguments_before_browser_startup() -> (
    None
):
    """returns schema errors for typos instead of silently ignoring extra fields."""

    server = DrissionPageMCPServer()
    handler = server.server.request_handlers[CallToolRequest]

    result = await handler(_call_tool_request("page_screenshot", {"fullPage": True}))

    assert server.context is not None
    assert server.context.is_active() is False
    assert result.root.isError is True
    assert result.root.structuredContent["error"]["code"] == "MCP_ARGUMENT_INVALID"
    assert "fullPage" in result.root.structuredContent["message"]
    assert (
        result.root.structuredContent["error"]["details"]["hints"][0]["action"]
        == "check_input_schema"
    )


@pytest.mark.asyncio
async def test_call_tool_handler_reports_unknown_tool_without_browser_startup() -> None:
    """returns a deterministic not-found response for unknown tool names."""

    server = DrissionPageMCPServer()
    handler = server.server.request_handlers[CallToolRequest]

    result = await handler(_call_tool_request("not_a_tool", {}))

    assert result.root.content[0].type == "text"
    text = result.root.content[0].text
    assert result.root.isError is True
    assert text.startswith("### JSON_RESULT")
    payload = json.loads(re.search(r"```json\n(.*?)\n```", text, re.S).group(1))
    assert payload["ok"] is False
    assert payload["error"]["code"] == "TOOL_NOT_FOUND"
    assert payload["message"] == "Tool 'not_a_tool' not found"
    assert (
        payload["error"]["details"]["hints"][0]["action"] == "list_available_tools"
    )


@pytest.mark.asyncio
async def test_removed_alias_tools_return_actionable_tool_not_found() -> None:
    server = DrissionPageMCPServer()
    handler = server.server.request_handlers[CallToolRequest]

    result = await handler(_call_tool_request("element_input_text", {}))

    assert result.root.isError is True
    assert result.root.structuredContent["error"]["code"] == "TOOL_NOT_FOUND"
    assert result.root.structuredContent["error"]["details"]["suggested_tool"] == (
        "element_type"
    )
    assert "Use 'element_type' instead" in result.root.structuredContent["message"]


def _call_tool_request(name: str, arguments: Dict[str, Any]) -> CallToolRequest:
    return CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name=name, arguments=arguments),
    )


@pytest.mark.asyncio
async def test_stdio_client_initialize_list_and_call_tool() -> None:
    """smokes the real stdio MCP client path without external network access."""

    params = StdioServerParameters(
        command="python",
        args=["-m", "drissionpage_mcp.cli", "--log-level", "ERROR"],
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            init = await session.initialize()
            assert init.serverInfo.name == "DrissionPage MCP"
            assert init.serverInfo.version == drissionpage_mcp.__version__

            tools = await session.list_tools()
            assert len(tools.tools) == 52
            assert {tool.name for tool in tools.tools} >= {
                "page_get_url",
                "page_navigate",
                "page_screenshot_save",
                "page_observe",
                "page_console_logs",
                "page_evaluate",
                "page_snapshot",
                "tab_list",
                "element_find_all",
                "form_inspect",
                "wait_until",
                "element_upload_file",
                "frame_list",
                "shadow_find",
                "storage_get",
                "browser_open_and_snapshot",
                "browser_extract_links",
                "form_fill_preview",
                "network_listen_start",
                "network_listen_wait",
                "network_listen_stop",
            }
            assert "element_input_text" not in {tool.name for tool in tools.tools}
            assert "wait_sleep" not in {tool.name for tool in tools.tools}

            wait_result = await session.call_tool("wait_time", {"seconds": 0})
            assert wait_result.isError is not True
            assert wait_result.structuredContent["ok"] is True
            assert wait_result.structuredContent["data"]["waited_seconds"] == 0

            result = await session.call_tool("not_a_tool", {})
            assert result.isError is True
            assert result.structuredContent["error"]["code"] == "TOOL_NOT_FOUND"
            assert result.content[0].text.startswith("### JSON_RESULT")


@pytest.mark.asyncio
async def test_list_tools_exposes_shared_output_schema_when_supported() -> None:
    """exposes the stable typed ToolResult envelope through MCP outputSchema."""

    server = DrissionPageMCPServer()
    handler = server.server.request_handlers[ListToolsRequest]

    result = await handler(ListToolsRequest(method="tools/list"))

    schemas = {tool.name: tool.outputSchema for tool in result.root.tools}
    for tool in result.root.tools:
        if getattr(tool, "outputSchema", None) is None:
            pytest.skip("Installed MCP SDK Tool model does not expose outputSchema")
        schema = tool.outputSchema
        assert schema["type"] == "object"
        assert schema["oneOf"][0]["required"] == ["ok", "message", "data"]
        assert schema["oneOf"][0]["properties"]["ok"]["const"] is True
        assert schema["oneOf"][1]["required"] == ["ok", "message", "error"]
        assert schema["oneOf"][1]["properties"]["ok"]["const"] is False
        assert schema["oneOf"][1]["properties"]["error"]["required"] == [
            "code",
            "message",
        ]

    assert schemas["page_navigate"]["oneOf"][0]["properties"]["data"]["title"] == (
        "PageNavigateData"
    )
    assert "final_url" in schemas["page_navigate"]["oneOf"][0]["properties"]["data"][
        "properties"
    ]
    assert schemas["element_find"]["oneOf"][0]["properties"]["data"]["title"] == (
        "ElementFindData"
    )
    assert "element" in schemas["element_find"]["oneOf"][0]["properties"]["data"][
        "required"
    ]
    assert schemas["wait_time"]["oneOf"][0]["properties"]["data"]["title"] == (
        "WaitTimeData"
    )
    assert schemas["page_snapshot"]["oneOf"][0]["properties"]["data"]["title"] == (
        "PageSnapshotData"
    )
    assert "links" in schemas["page_snapshot"]["oneOf"][0]["properties"]["data"][
        "properties"
    ]
    assert schemas["element_find_all"]["oneOf"][0]["properties"]["data"]["title"] == (
        "ElementFindAllData"
    )
    assert "elements" in schemas["element_find_all"]["oneOf"][0]["properties"]["data"][
        "required"
    ]
    assert schemas["form_inspect"]["oneOf"][0]["properties"]["data"]["title"] == (
        "FormInspectData"
    )
    assert "forms" in schemas["form_inspect"]["oneOf"][0]["properties"]["data"][
        "required"
    ]
    assert schemas["element_upload_file"]["oneOf"][0]["properties"]["data"]["title"] == (
        "ElementUploadFileData"
    )
    assert schemas["frame_snapshot"]["oneOf"][0]["properties"]["data"]["title"] == (
        "FrameSnapshotData"
    )
    assert schemas["storage_get"]["oneOf"][0]["properties"]["data"]["title"] == (
        "StorageGetData"
    )
    assert schemas["browser_open_and_snapshot"]["oneOf"][0]["properties"]["data"]["title"] == (
        "BrowserOpenAndSnapshotData"
    )
    assert schemas["browser_extract_links"]["oneOf"][0]["properties"]["data"]["title"] == (
        "BrowserExtractLinksData"
    )
    assert schemas["form_fill_preview"]["oneOf"][0]["properties"]["data"]["title"] == (
        "FormFillPreviewData"
    )
    assert schemas["network_listen_wait"]["oneOf"][0]["properties"]["data"]["title"] == (
        "NetworkListenWaitData"
    )
