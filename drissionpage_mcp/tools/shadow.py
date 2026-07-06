"""Shadow DOM read-only tools for DrissionPage MCP."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from ..limits import MAX_WAIT_SECONDS
from ..metadata import with_response_meta
from .base import ToolInput, ToolType, define_tool, tool_errors

if TYPE_CHECKING:
    from ..context import DrissionPageContext
    from ..response import ToolResponse


class ShadowFindInput(ToolInput):
    """Input schema for finding one element inside an open shadow root."""

    host_selector: str = Field(..., description="Selector for the shadow host element.")
    selector: str = Field(..., description="Selector inside the shadow root.")
    timeout: int = Field(default=3, ge=0, le=MAX_WAIT_SECONDS)


class ShadowFindAllInput(ToolInput):
    """Input schema for finding repeated elements inside an open shadow root."""

    host_selector: str = Field(..., description="Selector for the shadow host element.")
    selector: str = Field(..., description="Selector inside the shadow root.")
    limit: int = Field(default=20, ge=1, le=100)
    include_html: bool = Field(default=False)


@define_tool(
    name="shadow_find",
    title="Find Shadow Element",
    description="Find one element inside an open shadow root.",
    input_schema=ShadowFindInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
)
async def shadow_find(
    context: "DrissionPageContext", args: ShadowFindInput, response: "ToolResponse"
) -> None:
    async with tool_errors(
        response,
        lambda e: f"Failed to find shadow element '{args.selector}': {e}",
    ):
        tab = context.current_tab_or_die()
        result = await tab.shadow_find(
            host_selector=args.host_selector,
            selector=args.selector,
            timeout=args.timeout,
        )
        response.add_code("page.ele(<host>).shadow_root.ele(<selector>)")
        response.add_result(f"Found shadow element: {args.selector}", **result)


@define_tool(
    name="shadow_find_all",
    title="Find Shadow Elements",
    description="Find repeated elements inside an open shadow root.",
    input_schema=ShadowFindAllInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
)
async def shadow_find_all(
    context: "DrissionPageContext", args: ShadowFindAllInput, response: "ToolResponse"
) -> None:
    async with tool_errors(
        response,
        lambda e: f"Failed to find shadow elements '{args.selector}': {e}",
    ):
        tab = context.current_tab_or_die()
        result = await tab.shadow_find_all(
            host_selector=args.host_selector,
            selector=args.selector,
            limit=args.limit,
            include_html=args.include_html,
        )
        response.add_code("page.ele(<host>).shadow_root.eles(<selector>)")
        response.add_result(
            f"Found {result['returned']} of {result['count']} shadow elements",
            **with_response_meta(result),
        )


tools = [shadow_find, shadow_find_all]
