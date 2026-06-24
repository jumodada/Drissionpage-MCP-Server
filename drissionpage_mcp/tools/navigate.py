"""Navigation tools for DrissionPage MCP."""

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from .base import ToolType, define_tool, tool_errors

if TYPE_CHECKING:
    from ..context import DrissionPageContext
    from ..response import ToolResponse


class NavigateInput(BaseModel):
    """Input schema for navigate tool."""

    url: str = Field(..., description="The URL to navigate to")


class EmptyInput(BaseModel):
    """Empty input schema for tools that don't require parameters."""

    pass


@define_tool(
    name="page_navigate",
    title="Navigate to URL",
    description="Navigate to a specific URL in the browser",
    input_schema=NavigateInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def navigate(
    context: "DrissionPageContext", args: NavigateInput, response: "ToolResponse"
) -> None:
    """Navigate to a URL."""
    async with tool_errors(
        response, lambda e: f"Failed to navigate to {args.url}: {e}"
    ):
        tab = await context.ensure_tab()
        await tab.navigate(args.url)

        response.add_code(f"page.get({args.url!r})")
        response.add_result(f"Successfully navigated to: {args.url}")
        response.set_include_snapshot(True)


@define_tool(
    name="page_go_back",
    title="Go Back",
    description="Go back to the previous page in browser history",
    input_schema=EmptyInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def go_back(
    context: "DrissionPageContext", args: EmptyInput, response: "ToolResponse"
) -> None:
    """Go back to the previous page."""
    async with tool_errors(response, "Failed to go back"):
        tab = context.current_tab_or_die()
        await tab.go_back()

        response.add_code("page.back()")
        response.add_result("Successfully went back to previous page")
        response.set_include_snapshot(True)


@define_tool(
    name="page_go_forward",
    title="Go Forward",
    description="Go forward to the next page in browser history",
    input_schema=EmptyInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def go_forward(
    context: "DrissionPageContext", args: EmptyInput, response: "ToolResponse"
) -> None:
    """Go forward to the next page."""
    async with tool_errors(response, "Failed to go forward"):
        tab = context.current_tab_or_die()
        await tab.go_forward()

        response.add_code("page.forward()")
        response.add_result("Successfully went forward to next page")
        response.set_include_snapshot(True)


@define_tool(
    name="page_refresh",
    title="Refresh Page",
    description="Refresh the current page",
    input_schema=EmptyInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def refresh(
    context: "DrissionPageContext", args: EmptyInput, response: "ToolResponse"
) -> None:
    """Refresh the current page."""
    async with tool_errors(response, "Failed to refresh page"):
        tab = context.current_tab_or_die()
        await tab.refresh()

        response.add_code("page.refresh()")
        response.add_result("Successfully refreshed page")
        response.set_include_snapshot(True)


# Export all tools
tools = [navigate, go_back, go_forward, refresh]


class NavigateTools:
    """Backward-compatible facade for older tests/integrations."""

    @staticmethod
    def get_tools():
        return tools

    _navigate = staticmethod(navigate.handler)
