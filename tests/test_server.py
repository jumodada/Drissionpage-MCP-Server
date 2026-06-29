"""Test MCP server functionality."""

from unittest.mock import Mock

import pytest
from mcp.types import CallToolResult
from pydantic import BaseModel

import drissionpage_mcp.server as server_module
from drissionpage_mcp import __version__
from drissionpage_mcp.response import JSON_RESULT_SENTINEL
from drissionpage_mcp.server import DrissionPageMCPServer, _tool_supports_output_schema
from drissionpage_mcp.tools import get_all_tools
from drissionpage_mcp.tools.base import Tool, ToolSchema, ToolType


class TestDrissionPageMCPServer:
    """Test MCP server."""

    def test_server_initialization(self):
        """Test server can be initialized."""
        server = DrissionPageMCPServer()
        assert server.name == "DrissionPage MCP"
        assert server.version == __version__
        assert server.context is None

    def test_server_custom_name_version(self):
        """Test server with custom name and version."""
        server = DrissionPageMCPServer(name="Custom MCP", version="1.0.0")
        assert server.name == "Custom MCP"
        assert server.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_cleanup(self):
        """Test server cleanup."""
        server = DrissionPageMCPServer()

        # Mock context
        mock_context = Mock()
        mock_context.cleanup = Mock(return_value=None)
        server.context = mock_context

        await server.cleanup()

        mock_context.cleanup.assert_called_once()
        assert server.context is None


class TestToolsIntegration:
    """Test tools integration."""

    def test_all_tools_have_required_attributes(self):
        """Test that all tools have required attributes."""
        tools = get_all_tools()

        for tool in tools:
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")
            assert hasattr(tool, "input_schema")
            assert hasattr(tool, "handler")

            assert isinstance(tool.name, str)
            assert isinstance(tool.description, str)
            assert len(tool.name) > 0
            assert len(tool.description) > 0

    def test_tool_names_are_unique(self):
        """Test that all tool names are unique."""
        tools = get_all_tools()
        names = [tool.name for tool in tools]

        assert len(names) == len(set(names)), "Tool names should be unique"

    def test_expected_tools_present(self):
        """Test that expected tools are present."""
        tools = get_all_tools()
        tool_names = [tool.name for tool in tools]

        # Navigation tools
        assert "page_navigate" in tool_names
        assert "page_go_back" in tool_names
        assert "page_go_forward" in tool_names
        assert "page_refresh" in tool_names

        # Common tools
        assert "page_resize" in tool_names
        assert "page_screenshot" in tool_names
        assert "page_snapshot" in tool_names
        assert "page_click_xy" in tool_names
        assert "page_close" in tool_names
        assert "page_get_url" in tool_names

        # Element tools
        assert "element_find" in tool_names
        assert "element_find_all" in tool_names
        assert "element_click" in tool_names
        assert "element_type" in tool_names
        assert "element_input_text" not in tool_names
        assert "element_get_text" in tool_names
        assert "element_get_attribute" in tool_names
        assert "element_get_property" in tool_names
        assert "element_get_html" in tool_names

        # Wait tools
        assert "wait_for_element" in tool_names
        assert "wait_for_url" in tool_names
        assert "wait_time" in tool_names
        assert "wait_sleep" not in tool_names
        assert len(tool_names) == 21


if __name__ == "__main__":
    pytest.main([__file__])


class TestCallToolResultContract:
    """Test server call result shape."""

    def test_call_result_has_structured_content_and_text_mirror(self):
        server = DrissionPageMCPServer()
        from drissionpage_mcp.response import ToolResponse

        response = ToolResponse()
        response.add_result("done")
        result = server._call_result(response)

        assert isinstance(result, CallToolResult)
        assert result.structuredContent["ok"] is True
        assert result.content[0].text.startswith(JSON_RESULT_SENTINEL)
        assert result.isError is False


@pytest.mark.asyncio
async def test_internal_call_tool_impl_success_path_uses_context() -> None:
    server = DrissionPageMCPServer()
    result = await server._call_tool_impl("wait_time", {"seconds": 0})

    assert result.isError is False
    assert result.structuredContent == {
        "ok": True,
        "message": "Waited for 0.0 seconds",
        "data": {"waited_seconds": 0.0},
    }
    assert server.context is not None


@pytest.mark.asyncio
async def test_internal_call_tool_impl_converts_unexpected_exceptions() -> None:
    class EmptyArgs(BaseModel):
        pass

    async def boom(_context, _args, _response) -> None:
        raise RuntimeError("browser launch failed")

    server = DrissionPageMCPServer()
    server.tools["boom"] = Tool(
        ToolSchema("boom", "Boom", "Raise for tests", EmptyArgs, ToolType.READ_ONLY),
        boom,
    )

    result = await server._call_tool_impl("boom", {})

    assert result.isError is True
    assert result.structuredContent["error"]["code"] == "BROWSER_START_FAILED"
    assert result.structuredContent["error"]["details"]["tool_name"] == "boom"


@pytest.mark.asyncio
async def test_run_server_cleans_up_after_server_error() -> None:
    class FakeLowLevelServer:
        def get_capabilities(self, **_kwargs):
            return {}

        async def run(self, *_args, **_kwargs) -> None:
            raise RuntimeError("stdio failed")

    class AsyncCleanupContext:
        def __init__(self) -> None:
            self.cleaned = False

        async def cleanup(self) -> None:
            self.cleaned = True

    server = DrissionPageMCPServer()
    context = AsyncCleanupContext()
    server.context = context
    server.server = FakeLowLevelServer()  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="stdio failed"):
        await server.run_server(object(), object())

    assert context.cleaned is True
    assert server.context is None


def test_tool_supports_output_schema_signature_fallback(monkeypatch) -> None:
    def fake_tool(*, outputSchema=None):  # noqa: N803 - mirror MCP field name
        return outputSchema

    monkeypatch.setattr(server_module, "Tool", fake_tool)

    assert _tool_supports_output_schema() is True

    def fail_signature(_obj):
        raise ValueError("not inspectable")

    monkeypatch.setattr(server_module.inspect, "signature", fail_signature)

    assert _tool_supports_output_schema() is False
