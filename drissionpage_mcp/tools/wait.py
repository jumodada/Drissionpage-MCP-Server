"""Wait operation tools for DrissionPage MCP."""

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from .base import ToolType, define_tool, tool_errors

if TYPE_CHECKING:
    from ..context import DrissionPageContext
    from ..response import ToolResponse


class WaitElementInput(BaseModel):
    """Input schema for waiting for elements."""

    selector: str = Field(..., description="CSS selector or XPath to wait for")
    timeout: int = Field(default=10, description="Timeout in seconds")


class WaitTimeInput(BaseModel):
    """Input schema for waiting a specific time."""

    seconds: float = Field(..., description="Number of seconds to wait")


class WaitUrlInput(BaseModel):
    """Input schema for waiting for URL changes."""

    url_pattern: str = Field(
        ..., description="Substring or pattern expected in the current URL"
    )
    timeout: int = Field(default=10, description="Timeout in seconds")


@define_tool(
    name="wait_for_element",
    title="Wait for Element",
    description="Wait for an element to appear on the page",
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
        found = await tab.wait_for_element(args.selector, timeout=args.timeout)
        if not found:
            raise TimeoutError(f"Element '{args.selector}' not found")

        response.add_code(
            f"page.wait.ele_loaded({args.selector!r}, timeout={args.timeout!r})"
        )
        response.add_result(
            f"Element '{args.selector}' appeared within {args.timeout} seconds"
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
            f"URL matched '{args.url_pattern}' within {args.timeout} seconds"
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
        response.add_result(f"Waited for {args.seconds} seconds")


@define_tool(
    name="wait_sleep",
    title="Sleep",
    description="Wait for a specific amount of time (backward-compatible alias of wait_time)",
    input_schema=WaitTimeInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
)
async def wait_sleep(
    context: "DrissionPageContext", args: WaitTimeInput, response: "ToolResponse"
) -> None:
    """Backward-compatible alias for wait_time."""
    await wait_time.handler(context, args, response)


# Export all tools
tools = [wait_for_element, wait_for_url, wait_time, wait_sleep]
