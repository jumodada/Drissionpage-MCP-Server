"""Wait operation tools for DrissionPage MCP."""

from typing import TYPE_CHECKING, Literal

from pydantic import Field

from ..limits import MAX_WAIT_SECONDS
from ..selector import normalize_selector
from .base import ToolInput, ToolType, define_tool, tool_errors

if TYPE_CHECKING:
    from ..context import DrissionPageContext
    from ..response import ToolResponse


class WaitElementInput(ToolInput):
    """Input schema for waiting for elements."""

    selector: str = Field(
        ...,
        description=(
            "CSS selector or XPath to wait for. Bare selectors are CSS; "
            "use text:... for text matching or explicit tag:/css:/xpath:/@attr locators."
        ),
    )
    timeout: int = Field(
        default=10,
        ge=0,
        le=MAX_WAIT_SECONDS,
        description="Timeout in seconds",
    )


class WaitTimeInput(ToolInput):
    """Input schema for waiting a specific time."""

    seconds: float = Field(
        ...,
        ge=0,
        le=MAX_WAIT_SECONDS,
        description="Number of seconds to wait",
    )


class WaitUrlInput(ToolInput):
    """Input schema for waiting for URL changes."""

    url_pattern: str = Field(
        ..., description="Substring or pattern expected in the current URL"
    )
    timeout: int = Field(
        default=10,
        ge=0,
        le=MAX_WAIT_SECONDS,
        description="Timeout in seconds",
    )


class WaitUntilInput(ToolInput):
    """Input schema for generalized observable waits."""

    condition: Literal[
        "present",
        "visible",
        "hidden",
        "detached",
        "clickable",
        "stable",
        "text_contains",
        "text_matches",
        "url_contains",
        "url_matches",
    ] = Field(..., description="Condition to wait for")
    selector: str = Field(
        default="",
        description="CSS/XPath/DrissionPage locator for element or text conditions",
    )
    value: str = Field(
        default="",
        description="Expected substring or regular expression for text/URL conditions",
    )
    timeout: float = Field(
        default=10,
        ge=0,
        le=MAX_WAIT_SECONDS,
        description="Timeout in seconds",
    )
    interval: float = Field(
        default=0.1,
        ge=0.01,
        le=5,
        description="Polling interval in seconds",
    )
    stable_ms: int = Field(
        default=300,
        ge=0,
        le=5000,
        description="Element stability window for the stable condition",
    )


@define_tool(
    name="wait_for_element",
    title="Wait for Element",
    description=(
        "Wait for an element to appear on the page. Bare selectors are treated "
        "as CSS; use text:... for text matching."
    ),
    input_schema=WaitElementInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
)
async def wait_for_element(
    context: "DrissionPageContext", args: WaitElementInput, response: "ToolResponse"
) -> None:
    """Wait for an element to appear."""
    async with tool_errors(
        response,
        lambda e: (
            f"Element '{args.selector}' did not appear within "
            f"{args.timeout} seconds: {e}"
        ),
        ):
        tab = context.current_tab_or_die()
        plan = normalize_selector(args.selector)
        found = await tab.wait_for_element(args.selector, timeout=args.timeout)
        if not found:
            raise TimeoutError(f"Element '{args.selector}' not found")

        response.add_code(
            f"page.wait.ele_loaded({plan.locator!r}, timeout={args.timeout!r})"
        )
        response.add_result(
            f"Element '{args.selector}' appeared within {args.timeout} seconds",
            **plan.metadata(),
            found=True,
            timeout=args.timeout,
        )


@define_tool(
    name="wait_for_url",
    title="Wait for URL",
    description="Wait for the current URL to contain a substring",
    input_schema=WaitUrlInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
)
async def wait_for_url(
    context: "DrissionPageContext", args: WaitUrlInput, response: "ToolResponse"
) -> None:
    """Wait for URL to match a pattern."""
    async with tool_errors(
        response,
        lambda e: (
            f"URL did not match '{args.url_pattern}' within "
            f"{args.timeout} seconds: {e}"
        ),
    ):
        tab = context.current_tab_or_die()
        matched = await tab.wait_for_url(args.url_pattern, timeout=args.timeout)
        if not matched:
            raise TimeoutError(f"URL did not contain '{args.url_pattern}'")

        response.add_code(f"# wait until {args.url_pattern!r} in page.url")
        response.add_result(
            f"URL matched '{args.url_pattern}' within {args.timeout} seconds",
            url_pattern=args.url_pattern,
            matched=True,
            url=tab.url,
            timeout=args.timeout,
        )


@define_tool(
    name="wait_time",
    title="Wait Time",
    description="Wait for a specific amount of time",
    input_schema=WaitTimeInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
)
async def wait_time(
    context: "DrissionPageContext", args: WaitTimeInput, response: "ToolResponse"
) -> None:
    """Wait for a specific time."""
    async with tool_errors(response, "Failed to wait"):
        await context.wait(args.seconds)

        response.add_code(f"time.sleep({args.seconds})")
        response.add_result(
            f"Waited for {args.seconds} seconds",
            waited_seconds=args.seconds,
        )


@define_tool(
    name="wait_until",
    title="Wait Until",
    description=(
        "Wait for observable page state: element present/visible/hidden/"
        "detached/clickable/stable, text contains/matches, or URL contains/matches."
    ),
    input_schema=WaitUntilInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
)
async def wait_until(
    context: "DrissionPageContext", args: WaitUntilInput, response: "ToolResponse"
) -> None:
    """Wait until an observable condition is satisfied."""
    async with tool_errors(
        response,
        lambda e: (
            f"Condition '{args.condition}' was not met within "
            f"{args.timeout} seconds: {e}"
        ),
    ):
        tab = context.current_tab_or_die()
        result = await tab.wait_until(
            condition=args.condition,
            selector=args.selector,
            value=args.value,
            timeout=args.timeout,
            interval=args.interval,
            stable_ms=args.stable_ms,
        )

        response.add_code(f"# wait until {args.condition!r}")
        response.add_result(
            f"Condition '{args.condition}' matched within {args.timeout} seconds",
            **result,
        )


# Export all tools
tools = [wait_for_element, wait_for_url, wait_time, wait_until]
