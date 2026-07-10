"""Test tools functionality."""

from unittest.mock import AsyncMock, Mock
import pytest
from drissionpage_mcp.context import DrissionPageContext
from drissionpage_mcp.response_errors import ErrorCode
from drissionpage_mcp.tools.base import JSON_RESULT_SENTINEL, ToolOutcome
from drissionpage_mcp.tools import get_all_tools
from drissionpage_mcp.tools.navigate import NavigateInput, navigate


class TestNavigationTools:
    """Test navigation tools."""

    @pytest.mark.asyncio
    async def test_get_all_tools(self):
        """Test that we can get all tools."""
        tools = get_all_tools()
        assert len(tools) > 0
        tool_names = [tool.name for tool in tools]
        assert "page_navigate" in tool_names
        assert "element_click" in tool_names
        assert "wait_for_element" in tool_names

    @pytest.mark.asyncio
    async def test_navigate_tool_definition(self):
        """Test navigate tool definition."""
        navigate_tool = navigate
        assert navigate_tool.name == "page_navigate"
        assert "navigate" in navigate_tool.description.lower()
        assert navigate_tool.input_schema == NavigateInput

    @pytest.mark.asyncio
    async def test_navigate_input_validation(self):
        """Test navigate input validation."""
        valid_input = NavigateInput(url="https://example.com")
        assert valid_input.url == "https://example.com"
        with pytest.raises(Exception):
            NavigateInput()

    @pytest.mark.asyncio
    async def test_navigate_execution_mock(self):
        """Test navigate tool execution with mocked DrissionPage."""
        mock_context = Mock(spec=DrissionPageContext)
        mock_tab = Mock()
        mock_tab.url = "https://example.com"
        mock_tab.navigation = Mock()
        mock_tab.navigation.navigate = AsyncMock(return_value=None)
        mock_context.ensure_tab = AsyncMock(return_value=mock_tab)
        response = ToolOutcome()
        input_data = NavigateInput(url="https://example.com")
        response = await navigate.execute(mock_context, input_data)
        mock_context.ensure_tab.assert_called_once()
        mock_tab.navigation.navigate.assert_called_once_with("https://example.com")
        content = response.content()
        assert len(content) > 0
        assert any(
            (
                "successfully navigated" in str(content_item).lower()
                for content_item in content
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments", "expected_message", "expected_code"),
    [
        (
            "page_resize",
            {"width": 800, "height": 600},
            "Failed to resize window",
            "BROWSER_NOT_INITIALIZED",
        ),
        ("page_get_url", {}, "Failed to get URL", "BROWSER_NOT_INITIALIZED"),
        ("element_get_text", {}, "Failed to get text", "BROWSER_NOT_INITIALIZED"),
        (
            "wait_for_element",
            {"selector": "#missing", "timeout": 1},
            "did not appear",
            "BROWSER_NOT_INITIALIZED",
        ),
    ],
)
async def test_tool_handlers_convert_exceptions_to_structured_errors(
    tool_name, arguments, expected_message, expected_code
):
    """Tool handlers keep failures in ToolOutcome instead of leaking exceptions."""
    tool = next((tool for tool in get_all_tools() if tool.name == tool_name))
    response = ToolOutcome()
    response = await tool.execute(
        DrissionPageContext(), tool.input_schema.model_validate(arguments)
    )
    payload = response.structured_content()
    assert response.is_error
    assert payload["ok"] is False
    assert payload["error"]["code"] == expected_code
    assert expected_message in payload["message"]


class TestToolOutcome:
    """Test ToolOutcome functionality."""

    def test_add_text(self):
        """Test adding text to response."""
        response = ToolOutcome()
        response.add_text("Test message")
        content = response.content()
        assert len(content) == 2
        assert content[0].type == "text"
        assert JSON_RESULT_SENTINEL in content[0].text
        assert "Test message" in content[1].text

    def test_add_error(self):
        """Test adding error to response."""
        response = ToolOutcome()
        response.add_error("Test error")
        content = response.content()
        assert len(content) == 2
        assert content[0].type == "text"
        assert JSON_RESULT_SENTINEL in content[0].text
        assert "UNKNOWN_ERROR" in content[0].text
        assert "Error" in content[1].text
        assert "Test error" in content[1].text
        assert response.is_error

    def test_add_code(self):
        """Test adding code to response."""
        response = ToolOutcome()
        response.add_code("print('hello')")
        content = response.content()
        assert len(content) == 2
        assert JSON_RESULT_SENTINEL in content[0].text
        assert "```python" in content[1].text
        assert "print('hello')" in content[1].text

    def test_empty_response(self):
        """Test empty response gets default content."""
        response = ToolOutcome()
        content = response.content()
        assert len(content) == 2
        assert JSON_RESULT_SENTINEL in content[0].text
        assert "operation completed successfully" in content[0].text.lower()
        assert "operation completed successfully" in content[1].text.lower()


if __name__ == "__main__":
    pytest.main([__file__])


class TestToolResultContract:
    """Test stable machine-readable tool result contract."""

    def test_structured_success_payload(self):
        response = ToolOutcome()
        response.add_result("ok", value=1)
        payload = response.structured_content()
        assert payload == {"ok": True, "message": "ok", "data": {"value": 1}}
        assert response.content()[0].text.startswith(JSON_RESULT_SENTINEL)

    def test_structured_error_payload(self):
        response = ToolOutcome()
        response.add_error("missing", ErrorCode.ELEMENT_NOT_FOUND, selector="#nope")
        payload = response.structured_content()
        assert payload["ok"] is False
        assert payload["error"]["code"] == "ELEMENT_NOT_FOUND"
        assert payload["error"]["details"]["selector"] == "#nope"


def test_tool_core_has_single_typed_registry_without_legacy_surfaces() -> None:
    """Keep future features on ToolSpec/ToolOutcome instead of rebuilding adapters."""

    import ast
    import re
    from pathlib import Path

    from drissionpage_mcp.tools import ALL_TOOLS
    from drissionpage_mcp.tools.base import ToolOutcome, ToolSpec

    assert len(ALL_TOOLS) == 52
    assert len({tool.name for tool in ALL_TOOLS}) == 52
    assert all(isinstance(tool, ToolSpec) for tool in ALL_TOOLS)
    assert all(tool.output_model is not None for tool in ALL_TOOLS)

    forbidden = {"ToolResponse", "ToolSchema", "tool_errors", "TOOL_DATA_SCHEMAS"}
    production = Path("drissionpage_mcp")
    for path in production.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        pattern = r"\b(" + "|".join(sorted(forbidden)) + r")\b"
        assert re.search(pattern, source) is None, path

    for path in Path("drissionpage_mcp/tools").glob("*.py"):
        if path.name in {"base.py", "__init__.py", "_observe.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            if not any(
                isinstance(decorator, ast.Call)
                and getattr(decorator.func, "id", None) == "define_tool"
                for decorator in node.decorator_list
            ):
                continue
            assert [argument.arg for argument in node.args.args] == ["context", "args"]

    outcome = ToolOutcome()
    outcome.add_result("ok")
    assert outcome.structured_content() == {"ok": True, "message": "ok", "data": {}}
