"""Navigation tools for DrissionPage MCP."""

from typing import TYPE_CHECKING
from pydantic import Field
from ..policy import PolicyDeniedError, validate_navigation
from ..response_errors import ErrorCode
from ._observe import maybe_observe, observed_changes
from .base import EmptyInput, ToolInput, ToolType, define_tool, ToolOutcome
from ..tool_outputs import (
    PageNavigateData,
    PageGoBackData,
    PageGoForwardData,
    PageRefreshData,
)

if TYPE_CHECKING:
    from ..context import DrissionPageContext


class NavigateInput(ToolInput):
    """Input schema for navigate tool."""

    url: str = Field(..., description="The URL to navigate to")
    new_tab: bool = Field(
        default=False,
        description="Open the URL in a new browser tab instead of the current tab.",
    )
    observe: bool = Field(
        default=False, description="Return a compact before/after page change summary."
    )


@define_tool(
    name="page_navigate",
    title="Navigate to URL",
    description="Navigate to a specific URL in the browser",
    input_schema=NavigateInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=PageNavigateData,
    failure_message=lambda args, exc: (
        lambda e: f"Failed to navigate to {args.url}: {e}"
    )(exc),
)
async def navigate(
    context: "DrissionPageContext", args: NavigateInput
) -> "ToolOutcome":
    """Navigate to a URL."""
    outcome = ToolOutcome()
    try:
        validate_navigation(args.url)
    except PolicyDeniedError as exc:
        outcome.add_error(
            str(exc), ErrorCode.POLICY_DENIED, rule=exc.rule, value=exc.value
        )
        return outcome
    tab = await context.new_tab() if args.new_tab else await context.ensure_tab()
    before = await maybe_observe(tab, args.observe)
    await tab.navigation.navigate(args.url)
    changes = await observed_changes(tab, before)
    outcome.add_code(f"page.get({args.url!r})")
    data = {
        "url": args.url,
        "final_url": tab.url,
        "new_tab": args.new_tab,
        "tab_id": _safe_tab_id(tab),
    }
    if changes is not None:
        data["changes"] = changes
    outcome.add_result(f"Successfully navigated to: {args.url}", **data)
    outcome.set_include_snapshot(True)
    return outcome


@define_tool(
    name="page_go_back",
    title="Go Back",
    description="Go back to the previous page in browser history",
    input_schema=EmptyInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=PageGoBackData,
    failure_message=lambda args, exc: "Failed to go back: " + str(exc),
)
async def go_back(context: "DrissionPageContext", args: EmptyInput) -> "ToolOutcome":
    """Go back to the previous page."""
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    await tab.navigation.back()
    outcome.add_code("page.back()")
    outcome.add_result("Successfully went back to previous page", url=tab.url)
    outcome.set_include_snapshot(True)
    return outcome


@define_tool(
    name="page_go_forward",
    title="Go Forward",
    description="Go forward to the next page in browser history",
    input_schema=EmptyInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=PageGoForwardData,
    failure_message=lambda args, exc: "Failed to go forward: " + str(exc),
)
async def go_forward(context: "DrissionPageContext", args: EmptyInput) -> "ToolOutcome":
    """Go forward to the next page."""
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    await tab.navigation.forward()
    outcome.add_code("page.forward()")
    outcome.add_result("Successfully went forward to next page", url=tab.url)
    outcome.set_include_snapshot(True)
    return outcome


@define_tool(
    name="page_refresh",
    title="Refresh Page",
    description="Refresh the current page",
    input_schema=EmptyInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=PageRefreshData,
    failure_message=lambda args, exc: "Failed to refresh page: " + str(exc),
)
async def refresh(context: "DrissionPageContext", args: EmptyInput) -> "ToolOutcome":
    """Refresh the current page."""
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    await tab.navigation.refresh()
    outcome.add_code("page.refresh()")
    outcome.add_result("Successfully refreshed page", url=tab.url)
    outcome.set_include_snapshot(True)
    return outcome


def _safe_tab_id(tab) -> str:
    value = getattr(tab, "mcp_tab_id", "")
    return value if isinstance(value, str) else ""
