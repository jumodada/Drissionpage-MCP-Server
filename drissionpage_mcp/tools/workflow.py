"""High-level workflow tools for common browser automation tasks."""

from __future__ import annotations
from typing import TYPE_CHECKING, Literal

from pydantic import Field
from ..limits import MAX_WAIT_SECONDS
from ..metadata import with_response_meta
from ..policy import PolicyDeniedError, validate_navigation
from ..response_errors import ErrorCode
from .base import ToolInput, ToolType, define_tool, ToolOutcome
from ..tool_outputs import BrowserExtractLinksData, BrowserOpenAndSnapshotData

if TYPE_CHECKING:
    from ..context import DrissionPageContext
WaitCondition = Literal[
    "",
    "present",
    "visible",
    "hidden",
    "detached",
    "clickable",
    "stable",
    "url_contains",
    "url_matches",
    "text_contains",
    "text_matches",
]


class BrowserOpenAndSnapshotInput(ToolInput):
    """Input schema for opening a page and immediately capturing context."""

    url: str = Field(..., description="URL to open in the active browser tab.")
    wait_condition: WaitCondition = Field(
        default="", description="Optional wait condition before snapshot capture."
    )
    selector: str = Field(
        default="", description="Selector used by element/text wait conditions."
    )
    wait_value: str = Field(
        default="", description="Value used by URL/text wait conditions."
    )
    wait_timeout: float = Field(
        default=5.0,
        ge=0,
        le=MAX_WAIT_SECONDS,
        description="Maximum seconds for the optional wait condition.",
    )
    include_html: bool = Field(
        default=False,
        description="Include bounded HTML excerpts in the nested page snapshot.",
    )
    include_console: bool = Field(
        default=False, description="Also include recent console messages from the page."
    )
    max_elements: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum summarized elements in the nested snapshot.",
    )
    max_text_chars: int = Field(
        default=4000,
        ge=0,
        le=20000,
        description="Maximum page text excerpt characters in the nested snapshot.",
    )


class BrowserExtractLinksInput(ToolInput):
    """Input schema for bounded link extraction."""

    selector: str = Field(
        default="a",
        description="CSS/XPath/DrissionPage locator selecting links or containers.",
    )
    limit: int = Field(default=50, ge=1, le=200, description="Maximum links to return.")
    include_text: bool = Field(
        default=True, description="Include bounded visible link text."
    )
    same_origin_only: bool = Field(
        default=False,
        description="Return only links whose absolute URL has the current page origin.",
    )
    absolute_urls: bool = Field(
        default=True, description="Return absolute URLs in the url field when possible."
    )


@define_tool(
    name="browser_open_and_snapshot",
    title="Open and Snapshot",
    description="Open a URL, optionally wait for a page condition, then return a bounded snapshot plus optional HTML and console context.",
    input_schema=BrowserOpenAndSnapshotInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=BrowserOpenAndSnapshotData,
    failure_message=lambda args, exc: (
        lambda e: f"Open-and-snapshot workflow failed for {args.url!r}: {e}"
    )(exc),
)
async def browser_open_and_snapshot(
    context: "DrissionPageContext", args: BrowserOpenAndSnapshotInput
) -> "ToolOutcome":
    """Open a page and capture immediate context."""
    outcome = ToolOutcome()
    try:
        validate_navigation(args.url)
    except PolicyDeniedError as exc:
        outcome.add_error(
            str(exc),
            ErrorCode.POLICY_DENIED,
            rule=exc.rule,
            value=exc.value,
        )
        return outcome
    tab = await context.ensure_tab()
    result = await tab.workflows.open_and_snapshot(
        url=args.url,
        wait_condition=args.wait_condition,
        selector=args.selector,
        wait_value=args.wait_value,
        wait_timeout=args.wait_timeout,
        include_html=args.include_html,
        include_console=args.include_console,
        max_elements=args.max_elements,
        max_text_chars=args.max_text_chars,
    )
    outcome.add_code("page.get(url); page.run_js(<bounded snapshot workflow>)")
    outcome.add_result(
        f"Opened {result['final_url']} and captured snapshot",
        **with_response_meta(result),
    )
    outcome.set_include_snapshot(True)
    return outcome


@define_tool(
    name="browser_extract_links",
    title="Extract Links",
    description="Extract bounded link data from the current page with optional origin filtering and URL normalization.",
    input_schema=BrowserExtractLinksInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
    output_model=BrowserExtractLinksData,
    failure_message=lambda args, exc: "Failed to extract page links: " + str(exc),
)
async def browser_extract_links(
    context: "DrissionPageContext", args: BrowserExtractLinksInput
) -> "ToolOutcome":
    """Extract links from the active page."""
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    result = await tab.workflows.extract_links(
        selector=args.selector,
        limit=args.limit,
        include_text=args.include_text,
        same_origin_only=args.same_origin_only,
        absolute_urls=args.absolute_urls,
    )
    outcome.add_code("page.run_js(<bounded link extraction script>)")
    outcome.add_result(
        f"Extracted {result['returned']} of {result['count']} links",
        **with_response_meta(result),
    )
    return outcome
