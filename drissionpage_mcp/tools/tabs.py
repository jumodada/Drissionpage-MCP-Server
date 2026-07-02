"""Browser tab management tools for DrissionPage MCP."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from .base import EmptyInput, ToolInput, ToolType, define_tool, tool_errors

if TYPE_CHECKING:
    from ..context import DrissionPageContext
    from ..response import ToolResponse


class TabIdInput(ToolInput):
    """Input schema for tab id based operations."""

    tab_id: str = Field(
        ...,
        description="MCP tab id from tab_list, or the underlying DrissionPage native tab id.",
    )


@define_tool(
    name="tab_list",
    title="List Tabs",
    description="List browser tabs tracked by the current DrissionPage MCP session.",
    input_schema=EmptyInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
)
async def tab_list(
    context: "DrissionPageContext", args: EmptyInput, response: "ToolResponse"
) -> None:
    """List current browser tabs."""

    async with tool_errors(response, "Failed to list tabs"):
        await context.sync_tabs()
        summaries = context.tab_summaries()
        active_tab = next((tab for tab in summaries if tab.get("active")), None)
        response.add_code("browser.get_tabs()")
        response.add_result(
            f"Found {len(summaries)} browser tabs",
            tabs=summaries,
            count=len(summaries),
            active_tab_id=str(active_tab.get("id", "")) if active_tab else "",
        )


@define_tool(
    name="tab_switch",
    title="Switch Tab",
    description="Switch the active browser tab by id from tab_list.",
    input_schema=TabIdInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def tab_switch(
    context: "DrissionPageContext", args: TabIdInput, response: "ToolResponse"
) -> None:
    """Switch active browser tab."""

    async with tool_errors(
        response, lambda e: f"Failed to switch to tab {args.tab_id!r}: {e}"
    ):
        tab = await context.switch_tab(args.tab_id)
        summaries = context.tab_summaries()
        active = next(
            (item for item in summaries if item.get("id") == tab.mcp_tab_id),
            tab.summary(active=True),
        )
        response.add_code(f"browser.activate_tab({tab.native_tab_id or args.tab_id!r})")
        response.add_result(
            f"Switched to tab: {tab.mcp_tab_id}",
            tab=active,
            tab_id=tab.mcp_tab_id,
            url=tab.url,
        )


@define_tool(
    name="tab_close",
    title="Close Tab",
    description="Close a browser tab by id from tab_list without closing the whole browser.",
    input_schema=TabIdInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def tab_close(
    context: "DrissionPageContext", args: TabIdInput, response: "ToolResponse"
) -> None:
    """Close a browser tab."""

    async with tool_errors(
        response, lambda e: f"Failed to close tab {args.tab_id!r}: {e}"
    ):
        await context.close_tab_by_id(args.tab_id)
        summaries = context.tab_summaries()
        active_tab = next((tab for tab in summaries if tab.get("active")), None)
        response.add_code(f"browser.close_tabs({args.tab_id!r})")
        response.add_result(
            f"Closed tab: {args.tab_id}",
            closed=True,
            tab_id=args.tab_id,
            remaining_count=len(summaries),
            active_tab_id=str(active_tab.get("id", "")) if active_tab else "",
        )


tools = [tab_list, tab_switch, tab_close]
