"""MCP protocol smoke coverage without external network access."""

from __future__ import annotations

import json
import re
from typing import Any, Dict

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolRequest, CallToolRequestParams, ListToolsRequest

from drissionpage_mcp.server import DrissionPageMCPServer


@pytest.mark.asyncio
async def test_list_tools_handler_returns_current_mcp_tools_with_annotations() -> None:
    """lists all current tools through the MCP Server request handler."""

    server = DrissionPageMCPServer()
    handler = server.server.request_handlers[ListToolsRequest]

    result = await handler(ListToolsRequest(method="tools/list"))

    tools = result.root.tools
    assert len(tools) == 19
    assert "element_input_text" not in {tool.name for tool in tools}
    assert "wait_sleep" not in {tool.name for tool in tools}
    assert {tool.name for tool in tools} >= {
        "page_navigate",
        "element_get_text",
        "wait_time",
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

            tools = await session.list_tools()
            assert len(tools.tools) == 19
            assert {tool.name for tool in tools.tools} >= {
                "page_get_url",
                "page_navigate",
            }
            assert "element_input_text" not in {tool.name for tool in tools.tools}
            assert "wait_sleep" not in {tool.name for tool in tools.tools}

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
