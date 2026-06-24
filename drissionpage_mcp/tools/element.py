"""Element interaction tools for DrissionPage MCP."""

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from .base import define_tool, ToolType

if TYPE_CHECKING:
    from ..context import DrissionPageContext
    from ..response import ToolResponse


class FindElementInput(BaseModel):
    """Input schema for finding elements."""
    selector: str = Field(..., description="CSS selector or XPath to find the element")
    timeout: int = Field(default=10, description="Timeout in seconds to wait for element")


class ClickElementInput(BaseModel):
    """Input schema for clicking elements."""
    selector: str = Field(..., description="CSS selector or XPath to find the element")
    timeout: int = Field(default=10, description="Timeout in seconds to wait for element")


class TypeTextInput(BaseModel):
    """Input schema for typing text."""
    selector: str = Field(..., description="CSS selector or XPath to find the input element")
    text: str = Field(..., description="Text to type into the element")
    timeout: int = Field(default=10, description="Timeout in seconds to wait for element")
    clear: bool = Field(default=True, description="Clear existing input content before typing")


class GetTextInput(BaseModel):
    """Input schema for getting text."""
    selector: str = Field(default="", description="CSS selector or XPath; empty means whole page")


class GetAttributeInput(BaseModel):
    """Input schema for getting an element attribute."""
    selector: str = Field(..., description="CSS selector or XPath to find the element")
    attribute: str = Field(..., description="Attribute name to retrieve")


class GetPropertyInput(BaseModel):
    """Input schema for getting a live DOM property."""
    selector: str = Field(..., description="CSS selector or XPath to find the element")
    property_name: str = Field(..., description="DOM property name to retrieve, e.g. value")


class GetHtmlInput(BaseModel):
    """Input schema for getting HTML."""
    selector: str = Field(default="", description="CSS selector or XPath; empty means whole page")


@define_tool(
    name="element_find",
    title="Find Element",
    description="Find an element on the page using CSS selector or XPath",
    input_schema=FindElementInput,
    tool_type=ToolType.READ_ONLY
)
async def find_element(
    context: "DrissionPageContext",
    args: FindElementInput,
    response: "ToolResponse"
) -> None:
    """Find an element on the page."""
    try:
        tab = context.current_tab_or_die()
        element = await tab.find_element(args.selector, timeout=args.timeout)
        
        response.add_code(f"element = page.ele({args.selector!r})")
        response.add_result(json.dumps(element, ensure_ascii=False, indent=2))
        
    except Exception as e:
        response.add_error(f"Failed to find element '{args.selector}': {str(e)}")


@define_tool(
    name="element_click",
    title="Click Element",
    description="Click on an element found by CSS selector or XPath",
    input_schema=ClickElementInput,
    tool_type=ToolType.DESTRUCTIVE
)
async def click_element(
    context: "DrissionPageContext",
    args: ClickElementInput,
    response: "ToolResponse"
) -> None:
    """Click on an element."""
    try:
        tab = context.current_tab_or_die()
        await tab.click_element(args.selector, timeout=args.timeout)
        
        response.add_code(f"page.ele({args.selector!r}).click()")
        response.add_result(f"Successfully clicked element: {args.selector}")
        response.set_include_snapshot(True)
        
    except Exception as e:
        response.add_error(f"Failed to click element '{args.selector}': {str(e)}")


@define_tool(
    name="element_type",
    title="Type Text",
    description="Type text into an input element",
    input_schema=TypeTextInput,
    tool_type=ToolType.DESTRUCTIVE
)
async def type_text(
    context: "DrissionPageContext",
    args: TypeTextInput,
    response: "ToolResponse"
) -> None:
    """Type text into an element."""
    try:
        tab = context.current_tab_or_die()
        await tab.type_text(args.selector, args.text, timeout=args.timeout, clear=args.clear)
        
        response.add_code(f"page.ele({args.selector!r}).input({args.text!r}, clear={args.clear!r})")
        response.add_result(f"Successfully typed text into element: {args.selector}")
        response.set_include_snapshot(True)
        
    except Exception as e:
        response.add_error(f"Failed to type text into element '{args.selector}': {str(e)}")


@define_tool(
    name="element_input_text",
    title="Input Text",
    description="Input text into an element (backward-compatible alias of element_type)",
    input_schema=TypeTextInput,
    tool_type=ToolType.DESTRUCTIVE
)
async def input_text(
    context: "DrissionPageContext",
    args: TypeTextInput,
    response: "ToolResponse"
) -> None:
    """Input text into an element."""
    await type_text.handler(context, args, response)


@define_tool(
    name="element_get_text",
    title="Get Text",
    description="Get text from an element or the whole page",
    input_schema=GetTextInput,
    tool_type=ToolType.READ_ONLY
)
async def get_text(
    context: "DrissionPageContext",
    args: GetTextInput,
    response: "ToolResponse"
) -> None:
    """Get text from an element or the page."""
    try:
        tab = context.current_tab_or_die()
        text = await tab.get_text(args.selector)

        code = f"page.ele({args.selector!r}).text" if args.selector else "page.text"
        response.add_code(code)
        response.add_result(text or "")

    except Exception as e:
        target = args.selector or "page"
        response.add_error(f"Failed to get text from '{target}': {str(e)}")


@define_tool(
    name="element_get_attribute",
    title="Get Attribute",
    description="Get an attribute value from an element",
    input_schema=GetAttributeInput,
    tool_type=ToolType.READ_ONLY
)
async def get_attribute(
    context: "DrissionPageContext",
    args: GetAttributeInput,
    response: "ToolResponse"
) -> None:
    """Get an attribute value from an element."""
    try:
        tab = context.current_tab_or_die()
        value = await tab.get_attribute(args.selector, args.attribute)

        response.add_code(f"page.ele({args.selector!r}).attr({args.attribute!r})")
        response.add_result("" if value is None else str(value))

    except Exception as e:
        response.add_error(
            f"Failed to get attribute '{args.attribute}' from '{args.selector}': {str(e)}"
        )


@define_tool(
    name="element_get_property",
    title="Get Property",
    description="Get a live DOM property value from an element, such as an input's current value",
    input_schema=GetPropertyInput,
    tool_type=ToolType.READ_ONLY
)
async def get_property(
    context: "DrissionPageContext",
    args: GetPropertyInput,
    response: "ToolResponse"
) -> None:
    """Get a live DOM property value from an element."""
    try:
        tab = context.current_tab_or_die()
        value = await tab.get_property(args.selector, args.property_name)

        response.add_code(f"page.ele({args.selector!r}).property({args.property_name!r})")
        response.add_result("" if value is None else str(value))

    except Exception as e:
        response.add_error(
            f"Failed to get property '{args.property_name}' from '{args.selector}': {str(e)}"
        )


@define_tool(
    name="element_get_html",
    title="Get HTML",
    description="Get HTML from an element or the whole page",
    input_schema=GetHtmlInput,
    tool_type=ToolType.READ_ONLY
)
async def get_html(
    context: "DrissionPageContext",
    args: GetHtmlInput,
    response: "ToolResponse"
) -> None:
    """Get HTML from an element or the page."""
    try:
        tab = context.current_tab_or_die()
        html = await tab.get_html(args.selector)

        code = f"page.ele({args.selector!r}).html" if args.selector else "page.html"
        response.add_code(code)
        response.add_result(html or "")

    except Exception as e:
        target = args.selector or "page"
        response.add_error(f"Failed to get HTML from '{target}': {str(e)}")


# Export all tools
tools = [
    find_element,
    click_element,
    type_text,
    input_text,
    get_text,
    get_attribute,
    get_property,
    get_html,
]
