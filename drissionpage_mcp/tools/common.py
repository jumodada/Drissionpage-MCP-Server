"""Common tools for DrissionPage MCP."""

from typing import TYPE_CHECKING, Any

from pydantic import Field

from ..metadata import with_response_meta
from ..policy import PolicyDeniedError, validate_screenshot_path
from ..response import ErrorCode, build_screenshot_metadata
from .base import ToolInput, ToolType, define_tool, tool_errors

if TYPE_CHECKING:
    from ..context import DrissionPageContext
    from ..response import ToolResponse


class ResizeInput(ToolInput):
    """Input schema for resize tool."""

    width: int = Field(..., description="Width of the browser window")
    height: int = Field(..., description="Height of the browser window")


class ScreenshotInput(ToolInput):
    """Input schema for screenshot tool."""

    full_page: bool = Field(default=False, description="Take a full page screenshot")
    path: str = Field(
        default="", description="Optional local file path to save screenshot"
    )


class PageSnapshotInput(ToolInput):
    """Input schema for page snapshot tool."""

    include_html: bool = Field(
        default=False,
        description="Include bounded outerHTML excerpts for summarized elements",
    )
    max_elements: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum total headings/links/buttons/inputs/forms to return",
    )
    max_text_chars: int = Field(
        default=4000,
        ge=0,
        le=20000,
        description="Maximum page text excerpt characters to return",
    )


class PageObserveInput(ToolInput):
    """Input schema for compact page observation."""

    max_texts: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of visible text samples to return",
    )
    max_text_chars: int = Field(
        default=160,
        ge=20,
        le=1000,
        description="Maximum characters per visible text sample",
    )


class PageEvaluateInput(ToolInput):
    """Input schema for bounded JavaScript evaluation."""

    script: str = Field(
        ...,
        description=(
            "JavaScript function body to run in the current page. Use return "
            "to provide a JSON-serializable result."
        ),
    )
    args: list[Any] = Field(
        default_factory=list,
        description="JSON arguments passed to the JavaScript function body",
    )
    max_chars: int = Field(
        default=4000,
        ge=100,
        le=20000,
        description="Maximum serialized JSON characters returned in result",
    )


class ClickCoordinatesInput(ToolInput):
    """Input schema for clicking at coordinates."""

    x: int = Field(..., description="X coordinate to click")
    y: int = Field(..., description="Y coordinate to click")
    element: str = Field(
        "", description="Human-readable element description for permission"
    )


class EmptyInput(ToolInput):
    """Empty input schema."""

    pass


@define_tool(
    name="page_resize",
    title="Resize Window",
    description="Resize the browser window to specified dimensions",
    input_schema=ResizeInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def resize(
    context: "DrissionPageContext", args: ResizeInput, response: "ToolResponse"
) -> None:
    """Resize the browser window."""
    async with tool_errors(response, "Failed to resize window"):
        tab = context.current_tab_or_die()
        await tab.resize(args.width, args.height)

        response.add_code(f"page.set.window.size({args.width}, {args.height})")
        response.add_result(
            f"Successfully resized window to {args.width}x{args.height}",
            width=args.width,
            height=args.height,
        )


@define_tool(
    name="page_screenshot",
    title="Take Screenshot",
    description="Take a screenshot of the current page",
    input_schema=ScreenshotInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
)
async def screenshot(
    context: "DrissionPageContext", args: ScreenshotInput, response: "ToolResponse"
) -> None:
    """Take a screenshot."""
    try:
        validate_screenshot_path(args.path)
    except PolicyDeniedError as exc:
        response.add_error(
            str(exc),
            ErrorCode.POLICY_DENIED,
            rule=exc.rule,
            value=exc.value,
        )
        return

    async with tool_errors(response, "Failed to take screenshot"):
        tab = context.current_tab_or_die()
        screenshot_data = await tab.screenshot(
            path=args.path or None, full_page=args.full_page
        )

        response.add_code(
            f"page.get_screenshot(path={args.path!r}, full_page={args.full_page!r})"
        )
        if args.path:
            response.add_result(
                f"Screenshot saved to: {screenshot_data}",
                screenshot=build_screenshot_metadata(
                    path=screenshot_data,
                    full_page=args.full_page,
                    inline=False,
                ),
            )
        else:
            response.add_screenshot(screenshot_data, {"full_page": args.full_page})


@define_tool(
    name="page_snapshot",
    title="Page Snapshot",
    description=(
        "Return a bounded page outline with text excerpt, headings, links, "
        "buttons, inputs, forms, and recommended selectors."
    ),
    input_schema=PageSnapshotInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
)
async def page_snapshot(
    context: "DrissionPageContext", args: PageSnapshotInput, response: "ToolResponse"
) -> None:
    """Get a bounded page outline for LLM page understanding."""
    async with tool_errors(response, "Failed to build page snapshot"):
        tab = context.current_tab_or_die()
        snapshot = await tab.page_snapshot(
            include_html=args.include_html,
            max_elements=args.max_elements,
            max_text_chars=args.max_text_chars,
        )

        response.add_code(
            "page.run_js(<bounded page outline script>)"
        )
        response.add_result(
            "Captured page snapshot",
            **with_response_meta(snapshot),
        )


@define_tool(
    name="page_observe",
    title="Observe Page",
    description=(
        "Return a compact current-page fingerprint with URL, title, ready state, "
        "element counts, visible text samples, and active element."
    ),
    input_schema=PageObserveInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
)
async def page_observe(
    context: "DrissionPageContext", args: PageObserveInput, response: "ToolResponse"
) -> None:
    """Observe the current page state."""
    async with tool_errors(response, "Failed to observe page"):
        tab = context.current_tab_or_die()
        observation = await tab.observe(
            max_texts=args.max_texts,
            max_text_chars=args.max_text_chars,
        )

        response.add_code("page.run_js(<compact page observation script>)")
        response.add_result("Observed page state", **observation)


@define_tool(
    name="page_evaluate",
    title="Evaluate JavaScript",
    description=(
        "Run a bounded JavaScript function body in the current page and return "
        "a JSON-safe result. This can mutate the page."
    ),
    input_schema=PageEvaluateInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def page_evaluate(
    context: "DrissionPageContext", args: PageEvaluateInput, response: "ToolResponse"
) -> None:
    """Evaluate JavaScript in the current page with bounded output."""
    async with tool_errors(response, "Failed to evaluate JavaScript"):
        tab = context.current_tab_or_die()
        result = await tab.evaluate_script(
            args.script,
            args=args.args,
            max_chars=args.max_chars,
        )

        response.add_code("page.run_js(<bounded user JavaScript>)")
        response.add_result("Evaluated JavaScript", **result)


@define_tool(
    name="page_click_xy",
    title="Click Coordinates",
    description="Click at specific coordinates on the page",
    input_schema=ClickCoordinatesInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def click_coordinates(
    context: "DrissionPageContext",
    args: ClickCoordinatesInput,
    response: "ToolResponse",
) -> None:
    """Click at coordinates."""
    async with tool_errors(
        response, lambda e: f"Failed to click at ({args.x}, {args.y}): {e}"
    ):
        tab = context.current_tab_or_die()
        await tab.click(args.x, args.y)

        response.add_code(f"page.actions.click(({args.x}, {args.y}))")
        response.add_result(
            f"Successfully clicked at coordinates ({args.x}, {args.y})",
            x=args.x,
            y=args.y,
            element=args.element,
            url=tab.url,
        )
        response.set_include_snapshot(True)


@define_tool(
    name="page_close",
    title="Close Browser",
    description="Close the current page/browser",
    input_schema=EmptyInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def close(
    context: "DrissionPageContext", args: EmptyInput, response: "ToolResponse"
) -> None:
    """Close the browser."""
    async with tool_errors(response, "Failed to close browser"):
        await context.close_browser()

        response.add_code("page.quit()")
        response.add_result("Successfully closed browser", closed=True)


@define_tool(
    name="page_get_url",
    title="Get Current URL",
    description="Get the current URL of the page",
    input_schema=EmptyInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
)
async def get_url(
    context: "DrissionPageContext", args: EmptyInput, response: "ToolResponse"
) -> None:
    """Get current URL."""
    async with tool_errors(response, "Failed to get URL"):
        tab = context.current_tab_or_die()
        url = tab.url

        response.add_code("page.url")
        response.add_result(f"Current URL: {url}", url=url)


# Export all tools
tools = [
    resize,
    screenshot,
    page_snapshot,
    page_observe,
    page_evaluate,
    click_coordinates,
    close,
    get_url,
]
