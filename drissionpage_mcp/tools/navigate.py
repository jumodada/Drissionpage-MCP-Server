"""Navigation tools for DrissionPage MCP."""

from typing import TYPE_CHECKING

from pydantic import Field

from ..policy import PolicyDeniedError, validate_navigation
from ..response import ErrorCode
from ._observe import maybe_observe, observed_changes
from .base import EmptyInput, ToolInput, ToolType, define_tool, tool_errors

if TYPE_CHECKING:
    from ..context import DrissionPageContext
    from ..response import ToolResponse


class NavigateInput(ToolInput):
    """Input schema for navigate tool."""

    url: str = Field(..., description="The URL to navigate to")
    new_tab: bool = Field(
        default=False,
        description="Open the URL in a new browser tab instead of the current tab.",
    )
    observe: bool = Field(
        default=False,
        description="Return a compact before/after page change summary.",
    )


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
    try:
        validate_navigation(args.url)
    except PolicyDeniedError as exc:
        response.add_error(
            str(exc),
            ErrorCode.POLICY_DENIED,
            rule=exc.rule,
            value=exc.value,
        )
        return

    async with tool_errors(
        response, lambda e: f"Failed to navigate to {args.url}: {e}"
    ):
        tab = await context.new_tab() if args.new_tab else await context.ensure_tab()
        before = await maybe_observe(tab, args.observe)
        await tab.navigation.navigate(args.url)
        changes = await observed_changes(tab, before)

        response.add_code(f"page.get({args.url!r})")
        data = {
            "url": args.url,
            "final_url": tab.url,
            "new_tab": args.new_tab,
            "tab_id": _safe_tab_id(tab),
        }
        if changes is not None:
            data["changes"] = changes
        response.add_result(f"Successfully navigated to: {args.url}", **data)
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
        await tab.navigation.back()

        response.add_code("page.back()")
        response.add_result("Successfully went back to previous page", url=tab.url)
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
        await tab.navigation.forward()

        response.add_code("page.forward()")
        response.add_result("Successfully went forward to next page", url=tab.url)
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
        await tab.navigation.refresh()

        response.add_code("page.refresh()")
        response.add_result("Successfully refreshed page", url=tab.url)
        response.set_include_snapshot(True)


# Export all tools
tools = [navigate, go_back, go_forward, refresh]


def _safe_tab_id(tab) -> str:
    value = getattr(tab, "mcp_tab_id", "")
    return value if isinstance(value, str) else ""
