"""Navigation tools for DrissionPage MCP."""

from typing import TYPE_CHECKING, Any

from pydantic import Field, model_validator

from ..policy import PolicyDeniedError, validate_navigation
from ..response_errors import ErrorCode, classify_error
from ..tool_outputs import (
    PageGoBackData,
    PageGoForwardData,
    PageNavigateData,
    PageRefreshData,
)
from ._observe import maybe_observe, observed_changes
from .base import (
    TabScopedEmptyInput,
    TabScopedInput,
    ToolOutcome,
    ToolType,
    define_tool,
)

if TYPE_CHECKING:
    from ..context import DrissionPageContext


class NavigateInput(TabScopedInput):
    """Input schema for navigate tool."""

    url: str = Field(..., description="The URL to navigate to")
    new_tab: bool = Field(
        default=False,
        description="Open the URL in a new browser tab instead of the current tab.",
    )
    background: bool = Field(
        default=False,
        description=(
            "Create the requested new tab in the background without changing the "
            "MCP current tab. Requires new_tab=true."
        ),
    )
    new_window: bool = Field(
        default=False,
        description="Open the requested new tab in a separate window. Requires new_tab=true.",
    )
    new_context: bool = Field(
        default=False,
        description=(
            "Create the requested new tab in a disposable Chromium browser context. "
            "Closing the tab disposes that context. Requires new_tab=true."
        ),
    )
    observe: bool = Field(
        default=False, description="Return a compact before/after page change summary."
    )
    timeout: float | None = Field(
        default=None,
        gt=0,
        le=300,
        description=(
            "Optional total navigation and stabilization budget in seconds. Browser "
            "startup, tab-lock queueing, and the pre-navigation observation are excluded."
        ),
    )

    @model_validator(mode="after")
    def validate_creation_options(self) -> "NavigateInput":
        if not self.new_tab and any(
            (self.background, self.new_window, self.new_context)
        ):
            raise ValueError(
                "background, new_window, and new_context require new_tab=true"
            )
        if self.new_tab and self.tab_id is not None:
            raise ValueError("tab_id cannot be combined with new_tab=true")
        return self


@define_tool(
    name="page_navigate",
    title="Navigate to URL",
    description="Navigate to a specific URL in the browser",
    input_schema=NavigateInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=PageNavigateData,
    failure_message=lambda args, exc: (
        "Browser failed to start."
        if classify_error(exc, "page_navigate") is ErrorCode.BROWSER_START_FAILED
        else "Page navigation failed."
    ),
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
    tab: Any
    if args.new_tab:
        tab = (
            await context.new_tab(
                background=args.background,
                new_window=args.new_window,
                new_context=args.new_context,
            )
            if any((args.background, args.new_window, args.new_context))
            else await context.new_tab()
        )
    else:
        bound_tab_getter = getattr(type(context), "bound_tab", None)
        tab = (
            bound_tab_getter(context)
            if callable(bound_tab_getter)
            else None
        )
        if tab is None:
            tab = await context.ensure_tab()
    if args.new_tab:
        action = getattr(tab, "action", None)
        if callable(action):
            async with action():
                data = await _navigate_and_build_result(context, tab, args)
        else:
            data = await _navigate_and_build_result(context, tab, args)
    else:
        data = await _navigate_and_build_result(context, tab, args)
    outcome.add_result(f"Successfully navigated to: {args.url}", **data)
    return outcome


async def _navigate_and_build_result(
    context: "DrissionPageContext", tab: Any, args: NavigateInput
) -> dict[str, Any]:
    before = await maybe_observe(tab, args.observe)
    evidence = (
        await tab.navigation.navigate(args.url)
        if args.timeout is None
        else await tab.navigation.navigate(args.url, timeout=args.timeout)
    )
    changes = await observed_changes(tab, before)
    evidence = evidence if isinstance(evidence, dict) else {}
    data = {
        "url": args.url,
        "final_url": tab.url,
        "new_tab": args.new_tab,
        "background": args.background,
        "new_window": args.new_window,
        "new_context": args.new_context,
        "active": _is_active_tab(context, tab, background=args.background),
        "tab_id": _safe_tab_id(tab),
        "ready_state": evidence.get("ready_state", ""),
        "settled": evidence.get("settled", False),
        "navigation_ms": evidence.get("navigation_ms", 0),
        "settle_ms": evidence.get("settle_ms", 0),
        "total_ms": evidence.get("total_ms", 0),
    }
    if changes is not None:
        data["changes"] = changes
    return data


@define_tool(
    name="page_go_back",
    title="Go Back",
    description="Go back to the previous page in browser history",
    input_schema=TabScopedEmptyInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=PageGoBackData,
    failure_message=lambda args, exc: "Failed to go back: " + str(exc),
)
async def go_back(
    context: "DrissionPageContext", args: TabScopedEmptyInput
) -> "ToolOutcome":
    """Go back to the previous page."""
    tab = context.current_tab_or_die()
    await tab.navigation.back()
    return ToolOutcome().add_result("Successfully went back to previous page", url=tab.url)


@define_tool(
    name="page_go_forward",
    title="Go Forward",
    description="Go forward to the next page in browser history",
    input_schema=TabScopedEmptyInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=PageGoForwardData,
    failure_message=lambda args, exc: "Failed to go forward: " + str(exc),
)
async def go_forward(
    context: "DrissionPageContext", args: TabScopedEmptyInput
) -> "ToolOutcome":
    """Go forward to the next page."""
    tab = context.current_tab_or_die()
    await tab.navigation.forward()
    return ToolOutcome().add_result("Successfully went forward to next page", url=tab.url)


@define_tool(
    name="page_refresh",
    title="Refresh Page",
    description="Refresh the current page",
    input_schema=TabScopedEmptyInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=PageRefreshData,
    failure_message=lambda args, exc: "Failed to refresh page: " + str(exc),
)
async def refresh(
    context: "DrissionPageContext", args: TabScopedEmptyInput
) -> "ToolOutcome":
    """Refresh the current page."""
    tab = context.current_tab_or_die()
    await tab.navigation.refresh()
    return ToolOutcome().add_result("Successfully refreshed page", url=tab.url)


def _safe_tab_id(tab) -> str:
    value = getattr(tab, "mcp_tab_id", "")
    return value if isinstance(value, str) else ""


def _is_active_tab(context: "DrissionPageContext", tab: Any, *, background: bool) -> bool:
    current_tab = getattr(context, "current_tab", None)
    if callable(current_tab):
        return current_tab() is tab
    return not background
