"""Element interaction tools for DrissionPage MCP."""

import json
from typing import TYPE_CHECKING

from pydantic import Field

from ..selector import normalize_selector
from .base import ToolInput, ToolType, define_tool, tool_errors

if TYPE_CHECKING:
    from ..context import DrissionPageContext
    from ..response import ToolResponse


class FindElementInput(ToolInput):
    """Input schema for finding elements."""

    selector: str = Field(
        ...,
        description=(
            "CSS selector or XPath to find the element. Bare selectors are CSS; "
            "use text:... for text matching or explicit tag:/css:/xpath:/@attr locators."
        ),
    )
    timeout: int = Field(
        default=3, description="Timeout in seconds to wait for element"
    )


class ClickElementInput(ToolInput):
    """Input schema for clicking elements."""

    selector: str = Field(
        ...,
        description=(
            "CSS selector or XPath to find the element. Bare selectors are CSS; "
            "use text:... for text matching or explicit tag:/css:/xpath:/@attr locators."
        ),
    )
    timeout: int = Field(
        default=10, description="Timeout in seconds to wait for element"
    )


class TypeTextInput(ToolInput):
    """Input schema for typing text."""

    selector: str = Field(
        ...,
        description=(
            "CSS selector or XPath to find the input element. Bare selectors are CSS; "
            "use text:... for text matching or explicit tag:/css:/xpath:/@attr locators."
        ),
    )
    text: str = Field(..., description="Text to type into the element")
    timeout: int = Field(
        default=10, description="Timeout in seconds to wait for element"
    )
    clear: bool = Field(
        default=True, description="Clear existing input content before typing"
    )


class GetTextInput(ToolInput):
    """Input schema for getting text."""

    selector: str = Field(
        default="",
        description=(
            "CSS selector or XPath; empty means whole page. Bare selectors are CSS; "
            "use text:... for text matching."
        ),
    )


class GetAttributeInput(ToolInput):
    """Input schema for getting an element attribute."""

    selector: str = Field(
        ...,
        description=(
            "CSS selector or XPath to find the element. Bare selectors are CSS; "
            "use text:... for text matching or explicit tag:/css:/xpath:/@attr locators."
        ),
    )
    attribute: str = Field(..., description="Attribute name to retrieve")


class GetPropertyInput(ToolInput):
    """Input schema for getting a live DOM property."""

    selector: str = Field(
        ...,
        description=(
            "CSS selector or XPath to find the element. Bare selectors are CSS; "
            "use text:... for text matching or explicit tag:/css:/xpath:/@attr locators."
        ),
    )
    property: str = Field(..., description="DOM property to retrieve, e.g. value")


class GetHtmlInput(ToolInput):
    """Input schema for getting HTML."""

    selector: str = Field(
        default="",
        description=(
            "CSS selector or XPath; empty means whole page. Bare selectors are CSS; "
            "use text:... for text matching."
        ),
    )


@define_tool(
    name="element_find",
    title="Find Element",
    description=(
        "Find an element on the page using CSS selector or XPath. Bare selectors "
        "are treated as CSS; use text:... for text matching."
    ),
    input_schema=FindElementInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
)
async def find_element(
    context: "DrissionPageContext", args: FindElementInput, response: "ToolResponse"
) -> None:
    """Find an element on the page."""
    async with tool_errors(
        response, lambda e: f"Failed to find element '{args.selector}': {e}"
    ):
        tab = context.current_tab_or_die()
        element = await tab.find_element(args.selector, timeout=args.timeout)

        response.add_code(f"element = page.ele({element['locator']!r})")
        response.add_result(f"Found element: {args.selector}", element=element)


@define_tool(
    name="element_click",
    title="Click Element",
    description=(
        "Click an element found by CSS selector or XPath. Bare selectors are "
        "treated as CSS; use text:... for text matching."
    ),
    input_schema=ClickElementInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def click_element(
    context: "DrissionPageContext", args: ClickElementInput, response: "ToolResponse"
) -> None:
    """Click on an element."""
    async with tool_errors(
        response, lambda e: f"Failed to click element '{args.selector}': {e}"
    ):
        tab = context.current_tab_or_die()
        plan = normalize_selector(args.selector)
        await tab.click_element(args.selector, timeout=args.timeout)

        response.add_code(f"page.ele({plan.locator!r}).click()")
        response.add_result(
            f"Successfully clicked element: {args.selector}",
            **plan.metadata(),
            url=tab.url,
        )
        response.set_include_snapshot(True)


@define_tool(
    name="element_type",
    title="Type Text",
    description="Type text into an input element",
    input_schema=TypeTextInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def type_text(
    context: "DrissionPageContext", args: TypeTextInput, response: "ToolResponse"
) -> None:
    """Type text into an element."""
    async with tool_errors(
        response, lambda e: f"Failed to type text into element '{args.selector}': {e}"
    ):
        tab = context.current_tab_or_die()
        plan = normalize_selector(args.selector)
        await tab.type_text(
            args.selector, args.text, timeout=args.timeout, clear=args.clear
        )

        response.add_code(
            f"page.ele({plan.locator!r}).input({args.text!r}, clear={args.clear!r})"
        )
        response.add_result(
            f"Successfully typed text into element: {args.selector}",
            **plan.metadata(),
            typed=True,
            cleared=args.clear,
        )
        response.set_include_snapshot(True)


@define_tool(
    name="element_get_text",
    title="Get Text",
    description="Get text from an element or the whole page",
    input_schema=GetTextInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
)
async def get_text(
    context: "DrissionPageContext", args: GetTextInput, response: "ToolResponse"
) -> None:
    """Get text from an element or the page."""
    async with tool_errors(
        response,
        lambda e: f"Failed to get text from '{args.selector or 'page'}': {e}",
    ):
        tab = context.current_tab_or_die()
        plan = normalize_selector(args.selector)
        text = await tab.get_text(args.selector)

        code = f"page.ele({plan.locator!r}).text" if args.selector else "page.text"
        response.add_code(code)
        response.add_result(text or "", text=text or "", **plan.metadata())


@define_tool(
    name="element_get_attribute",
    title="Get Attribute",
    description="Get an attribute value from an element",
    input_schema=GetAttributeInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
)
async def get_attribute(
    context: "DrissionPageContext", args: GetAttributeInput, response: "ToolResponse"
) -> None:
    """Get an attribute value from an element."""
    async with tool_errors(
        response,
        lambda e: (
            f"Failed to get attribute '{args.attribute}' "
            f"from '{args.selector}': {e}"
        ),
        ):
        tab = context.current_tab_or_die()
        plan = normalize_selector(args.selector)
        value = await tab.get_attribute(args.selector, args.attribute)

        response.add_code(f"page.ele({plan.locator!r}).attr({args.attribute!r})")
        response.add_result(
            "" if value is None else str(value),
            **plan.metadata(),
            attribute=args.attribute,
            value=value,
        )


@define_tool(
    name="element_get_property",
    title="Get Property",
    description="Get a live DOM property value from an element, such as an input's current value",
    input_schema=GetPropertyInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
)
async def get_property(
    context: "DrissionPageContext", args: GetPropertyInput, response: "ToolResponse"
) -> None:
    """Get a live DOM property value from an element."""
    async with tool_errors(
        response,
        lambda e: (
            f"Failed to get property '{args.property}' "
            f"from '{args.selector}': {e}"
        ),
    ):
        tab = context.current_tab_or_die()
        plan = normalize_selector(args.selector)
        value = await tab.get_property(args.selector, args.property)

        response.add_code(f"page.ele({plan.locator!r}).property({args.property!r})")
        response.add_result(
            "" if value is None else str(value),
            **plan.metadata(),
            property=args.property,
            value=_json_safe(value),
        )


@define_tool(
    name="element_get_html",
    title="Get HTML",
    description="Get HTML from an element or the whole page",
    input_schema=GetHtmlInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
)
async def get_html(
    context: "DrissionPageContext", args: GetHtmlInput, response: "ToolResponse"
) -> None:
    """Get HTML from an element or the page."""
    async with tool_errors(
        response,
        lambda e: f"Failed to get HTML from '{args.selector or 'page'}': {e}",
        ):
        tab = context.current_tab_or_die()
        plan = normalize_selector(args.selector)
        html = await tab.get_html(args.selector)

        code = f"page.ele({plan.locator!r}).html" if args.selector else "page.html"
        response.add_code(code)
        response.add_result(html or "", html=html or "", **plan.metadata())


# Export all tools
tools = [
    find_element,
    click_element,
    type_text,
    get_text,
    get_attribute,
    get_property,
    get_html,
]


def _json_safe(value):
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value
