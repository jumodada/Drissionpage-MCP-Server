"""Additional page and element interaction tools for DrissionPage MCP."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import Field

from ..limits import MAX_WAIT_SECONDS
from .base import ToolInput, ToolType, define_tool, tool_errors

if TYPE_CHECKING:
    from ..context import DrissionPageContext
    from ..response import ToolResponse


ScrollDirection = Literal[
    "down",
    "up",
    "left",
    "right",
    "top",
    "bottom",
    "half",
    "position",
]
SelectBy = Literal["value", "text", "index"]


class PageScrollInput(ToolInput):
    """Input schema for page scrolling."""

    direction: ScrollDirection = Field(
        default="down",
        description="Scroll direction or target: down, up, left, right, top, bottom, half, position.",
    )
    pixels: int = Field(
        default=300,
        ge=0,
        le=20000,
        description="Pixel distance for directional scrolling.",
    )
    x: int = Field(default=0, ge=0, description="X coordinate for direction=position.")
    y: int = Field(default=0, ge=0, description="Y coordinate for direction=position.")


class ElementScrollIntoViewInput(ToolInput):
    """Input schema for scrolling an element into view."""

    selector: str = Field(..., description="CSS/XPath/DrissionPage element locator.")
    center: bool = Field(
        default=True, description="Center the element in the viewport."
    )
    timeout: int = Field(default=10, ge=0, le=MAX_WAIT_SECONDS)


class ElementHoverInput(ToolInput):
    """Input schema for hovering an element."""

    selector: str = Field(..., description="CSS/XPath/DrissionPage element locator.")
    timeout: int = Field(default=10, ge=0, le=MAX_WAIT_SECONDS)
    offset_x: int | None = Field(default=None, description="Optional hover X offset.")
    offset_y: int | None = Field(default=None, description="Optional hover Y offset.")


class KeyboardPressInput(ToolInput):
    """Input schema for sending keys to the active element."""

    keys: str = Field(..., description="Text or DrissionPage key string to send.")
    interval: float = Field(
        default=0,
        ge=0,
        le=2,
        description="Optional interval between key events in seconds.",
    )


class ElementSelectInput(ToolInput):
    """Input schema for selecting an option."""

    selector: str = Field(..., description="CSS/XPath/DrissionPage select locator.")
    value: str = Field(..., description="Option value, text, or index string.")
    by: SelectBy = Field(
        default="value", description="Select by value, text, or index."
    )
    timeout: int = Field(default=10, ge=0, le=MAX_WAIT_SECONDS)


class ElementCheckInput(ToolInput):
    """Input schema for checkbox/radio state."""

    selector: str = Field(..., description="CSS/XPath/DrissionPage checkbox locator.")
    checked: bool = Field(default=True, description="Desired checked state.")
    by_js: bool = Field(default=False, description="Use JavaScript-backed checking.")
    timeout: int = Field(default=10, ge=0, le=MAX_WAIT_SECONDS)


@define_tool(
    name="page_scroll",
    title="Scroll Page",
    description="Scroll the current page by direction or to a position.",
    input_schema=PageScrollInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def page_scroll(
    context: "DrissionPageContext", args: PageScrollInput, response: "ToolResponse"
) -> None:
    async with tool_errors(response, "Failed to scroll page"):
        tab = context.current_tab_or_die()
        result = await tab.interaction.scroll_page(
            direction=args.direction,
            pixels=args.pixels,
            x=args.x,
            y=args.y,
        )
        response.add_code(f"page.scroll.{args.direction}()")
        response.add_result(f"Scrolled page {args.direction}", **result)
        response.set_include_snapshot(True)


@define_tool(
    name="element_scroll_into_view",
    title="Scroll Element Into View",
    description="Scroll an element into the viewport before a later action.",
    input_schema=ElementScrollIntoViewInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def element_scroll_into_view(
    context: "DrissionPageContext",
    args: ElementScrollIntoViewInput,
    response: "ToolResponse",
) -> None:
    async with tool_errors(
        response, lambda e: f"Failed to scroll element '{args.selector}' into view: {e}"
    ):
        tab = context.current_tab_or_die()
        result = await tab.interaction.scroll_element_into_view(
            args.selector,
            center=args.center,
            timeout=args.timeout,
        )
        response.add_code(f"page.ele({result['locator']!r}).scroll.to_see()")
        response.add_result(f"Scrolled element into view: {args.selector}", **result)
        response.set_include_snapshot(True)


@define_tool(
    name="element_hover",
    title="Hover Element",
    description="Move the mouse over an element.",
    input_schema=ElementHoverInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def element_hover(
    context: "DrissionPageContext", args: ElementHoverInput, response: "ToolResponse"
) -> None:
    async with tool_errors(
        response, lambda e: f"Failed to hover element '{args.selector}': {e}"
    ):
        tab = context.current_tab_or_die()
        result = await tab.interaction.hover_element(
            args.selector,
            timeout=args.timeout,
            offset_x=args.offset_x,
            offset_y=args.offset_y,
        )
        response.add_code(f"page.ele({result['locator']!r}).hover()")
        response.add_result(f"Hovered element: {args.selector}", **result)
        response.set_include_snapshot(True)


@define_tool(
    name="keyboard_press",
    title="Keyboard Press",
    description="Send keyboard text/keys to the active page element.",
    input_schema=KeyboardPressInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def keyboard_press(
    context: "DrissionPageContext", args: KeyboardPressInput, response: "ToolResponse"
) -> None:
    async with tool_errors(response, "Failed to send keyboard keys"):
        tab = context.current_tab_or_die()
        result = await tab.interaction.keyboard_press(args.keys, interval=args.interval)
        response.add_code(f"page.actions.type({args.keys!r})")
        response.add_result("Sent keyboard keys", **result)
        response.set_include_snapshot(True)


@define_tool(
    name="element_select",
    title="Select Element Option",
    description="Select an option from a select element by value, text, or index.",
    input_schema=ElementSelectInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def element_select(
    context: "DrissionPageContext", args: ElementSelectInput, response: "ToolResponse"
) -> None:
    async with tool_errors(
        response, lambda e: f"Failed to select option for '{args.selector}': {e}"
    ):
        tab = context.current_tab_or_die()
        result = await tab.interaction.select_element(
            args.selector,
            value=args.value,
            by=args.by,
            timeout=args.timeout,
        )
        response.add_code(f"page.ele({result['locator']!r}).select.{args.by}()")
        response.add_result(f"Selected option in: {args.selector}", **result)
        response.set_include_snapshot(True)


@define_tool(
    name="element_check",
    title="Check Element",
    description="Set a checkbox or radio element to checked/unchecked.",
    input_schema=ElementCheckInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def element_check(
    context: "DrissionPageContext", args: ElementCheckInput, response: "ToolResponse"
) -> None:
    async with tool_errors(
        response, lambda e: f"Failed to set check state for '{args.selector}': {e}"
    ):
        tab = context.current_tab_or_die()
        result = await tab.interaction.check_element(
            args.selector,
            checked=args.checked,
            by_js=args.by_js,
            timeout=args.timeout,
        )
        response.add_code(f"page.ele({result['locator']!r}).check()")
        response.add_result(f"Set check state for: {args.selector}", **result)
        response.set_include_snapshot(True)


tools = [
    page_scroll,
    element_scroll_into_view,
    element_hover,
    keyboard_press,
    element_select,
    element_check,
]
