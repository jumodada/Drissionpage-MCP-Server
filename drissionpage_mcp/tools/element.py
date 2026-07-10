"""Element interaction tools for DrissionPage MCP."""

import json
from typing import TYPE_CHECKING
from pydantic import Field
from ..limits import MAX_WAIT_SECONDS
from ..metadata import with_response_meta
from ..selector import normalize_selector
from ._observe import maybe_observe, observed_changes
from .base import ToolInput, ToolType, define_tool, ToolOutcome
from ..tool_outputs import (
    ElementFindData,
    ElementFindAllData,
    ElementClickData,
    ElementTypeData,
    ElementGetTextData,
    ElementGetAttributeData,
    ElementGetPropertyData,
    ElementGetHtmlData,
)

if TYPE_CHECKING:
    from ..context import DrissionPageContext


class FindElementInput(ToolInput):
    """Input schema for finding elements."""

    selector: str = Field(
        ...,
        description="CSS selector or XPath to find the element. Bare selectors are CSS; use text:... for text matching or explicit tag:/css:/xpath:/@attr locators.",
    )
    timeout: int = Field(
        default=3,
        ge=0,
        le=MAX_WAIT_SECONDS,
        description="Timeout in seconds to wait for element",
    )


class FindAllElementsInput(ToolInput):
    """Input schema for bounded multi-element extraction."""

    selector: str = Field(
        ...,
        description="CSS selector, XPath, or explicit DrissionPage locator for repeated elements. Bare selectors are CSS.",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of matched elements to return",
    )
    include_html: bool = Field(
        default=False,
        description="Include bounded outerHTML excerpts for each returned element",
    )


class ClickElementInput(ToolInput):
    """Input schema for clicking elements."""

    selector: str = Field(
        ...,
        description="CSS selector or XPath to find the element. Bare selectors are CSS; use text:... for text matching or explicit tag:/css:/xpath:/@attr locators.",
    )
    timeout: int = Field(
        default=10,
        ge=0,
        le=MAX_WAIT_SECONDS,
        description="Timeout in seconds to wait for element",
    )
    observe: bool = Field(
        default=False, description="Return a compact before/after page change summary."
    )


class TypeTextInput(ToolInput):
    """Input schema for typing text."""

    selector: str = Field(
        ...,
        description="CSS selector or XPath to find the input element. Bare selectors are CSS; use text:... for text matching or explicit tag:/css:/xpath:/@attr locators.",
    )
    text: str = Field(..., description="Text to type into the element")
    timeout: int = Field(
        default=10,
        ge=0,
        le=MAX_WAIT_SECONDS,
        description="Timeout in seconds to wait for element",
    )
    clear: bool = Field(
        default=True, description="Clear existing input content before typing"
    )
    observe: bool = Field(
        default=False, description="Return a compact before/after page change summary."
    )


class GetTextInput(ToolInput):
    """Input schema for getting text."""

    selector: str = Field(
        default="",
        description="CSS selector or XPath; empty means whole page. Bare selectors are CSS; use text:... for text matching.",
    )


class GetAttributeInput(ToolInput):
    """Input schema for getting an element attribute."""

    selector: str = Field(
        ...,
        description="CSS selector or XPath to find the element. Bare selectors are CSS; use text:... for text matching or explicit tag:/css:/xpath:/@attr locators.",
    )
    attribute: str = Field(..., description="Attribute name to retrieve")


class GetPropertyInput(ToolInput):
    """Input schema for getting a live DOM property."""

    selector: str = Field(
        ...,
        description="CSS selector or XPath to find the element. Bare selectors are CSS; use text:... for text matching or explicit tag:/css:/xpath:/@attr locators.",
    )
    property: str = Field(..., description="DOM property to retrieve, e.g. value")


class GetHtmlInput(ToolInput):
    """Input schema for getting HTML."""

    selector: str = Field(
        default="",
        description="CSS selector or XPath; empty means whole page. Bare selectors are CSS; use text:... for text matching.",
    )


@define_tool(
    name="element_find",
    title="Find Element",
    description="Find an element on the page using CSS selector or XPath. Bare selectors are treated as CSS; use text:... for text matching.",
    input_schema=FindElementInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
    output_model=ElementFindData,
    failure_message=lambda args, exc: (
        lambda e: f"Failed to find element '{args.selector}': {e}"
    )(exc),
)
async def find_element(
    context: "DrissionPageContext", args: FindElementInput
) -> "ToolOutcome":
    """Find an element on the page."""
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    element = await tab.elements.find(args.selector, timeout=args.timeout)
    outcome.add_code(f"element = page.ele({element['locator']!r})")
    outcome.add_result(f"Found element: {args.selector}", element=element)
    return outcome


@define_tool(
    name="element_find_all",
    title="Find All Elements",
    description="Find multiple matching elements with bounded text/attribute summaries and recommended selectors for repeated lists, cards, and tables.",
    input_schema=FindAllElementsInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
    output_model=ElementFindAllData,
    failure_message=lambda args, exc: (
        lambda e: f"Failed to find elements '{args.selector}': {e}"
    )(exc),
)
async def find_all_elements(
    context: "DrissionPageContext", args: FindAllElementsInput
) -> "ToolOutcome":
    """Find multiple elements on the page."""
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    result = await tab.elements.find_all(
        args.selector, limit=args.limit, include_html=args.include_html
    )
    outcome.add_code(f"elements = page.eles({result['locator']!r}, timeout=0)")
    outcome.add_result(
        f"Found {result['returned']} of {result['count']} elements: {args.selector}",
        **with_response_meta(result),
    )
    return outcome


@define_tool(
    name="element_click",
    title="Click Element",
    description="Click an element found by CSS selector or XPath. Bare selectors are treated as CSS; use text:... for text matching.",
    input_schema=ClickElementInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=ElementClickData,
    failure_message=lambda args, exc: (
        lambda e: f"Failed to click element '{args.selector}': {e}"
    )(exc),
)
async def click_element(
    context: "DrissionPageContext", args: ClickElementInput
) -> "ToolOutcome":
    """Click on an element."""
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    plan = normalize_selector(args.selector)
    before = await maybe_observe(tab, args.observe)
    await tab.elements.click(args.selector, timeout=args.timeout)
    changes = await observed_changes(tab, before)
    outcome.add_code(f"page.ele({plan.locator!r}).click()")
    data = {**plan.metadata(), "url": tab.url}
    if changes is not None:
        data["changes"] = changes
    outcome.add_result(f"Successfully clicked element: {args.selector}", **data)
    outcome.set_include_snapshot(True)
    return outcome


@define_tool(
    name="element_type",
    title="Type Text",
    description="Type text into an input element",
    input_schema=TypeTextInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=ElementTypeData,
    failure_message=lambda args, exc: (
        lambda e: f"Failed to type text into element '{args.selector}': {e}"
    )(exc),
)
async def type_text(
    context: "DrissionPageContext", args: TypeTextInput
) -> "ToolOutcome":
    """Type text into an element."""
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    plan = normalize_selector(args.selector)
    before = await maybe_observe(tab, args.observe)
    await tab.elements.type(
        args.selector, args.text, timeout=args.timeout, clear=args.clear
    )
    changes = await observed_changes(tab, before)
    outcome.add_code(
        f"page.ele({plan.locator!r}).input({args.text!r}, clear={args.clear!r})"
    )
    data = {**plan.metadata(), "typed": True, "cleared": args.clear}
    if changes is not None:
        data["changes"] = changes
    outcome.add_result(f"Successfully typed text into element: {args.selector}", **data)
    outcome.set_include_snapshot(True)
    return outcome


@define_tool(
    name="element_get_text",
    title="Get Text",
    description="Get text from an element or the whole page",
    input_schema=GetTextInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
    output_model=ElementGetTextData,
    failure_message=lambda args, exc: (
        lambda e: f"Failed to get text from '{args.selector or 'page'}': {e}"
    )(exc),
)
async def get_text(context: "DrissionPageContext", args: GetTextInput) -> "ToolOutcome":
    """Get text from an element or the page."""
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    plan = normalize_selector(args.selector)
    text = await tab.elements.text(args.selector)
    code = f"page.ele({plan.locator!r}).text" if args.selector else "page.text"
    outcome.add_code(code)
    outcome.add_result(text or "", text=text or "", **plan.metadata())
    return outcome


@define_tool(
    name="element_get_attribute",
    title="Get Attribute",
    description="Get an attribute value from an element",
    input_schema=GetAttributeInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
    output_model=ElementGetAttributeData,
    failure_message=lambda args, exc: (
        lambda e: f"Failed to get attribute '{args.attribute}' from '{args.selector}': {e}"
    )(exc),
)
async def get_attribute(
    context: "DrissionPageContext", args: GetAttributeInput
) -> "ToolOutcome":
    """Get an attribute value from an element."""
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    plan = normalize_selector(args.selector)
    value = await tab.elements.attribute(args.selector, args.attribute)
    outcome.add_code(f"page.ele({plan.locator!r}).attr({args.attribute!r})")
    outcome.add_result(
        "" if value is None else str(value),
        **plan.metadata(),
        attribute=args.attribute,
        value=value,
    )
    return outcome


@define_tool(
    name="element_get_property",
    title="Get Property",
    description="Get a live DOM property value from an element, such as an input's current value",
    input_schema=GetPropertyInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
    output_model=ElementGetPropertyData,
    failure_message=lambda args, exc: (
        lambda e: f"Failed to get property '{args.property}' from '{args.selector}': {e}"
    )(exc),
)
async def get_property(
    context: "DrissionPageContext", args: GetPropertyInput
) -> "ToolOutcome":
    """Get a live DOM property value from an element."""
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    plan = normalize_selector(args.selector)
    value = await tab.elements.property(args.selector, args.property)
    outcome.add_code(f"page.ele({plan.locator!r}).property({args.property!r})")
    outcome.add_result(
        "" if value is None else str(value),
        **plan.metadata(),
        property=args.property,
        value=_json_safe(value),
    )
    return outcome


@define_tool(
    name="element_get_html",
    title="Get HTML",
    description="Get HTML from an element or the whole page",
    input_schema=GetHtmlInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
    output_model=ElementGetHtmlData,
    failure_message=lambda args, exc: (
        lambda e: f"Failed to get HTML from '{args.selector or 'page'}': {e}"
    )(exc),
)
async def get_html(context: "DrissionPageContext", args: GetHtmlInput) -> "ToolOutcome":
    """Get HTML from an element or the page."""
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    plan = normalize_selector(args.selector)
    html = await tab.elements.html(args.selector)
    code = f"page.ele({plan.locator!r}).html" if args.selector else "page.html"
    outcome.add_code(code)
    outcome.add_result(html or "", html=html or "", **plan.metadata())
    return outcome


def _json_safe(value):
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value
