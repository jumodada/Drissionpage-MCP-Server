"""Test MCP server functionality."""

from unittest.mock import Mock
import pytest
from mcp.types import CallToolResult
from pydantic import BaseModel
import drissionpage_mcp.server as server_module
from drissionpage_mcp import __version__
from drissionpage_mcp.tools.base import JSON_RESULT_SENTINEL
from drissionpage_mcp.server import DrissionPageMCPServer, _tool_supports_output_schema
from drissionpage_mcp.tools import get_all_tools
from drissionpage_mcp.tools.base import ToolSpec, ToolType


class TestDrissionPageMCPServer:
    """Test MCP server."""

    def test_server_initialization(self):
        """Test server can be initialized."""
        server = DrissionPageMCPServer()
        assert server.name == "DrissionPage MCP"
        assert server.version == __version__
        assert server.context is None
        assert server.server.instructions
        assert "DrissionPage>=4.1.1.4,<5" in server.server.instructions
        assert "page_snapshot" in server.server.instructions
        assert "form_fill_preview" in server.server.instructions
        assert "network_listen_start" in server.server.instructions
        assert "page_click_xy" in server.server.instructions
        assert "viewport CSS coordinates" in server.server.instructions
        assert "full_page=false" in server.server.instructions
        assert "natural is the default" in server.server.instructions
        assert "stale coordinate actions" in server.server.instructions
        assert "element_input_text" not in server.server.instructions

    def test_server_custom_name_version(self):
        """Test server with custom name and version."""
        server = DrissionPageMCPServer(name="Custom MCP", version="1.0.0")
        assert server.name == "Custom MCP"
        assert server.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_cleanup(self):
        """Test server cleanup."""
        server = DrissionPageMCPServer()
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
        assert "page_navigate" in tool_names
        assert "page_go_back" in tool_names
        assert "page_go_forward" in tool_names
        assert "page_refresh" in tool_names
        assert "tab_list" in tool_names
        assert "tab_switch" in tool_names
        assert "tab_close" in tool_names
        assert "page_resize" in tool_names
        assert "page_screenshot" in tool_names
        assert "page_screenshot_save" in tool_names
        assert "page_snapshot" in tool_names
        assert "page_observe" in tool_names
        assert "page_console_logs" in tool_names
        assert "page_evaluate" in tool_names
        assert "page_pointer_move" in tool_names
        assert "page_pointer_drag" in tool_names
        assert "page_detect_challenges" in tool_names
        assert "page_click_xy_batch" in tool_names
        assert "page_wait_challenge_result" in tool_names
        assert "page_click_xy" in tool_names
        assert "page_close" in tool_names
        assert "page_get_url" in tool_names
        assert "element_find" in tool_names
        assert "element_find_all" in tool_names
        assert "element_click" in tool_names
        assert "element_type" in tool_names
        assert "element_upload_file" in tool_names
        assert "element_scroll_into_view" in tool_names
        assert "element_hover" in tool_names
        assert "element_select" in tool_names
        assert "element_check" in tool_names
        assert "element_input_text" not in tool_names
        assert "element_get_text" in tool_names
        assert "element_get_attribute" in tool_names
        assert "element_get_property" in tool_names
        assert "element_get_html" in tool_names
        assert "page_scroll" in tool_names
        assert "keyboard_press" in tool_names
        assert "frame_list" in tool_names
        assert "frame_snapshot" in tool_names
        assert "frame_find" in tool_names
        assert "shadow_find" in tool_names
        assert "shadow_find_all" in tool_names
        assert "browser_cookies_get" in tool_names
        assert "storage_get" in tool_names
        assert "storage_set" in tool_names
        assert "storage_clear" in tool_names
        assert "form_inspect" in tool_names
        assert "browser_open_and_snapshot" in tool_names
        assert "browser_extract_links" in tool_names
        assert "form_fill_preview" in tool_names
        assert "network_listen_start" in tool_names
        assert "network_listen_wait" in tool_names
        assert "network_listen_stop" in tool_names
        assert "wait_for_element" in tool_names
        assert "wait_for_url" in tool_names
        assert "wait_time" in tool_names
        assert "wait_until" in tool_names
        assert "wait_sleep" not in tool_names
        assert len(tool_names) == 57


if __name__ == "__main__":
    pytest.main([__file__])


class TestCallToolResultContract:
    """Test server call result shape."""

    def test_call_result_has_structured_content_and_text_mirror(self):
        server = DrissionPageMCPServer()
        from drissionpage_mcp.tools.base import ToolOutcome

        response = ToolOutcome()
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
    history = server.context.action_history()
    assert history["count"] == 1
    assert history["actions"][0]["tool"] == "wait_time"
    assert history["actions"][0]["result"]["ok"] is True


@pytest.mark.asyncio
async def test_internal_call_tool_impl_redacts_history_arguments() -> None:
    server = DrissionPageMCPServer()
    result = await server._call_tool_impl(
        "element_type", {"selector": "#password", "text": "secret", "timeout": 0}
    )
    assert result.isError is True
    assert server.context is not None
    action = server.context.action_history()["actions"][0]
    assert action["tool"] == "element_type"
    assert action["args"]["text"] == "<redacted>"


@pytest.mark.asyncio
async def test_internal_call_tool_impl_converts_unexpected_exceptions() -> None:

    class EmptyArgs(BaseModel):
        pass

    async def boom(_context, _args):
        raise RuntimeError("browser launch failed")

    server = DrissionPageMCPServer()
    from drissionpage_mcp.tool_outputs import PageCloseData

    server.tools["boom"] = ToolSpec(
        name="boom",
        title="Boom",
        description="Raise for tests",
        input_model=EmptyArgs,
        output_model=PageCloseData,
        handler=boom,
        tool_type=ToolType.READ_ONLY,
    )
    result = await server._call_tool_impl("boom", {})
    assert result.isError is True
    assert result.structuredContent["error"]["code"] == "BROWSER_START_FAILED"
    assert result.structuredContent["error"]["details"]["tool_name"] == "boom"
    assert any(
        (
            hint.get("command") == "drissionpage-mcp doctor --launch-browser"
            for hint in result.structuredContent["error"]["details"]["hints"]
        )
    )


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
    server.server = FakeLowLevelServer()
    with pytest.raises(RuntimeError, match="stdio failed"):
        await server.run_server(object(), object())
    assert context.cleaned is True
    assert server.context is None


def test_tool_supports_output_schema_signature_fallback(monkeypatch) -> None:

    def fake_tool(*, outputSchema=None):
        return outputSchema

    monkeypatch.setattr(server_module, "Tool", fake_tool)
    assert _tool_supports_output_schema() is True

    def fail_signature(_obj):
        raise ValueError("not inspectable")

    monkeypatch.setattr(server_module.inspect, "signature", fail_signature)
    assert _tool_supports_output_schema() is False
